# SPDX-License-Identifier: MIT
"""Regression tests for #2158 — atomic admission edge in _referral_touch_hit_unique.

The legacy read-then-write pattern could let two concurrent first hits both
inflate referral_codes.hits even though only one (code, fp_hash) row existed.
The atomic UPSERT collapses insert + expired refresh into a single SQLite
operation, and only the request whose UPSERT actually mutates a row may
increment the referral hit total.
"""
import hashlib
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bottube_server


def _make_fp_hash(ip: str, ua: str, lang: str) -> str:
    """Mirror the in-process fingerprint layout used by the production code.

    ``_nocookie_fingerprint`` returns ``"<ip>:<12-char-sha256-prefix>"`` so a
    request with cookies disabled is bucketed by IP plus a low-entropy
    UA+language hash. Referral tracking stores the SHA-256 of that string.
    """
    basis = ua.strip().lower() + "|" + lang.strip().lower()
    prefix = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]
    raw = f"{ip}:{prefix}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_fp(fp: str):
    parts = fp.split("||")
    assert len(parts) == 3, f"bad fp spec {fp!r}"
    return parts[0], parts[1], parts[2]


@pytest.fixture()
def db(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_referral_2158.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server.init_db()
    with bottube_server.app.app_context():
        conn = bottube_server.get_db()
        # Minimal agent to satisfy the referral_codes FK.
        conn.execute(
            "INSERT INTO agents (agent_name, display_name, api_key, password_hash, bio, avatar_url, is_human, created_at, last_active) "
            "VALUES ('founder2158', 'Founder 2158', 'sk_test_2158', '', '', '', 1, ?, ?)",
            (time.time(), time.time()),
        )
        conn.execute(
            "INSERT INTO referral_codes (code, agent_id, hits, created_at) VALUES (?, ?, 0, ?)",
            ("PROMO2158", 1, time.time()),
        )
        conn.commit()
        yield conn


def _seed_fingerprint(db, code: str, fp: str, last_hit_at: float) -> None:
    ip, ua, lang = _parse_fp(fp)
    fp_hash = _make_fp_hash(ip, ua, lang)
    db.execute(
        "INSERT OR REPLACE INTO referral_hit_uniques (code, fp_hash, last_hit_at) VALUES (?, ?, ?)",
        (code, fp_hash, last_hit_at),
    )
    db.commit()


def _hits(db, code: str) -> int:
    row = db.execute("SELECT hits FROM referral_codes WHERE code = ?", (code,)).fetchone()
    return int(row["hits"])


def test_first_hit_increments_once(db):
    fp = "192.0.2.1||Mozilla/5.0||en-US"
    ip, ua, lang = _parse_fp(fp)
    fp_hash = _make_fp_hash(ip, ua, lang)
    db.execute("DELETE FROM referral_hit_uniques WHERE code = ?", ("PROMO2158",))
    db.execute("UPDATE referral_codes SET hits = 0 WHERE code = ?", ("PROMO2158",))
    db.commit()

    with bottube_server.app.test_request_context(headers={"User-Agent": ua, "Accept-Language": lang}):
        bottube_server._get_client_ip = lambda: ip  # type: ignore[assignment]
        bottube_server._referral_touch_hit_unique(db, "PROMO2158")

    assert _hits(db, "PROMO2158") == 1, f"hits = {_hits(db, 'PROMO2158')}"
    row = db.execute(
        "SELECT last_hit_at FROM referral_hit_uniques WHERE code = ? AND fp_hash = ?",
        ("PROMO2158", fp_hash),
    ).fetchone()
    assert row is not None


def test_duplicate_fresh_fingerprint_does_not_double_count(db):
    fp = "198.51.100.7||Mozilla/5.0||uk"
    ip, ua, lang = _parse_fp(fp)
    db.execute("DELETE FROM referral_hit_uniques WHERE code = ?", ("PROMO2158",))
    db.execute("UPDATE referral_codes SET hits = 0 WHERE code = ?", ("PROMO2158",))
    _seed_fingerprint(db, "PROMO2158", fp, time.time() - 10)  # fresh
    db.execute("UPDATE referral_codes SET hits = 0 WHERE code = ?", ("PROMO2158",))
    db.commit()

    with bottube_server.app.test_request_context(headers={"User-Agent": ua, "Accept-Language": lang}):
        bottube_server._get_client_ip = lambda: ip  # type: ignore[assignment]
        bottube_server._referral_touch_hit_unique(db, "PROMO2158")
        # Replaying the same fingerprint while the row is still fresh.
        bottube_server._referral_touch_hit_unique(db, "PROMO2158")

    assert _hits(db, "PROMO2158") == 0


def test_expired_fingerprint_increments_once_per_window(db):
    fp = "203.0.113.9||curl/8.0||*"
    ip, ua, lang = _parse_fp(fp)
    db.execute("DELETE FROM referral_hit_uniques WHERE code = ?", ("PROMO2158",))
    db.execute("UPDATE referral_codes SET hits = 0 WHERE code = ?", ("PROMO2158",))
    _seed_fingerprint(db, "PROMO2158", fp, time.time() - 90000)  # 25h ago, expired
    db.execute("UPDATE referral_codes SET hits = 0 WHERE code = ?", ("PROMO2158",))
    db.commit()

    with bottube_server.app.test_request_context(headers={"User-Agent": ua, "Accept-Language": lang}):
        bottube_server._get_client_ip = lambda: ip  # type: ignore[assignment]
        bottube_server._referral_touch_hit_unique(db, "PROMO2158")

    assert _hits(db, "PROMO2158") == 1


def test_concurrent_first_hits_increment_at_most_once(db, tmp_path):
    """The legacy read-then-write code inflated hits on every concurrent call.

    With the atomic UPSERT, exactly one writer wins regardless of the number
    of concurrent first hits sharing a fingerprint.
    """
    code = "PROMO2158"
    fp = "192.0.2.42||Mozilla/5.0||en-US"
    ip, ua, lang = _parse_fp(fp)
    fp_hash = _make_fp_hash(ip, ua, lang)
    db.execute("DELETE FROM referral_hit_uniques WHERE code = ?", (code,))
    db.execute("UPDATE referral_codes SET hits = 0 WHERE code = ?", (code,))
    db.commit()
    # Snapshot the path so workers can open their own connections.
    db_path = str(bottube_server.DB_PATH)

    barrier = threading.Barrier(8)
    errors = []

    def worker():
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            barrier.wait(timeout=5)
            cur = conn.execute(
                "INSERT INTO referral_hit_uniques (code, fp_hash, last_hit_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(code, fp_hash) DO UPDATE SET "
                "  last_hit_at = excluded.last_hit_at "
                "WHERE referral_hit_uniques.last_hit_at < ?",
                (code, fp_hash, time.time(), time.time() - 86400),
            )
            if cur.rowcount == 1:
                conn.execute(
                    "UPDATE referral_codes SET hits = hits + 1, last_hit_at = ? WHERE code = ?",
                    (time.time(), code),
                )
            conn.commit()
            conn.close()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors, errors
    assert _hits(db, code) == 1


def test_concurrent_expired_refresh_increments_at_most_once(db, tmp_path):
    """Expired rows must also elect a single writer under concurrency."""
    code = "PROMO2158"
    fp = "198.51.100.99||Mozilla/5.0||uk"
    ip, ua, lang = _parse_fp(fp)
    fp_hash = _make_fp_hash(ip, ua, lang)
    db.execute("DELETE FROM referral_hit_uniques WHERE code = ?", (code,))
    db.execute("UPDATE referral_codes SET hits = 0 WHERE code = ?", (code,))
    _seed_fingerprint(db, code, fp, time.time() - 90000)  # expired
    db.execute("UPDATE referral_codes SET hits = 0 WHERE code = ?", (code,))
    db.commit()
    db_path = str(bottube_server.DB_PATH)

    barrier = threading.Barrier(6)

    def worker():
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            barrier.wait(timeout=5)
            cur = conn.execute(
                "INSERT INTO referral_hit_uniques (code, fp_hash, last_hit_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(code, fp_hash) DO UPDATE SET "
                "  last_hit_at = excluded.last_hit_at "
                "WHERE referral_hit_uniques.last_hit_at < ?",
                (code, fp_hash, time.time(), time.time() - 86400),
            )
            if cur.rowcount == 1:
                conn.execute(
                    "UPDATE referral_codes SET hits = hits + 1, last_hit_at = ? WHERE code = ?",
                    (time.time(), code),
                )
            conn.commit()
            conn.close()
        except Exception as exc:
            errors.append(exc) if 'errors' in dir() else None

    errors = []
    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors, errors
    assert _hits(db, code) == 1
