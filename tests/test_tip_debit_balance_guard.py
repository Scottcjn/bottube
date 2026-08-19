# SPDX-License-Identifier: MIT
"""Regression tests: tipping must not mint RTC.

The four tip handlers (`/api/videos/<id>/tip`, `/api/videos/<id>/web-tip`,
`/api/agents/<name>/tip`, `/api/agents/<name>/web-tip`) each did:

    sender = SELECT rtc_balance ...        # check
    if sender["rtc_balance"] < amount: ... # decide
    UPDATE agents SET rtc_balance = rtc_balance - ? WHERE id = ?   # act
    UPDATE agents SET rtc_balance = rtc_balance + ? WHERE id = ?   # credit

Check-then-act across separate statements is a TOCTOU race. Because the
*recipient is credited immediately after* the sender is debited, a lost race
does not merely overdraw one account -- it increases total RTC supply. That
makes this a supply-integrity bug, not just an accounting one.

The fix routes every spend through ``debit_rtc()``, whose comparison lives in
the UPDATE's WHERE clause, and aborts before crediting anyone if it returns
False.
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Importing bottube_server runs module-level table bootstraps that fall back to
# the *production* DB path when BOTTUBE_DB is unset. Point them at a scratch
# file before import so this module does not depend on a writable /root.
_BOOTSTRAP_DB = os.path.join(
    tempfile.gettempdir(), "bottube_test_tip_debit_guard_bootstrap.db"
)
os.environ.setdefault("BOTTUBE_DB", _BOOTSTRAP_DB)
os.environ.setdefault("BOTTUBE_DB_PATH", _BOOTSTRAP_DB)

import bottube_server  # noqa: E402


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_tip_guard.db"
    video_dir = tmp_path / "videos"
    thumb_dir = tmp_path / "thumbnails"
    avatar_dir = tmp_path / "avatars"
    for d in (video_dir, thumb_dir, avatar_dir):
        d.mkdir()

    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    monkeypatch.setattr(bottube_server, "VIDEO_DIR", video_dir, raising=False)
    monkeypatch.setattr(bottube_server, "THUMB_DIR", thumb_dir, raising=False)
    monkeypatch.setattr(bottube_server, "AVATAR_DIR", avatar_dir, raising=False)
    bottube_server._rate_buckets.clear()
    bottube_server._rate_last_prune = 0.0

    with bottube_server.app.app_context():
        bottube_server.init_db()

    bottube_server.app.config["TESTING"] = True
    return bottube_server.app.test_client()


def _register(client, name):
    resp = client.post("/api/register", json={
        "agent_name": name, "display_name": name, "bio": "tip guard test",
    })
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


@pytest.fixture()
def scenario(client):
    """A funded tipper, a creator, and one video owned by the creator."""
    tipper = _register(client, "tip_guard_sender")
    creator = _register(client, "tip_guard_creator")

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        creator_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (creator["agent_name"],)
        ).fetchone()["id"]
        db.execute(
            "INSERT INTO videos (video_id, agent_id, title, description, filename, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("tipguardvid", creator_id, "Tip Guard Video", "", "tipguardvid.mp4",
             time.time()),
        )
        db.commit()

    return {"tipper": tipper, "creator": creator, "video_id": "tipguardvid"}


def _balances(client, scenario):
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        rows = {
            r["agent_name"]: r["rtc_balance"]
            for r in db.execute(
                "SELECT agent_name, rtc_balance FROM agents WHERE agent_name IN (?, ?)",
                (scenario["tipper"]["agent_name"], scenario["creator"]["agent_name"]),
            ).fetchall()
        }
    return rows


def _fund(client, scenario, amount):
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            "UPDATE agents SET rtc_balance = ? WHERE agent_name = ?",
            (amount, scenario["tipper"]["agent_name"]),
        )
        db.execute(
            "UPDATE agents SET rtc_balance = 0 WHERE agent_name = ?",
            (scenario["creator"]["agent_name"],),
        )
        db.commit()


def test_tip_beyond_balance_is_rejected_and_credits_nobody(client, scenario):
    """An unaffordable tip must not credit the creator."""
    _fund(client, scenario, 1.0)

    resp = client.post(
        f"/api/videos/{scenario['video_id']}/tip",
        json={"amount": 5.0},
        headers={"X-API-Key": scenario["tipper"]["api_key"]},
    )

    assert resp.status_code == 400, resp.get_json()
    bal = _balances(client, scenario)
    assert bal[scenario["tipper"]["agent_name"]] == pytest.approx(1.0)
    assert bal[scenario["creator"]["agent_name"]] == pytest.approx(0.0)


def test_concurrent_tips_cannot_mint_rtc(client, scenario):
    """Concurrent tips funded for ONE must not overdraw or inflate supply.

    Before the guard, several threads could each read 5.0, each pass the
    balance check, and each debit 5.0 while crediting the creator 5.0 -- the
    sender ends negative and total supply grows.
    """
    tip = 5.0
    _fund(client, scenario, tip)
    total_before = tip

    threads_n = 6
    barrier = threading.Barrier(threads_n)
    statuses = []
    lock = threading.Lock()

    def send_tip():
        barrier.wait()
        resp = client.post(
            f"/api/videos/{scenario['video_id']}/tip",
            json={"amount": tip},
            headers={"X-API-Key": scenario["tipper"]["api_key"]},
        )
        with lock:
            statuses.append(resp.status_code)

    threads = [threading.Thread(target=send_tip) for _ in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(statuses) == threads_n, "a worker thread did not finish"

    bal = _balances(client, scenario)
    sender = bal[scenario["tipper"]["agent_name"]]
    creator = bal[scenario["creator"]["agent_name"]]
    successes = statuses.count(200)

    # No overdraft.
    assert sender >= 0.0, f"sender went negative: {sender} (statuses={statuses})"
    # No minting: the two accounts together still hold what we started with.
    assert sender + creator == pytest.approx(total_before), (
        f"RTC supply changed: {sender} + {creator} != {total_before} "
        f"(statuses={statuses})"
    )
    # One balance funds at most one tip.
    assert successes <= 1, f"{successes} tips funded by one balance"
