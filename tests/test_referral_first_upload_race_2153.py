# SPDX-License-Identifier: MIT
"""Regression tests for issue #2153 — Referral first-upload counter race.

The previous implementation read `referral_first_upload_counted` and then
performed an unconditional flag UPDATE followed by a counter increment.
Two concurrent first-upload requests could both observe `0`, both flip the
flag, and both increment `referral_codes.first_uploads`, inflating the
referral leaderboard.

These tests verify that under concurrent invocations exactly one request
per referred agent wins the flag transition and the counter is bumped
exactly once.
"""
import os
import sqlite3
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_referral_race.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_referral_race.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import paypal_packages


_orig_init_store_db = paypal_packages.init_store_db


def _test_init_store_db(db_path=None):
    bootstrap_path = os.environ["BOTTUBE_DB_PATH"]
    Path(bootstrap_path).parent.mkdir(parents=True, exist_ok=True)
    Path(bootstrap_path).unlink(missing_ok=True)
    return _orig_init_store_db(bootstrap_path)


paypal_packages.init_store_db = _test_init_store_db

import bottube_server

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_referral_race.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "ADMIN_KEY", "test-admin", raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_agent(agent_name: str, api_key: str, *, referred_by_code: str = "") -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio, avatar_url,
                 is_human, created_at, last_active, referred_by_code, referral_first_upload_counted)
            VALUES (?, ?, ?, '', '', '', 0, 1.0, 1.0, ?, 0)
            """,
            (agent_name, agent_name.title(), api_key, referred_by_code),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_referral_code(code: str, agent_id: int) -> None:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT OR IGNORE INTO referral_codes
                (code, agent_id, created_at, hits, signups, first_uploads,
                 last_hit_at, last_signup_at, last_first_upload_at, allowed_track)
            VALUES (?, ?, 1.0, 0, 0, 0, 0, 0, 0, 'both')
            """,
            (code, agent_id),
        )
        db.commit()


def _counter_value(code: str) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        row = db.execute(
            "SELECT first_uploads FROM referral_codes WHERE code = ?", (code,)
        ).fetchone()
        assert row is not None, f"referral_codes row missing for code={code}"
        return int(row["first_uploads"] or 0)


def _flag_value(agent_id: int) -> int:
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        row = db.execute(
            "SELECT referral_first_upload_counted FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        return int(row["referral_first_upload_counted"] or 0)


def test_concurrent_first_upload_increments_counter_exactly_once(client):
    """N concurrent calls must bump the referral counter exactly once."""
    # First create a referrer agent so the FK on referral_codes.agent_id holds.
    referrer_id = _insert_agent("referrerA", "bottube_sk_referrerA")
    code = "race2153a"  # lowercase: real codes are normalized to lowercase via _normalize_ref_code
    _insert_referral_code(code, referrer_id)
    agent_id = _insert_agent("raceagentA", "bottube_sk_raceA", referred_by_code=code)

    # Each thread opens its own sqlite3 connection (mimics a real Flask worker
    # process or a real concurrent request handler). Sharing one connection
    # would serialize the calls on the GIL and not exercise the race.
    def worker():
        # _referral_mark_first_upload uses the per-request `db` connection
        # which under Flask is one per request — but here we explicitly want
        # the cross-connection case, so each thread creates its own.
        conn = sqlite3.connect(str(bottube_server.DB_PATH), timeout=30.0)
        try:
            # The function expects a sqlite3.Row-supporting db; row factory
            # has to be set so fetchone() returns a mapping.
            conn.row_factory = sqlite3.Row
            result = bottube_server._referral_mark_first_upload(conn, agent_id)
            return result
        finally:
            conn.close()

    n_threads = 8
    barrier = threading.Barrier(n_threads)
    results: list = [None] * n_threads

    def runner(idx):
        barrier.wait()  # release all threads simultaneously
        results[idx] = worker()

    threads = [threading.Thread(target=runner, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert all(r is not None for r in results), "all worker calls must return a value"
    applied_count = sum(1 for r in results if isinstance(r, dict) and r.get("applied") is True)
    assert applied_count == 1, (
        f"exactly one caller must flip the flag; got {applied_count} of {n_threads}"
    )
    assert _counter_value(code) == 1, (
        f"referral_codes.first_uploads must be 1 after concurrent calls, "
        f"got {_counter_value(code)}"
    )
    assert _flag_value(agent_id) == 1


def test_sequential_second_call_is_noop(client):
    """A second call after the flag is already set must be a no-op."""
    referrer_id = _insert_agent("referrerB", "bottube_sk_referrerB")
    code = "race2153b"
    _insert_referral_code(code, referrer_id)
    agent_id = _insert_agent("raceagentB", "bottube_sk_raceB", referred_by_code=code)

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        first = bottube_server._referral_mark_first_upload(db, agent_id)
        assert first == {"applied": True}
        second = bottube_server._referral_mark_first_upload(db, agent_id)

    assert second == {"applied": False, "reason": "race_lost_or_already_counted"}
    assert _counter_value(code) == 1


def test_no_referral_code_is_noop(client):
    """Agent with no referred_by_code must not touch any counter."""
    referrer_id = _insert_agent("referrerC", "bottube_sk_referrerC")
    _insert_referral_code("race2153c", referrer_id)
    agent_id = _insert_agent("raceagentC", "bottube_sk_raceC", referred_by_code="")

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        result = bottube_server._referral_mark_first_upload(db, agent_id)

    assert result == {"applied": False, "reason": "no_referred_by_code"}
    assert _counter_value("race2153c") == 0
    assert _flag_value(agent_id) == 0
