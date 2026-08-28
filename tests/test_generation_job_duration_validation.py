# SPDX-License-Identifier: MIT
"""Validation tests for modern generation job duration parsing."""

import sys
import types

import pytest
from flask import Flask


@pytest.fixture()
def generation_routes(monkeypatch):
    """Generation routes app under test with create_job/thread swapped to doubles."""
    created_requests = []

    class FakeDB:
        def execute(self, *_args, **_kwargs):
            """No-op cursor.execute that returns itself (FakeCursor)."""
            return self

        def fetchone(self):
            """FakeCursor.fetchone returning a canned agent row."""
            return {
                "id": 1,
                "agent_name": "generation_bot",
                "api_key": "test-key",
                "is_banned": 0,
            }

    fake_server = types.SimpleNamespace(get_db=lambda: FakeDB())
    monkeypatch.setitem(sys.modules, "bottube_server", fake_server)

    import generation.routes as routes

    monkeypatch.setattr(routes, "_check_rate", lambda _api_key: None)
    monkeypatch.setattr(routes, "_record_rate", lambda _api_key: None)

    def _create_job(_owner_id, req):
        """Stub create_job that records requests and returns a fixed job id."""
        created_requests.append(req)
        return "job-1"

    monkeypatch.setattr(routes, "create_job", _create_job)

    class DummyThread:
        def __init__(self, *_args, **_kwargs):
            """DummyThread no-op constructor."""
            pass

        def start(self):
            """DummyThread no-op start."""
            pass

    monkeypatch.setattr(routes.threading, "Thread", DummyThread)
    routes.created_requests = created_requests
    return routes


def _post_generation_job(routes, payload):
    """POST a generation job payload and return the response."""
    app = Flask(__name__)
    with app.test_request_context(
        "/api/generation/jobs",
        method="POST",
        json=payload,
        headers={"X-API-Key": "test-key"},
    ):
        return routes.create_generation_job()


def test_generation_job_rejects_boolean_duration(generation_routes):
    """A boolean duration is rejected with 400."""
    resp, status = _post_generation_job(
        generation_routes,
        {"prompt": "make a video", "duration": True},
    )

    assert status == 400
    assert resp.get_json() == {"error": "duration must be an integer"}
    assert generation_routes.created_requests == []


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": "make a video", "duration": "long"},
        {"prompt": "make a video", "duration": 1.9},
        {"prompt": "make a video", "durationSec": True},
        {"prompt": "make a video", "durationSec": 2.5},
    ],
)
def test_generation_job_rejects_malformed_duration_aliases(
    generation_routes,
    payload,
):
    """Malformed duration alias strings are rejected with 400."""
    resp, status = _post_generation_job(generation_routes, payload)

    assert status == 400
    assert resp.get_json() == {"error": "duration must be an integer"}
    assert generation_routes.created_requests == []


@pytest.mark.parametrize(
    ("payload", "expected_duration"),
    [
        ({"prompt": "make a video"}, 8),
        ({"prompt": "make a video", "duration": "12"}, 12),
        ({"prompt": "make a video", "durationSec": "15", "duration": "12"}, 15),
    ],
)
def test_generation_job_preserves_valid_duration_inputs(
    generation_routes,
    payload,
    expected_duration,
):
    """Valid duration inputs are accepted and passed through to create_job."""
    resp, status = _post_generation_job(generation_routes, payload)

    assert status == 202
    assert resp.get_json()["ok"] is True
    assert generation_routes.created_requests[-1].duration == expected_duration
