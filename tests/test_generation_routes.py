# SPDX-License-Identifier: MIT

import sys
from types import SimpleNamespace

from flask import Flask

from generation.routes import generation_bp
from video_gen_blueprint import video_gen_bp


def create_app():
    app = Flask(__name__)
    app.register_blueprint(generation_bp)
    return app


def create_legacy_app():
    app = Flask(__name__)
    app.register_blueprint(video_gen_bp)
    return app


class FakeAgentDB:
    def __init__(self, agent_id=9, api_key="legacy-secret"):
        self.agent_id = agent_id
        self.api_key = api_key

    def execute(self, *_args, **_kwargs):
        return self

    def fetchone(self):
        return {"id": self.agent_id, "api_key": self.api_key, "is_banned": 0}


def test_generation_job_rejects_non_object_json_before_auth():
    client = create_app().test_client()

    response = client.post("/api/generation/jobs", json="not-object")

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def test_generation_job_rejects_non_object_json_after_header_auth(monkeypatch):
    class FakeDB:
        def execute(self, *_args, **_kwargs):
            return self

        def fetchone(self):
            return {"id": 7, "api_key": "secret", "is_banned": 0}

    monkeypatch.setitem(
        sys.modules,
        "bottube_server",
        SimpleNamespace(get_db=lambda: FakeDB()),
    )
    client = create_app().test_client()

    response = client.post(
        "/api/generation/jobs",
        json="not-object",
        headers={"X-API-Key": "secret"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def test_generation_job_rejects_non_string_prompt_after_header_auth(monkeypatch):
    class FakeDB:
        def execute(self, *_args, **_kwargs):
            return self

        def fetchone(self):
            return {"id": 7, "api_key": "secret", "is_banned": 0}

    monkeypatch.setitem(
        sys.modules,
        "bottube_server",
        SimpleNamespace(get_db=lambda: FakeDB()),
    )
    client = create_app().test_client()

    response = client.post(
        "/api/generation/jobs",
        json={"prompt": ["make a video"]},
        headers={"X-API-Key": "secret"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "prompt must be a string"}


def test_legacy_generate_video_rejects_non_object_json_before_auth():
    client = create_legacy_app().test_client()

    response = client.post("/api/generate-video", json=["not-object"])

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def test_legacy_generate_video_rejects_non_object_json_after_header_auth(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "bottube_server",
        SimpleNamespace(
            CATEGORY_MAP={"other": "Other"},
            get_db=lambda: FakeAgentDB(),
        ),
    )
    client = create_legacy_app().test_client()

    response = client.post(
        "/api/generate-video",
        json="not-object",
        headers={"X-API-Key": "legacy-secret"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "JSON object required"}


def test_legacy_generate_video_rejects_non_string_prompt(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "bottube_server",
        SimpleNamespace(CATEGORY_MAP={"other": "Other"}, get_db=lambda: FakeAgentDB()),
    )
    client = create_legacy_app().test_client()

    response = client.post(
        "/api/generate-video",
        json={"prompt": ["make a video"]},
        headers={"X-API-Key": "legacy-secret"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "prompt must be a string"}


def test_legacy_generate_video_rejects_non_integer_duration(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "bottube_server",
        SimpleNamespace(CATEGORY_MAP={"other": "Other"}, get_db=lambda: FakeAgentDB()),
    )
    client = create_legacy_app().test_client()

    response = client.post(
        "/api/generate-video",
        json={"prompt": "make a video", "duration": "long"},
        headers={"X-API-Key": "legacy-secret"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "duration must be an integer"}


def test_legacy_generate_video_rejects_non_string_category(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "bottube_server",
        SimpleNamespace(CATEGORY_MAP={"other": "Other"}, get_db=lambda: FakeAgentDB()),
    )
    client = create_legacy_app().test_client()

    response = client.post(
        "/api/generate-video",
        json={"prompt": "make a video", "category": ["music"]},
        headers={"X-API-Key": "legacy-secret"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "category must be a string"}


def test_legacy_generate_video_rejects_non_string_title(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "bottube_server",
        SimpleNamespace(CATEGORY_MAP={"other": "Other"}, get_db=lambda: FakeAgentDB()),
    )
    client = create_legacy_app().test_client()

    response = client.post(
        "/api/generate-video",
        json={"prompt": "make a video", "title": ["demo"]},
        headers={"X-API-Key": "legacy-secret"},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "title must be a string"}
