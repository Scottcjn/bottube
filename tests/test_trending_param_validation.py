"""Tests for /api/trending query parameter validation and wiring.

Bug: /api/trending accepted malformed limit/days/since query params
without returning 400, and when days/since were present, the parsed
values were never wired into the trending window.
"""
import time
import pytest


class TestLimitValidation:
    def test_limit_abc_returns_400(self, client):
        r = client.get("/api/trending?limit=abc")
        assert r.status_code == 400

    def test_limit_zero_returns_400(self, client):
        r = client.get("/api/trending?limit=0")
        assert r.status_code == 400

    def test_limit_negative_returns_400(self, client):
        r = client.get("/api/trending?limit=-5")
        assert r.status_code == 400

    def test_limit_oversized_returns_400(self, client):
        r = client.get("/api/trending?limit=999999")
        assert r.status_code == 400

    def test_limit_valid_returns_200(self, client):
        r = client.get("/api/trending?limit=5")
        assert r.status_code == 200


class TestDaysValidation:
    def test_days_abc_returns_400(self, client):
        r = client.get("/api/trending?days=abc")
        assert r.status_code == 400

    def test_days_zero_returns_400(self, client):
        r = client.get("/api/trending?days=0")
        assert r.status_code == 400

    def test_days_negative_returns_400(self, client):
        r = client.get("/api/trending?days=-1")
        assert r.status_code == 400

    def test_days_above_90_returns_400(self, client):
        r = client.get("/api/trending?days=91")
        assert r.status_code == 400

    def test_days_valid_returns_200(self, client):
        r = client.get("/api/trending?days=7")
        assert r.status_code == 200


class TestSinceValidation:
    def test_since_abc_returns_400(self, client):
        r = client.get("/api/trending?since=abc")
        assert r.status_code == 400

    def test_since_zero_returns_400(self, client):
        r = client.get("/api/trending?since=0")
        assert r.status_code == 400

    def test_since_negative_returns_400(self, client):
        r = client.get("/api/trending?since=-5")
        assert r.status_code == 400

    def test_since_valid_returns_200(self, client):
        r = client.get("/api/trending?since=3600")
        assert r.status_code == 200


class TestDaysSinceWiring:
    """Verify days/since actually affect the activity window."""

    def _setup_video_with_view(self, app, label):
        import bottube_server
        with app.app_context():
            db = bottube_server.get_db()
            now = time.time()
            # Register an agent and get its auto-increment id
            db.execute(
                "INSERT INTO agents (agent_name, api_key, is_human, created_at) "
                "VALUES (?, ?, 1, ?)",
                (f"bot-{label}", f"key-{label}", now),
            )
            row = db.execute(
                "SELECT id FROM agents WHERE agent_name = ?", (f"bot-{label}",)
            ).fetchone()
            agent_id = row["id"]

            vid = f"vid-{label}"
            db.execute(
                "INSERT INTO videos (video_id, agent_id, title, filename, created_at, novelty_score) "
                "VALUES (?, ?, ?, ?, ?, 0.5)",
                (vid, agent_id, f"Video {label}", f"{label}.mp4", now - 3600),
            )
            # A view from 30 minutes ago
            db.execute(
                "INSERT INTO views (video_id, ip_address, created_at) "
                "VALUES (?, ?, ?)",
                (vid, "10.0.0.1", now - 1800),
            )
            db.commit()
            return vid

    def test_days_window_includes_recent_views(self, client, app):
        vid = self._setup_video_with_view(app, "days")
        r = client.get("/api/trending?days=1")
        assert r.status_code == 200
        data = r.get_json()
        found = [v for v in data["videos"] if v["video_id"] == vid]
        assert len(found) == 1
        assert found[0]["recent_views"] >= 1

    def test_since_narrow_window_excludes_old_views(self, client, app):
        vid = self._setup_video_with_view(app, "since")
        # since=10 (10 seconds) — view is from 30 min ago, should be excluded
        r = client.get("/api/trending?since=10")
        assert r.status_code == 200
        data = r.get_json()
        found = [v for v in data["videos"] if v["video_id"] == vid]
        if found:
            assert found[0]["recent_views"] == 0
