# SPDX-License-Identifier: MIT
from pathlib import Path

from providers.base import GeneratedVideo
from providers import router


class FailProvider:
    def __init__(self, message: str = "forced failure"):
        self.message = message

    def generate(self, prompt: str, duration: int = 8, **kwargs):
        raise RuntimeError(self.message)


class SuccessProvider:
    def __init__(self, name: str = "runway"):
        self.name = name

    def generate(self, prompt: str, duration: int = 8, **kwargs):
        return GeneratedVideo(provider=self.name, output_path=Path("/tmp/video.mp4"), metadata={})


class FailThenSuccessProvider:
    def __init__(self, failures: int = 1, message: str = "timeout"):
        self.failures = failures
        self.calls = 0
        self.message = message

    def generate(self, prompt: str, duration: int = 8, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError(self.message)
        return GeneratedVideo(provider="grok", output_path=Path("/tmp/video.mp4"), metadata={})


def test_choose_provider_runway_keywords():
    assert router.choose_provider("cinematic photoreal reveal", prefer="auto") == "runway"


def test_choose_provider_default_grok():
    assert router.choose_provider("retro computer in a lab", prefer="auto") == "grok"


def test_choose_provider_explicit_preference():
    assert router.choose_provider("anything", prefer="runway") == "runway"


def test_classify_error_categories():
    assert router.classify_error(RuntimeError("401 unauthorized")) == "auth"
    assert router.classify_error(RuntimeError("429 rate limit")) == "throttled"
    assert router.classify_error(RuntimeError("request timeout")) == "transient"
    assert router.classify_error(RuntimeError("400 bad request")) == "permanent"


def test_generate_video_fallback(monkeypatch):
    monkeypatch.setattr(
        router,
        "_PROVIDER_FACTORIES",
        {
            "grok": lambda: FailProvider("timeout"),
            "runway": lambda: SuccessProvider("runway"),
        },
    )

    result = router.generate_video(
        "retro system test",
        prefer="grok",
        fallback=True,
        duration=5,
    )

    assert result.provider == "runway"
    assert result.metadata.get("router_fallback_used") is True
    assert result.metadata.get("router_primary") == "grok"
    assert result.metadata.get("router_provider") == "runway"


def test_generate_video_retries_transient(monkeypatch):
    provider = FailThenSuccessProvider(failures=1, message="timeout while connecting")
    delays = []
    monkeypatch.setattr(
        router,
        "_PROVIDER_FACTORIES",
        {
            "grok": lambda: provider,
            "runway": lambda: SuccessProvider("runway"),
        },
    )

    result = router.generate_video(
        "retry test",
        prefer="grok",
        fallback=False,
        max_retries=2,
        retry_backoff_s=1.0,
        sleep_fn=delays.append,
    )

    assert result.provider == "grok"
    assert provider.calls == 2
    assert delays == [1.0]
    attempts = result.metadata.get("router_attempts") or []
    assert len(attempts) == 2
    assert attempts[0]["status"] == "error"
    assert attempts[1]["status"] == "ok"
    assert result.metadata.get("router_error_categories", {}).get("transient") == 1


def test_generate_video_auth_error_no_retry(monkeypatch):
    delays = []
    monkeypatch.setattr(
        router,
        "_PROVIDER_FACTORIES",
        {"grok": lambda: FailProvider("401 unauthorized"), "runway": lambda: SuccessProvider("runway")},
    )

    try:
        router.generate_video(
            "auth failure",
            prefer="grok",
            fallback=False,
            max_retries=3,
            sleep_fn=delays.append,
        )
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "All provider attempts failed" in str(exc)
        assert "auth" in str(exc)

    assert delays == []


def test_generate_video_without_fallback_raises(monkeypatch):
    monkeypatch.setattr(
        router,
        "_PROVIDER_FACTORIES",
        {"grok": lambda: FailProvider("forced failure"), "runway": lambda: FailProvider("forced failure")},
    )

    try:
        router.generate_video("test", prefer="grok", fallback=False)
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "All provider attempts failed" in str(exc)


def test_repeated_failures_emit_warning(monkeypatch):
    warnings = []
    monkeypatch.setattr(router, "_PROVIDER_FAILURE_STREAK", {"grok": 0, "runway": 0})
    monkeypatch.setattr(router._LOGGER, "warning", lambda *args, **kwargs: warnings.append(args))
    monkeypatch.setattr(
        router,
        "_PROVIDER_FACTORIES",
        {"grok": lambda: FailProvider("network timeout"), "runway": lambda: SuccessProvider("runway")},
    )

    for _ in range(3):
        try:
            router.generate_video("warn test", prefer="grok", fallback=False, max_retries=0)
        except RuntimeError:
            pass

    assert len(warnings) == 1
