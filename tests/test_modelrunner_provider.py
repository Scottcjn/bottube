# SPDX-License-Identifier: MIT
"""Tests for the ModelRunner video generation provider.

Covers what is easy to get wrong when adding a queue-based provider:
availability must be gated on the API key, the submit payload must stay inside
the model's accepted ranges, the queue's own status vocabulary must be mapped
onto the router's ("pending"/"running"/"completed"/"failed"), a run of poll
errors must end in a bounded "failed" rather than "pending" forever, every
call must refuse redirects (urllib would otherwise forward the API key to any
host a 3xx named), the finished video must come only from the media CDN, and
the ffmpeg re-encode must actually run. All offline except the one real-ffmpeg
test, which skips when ffmpeg is not installed.
"""
import http.client
import io
import json
import shutil
import subprocess
import urllib.error
import urllib.request
import urllib.response
from pathlib import Path

import pytest

from generation.models import GenerationMode, GenerationRequest
from generation.providers import modelrunner as mr


class _FakeResponse(io.BytesIO):
    """Minimal stand-in for the object open_url() returns as a context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def _respond(payload):
    """Build an open_url replacement that always returns `payload` as JSON."""
    def _open(request, timeout=None):
        return _FakeResponse(json.dumps(payload).encode())
    return _open


def _fail_with(exc):
    """Build an open_url replacement that always raises `exc`."""
    def _open(request, timeout=None):
        raise exc
    return _open


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
    """Run submit() with open_url stubbed out and return the payload it sent."""
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    sent = {}

    def _open(request, timeout=None):
        sent["url"] = request.full_url
        sent["payload"] = json.loads(request.data.decode())
        sent["auth"] = request.get_header("Authorization")
        return _FakeResponse(json.dumps({"request_id": "r" * 21}).encode())

    monkeypatch.setattr(mr, "open_url", _open)
    req = GenerationRequest(prompt="a neon city", duration=duration)
    ok, external_id = mr.ModelRunnerProvider().submit(req, Path("."))
    assert ok is True
    assert external_id == "r" * 21
    return sent


@pytest.mark.parametrize(
    "requested,expected",
    [(1, 2), (2, 2), (5, 5), (30, 30), (60, 30), (300, 30)],
)
def test_submit_clamps_duration_to_the_range_the_model_accepts(monkeypatch, requested, expected):
    # GenerationRequest allows 1-300s; the model accepts 2-30s.
    sent = _capture_submit(monkeypatch, requested)

    assert sent["payload"]["duration"] == expected


def test_submit_asks_for_a_silent_clip(monkeypatch):
    # The re-encode replaces the audio track for every provider, so requesting
    # audio would mean paying for a track that is thrown away.
    sent = _capture_submit(monkeypatch, 5)

    assert sent["payload"]["audio"] is False


def test_submit_posts_to_the_configured_model_with_key_auth(monkeypatch):
    sent = _capture_submit(monkeypatch, 5)

    assert sent["url"] == f"{mr.MODELRUNNER_QUEUE_URL}/{mr.MODELRUNNER_MODEL}"
    assert sent["auth"] == "Key test-key"


def test_submit_reports_failure_when_no_request_id_comes_back(monkeypatch):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    monkeypatch.setattr(mr, "open_url", _respond({}))

    ok, reason = mr.ModelRunnerProvider().submit(
        GenerationRequest(prompt="a neon city"), Path(".")
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
    monkeypatch.setattr(mr, "open_url", _respond({"status": queue_status}))

    status, progress = mr.ModelRunnerProvider().get_status("r" * 21)

    assert status == expected
    assert 0.0 <= progress <= 1.0


# ---------------------------------------------------------------------------
# Poll-error budget (the #2211 class of bug)
# ---------------------------------------------------------------------------

def test_transport_errors_are_pending_until_the_budget_then_failed(monkeypatch):
    # An unreachable queue must not read as "still queued" forever; mirrors
    # comfyui_ltx.get_status().
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    monkeypatch.setattr(mr, "open_url", _fail_with(OSError("connection reset")))
    provider = mr.ModelRunnerProvider()

    statuses = [provider.get_status("r" * 21) for _ in range(mr._MAX_CONSECUTIVE_POLL_ERRORS)]

    assert statuses[:-1] == [("pending", 0.0)] * (mr._MAX_CONSECUTIVE_POLL_ERRORS - 1)
    assert statuses[-1] == ("failed", 0.0)


def test_a_malformed_status_body_counts_as_a_poll_error(monkeypatch):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    monkeypatch.setattr(mr, "open_url", lambda request, timeout=None: _FakeResponse(b"not json"))
    provider = mr.ModelRunnerProvider()

    for _ in range(mr._MAX_CONSECUTIVE_POLL_ERRORS - 1):
        assert provider.get_status("r" * 21) == ("pending", 0.0)
    assert provider.get_status("r" * 21) == ("failed", 0.0)


def test_a_genuinely_queued_job_never_trips_the_budget(monkeypatch):
    # IN_QUEUE can outlast the budget on a cold start; a poll that reaches the
    # queue is not an error however long it reports that state.
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    monkeypatch.setattr(mr, "open_url", _respond({"status": "IN_QUEUE"}))
    provider = mr.ModelRunnerProvider()

    for _ in range(mr._MAX_CONSECUTIVE_POLL_ERRORS * 3):
        assert provider.get_status("r" * 21) == ("pending", 0.0)


def test_a_successful_poll_resets_the_error_budget(monkeypatch):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    provider = mr.ModelRunnerProvider()
    failing = _fail_with(OSError("timed out"))

    monkeypatch.setattr(mr, "open_url", failing)
    for _ in range(mr._MAX_CONSECUTIVE_POLL_ERRORS - 1):
        assert provider.get_status("r" * 21) == ("pending", 0.0)
    monkeypatch.setattr(mr, "open_url", _respond({"status": "IN_QUEUE"}))
    assert provider.get_status("r" * 21) == ("pending", 0.0)
    monkeypatch.setattr(mr, "open_url", failing)

    # One more error is no longer the Nth in a row.
    assert provider.get_status("r" * 21) == ("pending", 0.0)


# ---------------------------------------------------------------------------
# Network pinning
# ---------------------------------------------------------------------------

def _authed_request():
    return urllib.request.Request(
        f"{mr.MODELRUNNER_QUEUE_URL}/x", headers={"Authorization": "Key test-key"}
    )


def test_the_stock_redirect_handler_would_forward_the_api_key_off_host():
    # The hazard the pin exists for: urllib keeps every non-Content header on a
    # redirected request, Authorization included, whatever host it names.
    followed = urllib.request.HTTPRedirectHandler().redirect_request(
        _authed_request(), None, 302, "Found", {}, "https://evil.example/"
    )

    assert followed.full_url == "https://evil.example/"
    assert followed.get_header("Authorization") == "Key test-key"


def test_a_redirect_is_an_error_not_a_second_request():
    hops = []

    class _Redirecting302(urllib.request.HTTPSHandler):
        def https_open(self, req):
            hops.append(req.full_url)
            headers = http.client.HTTPMessage()
            headers["Location"] = "https://evil.example/"
            resp = urllib.response.addinfourl(io.BytesIO(b""), headers, req.full_url, 302)
            resp.msg = "Found"
            return resp

    opener = urllib.request.build_opener(mr._RefuseRedirects(), _Redirecting302())

    with pytest.raises(urllib.error.HTTPError) as raised:
        opener.open(_authed_request(), timeout=1)

    assert raised.value.code == 302
    assert hops == [f"{mr.MODELRUNNER_QUEUE_URL}/x"]


def test_open_url_goes_through_the_refusing_opener():
    assert any(isinstance(h, mr._RefuseRedirects) for h in mr._opener.handlers)
    assert not any(type(h) is urllib.request.HTTPRedirectHandler for h in mr._opener.handlers)


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://media.modelrunner.ai/v.mp4", True),
        ("https://cdn.media.modelrunner.ai/v.mp4", True),
        ("http://media.modelrunner.ai/v.mp4", False),                # plaintext
        ("https://media.modelrunner.ai.evil.example/v.mp4", False),  # suffix trick
        ("https://media.modelrunner.ai@evil.example/v.mp4", False),  # userinfo trick
        ("https://evil.example/media.modelrunner.ai/v.mp4", False),  # host in the path
        ("https://storage.provider.example/v.mp4", False),
        ("[output withheld - not yet rehosted]", False),
        ("", False),
    ],
)
def test_is_allowed_media_url_pins_the_download_host(url, allowed):
    assert mr.is_allowed_media_url(url) is allowed


def test_get_result_refuses_to_download_from_an_unlisted_host(monkeypatch, tmp_path):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    fetched = []

    def _open(request, timeout=None):
        fetched.append(request.full_url)
        return _FakeResponse(json.dumps({"output": "https://evil.example/v.mp4"}).encode())

    monkeypatch.setattr(mr, "open_url", _open)

    assert mr.ModelRunnerProvider().get_result("r" * 21, tmp_path) is None
    # The result envelope was read from the queue; the foreign URL never was.
    assert fetched == [f"{mr.MODELRUNNER_QUEUE_URL}/{mr.MODELRUNNER_MODEL}/requests/{'r' * 21}"]
    assert list(tmp_path.iterdir()) == []


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
# Result download and re-encode
# ---------------------------------------------------------------------------

def _serve_result_and_bytes(monkeypatch, video=b"\x00" * 64):
    """open_url that answers the result envelope for the API and raw bytes for the media URL."""
    def _open(request, timeout=None):
        if request.full_url == URL:
            assert request.get_header("Authorization") is None  # the key stays on the queue host
            return _FakeResponse(video)
        return _FakeResponse(json.dumps({"output": URL}).encode())
    monkeypatch.setattr(mr, "open_url", _open)


def test_get_result_downloads_then_reencodes_with_both_inputs_declared_first(monkeypatch, tmp_path):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    _serve_result_and_bytes(monkeypatch)
    seen = {}

    def _run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["raw_present"] = Path(cmd[cmd.index("-i") + 1]).exists()
        Path(cmd[-1]).write_bytes(b"encoded")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(mr.subprocess, "run", _run)

    out = mr.ModelRunnerProvider().get_result("r" * 21, tmp_path)

    assert out is not None and out.read_bytes() == b"encoded"
    assert seen["raw_present"] is True
    cmd = seen["cmd"]
    # ffmpeg reads arguments positionally: an output option ahead of the
    # second -i is taken as an option for that input and rejected outright.
    last_input = max(i for i, arg in enumerate(cmd) if arg == "-i")
    first_output_option = min(cmd.index(arg) for arg in ("-map", "-vf", "-c:v", "-c:a"))
    assert last_input < first_output_option
    # Video from the download, audio from the silent source, whatever the model returned.
    assert cmd[cmd.index("-map"):cmd.index("-map") + 4] == ["-map", "0:v:0", "-map", "1:a:0"]
    # The raw download is cleaned up; only the encoded file remains.
    assert [p.name for p in tmp_path.iterdir()] == [out.name]


def test_get_result_reports_nothing_when_ffmpeg_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(mr, "MODELRUNNER_KEY", "test-key")
    _serve_result_and_bytes(monkeypatch)
    def _run(cmd, **kwargs):
        # A mid-encode failure can leave a partial output behind.
        Path(cmd[-1]).write_bytes(b"partial")
        return subprocess.CompletedProcess(cmd, 1, b"", b"Invalid argument")

    monkeypatch.setattr(mr.subprocess, "run", _run)

    assert mr.ModelRunnerProvider().get_result("r" * 21, tmp_path) is None
    # Neither the raw download nor the partial encode is left in the work dir.
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs a real ffmpeg")
def test_reencode_produces_a_square_h264_file_with_real_ffmpeg(tmp_path):
    # The test the argument-order bug would have failed: ffmpeg rejected the
    # previous command before it ever opened the output file.
    raw = tmp_path / "raw.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=size=160x90:rate=8", "-t", "0.5",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(raw)],
        check=True, capture_output=True, timeout=60,
    )
    out = tmp_path / "out.mp4"

    assert mr._reencode(raw, out) is True
    assert out.stat().st_size > 0


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
