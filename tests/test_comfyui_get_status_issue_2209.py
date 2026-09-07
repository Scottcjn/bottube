# SPDX-License-Identifier: MIT
"""Regression tests for ComfyUI get_status() error handling (bottube issue #2209).

A transport error, timeout, HTTP error, or malformed JSON from the ComfyUI
history poll must surface as a distinct transient-error signal instead of
being silently folded into "pending". Only a valid history response with no
entry for the prompt_id is a genuine "not queued yet" pending.
"""
import json

import pytest

import generation.providers.comfyui_ltx as comfyui_module
from generation.providers.comfyui_ltx import ComfyUILTXProvider


@pytest.fixture()
def provider():
    return ComfyUILTXProvider()


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


class _FakeUrlopen:
    """Stands in for urllib.request.urlopen with a canned history payload."""

    def __init__(self, history):
        self._history = history

    def __call__(self, url, timeout=None):
        return _FakeResponse(self._history)


class _FailingUrlopen:
    """Stands in for urllib.request.urlopen and always raises."""

    def __init__(self, exc):
        self._exc = exc

    def __call__(self, url, timeout=None):
        raise self._exc


class TestGetStatusErrorHandling:
    def test_urlerror_is_not_silently_pending(self, provider, monkeypatch):
        """URLError from the history poll must be reported, not swallowed as pending."""
        import urllib.error

        monkeypatch.setattr(
            comfyui_module.urllib.request, "urlopen", _FailingUrlopen(urllib.error.URLError("connection refused"))
        )
        status, progress = provider.get_status("prompt-1")
        assert status != "pending"
        assert "error" in status

    def test_timeout_is_not_silently_pending(self, provider, monkeypatch):
        """A socket timeout must be reported as a transient error."""
        monkeypatch.setattr(comfyui_module.urllib.request, "urlopen", _FailingUrlopen(TimeoutError("request timed out")))
        status, _ = provider.get_status("prompt-2")
        assert status != "pending"
        assert "error" in status

    def test_http_error_is_not_silently_pending(self, provider, monkeypatch):
        """An HTTP 500 from the history endpoint must be reported."""
        import urllib.error

        exc = urllib.error.HTTPError("http://x", 500, "boom", None, None)
        monkeypatch.setattr(comfyui_module.urllib.request, "urlopen", _FailingUrlopen(exc))
        status, _ = provider.get_status("prompt-3")
        assert status != "pending"
        assert "error" in status

    def test_malformed_json_is_not_silently_pending(self, provider, monkeypatch):
        """Malformed JSON from the history endpoint must be reported."""
        exc = json.JSONDecodeError("Expecting value", "", 0)
        monkeypatch.setattr(comfyui_module.urllib.request, "urlopen", _FailingUrlopen(exc))
        status, _ = provider.get_status("prompt-4")
        assert status != "pending"
        assert "error" in status

    def test_valid_history_without_entry_is_pending(self, provider, monkeypatch):
        """A valid empty history response is the genuine pending case."""
        monkeypatch.setattr(comfyui_module.urllib.request, "urlopen", _FakeUrlopen({}))
        status, progress = provider.get_status("prompt-5")
        assert status == "pending"
        assert progress == 0.0

    def test_error_status_str_maps_to_failed(self, provider, monkeypatch):
        """status_str=error in a history entry must map to failed."""
        history = {"prompt-6": {"status": {"status_str": "error"}, "outputs": {}}}
        monkeypatch.setattr(comfyui_module.urllib.request, "urlopen", _FakeUrlopen(history))
        status, _ = provider.get_status("prompt-6")
        assert status == "failed"

    def test_outputs_present_maps_to_completed(self, provider, monkeypatch):
        """Outputs present must map to completed and cache the result."""
        outputs = {"node-7": {"images": [{"filename": "out.webp"}]}}
        history = {"prompt-7": {"status": {"status_str": "success"}, "outputs": outputs}}
        monkeypatch.setattr(comfyui_module.urllib.request, "urlopen", _FakeUrlopen(history))
        status, progress = provider.get_status("prompt-7")
        assert status == "completed"
        assert progress == 1.0
        assert provider._completed["prompt-7"] == outputs


class TestBoundedErrorBudget:
    def test_consecutive_errors_fail_after_budget(self, provider, monkeypatch):
        """Repeated poll errors must surface 'error' until the budget, then 'failed'."""
        monkeypatch.setattr(
            comfyui_module.urllib.request, "urlopen", _FailingUrlopen(TimeoutError("down"))
        )
        budget = provider.MAX_CONSECUTIVE_POLL_ERRORS
        statuses = [provider.get_status("prompt-8")[0] for _ in range(budget)]
        assert statuses[: budget - 1] == ["error"] * (budget - 1)
        assert statuses[-1] == "failed"
        # Stays failed — no budget reset without a successful poll.
        assert provider.get_status("prompt-8")[0] == "failed"

    def test_successful_poll_resets_error_budget(self, provider, monkeypatch):
        """A successful poll between failures must reset the consecutive budget."""
        budget = provider.MAX_CONSECUTIVE_POLL_ERRORS
        failing = _FailingUrlopen(TimeoutError("down"))
        ok = _FakeUrlopen({})

        for _ in range(budget - 1):
            comfyui_module.urllib.request.urlopen = failing
            assert provider.get_status("prompt-9")[0] == "error"
            comfyui_module.urllib.request.urlopen = ok
            assert provider.get_status("prompt-9")[0] == "pending"

        # Never reached the budget despite budget-1 total failures.
        comfyui_module.urllib.request.urlopen = failing
        assert provider.get_status("prompt-9")[0] == "error"
        assert provider._poll_errors["prompt-9"] == 1
