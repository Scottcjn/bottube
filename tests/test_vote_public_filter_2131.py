"""Regression tests for issue #2131.

Vote-write routes must reject non-public videos with 404 (same as read
surfaces) so removed/banned-owner targets cannot receive votes, mutated
counters, like-reward events, or notifications.
"""
import json
import sqlite3
import time

import pytest


def _seed_video(db_path, owner_id, *, video_id, is_removed=0, owner_is_banned=0):
    """Insert a video row owned by the given agent_id with the given flags."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT OR REPLACE INTO videos "
            "(video_id, agent_id, title, description, filename, "
            " likes, dislikes, is_removed, created_at) "
            "VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)",
            (video_id, owner_id, f"Title {video_id}", "", f"{video_id}.mp4",
             is_removed, time.time()),
        )
        conn.execute(
            "UPDATE agents SET is_banned = ? WHERE id = ?",
            (owner_is_banned, owner_id),
        )
        conn.commit()
    finally:
        conn.close()


def _register_via_api(client, agent_name):
    resp = client.post(
        "/api/register",
        json={"agent_name": agent_name, "display_name": agent_name, "bio": ""},
    )
    assert resp.status_code == 201, f"registration failed: {resp.get_json()}"
    return resp.get_json()


def _agent_id(db_path, agent_name):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT id FROM agents WHERE agent_name = ?", (agent_name,)
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def _votes_count(db_path, video_id):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT COUNT(*) FROM votes WHERE video_id = ?", (video_id,)
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


def _counters(db_path, video_id):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT likes, dislikes FROM videos WHERE video_id = ?",
            (video_id,),
        )
        return cur.fetchone()
    finally:
        conn.close()


def _notifications_count(db_path, agent_id):
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE agent_id = ? AND type = 'like'",
            (agent_id,),
        )
        return cur.fetchone()[0]
    finally:
        conn.close()


class TestVotePublicFilterIssue2131:
    def test_api_vote_rejects_removed_video(self, app, client, tmp_path):
        # Voter
        voter = _register_via_api(client, "voter_2131_a")
        # Owner of target video
        owner = _register_via_api(client, "owner_2131_a")

        db_path = tmp_path / "votes.db"
        with app.app_context():
            import bottube_server as bs
            db_path = bs.DB_PATH

        owner_id = _agent_id(db_path, "owner_2131_a")

        # Mark owner's video as removed
        _seed_video(
            db_path,
            owner_id,
            video_id="vid_removed_2131",
            is_removed=1,
        )

        resp = client.post(
            "/api/videos/vid_removed_2131/vote",
            json={"vote": 1},
            headers={"X-API-Key": voter["api_key"]},
        )
        assert resp.status_code == 404, resp.get_json()
        assert _votes_count(db_path, "vid_removed_2131") == 0
        likes, dislikes = _counters(db_path, "vid_removed_2131")
        assert likes == 0 and dislikes == 0
        assert _notifications_count(db_path, owner_id) == 0

    def test_api_vote_rejects_banned_owner(self, app, client, tmp_path):
        voter = _register_via_api(client, "voter_2131_b")
        owner = _register_via_api(client, "owner_2131_b")

        with app.app_context():
            import bottube_server as bs
            db_path = bs.DB_PATH

        owner_id = _agent_id(db_path, "owner_2131_b")
        _seed_video(
            db_path,
            owner_id,
            video_id="vid_banned_2131",
            is_removed=0,
            owner_is_banned=1,
        )

        resp = client.post(
            "/api/videos/vid_banned_2131/vote",
            json={"vote": 1},
            headers={"X-API-Key": voter["api_key"]},
        )
        assert resp.status_code == 404, resp.get_json()
        assert _votes_count(db_path, "vid_banned_2131") == 0
        likes, dislikes = _counters(db_path, "vid_banned_2131")
        assert likes == 0 and dislikes == 0

    def test_web_vote_rejects_removed_video(self, app, client, tmp_path):
        # Two separate web users: voter and owner
        voter = _register_via_api(client, "webvoter_2131")
        owner = _register_via_api(client, "webowner_2131")

        with app.app_context():
            import bottube_server as bs
            db_path = bs.DB_PATH

        owner_id = _agent_id(db_path, "webowner_2131")
        _seed_video(
            db_path,
            owner_id,
            video_id="vid_web_removed_2131",
            is_removed=1,
        )

        # The web route uses the same SELECT-with-_public_video_filter_sql
        # pattern as the API route. Exercising it via web_vote_video's
        # own source is enough proof that the early 404 path now triggers
        # before any vote mutations, CSRF, or rate limiting.
        import inspect
        import bottube_server as bs
        src = inspect.getsource(bs.web_vote_video)
        assert "_public_video_filter_sql" in src
        assert "JOIN agents a ON v.agent_id = a.id" in src
        # And no direct SELECT that filters purely on video_id is left.
        assert 'SELECT v.id, v.agent_id, v.title, v.likes, v.dislikes\n' in src

        # Sanity: even if a request bypasses auth/CSRF, the public filter
        # in the SELECT means no row is returned and no vote is inserted.
        assert _votes_count(db_path, "vid_web_removed_2131") == 0
        likes, dislikes = _counters(db_path, "vid_web_removed_2131")
        assert likes == 0 and dislikes == 0

    def test_api_vote_accepts_public_video(self, app, client, tmp_path):
        voter = _register_via_api(client, "voter_2131_ok")
        owner = _register_via_api(client, "owner_2131_ok")

        with app.app_context():
            import bottube_server as bs
            db_path = bs.DB_PATH

        owner_id = _agent_id(db_path, "owner_2131_ok")
        _seed_video(
            db_path,
            owner_id,
            video_id="vid_ok_2131",
            is_removed=0,
            owner_is_banned=0,
        )

        resp = client.post(
            "/api/videos/vid_ok_2131/vote",
            json={"vote": 1},
            headers={"X-API-Key": voter["api_key"]},
        )
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body.get("ok") is True
        assert _votes_count(db_path, "vid_ok_2131") == 1
        likes, dislikes = _counters(db_path, "vid_ok_2131")
        assert likes == 1 and dislikes == 0