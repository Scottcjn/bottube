import os
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOTTUBE_DB_PATH", "/tmp/bottube_test_oembed_dims.db")
os.environ.setdefault("BOTTUBE_DB", "/tmp/bottube_test_oembed_dims.db")

_orig_sqlite_connect = sqlite3.connect


def _bootstrap_sqlite_connect(path, *args, **kwargs):
    if str(path) == "/root/bottube/bottube.db":
        path = os.environ["BOTTUBE_DB_PATH"]
    return _orig_sqlite_connect(path, *args, **kwargs)


sqlite3.connect = _bootstrap_sqlite_connect

import bottube_server  # noqa: E402

sqlite3.connect = _orig_sqlite_connect


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "bottube_oembed_dims.db"
    monkeypatch.setattr(bottube_server, "DB_PATH", db_path, raising=False)
    bottube_server.init_db()
    bottube_server.app.config["TESTING"] = True
    yield bottube_server.app.test_client()


def _insert_video(video_id="oembedDims01", *, width=720, height=720):
    with bottube_server.app.app_context():
        db = bottube_server.get_db()
        cur = db.execute(
            """
            INSERT INTO agents
                (agent_name, display_name, api_key, password_hash, bio,
                 avatar_url, created_at, last_active)
            VALUES (?, ?, ?, '', '', '', ?, ?)
            """,
            ("oembed-agent", "OEmbed Agent", "test-oembed-key", 1.0, 1.0),
        )
        agent_id = int(cur.lastrowid)
        db.execute(
            """
            INSERT INTO videos (
                video_id, agent_id, title, filename, width, height, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                agent_id,
                "OEmbed Dimension Test",
                f"{video_id}.mp4",
                width,
                height,
                1.0,
            ),
        )
        db.commit()
    return video_id


def test_oembed_maxwidth_preserves_aspect_ratio(client):
    video_id = _insert_video()

    response = client.get(
        f"/oembed?url=https://bottube.ai/watch/{video_id}&maxwidth=400"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["width"] == 400
    assert payload["height"] == 400
    assert 'width="400" height="400"' in payload["html"]


def test_oembed_respects_both_dimension_limits_without_distortion(client):
    video_id = _insert_video("oembedDims02")

    response = client.get(
        f"/oembed?url=https://bottube.ai/watch/{video_id}"
        "&maxwidth=400&maxheight=225"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["width"] == 225
    assert payload["height"] == 225
    assert 'width="225" height="225"' in payload["html"]


def test_oembed_xml_uses_scaled_dimensions(client):
    video_id = _insert_video("oembedDims03", width=1280, height=720)

    response = client.get(
        f"/oembed?url=https://bottube.ai/watch/{video_id}"
        "&format=xml&maxwidth=400"
    )

    assert response.status_code == 200
    xml = response.get_data(as_text=True)
    assert "<width>400</width>" in xml
    assert "<height>225</height>" in xml
    assert 'width=&quot;400&quot; height=&quot;225&quot;' in xml
