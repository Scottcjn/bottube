# SPDX-License-Identifier: MIT
from pathlib import Path

from providers.base import GeneratedVideo
from providers import router


class FailProvider:
    def generate(self, prompt: str, duration: int = 8, **kwargs):
        raise RuntimeError("forced failure")


class SuccessProvider:
    def __init__(self, name: str = "runway"):
        self.name = name

    def generate(self, prompt: str, duration: int = 8, **kwargs):
        return GeneratedVideo(provider=self.name, output_path=Path("/tmp/video.mp4"), metadata={})


def test_choose_provider_runway_keywords():
    assert router.choose_provider("cinematic photoreal reveal", prefer="auto") == "runway"


def test_choose_provider_default_grok():
    assert router.choose_provider("retro computer in a lab", prefer="auto") == "grok"


def test_choose_provider_explicit_preference():
    assert router.choose_provider("anything", prefer="runway") == "runway"


def test_generate_video_fallback(monkeypatch):
    monkeypatch.setattr(
        router,
        "_PROVIDER_FACTORIES",
        {
            "grok": FailProvider,
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


def test_generate_video_without_fallback_raises(monkeypatch):
    monkeypatch.setattr(router, "_PROVIDER_FACTORIES", {"grok": FailProvider, "runway": FailProvider})

    try:
        router.generate_video("test", prefer="grok", fallback=False)
        assert False, "Expected RuntimeError"
    except RuntimeError as exc:
        assert "All provider attempts failed" in str(exc)
