# SPDX-License-Identifier: MIT
import sys
import time
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syndication_poller import SyndicationPoller, VideoInfo


def _write_config(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def test_queue_new_videos_applies_agent_platform_overrides(tmp_path):
    config_path = tmp_path / "syndication.yaml"
    _write_config(
        config_path,
        """
platforms:
  moltbook:
    enabled: true
    priority: 10
  twitter:
    enabled: true
    priority: 5
agents:
  quiet-bot:
    jitter_seconds: 7
    platforms:
      twitter:
        enabled: false
      moltbook:
        priority: 25
schedule:
  enabled: false
""",
    )

    poller = SyndicationPoller(
        api_key="test-key",
        db_path=str(tmp_path / "bottube.db"),
        config_file=str(config_path),
    )

    queued = poller.queue_new_videos(
        [
            VideoInfo(
                video_id="vid1",
                title="Hello",
                agent_id=7,
                agent_name="quiet-bot",
                created_at=time.time(),
            )
        ]
    )

    items = poller.queue.get_items_by_video("vid1")
    assert queued == 1
    assert len(items) == 1
    assert items[0].target_platform == "moltbook"
    assert items[0].priority == 45
    assert items[0].metadata["platform_priority"] == 25
    assert poller._get_jitter_seconds(agent_name="quiet-bot", agent_id=7) == 7


def test_process_pending_items_completes_dequeued_item_without_re_marking_processing(tmp_path):
    config_path = tmp_path / "syndication.yaml"
    _write_config(
        config_path,
        """
platforms:
  moltbook:
    enabled: true
    priority: 10
schedule:
  enabled: false
""",
    )

    poller = SyndicationPoller(
        api_key="test-key",
        db_path=str(tmp_path / "bottube.db"),
        config_file=str(config_path),
    )
    item = poller.queue.enqueue(
        video_id="vid2",
        video_title="World",
        agent_id=9,
        agent_name="builder-bot",
        target_platform="moltbook",
    )

    with patch.object(
        poller,
        "_syndicate_to_moltbook",
        return_value={"success": True, "platform": "moltbook", "external_id": "abc"},
    ):
        processed = poller.process_pending_items()

    updated = poller.queue.get_item(item.id)
    assert processed == 1
    assert updated is not None
    assert updated.state.value == "completed"


def test_reload_runtime_config_rebuilds_adapters_and_updates_poll_interval(tmp_path):
    config_path = tmp_path / "syndication.yaml"
    _write_config(
        config_path,
        """
poll_interval: 60
platforms:
  moltbook:
    enabled: true
    base_url: https://moltbook.example
    api_key: alpha
schedule:
  enabled: false
""",
    )

    poller = SyndicationPoller(
        api_key="test-key",
        db_path=str(tmp_path / "bottube.db"),
        config_file=str(config_path),
    )

    assert poller.config.poll_interval == 60
    assert "moltbook" in poller.adapters
    assert poller.adapters["moltbook"].api_key == "alpha"

    _write_config(
        config_path,
        """
poll_interval: 120
platforms:
  moltbook:
    enabled: true
    base_url: https://moltbook.example
    api_key: beta
schedule:
  enabled: false
""",
    )
    poller.config_manager._file_mtime = 0

    assert poller.reload_runtime_config() is True
    assert poller.config.poll_interval == 120
    assert poller.adapters["moltbook"].api_key == "beta"


def test_poll_watermark_does_not_skip_videos_created_during_fetch(tmp_path):
    """The next `since` watermark must be captured before the feed request."""
    config_path = tmp_path / "syndication.yaml"
    _write_config(
        config_path,
        """
poll_interval: 1
platforms: {}
schedule:
  enabled: false
""",
    )
    poller = SyndicationPoller(
        api_key="test-key",
        db_path=str(tmp_path / "bottube.db"),
        config_file=str(config_path),
    )

    class Clock:
        value = 100.0

        @classmethod
        def time(cls):
            return cls.value

    def fetch_during_upload_window(*, since):
        assert since is None
        Clock.value = 200.0
        return []

    def stop_after_first_cycle(_seconds):
        poller.running = False

    with (
        patch("syndication_poller.time.time", side_effect=Clock.time),
        patch("syndication_poller.time.sleep", side_effect=stop_after_first_cycle),
        patch("syndication_poller.random.random", return_value=1.0),
        patch.object(poller, "_load_known_videos"),
        patch.object(poller, "fetch_new_videos", side_effect=fetch_during_upload_window),
        patch.object(poller, "process_pending_items", return_value=0),
    ):
        poller.run()

    assert poller.last_poll_time == 100.0
