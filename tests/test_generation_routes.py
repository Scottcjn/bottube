# SPDX-License-Identifier: MIT

import sys
import types

import pytest
from flask import Flask


@pytest.fixture
def fake_bottube_server(monkeypatch):
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
    from generation.routes import generation_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(generation_bp)
    return app.test_client()


@pytest.fixture
def legacy_generation_client(fake_bottube_server):
    from video_gen_blueprint import video_gen_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(video_gen_bp)
    return app.test_client()


def test_generation_job_rejects_non_object_json_before_auth(generation_client):
    resp = generation_client.post("/api/generation/jobs", json="not-object")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON object required"}


def test_generation_job_rejects_non_string_prompt(generation_client):
    resp = generation_client.post(
        "/api/generation/jobs",
        json={"prompt": ["make a video"]},
        headers={"X-API-Key": "test-key"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "prompt must be a string"}


def test_generation_job_rejects_non_string_body_api_key(generation_client):
    resp = generation_client.post(
        "/api/generation/jobs",
        json={"agent_api_key": ["test-key"], "prompt": "make a video"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "agent_api_key must be a string"}


def test_legacy_generate_video_rejects_non_object_json_before_auth(
    legacy_generation_client,
):
    resp = legacy_generation_client.post(
        "/api/generate-video",
        json=["not", "an", "object"],
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "JSON object required"}


def test_legacy_generate_video_rejects_malformed_fields(legacy_generation_client):
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


def test_legacy_generate_video_rejects_non_string_body_api_key(
    legacy_generation_client,
):
    resp = legacy_generation_client.post(
        "/api/generate-video",
        json={"agent_api_key": ["test-key"], "prompt": "make a video"},
    )

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "agent_api_key must be a string"}
