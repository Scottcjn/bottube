# SPDX-License-Identifier: MIT
"""Tests for the ModelRunner video generation provider.

Covers the three things that are easy to get wrong when adding a queue-based
provider: availability must be gated on the API key, the submit payload must
stay inside the model's accepted ranges, and the queue's own status vocabulary
must be mapped onto the router's ("pending"/"running"/"completed"/"failed").
All offline - no network call is made.
"""
import json
import io

import pytest

from generation.models import GenerationMode, GenerationRequest
from generation.providers import modelrunner as mr


class _FakeResponse(io.BytesIO):
    """Minimal stand-in for the object urlopen() returns as a context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def _respond(payload):
    """Build a urlopen replacement that always returns `payload` as JSON."""
    def _urlopen(request, timeout=None):
        return _FakeResponse(json.dumps(payload).encode())
    return _urlopen


# ---------------------------------------------------------------------------
# Availability and validation
# ---------------------------------------------------------------------------

def test_provider_is_unavailable_without_an_api_key(monkeypatch):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "")

    assert mr.ModelRunnerProvider().get_capabilities().available is False


def test_provider_is_available_once_the_api_key_is_set(monkeypatch):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")

    caps = mr.ModelRunnerProvider().get_capabilities()

    assert caps.available is True
    assert caps.requires_api_key is True
    assert GenerationMode.text_to_video in caps.modes


def test_validate_input_rejects_an_empty_prompt(monkeypatch):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")

    ok, reason = mr.ModelRunnerProvider().validate_input(GenerationRequest(prompt=""))

    assert ok is False
    assert "prompt" in reason


def test_validate_input_rejects_a_missing_api_key(monkeypatch):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "")

    ok, reason = mr.ModelRunnerProvider().validate_input(GenerationRequest(prompt="a cat"))

    assert ok is False
    assert "MODELRUNNER_KEY" in reason


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------

def _capture_submit(monkeypatch, duration):
    """Run submit() with urlopen stubbed out and return the payload it sent."""
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    sent = {}

    def _urlopen(request, timeout=None):
        sent["url"] = request.full_url
        sent["payload"] = json.loads(request.data.decode())
        sent["auth"] = request.get_header("Authorization")
        return _FakeResponse(json.dumps({"request_id": "r" * 21}).encode())

    monkeypatch.setattr(mr.urllib.request, "urlopen", _urlopen)
    req = GenerationRequest(prompt="a neon city", duration=duration)
    ok, external_id = mr.ModelRunnerProvider().submit(req, tmp_path_stub())
    assert ok is True
    assert external_id == "r" * 21
    return sent


def tmp_path_stub():
    """submit() never touches the output dir, so any Path will do."""
    from pathlib import Path
    return Path(".")


@pytest.mark.parametrize(
    "requested,expected",
    [(1, 2), (2, 2), (5, 5), (30, 30), (60, 30), (300, 30)],
)
def test_submit_clamps_duration_to_the_range_the_model_accepts(monkeypatch, requested, expected):
    # GenerationRequest allows 1-300s; the model accepts 2-30s.
    sent = _capture_submit(monkeypatch, requested)

    assert sent["payload"]["duration"] == expected


def test_submit_asks_for_a_silent_clip(monkeypatch):
    # _reencode_to_square replaces the audio track for every provider, so
    # requesting audio would mean paying for a track that is thrown away.
    sent = _capture_submit(monkeypatch, 5)

    assert sent["payload"]["audio"] is False


def test_submit_posts_to_the_configured_model_with_key_auth(monkeypatch):
    sent = _capture_submit(monkeypatch, 5)

    assert sent["url"] == f"{mr.MODELRUNNER_QUEUE_URL}/{mr.MODELRUNNER_MODEL}"
    assert sent["auth"] == "Key test-key"


def test_submit_reports_failure_when_no_request_id_comes_back(monkeypatch):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    monkeypatch.setattr(mr.urllib.request, "urlopen", _respond({}))

    ok, reason = mr.ModelRunnerProvider().submit(
        GenerationRequest(prompt="a neon city"), tmp_path_stub()
    )

    assert ok is False
    assert "request_id" in reason


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "queue_status,expected",
    [
        ("IN_QUEUE", "pending"),
        ("IN_PROGRESS", "running"),
        ("COMPLETED", "completed"),
        ("FAILED", "failed"),
        ("CANCELLED", "failed"),
    ],
)
def test_get_status_maps_every_queue_state(monkeypatch, queue_status, expected):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    monkeypatch.setattr(mr.urllib.request, "urlopen", _respond({"status": queue_status}))

    status, progress = mr.ModelRunnerProvider().get_status("r" * 21)

    assert status == expected
    assert 0.0 <= progress <= 1.0


def test_get_status_treats_an_unreachable_queue_as_pending(monkeypatch):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")

    def _boom(request, timeout=None):
        raise OSError("connection reset")

    monkeypatch.setattr(mr.urllib.request, "urlopen", _boom)

    assert mr.ModelRunnerProvider().get_status("r" * 21) == ("pending", 0.0)


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------

URL = "https://media.modelrunner.ai/example.mp4"


@pytest.mark.parametrize(
    "output,expected",
    [
        (URL, URL),                      # bare string: what video models return today
        ({"video_url": URL}, URL),
        ({"url": URL}, URL),
        ({"video": URL}, URL),
        ({"video": {"url": URL}}, URL),
        ([URL], URL),
        (None, ""),
        ({}, ""),
        ("", ""),
        ({"unexpected": 42}, ""),
    ],
)
def test_extract_video_url_handles_the_output_shapes_models_return(output, expected):
    # Output shape is defined by the model, not the platform, so
    # MODELRUNNER_VIDEO_MODEL can point at any of these without a code change.
    assert mr._extract_video_url(output) == expected


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_provider_is_registered_in_the_worker_registry(monkeypatch):
    monkeypatch.setenv("MODELRUNNER_KEY", "test-key")
    import generation.worker as worker

    monkeypatch.setattr(worker, "_registry", None)

    assert "modelrunner" in worker.get_registry().names()


def test_provider_is_registered_in_the_video_generation_blueprint(monkeypatch):
    # The blueprint registry is what the running server actually dispatches to.
    # ProviderRegistry.register() drops any provider whose required key env is
    # unset, so the key has to be present before the registry is rebuilt.
    import video_gen_blueprint as vgb

    monkeypatch.setenv("MODELRUNNER_KEY", "test-key")
    monkeypatch.setattr(vgb, "_provider_registry", vgb.ProviderRegistry())
    vgb._init_provider_registry()

    assert "modelrunner" in vgb._provider_registry._providers


def test_blueprint_provider_is_skipped_when_the_key_is_absent(monkeypatch):
    # The other half of the contract: no key, no registration, no failed calls.
    import video_gen_blueprint as vgb

    monkeypatch.delenv("MODELRUNNER_KEY", raising=False)
    monkeypatch.setattr(vgb, "_provider_registry", vgb.ProviderRegistry())
    vgb._init_provider_registry()

    assert "modelrunner" not in vgb._provider_registry._providers
