# SPDX-License-Identifier: MIT
"""Regression tests for ComfyUILTXProvider.get_status() transient-error handling.

Before this fix, get_status() wrapped the whole history poll in
`try: ... except Exception: pass` and always fell through to
`return "pending", 0.0`. A transport error, timeout, HTTP error, or
malformed JSON response was therefore indistinguishable from a job that is
genuinely still queued -- callers polled forever and users never saw a
failure. See issue: generation: ComfyUI get_status() turns every error into
permanent "pending".
"""
import json
import urllib.error

from generation.providers.comfyui_ltx import (
    _MAX_CONSECUTIVE_POLL_ERRORS,
    ComfyUILTXProvider,
)


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._payload


def test_transport_error_is_pending_until_budget_then_fails(monkeypatch):
    """A URLError should not be silently pending forever."""
    provider = ComfyUILTXProvider()
    calls = {"n": 0}

    def fake_urlopen(url, timeout):
        calls["n"] += 1
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(
        "generation.providers.comfyui_ltx.urllib.request.urlopen", fake_urlopen
    )

    statuses = [provider.get_status("job-1") for _ in range(_MAX_CONSECUTIVE_POLL_ERRORS)]

    # Every attempt before the budget is exhausted is a transient "pending"...
    assert statuses[:-1] == [("pending", 0.0)] * (_MAX_CONSECUTIVE_POLL_ERRORS - 1)
    # ...and the Nth consecutive failure gives up and reports it failed.
    assert statuses[-1] == ("failed", 0.0)
    assert calls["n"] == _MAX_CONSECUTIVE_POLL_ERRORS


def test_malformed_json_counts_as_a_poll_error_too(monkeypatch):
    """A non-JSON / truncated response is the same class of failure as a transport error."""
    provider = ComfyUILTXProvider()

    monkeypatch.setattr(
        "generation.providers.comfyui_ltx.urllib.request.urlopen",
        lambda url, timeout: _FakeResponse(b"not json"),
    )

    for _ in range(_MAX_CONSECUTIVE_POLL_ERRORS - 1):
        assert provider.get_status("job-2") == ("pending", 0.0)
    assert provider.get_status("job-2") == ("failed", 0.0)


def test_valid_history_with_no_entry_yet_stays_pending_indefinitely(monkeypatch):
    """A reachable ComfyUI with no entry for this id yet is genuinely queued, not an error."""
    provider = ComfyUILTXProvider()

    monkeypatch.setattr(
        "generation.providers.comfyui_ltx.urllib.request.urlopen",
        lambda url, timeout: _FakeResponse(json.dumps({}).encode()),
    )

    # Well past the error budget -- a real "no entry yet" must never trip it.
    for _ in range(_MAX_CONSECUTIVE_POLL_ERRORS * 3):
        assert provider.get_status("job-3") == ("pending", 0.0)


def test_a_successful_poll_resets_the_error_budget(monkeypatch):
    """Transient errors that later recover shouldn't leave a job one poll from failing."""
    provider = ComfyUILTXProvider()
    external_id = "job-4"
    calls = {"n": 0}

    def flaky_then_recovers(url, timeout):
        calls["n"] += 1
        if calls["n"] <= _MAX_CONSECUTIVE_POLL_ERRORS - 1:
            raise urllib.error.URLError("timeout")
        return _FakeResponse(json.dumps({}).encode())

    monkeypatch.setattr(
        "generation.providers.comfyui_ltx.urllib.request.urlopen", flaky_then_recovers
    )

    for _ in range(_MAX_CONSECUTIVE_POLL_ERRORS - 1):
        assert provider.get_status(external_id) == ("pending", 0.0)
    # The recovering poll succeeds and resets the counter...
    assert provider.get_status(external_id) == ("pending", 0.0)

    # ...so a fresh run of transport errors needs the full budget again,
    # rather than failing on the very next call.
    monkeypatch.setattr(
        "generation.providers.comfyui_ltx.urllib.request.urlopen",
        lambda url, timeout: (_ for _ in ()).throw(urllib.error.URLError("timeout")),
    )
    for _ in range(_MAX_CONSECUTIVE_POLL_ERRORS - 1):
        assert provider.get_status(external_id) == ("pending", 0.0)
    assert provider.get_status(external_id) == ("failed", 0.0)


def test_status_str_error_is_reported_failed(monkeypatch):
    """ComfyUI's own status_str=error must map to a failed job (unchanged behavior)."""
    provider = ComfyUILTXProvider()
    history = {"job-5": {"status": {"status_str": "error"}}}

    monkeypatch.setattr(
        "generation.providers.comfyui_ltx.urllib.request.urlopen",
        lambda url, timeout: _FakeResponse(json.dumps(history).encode()),
    )

    assert provider.get_status("job-5") == ("failed", 0.0)


def test_outputs_present_is_reported_completed(monkeypatch):
    """A history entry with outputs must map to completed (unchanged behavior)."""
    provider = ComfyUILTXProvider()
    history = {"job-6": {"outputs": {"7": {"images": [{"filename": "out.webp"}]}}}}

    monkeypatch.setattr(
        "generation.providers.comfyui_ltx.urllib.request.urlopen",
        lambda url, timeout: _FakeResponse(json.dumps(history).encode()),
    )

    assert provider.get_status("job-6") == ("completed", 1.0)
    # Second call short-circuits via the completed-jobs cache, no network call.
    monkeypatch.setattr(
        "generation.providers.comfyui_ltx.urllib.request.urlopen",
        lambda url, timeout: (_ for _ in ()).throw(AssertionError("should not poll again")),
    )
    assert provider.get_status("job-6") == ("completed", 1.0)
