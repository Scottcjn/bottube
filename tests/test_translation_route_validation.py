# SPDX-License-Identifier: MIT
import sqlite3
import sys
import types
from importlib import metadata
from pathlib import Path

import pytest
import werkzeug
from flask import Flask, g


if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(monkeypatch, tmp_path):
    original_translation_routes = sys.modules.pop("translation_routes", None)
    db_path = tmp_path / "translations.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY,
                agent_name TEXT NOT NULL,
                is_banned INTEGER DEFAULT 0
            )
            """
        )
        db.execute(
            """
            CREATE TABLE videos (
                id INTEGER PRIMARY KEY,
                video_id TEXT UNIQUE NOT NULL,
                agent_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_removed INTEGER DEFAULT 0
            )
            """
        )
        db.executemany(
            "INSERT INTO agents (id, agent_name) VALUES (?, ?)",
            [(1, "creator"), (7, "translator")],
        )
        db.execute(
            """INSERT INTO videos
               (id, video_id, agent_id, title, description)
               VALUES (42, 'public-video-id', 1, 'Original', 'Original description')"""
        )
        db.commit()

    def get_db():
        if "test_db" in g:
            return g.test_db
        db = sqlite3.connect(str(db_path))
        db.row_factory = sqlite3.Row
        g.test_db = db
        return db

    def require_api_key(fn):
        def wrapper(*args, **kwargs):
            g.agent = {"id": 7}
            return fn(*args, **kwargs)

        wrapper.__name__ = fn.__name__
        return wrapper

    fake_server = types.SimpleNamespace(get_db=get_db, require_api_key=require_api_key)
    monkeypatch.setitem(sys.modules, "bottube_server", fake_server)

    import translation_routes

    with sqlite3.connect(db_path) as db:
        translation_routes.init_translation_tables(db)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(translation_routes.translation_bp)
    test_client = app.test_client()
    test_client.db_path = db_path
    yield test_client

    sys.modules.pop("translation_routes", None)
    if original_translation_routes is not None:
        sys.modules["translation_routes"] = original_translation_routes


def _translation_count(client):
    with sqlite3.connect(client.db_path) as db:
        return db.execute("SELECT COUNT(*) FROM video_translations").fetchone()[0]


def test_add_translation_rejects_non_object_json(client):
    resp = client.post("/api/translations", json=["not", "an", "object"])

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON object required"}
    assert _translation_count(client) == 0


def test_add_translation_preserves_missing_field_error_for_objects(client):
    resp = client.post("/api/translations", json={})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Missing required fields"}
    assert _translation_count(client) == 0


def test_translation_round_trip_uses_public_video_id(client):
    created = client.post(
        "/api/translations",
        json={
            "video_id": "public-video-id",
            "language": "French",
            "title": "Titre",
            "description": "Description traduite",
        },
    )

    assert created.status_code == 200
    response = client.get("/api/translations/public-video-id/French")
    assert response.status_code == 200
    assert response.get_json()["title"] == "Titre"


def test_translation_write_rejects_unknown_video(client):
    response = client.post(
        "/api/translations",
        json={
            "video_id": "missing-video",
            "language": "French",
            "title": "Titre",
            "description": "Description traduite",
        },
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Video not found"}
    assert _translation_count(client) == 0
