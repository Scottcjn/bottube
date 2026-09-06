# SPDX-License-Identifier: MIT
"""Regression coverage for structured JSON in RTC tip messages."""

import time

import pytest


def _seed_tip_parties(app, sender_name):
    with app.app_context():
        import bottube_server

        db = bottube_server.get_db()
        sender = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (sender_name,)
        ).fetchone()
        db.execute("UPDATE agents SET rtc_balance = 10 WHERE id = ?", (sender["id"],))
        target = db.execute(
            """INSERT INTO agents
                   (agent_name, display_name, api_key, bio, avatar_url, created_at, last_active)
               VALUES ('tiptarget', 'Tip Target', 'bottube_sk_tiptarget', '', '', ?, ?)""",
            (time.time(), time.time()),
        )
        db.execute(
            """INSERT INTO videos
                   (video_id, agent_id, title, filename, created_at)
               VALUES ('tipvideo01AB', ?, 'Tip target video', 'tipvideo01AB.mp4', ?)""",
            (target.lastrowid, time.time()),
        )
        db.commit()
        return int(sender["id"]), int(target.lastrowid)


@pytest.mark.parametrize(
    ("path", "session_auth"),
    [
        ("/api/videos/tipvideo01AB/tip", False),
        ("/api/agents/tiptarget/tip", False),
        ("/api/videos/tipvideo01AB/web-tip", True),
        ("/api/agents/tiptarget/web-tip", True),
    ],
)
def test_tip_routes_reject_structured_message_without_moving_credits(
    app, client, registered_agent, path, session_auth
):
    import bottube_server

    sender_id, target_id = _seed_tip_parties(app, registered_agent["agent_name"])
    if session_auth:
        with client.session_transaction() as session:
            session["user_id"] = sender_id
            session["csrf_token"] = "test-csrf"
        headers = {"X-CSRF-Token": "test-csrf"}
    else:
        headers = {"X-API-Key": registered_agent["api_key"]}

    response = client.post(
        path,
        headers=headers,
        json={"amount": 1, "message": {"nested": "message"}},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "message must be a string"}
    with app.app_context():
        db = bottube_server.get_db()
        balances = db.execute(
            "SELECT id, rtc_balance FROM agents WHERE id IN (?, ?) ORDER BY id",
            (sender_id, target_id),
        ).fetchall()
        assert [row["rtc_balance"] for row in balances] == [10, 0]
        assert db.execute("SELECT COUNT(*) FROM tips").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM earnings").fetchone()[0] == 0


def test_tip_route_rejects_non_object_json(app, client, registered_agent):
    _seed_tip_parties(app, registered_agent["agent_name"])
    response = client.post(
        "/api/agents/tiptarget/tip",
        headers={"X-API-Key": registered_agent["api_key"]},
        json=["not", "an", "object"],
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON body must be an object"}
