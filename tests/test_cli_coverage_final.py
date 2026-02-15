import pytest
import runpy
import sys
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from bottube.cli import main
from bottube.client import BoTTubeError

# 覆盖 232-233: agent info 中的 BoTTubeError
def test_coverage_line_232_233():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_agent.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["agent", "info", "bot"])
        assert result.exit_code != 0
        assert "Error" in result.output

# 覆盖 253: agent stats 中的非 401 BoTTubeError
def test_coverage_line_253():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.whoami.side_effect = BoTTubeError("Error", status_code=500)
        runner = CliRunner()
        result = runner.invoke(main, ["agent", "stats"])
        assert result.exit_code != 0
        assert "Error" in result.output

# 覆盖 292-293: subscriptions 为空
def test_coverage_line_292_293():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.subscriptions.return_value = {"subscriptions": []}
        runner = CliRunner()
        result = runner.invoke(main, ["subscriptions"])
        assert "You are not following anyone yet" in result.output

# 覆盖 318: feed --json
def test_coverage_line_318():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_feed.return_value = {"videos": []}
        runner = CliRunner()
        result = runner.invoke(main, ["feed", "--json"])
        assert result.exit_code == 0

# 覆盖 443-444: categories 为空
def test_coverage_line_443_444():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.categories.return_value = {"categories": []}
        runner = CliRunner()
        result = runner.invoke(main, ["categories"])
        assert "No categories found" in result.output

# 覆盖 467-468: recent-comments 为空
def test_coverage_line_467_468():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.recent_comments.return_value = {"comments": []}
        runner = CliRunner()
        result = runner.invoke(main, ["recent-comments"])
        assert "No recent comments" in result.output

# 覆盖 511-512: tip list 为空
def test_coverage_line_511_512():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_tips.return_value = {"tips": []}
        runner = CliRunner()
        result = runner.invoke(main, ["tip", "list", "v1"])
        assert "No tips on this video yet" in result.output

# 覆盖 537-538: tip leaderboard 为空
def test_coverage_line_537_538():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.tip_leaderboard.return_value = {"leaderboard": []}
        runner = CliRunner()
        result = runner.invoke(main, ["tip", "leaderboard"])
        assert "Leaderboard is empty" in result.output

# 覆盖 601-602: playlists list 为空
def test_coverage_line_601_602():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.my_playlists.return_value = {"playlists": []}
        runner = CliRunner()
        result = runner.invoke(main, ["playlists", "list"])
        assert "No playlists found" in result.output

# 覆盖 664-665: webhooks list 为空
def test_coverage_line_664_665():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.list_webhooks.return_value = {"webhooks": []}
        runner = CliRunner()
        result = runner.invoke(main, ["webhooks", "list"])
        assert "No webhooks registered" in result.output

# 覆盖 728-729: agent subscribers 为空
def test_coverage_line_728_729():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.whoami.return_value = {"agent_name": "bot"}
        mock_instance.subscribers.return_value = {"subscribers": []}
        runner = CliRunner()
        result = runner.invoke(main, ["agent", "subscribers"])
        assert "has no subscribers yet" in result.output

# 覆盖 801: crosspost moltbook 成功输出
def test_coverage_line_801():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        runner = CliRunner()
        result = runner.invoke(main, ["crosspost", "moltbook", "v1"])
        assert "Posted to Moltbook!" in result.output

# 覆盖 854: playlists delete 取消确认
def test_coverage_line_854():
    runner = CliRunner()
    result = runner.invoke(main, ["playlists", "delete", "pl1"], input="n\n")
    assert result.exit_code == 0

# 覆盖 911: comments dislike 成功输出
def test_coverage_line_911():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        runner = CliRunner()
        result = runner.invoke(main, ["comments", "dislike", "123"])
        assert "Disliked comment #123" in result.output

# 覆盖 1054: upload 进度条回调
def test_coverage_line_1054(tmp_path):
    video = tmp_path / "test.mp4"
    video.write_text("content")
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        def mock_upload(**kwargs):
            if 'callback' in kwargs:
                kwargs['callback'](1024)
            return {"video_id": "v1", "watch_url": "url"}
        mock_instance.upload.side_effect = mock_upload
        runner = CliRunner()
        result = runner.invoke(main, ["upload", str(video)])
        assert result.exit_code == 0
