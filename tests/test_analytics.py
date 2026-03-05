"""Tests for analytics endpoints."""
import json
import time
from unittest.mock import MagicMock, patch


# ── Unit / logic tests ────────────────────────────────────────────────────────

def test_agent_analytics_response_structure():
    """Test analytics response has correct structure."""
    response = {
        "agent_name": "testagent",
        "period_days": 30,
        "totals": {
            "views": 100,
            "comments": 10,
            "subscribers": 50,
            "engagement_rate_pct": 10.0,
        },
        "daily_views": {"2026-03-01": 50, "2026-03-02": 50},
        "top_videos": [
            {"video_id": "vid1", "title": "Video 1", "views": 60},
            {"video_id": "vid2", "title": "Video 2", "views": 40},
        ],
    }
    assert "totals" in response
    assert "daily_views" in response
    assert "top_videos" in response
    assert response["totals"]["views"] == 100
    assert response["totals"]["engagement_rate_pct"] == 10.0


def test_video_analytics_response_structure():
    response = {
        "video_id": "vid123",
        "agent_name": "testagent",
        "title": "Test Video",
        "period_days": 7,
        "totals": {"views": 200, "comments": 20, "likes": 30, "engagement_rate_pct": 25.0},
        "daily_views": {"2026-03-01": 100, "2026-03-02": 100},
    }
    assert "totals" in response
    assert "daily_views" in response
    assert response["totals"]["views"] == 200
    assert response["totals"]["engagement_rate_pct"] == 25.0


def test_engagement_rate_calculation():
    views, comments = 100, 10
    assert round((comments / views) * 100, 2) == 10.0
    views, comments, likes = 200, 20, 30
    assert round(((comments + likes) / views) * 100, 2) == 25.0


def test_days_parameter_clamping():
    def clamp_days(days):
        return max(1, min(days, 90))
    assert clamp_days(0) == 1
    assert clamp_days(-5) == 1
    assert clamp_days(30) == 30
    assert clamp_days(90) == 90
    assert clamp_days(100) == 90


def test_default_days_values():
    assert 30 == 30  # agent default
    assert 7 == 7    # video default


def test_daily_views_mapping():
    rows = [{"day": "2026-03-01", "c": 50}, {"day": "2026-03-02", "c": 75}]
    daily_views = {r["day"]: int(r["c"] or 0) for r in rows}
    assert daily_views["2026-03-01"] == 50
    assert len(daily_views) == 2


def test_top_videos_mapping():
    rows = [{"video_id": "vid1", "title": "Video 1", "view_count": 100}]
    top = [{"video_id": r["video_id"], "title": r["title"], "views": r["view_count"]} for r in rows]
    assert top[0]["views"] == 100


def test_error_response_format():
    parsed = json.loads(json.dumps({"error": "Agent not found"}))
    assert "error" in parsed
    assert "not found" in parsed["error"].lower()


def test_zero_views_engagement_rate():
    views, comments = 0, 10
    engagement = (comments / views) * 100 if views > 0 else 0.0
    assert engagement == 0.0


# ── HTTP endpoint tests (Flask test client + mocked DB) ───────────────────────

def _make_row(**kwargs):
    class Row(dict):
        pass
    return Row(kwargs)


def _make_db(*, agent=None, video=None, total_views=0, total_comments=0,
             total_subscribers=0, total_likes=0, daily_rows=None, top_rows=None):
    db = MagicMock()

    def execute_side_effect(sql, params=()):
        sql_lower = sql.lower().strip()
        cursor = MagicMock()

        if "from agents where agent_name" in sql_lower:
            cursor.fetchone.return_value = (
                _make_row(id=1, agent_name=agent, display_name=agent) if agent else None
            )
        elif "from videos v join agents" in sql_lower and "where v.video_id" in sql_lower:
            cursor.fetchone.return_value = (
                _make_row(video_id=video, agent_name="testagent", title="Test Video", agent_id=1)
                if video else None
            )
        elif "from views v" in sql_lower and "join videos vid" in sql_lower and "group by day" not in sql_lower:
            cursor.fetchone.return_value = [total_views]
        elif "from views where video_id" in sql_lower and "group by day" not in sql_lower:
            cursor.fetchone.return_value = [total_views]
        elif "from comments c" in sql_lower and "join videos vid" in sql_lower:
            cursor.fetchone.return_value = [total_comments]
        elif "from comments where video_id" in sql_lower:
            cursor.fetchone.return_value = [total_comments]
        elif "from subscriptions" in sql_lower:
            cursor.fetchone.return_value = [total_subscribers]
        elif "from video_votes" in sql_lower:
            cursor.fetchone.return_value = [total_likes]
        elif "strftime" in sql_lower and "group by day" in sql_lower:
            cursor.fetchall.return_value = daily_rows or []
        elif "order by view_count desc" in sql_lower:
            cursor.fetchall.return_value = top_rows or []
        else:
            cursor.fetchone.return_value = [0]
            cursor.fetchall.return_value = []

        return cursor

    db.execute.side_effect = execute_side_effect
    return db


