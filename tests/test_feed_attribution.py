import sqlite3
import time


def test_feed_click_returns_404_for_unknown_impression(client):
    response = client.post(
        "/api/feed/click",
        json={"impression_id": "imp_deadbeef"},
    )

    assert response.status_code == 404
    assert response.get_json() == {
        "ok": False,
        "error": "impression not found",
    }


def test_feed_watch_returns_404_for_unknown_impression(client):
    response = client.post(
        "/api/feed/watch",
        json={"impression_id": "imp_deadbeef", "seconds": 10},
    )

    assert response.status_code == 404
    assert response.get_json() == {
        "ok": False,
        "error": "impression not found",
    }


def test_feed_click_remains_idempotent_for_existing_clicked_impression(app, client):
    import bottube_server

    bottube_server._feed_imp_ensure_schema()
    conn = sqlite3.connect(str(bottube_server.DB_PATH))
    try:
        conn.execute(
            """INSERT INTO feed_impressions
               (impression_id, visitor_id, surface, bucket, video_id, position,
                created_at, clicked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "imp_12345678",
                "visitor",
                "feed_api",
                "latest",
                "video-1",
                0,
                time.time(),
                time.time(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.post(
        "/api/feed/click",
        json={"impression_id": "imp_12345678"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
