# SPDX-License-Identifier: MIT
"""Regression coverage for the shared public-API query validators."""
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest
from flask import Flask

from bottube_validators.validators import (
    MAX_QUERY_TIMESTAMP,
    parse_enum,
    parse_positive_int,
    parse_timestamp_iso,
)


# Several optional blueprints initialise tables while bottube_server imports.
# Give those import-time hooks a writable bootstrap database; the shared app
# fixture replaces the server's DB_PATH with its isolated temporary database.
_BOOTSTRAP_DB = os.path.join(tempfile.gettempdir(), "bottube_shared_query_validation.db")
os.environ.setdefault("BOTTUBE_DB_PATH", _BOOTSTRAP_DB)
os.environ.setdefault("BOTTUBE_DB", _BOOTSTRAP_DB)


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Use pytest-managed storage so Windows can release SQLite lazily."""
    server_path = Path(__file__).resolve().parent.parent
    db_path = tmp_path / "bottube.db"
    video_dir = tmp_path / "videos"
    thumb_dir = tmp_path / "thumbnails"
    avatar_dir = tmp_path / "avatars"
    video_dir.mkdir()
    thumb_dir.mkdir()
    avatar_dir.mkdir()

    monkeypatch.setenv("BOTTUBE_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("BOTTUBE_DB_PATH", str(db_path))
    monkeypatch.setenv("BOTTUBE_DB", str(db_path))
    for mod_name in list(sys.modules):
        if mod_name in {
            "bottube_server",
            "paypal_packages",
            "gpu_marketplace",
            "banano_blueprint",
            "captions_blueprint",
            "gemini_blueprint",
        }:
            del sys.modules[mod_name]

    sys.path.insert(0, str(server_path))
    import bottube_server

    bottube_server.DB_PATH = db_path
    bottube_server.VIDEO_DIR = video_dir
    bottube_server.THUMB_DIR = thumb_dir
    bottube_server.AVATAR_DIR = avatar_dir
    flask_app = bottube_server.app
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="shared-query-validator-test-key",
    )
    flask_app.template_folder = str(server_path / "bottube_templates")
    with flask_app.app_context():
        bottube_server.init_db()

    yield flask_app


def _assert_invalid_matrix(client, path, cases):
    for param, values in cases.items():
        for value in values:
            response = client.get(path, query_string={param: value})
            assert response.status_code == 400, (
                f"{path}?{param}={value} returned {response.status_code}"
            )
            body = response.get_json()
            assert body["param"] == param
            assert param in body["error"]


def _assert_valid_matrix(client, path, cases):
    for param, value in cases.items():
        response = client.get(path, query_string={param: value})
        assert response.status_code == 200, (
            f"{path}?{param}={value} returned {response.status_code}: "
            f"{response.get_json()}"
        )


def _insert_related_video(app):
    import bottube_server

    with app.app_context():
        db = bottube_server.get_db()
        db.execute(
            """INSERT INTO agents (agent_name, display_name, api_key, created_at)
               VALUES (?, ?, ?, ?)""",
            ("shared-validator-owner", "Validator Owner", "validator-key", time.time()),
        )
        agent_id = db.execute(
            "SELECT id FROM agents WHERE agent_name = ?",
            ("shared-validator-owner",),
        ).fetchone()["id"]
        db.execute(
            """INSERT INTO videos
               (video_id, agent_id, title, filename, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            ("shared_validator_video", agent_id, "Validator", "validator.mp4", time.time()),
        )
        db.commit()


def test_feed_validates_every_reported_parameter(client):
    _assert_invalid_matrix(
        client,
        "/api/feed",
        {
            "limit": ("abc", -1, 999_999_999_999_999),
            "offset": ("abc", -1, 999_999_999_999_999),
            "page": ("abc", -1, 999_999_999_999_999),
            "since": ("abc", -1, 999_999_999_999_999),
            "before": ("abc", -1, 999_999_999_999_999),
            "category": ("abc", -1, 999_999_999_999_999),
            "sort": ("abc", -1, 999_999_999_999_999),
        },
    )


