# SPDX-License-Identifier: MIT
import time


def _insert_agent(agent_name, api_key):
    import bottube_server

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio,
                 avatar_url, is_human, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', 0, ?, ?)
            """,
            (agent_name, agent_name, api_key, time.time(), time.time()),
        )
        db.commit()
        return int(cur.lastrowid)


def _insert_video(owner_id, video_id="viewip1621A"):
    import bottube_server

    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """
            INSERT INTO videos
                (video_id, agent_id, title, filename, views, created_at, is_removed)
            VALUES (?, ?, ?, ?, 0, ?, 0)
            """,
            (video_id, owner_id, "IP test", f"{video_id}.mp4", time.time()),
        )
        db.commit()
    return video_id


def test_mood_routes_require_api_key(client):
    _insert_agent("moodbot", "bottube_sk_moodbot")

    update = client.post(
        "/api/v1/agents/moodbot/mood/update",
        json={"force_state": "frustrated"},
    )
    signal = client.post(
        "/api/v1/agents/moodbot/mood/signal",
        json={"signal_type": "view_count", "signal_value": 5},
    )

    assert update.status_code == 401
    assert update.get_json() == {"error": "Missing X-API-Key header"}
    assert signal.status_code == 401
    assert signal.get_json() == {"error": "Missing X-API-Key header"}


def test_view_dedupe_ignores_spoofed_x_real_ip_from_untrusted_remote(client, monkeypatch):
    import bottube_server

    owner_id = _insert_agent("viewowner1621", "bottube_sk_viewowner1621")
    video_id = _insert_video(owner_id)

    monkeypatch.setattr(
        bottube_server,
        "_view_reward_decision",
        lambda *args, **kwargs: {"awarded": False, "held": False, "risk_score": 0, "reasons": []},
    )
    monkeypatch.setattr(bottube_server, "check_view_milestones", lambda *args, **kwargs: None)
    monkeypatch.setattr(bottube_server, "_get_ctr_tracker", lambda: type("CTR", (), {"record_click": lambda self, vid: None})())

    first = client.get(
        f"/api/videos/{video_id}/view",
        headers={"X-Real-IP": "198.51.100.11"},
        environ_base={"REMOTE_ADDR": "198.51.100.200"},
    )
    second = client.get(
        f"/api/videos/{video_id}/view",
        headers={"X-Real-IP": "198.51.100.12"},
        environ_base={"REMOTE_ADDR": "198.51.100.200"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json()["views"] == 1
    assert second.get_json()["views"] == 1
    assert second.get_json()["reward"]["reasons"] == ["deduplicated recent view"]
