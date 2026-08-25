# SPDX-License-Identifier: MIT

import sys
import types
from importlib import metadata

import pytest
import werkzeug
from flask import Flask

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = metadata.version("werkzeug")


@pytest.fixture
def fake_bottube_server(monkeypatch):
    """Stub the server module so generation routes can validate request handling without the real app stack."""
    class FakeDB:
        def execute(self, *_args, **_kwargs):
            return self

        def fetchone(self):
            return {
                "id": 1,
                "agent_name": "generation_bot",
                "api_key": "test-key",
                "is_banned": 0,
            }

    module = types.SimpleNamespace(
        CATEGORY_MAP={"other": "Other"},
        get_db=lambda: FakeDB(),
    )
    monkeypatch.setitem(sys.modules, "bottube_server", module)
    return module


@pytest.fixture
def generation_client(fake_bottube_server):
    """Expose the modern generation blueprint through a Flask client for request validation tests."""
    from generation.routes import generation_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(generation_bp)
    return app.test_client()


@pytest.fixture
def legacy_generation_client(fake_bottube_server):
    """Expose the legacy generation blueprint so compatibility checks cover the older route surface too."""
    from video_gen_blueprint import video_gen_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(video_gen_bp)
    return app.test_client()


def test_generation_job_rejects_non_object_json_before_auth(generation_client):
    """Reject array JSON bodies before auth or generation logic touches the request."""
    resp = generation_client.post("/api/generation/jobs", json="not-object")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON object required"}


def test_generation_job_rejects_non_string_prompt(generation_client):
    """Require a string prompt so queued generation jobs always receive text instructions."""
    resp = generation_client.post(
        "/api/generation/jobs",
        json={"prompt": ["make a video"]},
        headers={"X-API-Key": "test-key"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "prompt must be a string"}


def test_generation_job_rejects_non_string_body_api_key(generation_client):
    """Reject malformed body API keys instead of attempting lookup with non-string values."""
    resp = generation_client.post(
        "/api/generation/jobs",
        json={"agent_api_key": ["test-key"], "prompt": "make a video"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "agent_api_key must be a string"}


def test_legacy_generate_video_rejects_non_object_json_before_auth(
    legacy_generation_client,
):
    """Apply the same object-only JSON contract to the legacy generate-video endpoint."""
    resp = legacy_generation_client.post(
        "/api/generate-video",
        json=["not", "an", "object"],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON object required"}


def test_legacy_generate_video_rejects_malformed_fields(legacy_generation_client):
    """Validate prompt, duration, category, and title types before the legacy route starts work."""
    headers = {"X-API-Key": "test-key"}

    prompt_resp = legacy_generation_client.post(
        "/api/generate-video",
        json={"prompt": ["make a video"]},
        headers=headers,
    )
    assert prompt_resp.status_code == 400
    assert prompt_resp.get_json() == {"error": "prompt must be a string"}

    duration_resp = legacy_generation_client.post(
        "/api/generate-video",
        json={"prompt": "make a video", "duration": "long"},
        headers=headers,
    )
    assert duration_resp.status_code == 400
    assert duration_resp.get_json() == {"error": "duration must be an integer"}

    category_resp = legacy_generation_client.post(
        "/api/generate-video",
        json={"prompt": "make a video", "category": ["music"]},
        headers=headers,
    )
    assert category_resp.status_code == 400
    assert category_resp.get_json() == {"error": "category must be a string"}

    title_resp = legacy_generation_client.post(
        "/api/generate-video",
        json={"prompt": "make a video", "title": ["demo"]},
        headers=headers,
    )
    assert title_resp.status_code == 400
    assert title_resp.get_json() == {"error": "title must be a string"}


def test_legacy_generate_video_rejects_boolean_duration_before_start(
    legacy_generation_client,
    monkeypatch,
):
    """Block boolean duration values so the worker thread never starts from ambiguous input."""
    import video_gen_blueprint

    monkeypatch.setattr(
        video_gen_blueprint.threading,
        "Thread",
        lambda *_args, **_kwargs: pytest.fail("generation should not start"),
    )

    resp = legacy_generation_client.post(
        "/api/generate-video",
        json={"prompt": "make a video", "duration": True},
        headers={"X-API-Key": "test-key"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "duration must be an integer"}


def test_legacy_generate_video_rejects_non_string_body_api_key(
    legacy_generation_client,
):
    """Mirror API-key type validation on the legacy route to keep auth parsing predictable."""
    resp = legacy_generation_client.post(
        "/api/generate-video",
        json={"agent_api_key": ["test-key"], "prompt": "make a video"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "agent_api_key must be a string"}
