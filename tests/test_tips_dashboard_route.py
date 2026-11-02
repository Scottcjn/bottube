import pytest
import sqlite3
import time
from bottube_server import app, init_db, get_db



def test_tips_dashboard_renders_cleanly(client):
    """Verify /tips/dashboard responds 200 and renders the dashboard template."""
    res = client.get("/tips/dashboard")
    assert res.status_code == 200
    assert b"Tips &amp; Rewards Dashboard" in res.data or b"Tips & Rewards Dashboard" in res.data
    assert b"Confirmed Tips Volume" in res.data
    assert b"Top Tipped Creators" in res.data
    assert b"Top Tippers" in res.data
    assert b"Recent Tips" in res.data

def test_tips_dashboard_with_sample_data(client):
    """Verify /tips/dashboard calculates totals and displays tipped agents."""
    with app.app_context():
        db = get_db()
        # Seed test agents
        now = time.time()
        db.execute(
            "INSERT OR IGNORE INTO agents (id, agent_name, display_name, api_key, rtc_address, created_at) VALUES (99901, 'tipper_bot', 'Generous Tipper', 'key1', 'RTCtipper', ?)",
            (now,)
        )
        db.execute(
            "INSERT OR IGNORE INTO agents (id, agent_name, display_name, api_key, rtc_address, created_at) VALUES (99902, 'creator_bot', 'Star Creator', 'key2', 'RTCcreator', ?)",
            (now,)
        )
        # Seed confirmed tip
        db.execute(
            "INSERT INTO tips (from_agent_id, to_agent_id, video_id, amount, message, status, created_at) VALUES (99901, 99902, 'vid123', 5.5, 'Great video!', 'confirmed', ?)",
            (now,)
        )
        # Seed pending tip
        db.execute(
            "INSERT INTO tips (from_agent_id, to_agent_id, video_id, amount, message, status, created_at) VALUES (99901, 99902, 'vid123', 2.0, 'Pending bonus', 'pending', ?)",
            (now,)
        )
        db.commit()

    res = client.get("/tips/dashboard")
    assert res.status_code == 200
    assert b"Star Creator" in res.data or b"creator_bot" in res.data
    assert b"Generous Tipper" in res.data or b"tipper_bot" in res.data
    assert b"5.5000 RTC" in res.data
    assert b"Great video!" in res.data
