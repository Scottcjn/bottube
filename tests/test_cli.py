import json
import sys

import pytest


def run_cli(monkeypatch, capsys, args, fake_client=None):
    from bottube import cli as bottube_cli

    if fake_client is not None:
        monkeypatch.setattr(bottube_cli, "BoTTubeClient", lambda **kwargs: fake_client)

    monkeypatch.setattr(sys, "argv", ["bottube"] + args)
    bottube_cli.main()
    captured = capsys.readouterr()
    return captured.out.strip()


class FakeClient:
    def __init__(self):
        self._health = {"ok": True}

    def health(self):
        return self._health

    def list_videos(self, **kwargs):
        return {
            "total": 1,
            "videos": [
                {
                    "video_id": "v1",
                    "title": "Hello",
                    "agent_name": "alice",
                    "views": 1,
                    "likes": 2,
                }
            ],
        }

    def upload(self, *a, **k):
        return {"uploaded": True}


def test_health_json(monkeypatch, capsys):
    fake = FakeClient()
    s = run_cli(monkeypatch, capsys, ["--json", "health"], fake_client=fake)
    obj = json.loads(s)
    assert obj["ok"] is True


def test_videos_human(monkeypatch, capsys):
    fake = FakeClient()
    s = run_cli(monkeypatch, capsys, ["videos"], fake_client=fake)
    assert "[v1]" in s
    assert "@alice" in s


@pytest.mark.integration
def test_live_api_health():
    """Optional live integration test against bottube.ai.

    Enable by setting BOTTUBE_RUN_LIVE_TESTS=1.
    """
    import os

    if os.environ.get("BOTTUBE_RUN_LIVE_TESTS") != "1":
        pytest.skip("set BOTTUBE_RUN_LIVE_TESTS=1 to run")

    from bottube.client import BoTTubeClient

    c = BoTTubeClient(base_url="https://bottube.ai", api_key="", verify_ssl=True)
    r = c.health()
    assert r.get("ok") is True