def test_feed_accepts_valid_values_and_preserves_defaults(client):
    baseline = client.get("/api/feed")
    assert baseline.status_code == 200
    baseline_body = baseline.get_json()

    _assert_valid_matrix(
        client,
        "/api/feed",
        {
            "limit": 5,
            "offset": 0,
            "page": 1,
            "since": 1_700_000_000,
            "before": "2026-01-01T00:00:00Z",
            "category": "music",
            "sort": "latest",
        },
    )

    unchanged = client.get("/api/feed", query_string={"limit": 5}).get_json()
    assert unchanged["page"] == baseline_body["page"] == 1
    assert unchanged["mode"] == baseline_body["mode"]
    assert unchanged["bucket"] == baseline_body["bucket"]


def test_trending_validates_limit_days_and_since(client):
    _assert_invalid_matrix(
        client,
        "/api/trending",
        {
            "limit": ("abc", -1, 999_999_999_999_999),
            "days": ("abc", -1, 999_999_999_999_999),
            "since": ("abc", -1, 999_999_999_999_999),
        },
    )


def test_trending_accepts_valid_values_and_preserves_defaults(client):
    assert client.get("/api/trending").status_code == 200
    _assert_valid_matrix(
        client,
        "/api/trending",
        {
            "limit": 5,
            "days": 7,
            "since": "2026-01-01T00:00:00Z",
        },
    )


def test_videos_validates_page(client):
    _assert_invalid_matrix(
        client,
        "/api/videos",
        {"page": ("abc", -1, 999_999_999_999_999)},
    )
    assert client.get("/api/videos").status_code == 200
    assert client.get("/api/videos?page=1").status_code == 200


def test_related_validates_limit_before_database_lookup(client):
    _assert_invalid_matrix(
        client,
        "/api/videos/not_present/related",
        {"limit": ("abc", -1, 999_999_999_999_999)},
    )


def test_related_accepts_valid_limit_and_preserves_default(app, client):
    _insert_related_video(app)
    path = "/api/videos/shared_validator_video/related"
    assert client.get(path).status_code == 200
    assert client.get(path, query_string={"limit": 5}).status_code == 200


def test_shared_int_parser_covers_default_type_and_bounds():
    app = Flask(__name__)

    with app.test_request_context("/?limit="):
        assert parse_positive_int("limit", 20, min_value=1, max_value=50) == (20, None)
    with app.test_request_context("/?limit=5"):
        assert parse_positive_int("limit", 20, min_value=1, max_value=50) == (5, None)
    with app.test_request_context("/?limit=abc"):
        value, error = parse_positive_int("limit", 20, min_value=1, max_value=50)
        assert value is None
        assert error[1] == 400
        assert error[0].get_json()["param"] == "limit"
    with app.test_request_context("/?limit=0"):
        assert parse_positive_int("limit", 20, min_value=1, max_value=50)[1][1] == 400
    with app.test_request_context("/?limit=51"):
        assert parse_positive_int("limit", 20, min_value=1, max_value=50)[1][1] == 400


def test_shared_enum_parser_normalizes_and_names_bad_parameter():
    app = Flask(__name__)

    with app.test_request_context("/?sort=LATEST"):
        assert parse_enum(
            "sort",
            "latest",
            ("latest", "popular"),
            case_sensitive=False,
        ) == ("latest", None)
    with app.test_request_context("/?sort=sideways"):
        value, error = parse_enum("sort", "latest", ("latest", "popular"))
        assert value is None
        assert error[1] == 400
        assert error[0].get_json()["param"] == "sort"


def test_shared_timestamp_parser_accepts_unix_and_iso_and_rejects_bounds():
    app = Flask(__name__)

    with app.test_request_context("/?since=1700000000"):
        assert parse_timestamp_iso("since")[0] == 1_700_000_000
    with app.test_request_context("/?since=2026-01-01T00:00:00Z"):
        value, error = parse_timestamp_iso("since")
        assert error is None
        assert value == 1_767_225_600
    with app.test_request_context("/?since=not-a-date"):
        value, error = parse_timestamp_iso("since")
        assert value is None
        assert error[0].get_json()["param"] == "since"
    with app.test_request_context("/?since=-1"):
        assert parse_timestamp_iso("since")[1][1] == 400
    with app.test_request_context(f"/?since={MAX_QUERY_TIMESTAMP + 1}"):
        assert parse_timestamp_iso("since")[1][1] == 400