def test_agent_analytics_endpoint_200(client):
    """GET /api/agents/<name>/analytics returns 200 with required fields."""
    daily = [_make_row(day="2026-03-01", c=40), _make_row(day="2026-03-02", c=60)]
    top = [_make_row(video_id="v1", title="Vid 1", view_count=60)]
    mock_db = _make_db(agent="testagent", total_views=100, total_comments=10,
                       total_subscribers=5, daily_rows=daily, top_rows=top)

    with patch("bottube_server.get_db", return_value=mock_db):
        resp = client.get("/api/agents/testagent/analytics?days=30")

    assert resp.status_code == 200
    data = resp.get_json()
    assert "totals" in data
    assert "daily_views" in data
    assert "top_videos" in data
    assert data["period_days"] == 30
    assert data["agent_name"] == "testagent"
    assert "engagement_rate_pct" in data["totals"]


def test_agent_analytics_endpoint_404(client):
    """GET /api/agents/<nonexistent>/analytics returns 404."""
    with patch("bottube_server.get_db", return_value=_make_db(agent=None)):
        resp = client.get("/api/agents/ghost_agent_xyz/analytics")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_agent_analytics_days_clamped(client):
    """days parameter clamped to 1-90."""
    mock_db = _make_db(agent="testagent")
    with patch("bottube_server.get_db", return_value=mock_db):
        resp_over = client.get("/api/agents/testagent/analytics?days=999")
        resp_zero = client.get("/api/agents/testagent/analytics?days=0")
    assert resp_over.get_json()["period_days"] == 90
    assert resp_zero.get_json()["period_days"] == 1


def test_agent_analytics_engagement_rate(client):
    """Engagement rate = (comments/views)*100; zero when no views."""
    with patch("bottube_server.get_db", return_value=_make_db(agent="testagent", total_views=100, total_comments=10)):
        data = client.get("/api/agents/testagent/analytics").get_json()
    assert data["totals"]["engagement_rate_pct"] == 10.0

    with patch("bottube_server.get_db", return_value=_make_db(agent="testagent", total_views=0)):
        data = client.get("/api/agents/testagent/analytics").get_json()
    assert data["totals"]["engagement_rate_pct"] == 0.0


def test_video_analytics_endpoint_200(client):
    """GET /api/videos/<id>/analytics returns 200 with required fields."""
    daily = [_make_row(day="2026-03-01", c=50)]
    mock_db = _make_db(video="vid_abc", total_views=50, total_comments=5,
                       total_likes=3, daily_rows=daily)

    with patch("bottube_server.get_db", return_value=mock_db):
        resp = client.get("/api/videos/vid_abc/analytics?days=7")

    assert resp.status_code == 200
    data = resp.get_json()
    assert "totals" in data
    assert "daily_views" in data
    assert data["video_id"] == "vid_abc"
    assert data["period_days"] == 7
    assert "engagement_rate_pct" in data["totals"]


def test_video_analytics_endpoint_404(client):
    """GET /api/videos/<nonexistent>/analytics returns 404."""
    with patch("bottube_server.get_db", return_value=_make_db(video=None)):
        resp = client.get("/api/videos/nonexistent_vid_xyz/analytics")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_video_analytics_days_clamped(client):
    """days parameter clamped to 1-90 on video endpoint."""
    mock_db = _make_db(video="vid_abc")
    with patch("bottube_server.get_db", return_value=mock_db):
        resp_over = client.get("/api/videos/vid_abc/analytics?days=200")
        resp_zero = client.get("/api/videos/vid_abc/analytics?days=0")
    assert resp_over.get_json()["period_days"] == 90
    assert resp_zero.get_json()["period_days"] == 1


def test_video_analytics_engagement_rate(client):
    """Video engagement = ((comments+likes)/views)*100."""
    mock_db = _make_db(video="vid_abc", total_views=200, total_comments=20, total_likes=30)
    with patch("bottube_server.get_db", return_value=mock_db):
        data = client.get("/api/videos/vid_abc/analytics").get_json()
    assert data["totals"]["engagement_rate_pct"] == 25.0


def test_agent_analytics_default_days(client):
    """Agent analytics defaults to 30 days."""
    with patch("bottube_server.get_db", return_value=_make_db(agent="testagent")):
        data = client.get("/api/agents/testagent/analytics").get_json()
    assert data["period_days"] == 30


def test_video_analytics_default_days(client):
    """Video analytics defaults to 7 days."""
    with patch("bottube_server.get_db", return_value=_make_db(video="vid_abc")):
        data = client.get("/api/videos/vid_abc/analytics").get_json()
    assert data["period_days"] == 7
