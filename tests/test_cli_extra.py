import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from bottube.cli import main
from pathlib import Path

def test_cli_profile_view():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.whoami.return_value = {
            "display_name": "Test Agent",
            "agent_name": "testagent",
            "bio": "Test bio"
        }

        runner = CliRunner()
        result = runner.invoke(main, ["profile"])
        assert result.exit_code == 0
        assert "Test Agent" in result.output
        assert "testagent" in result.output

def test_cli_profile_update():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.update_profile.return_value = {"updated_fields": ["bio"]}

        runner = CliRunner()
        result = runner.invoke(main, ["profile", "--bio", "New bio"])
        assert result.exit_code == 0
        assert "Profile updated!" in result.output
        assert "bio" in result.output
        mock_instance.update_profile.assert_called_once_with(bio="New bio")

def test_cli_avatar_upload(tmp_path):
    img = tmp_path / "avatar.png"
    img.write_text("fake data")

    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.upload_avatar.return_value = {"avatar_url": "http://test.com/av.png"}

        runner = CliRunner()
        result = runner.invoke(main, ["avatar", str(img)])
        assert result.exit_code == 0
        assert "Avatar uploaded successfuly!" in result.output
        assert "http://test.com/av.png" in result.output

def test_cli_delete_video():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.delete_video.return_value = {"title": "Deleted Video"}

        runner = CliRunner()
        # Mock confirmation prompt
        result = runner.invoke(main, ["delete", "v123"], input="y\n")
        assert result.exit_code == 0
        assert "Deleted: Deleted Video (v123)" in result.output
        mock_instance.delete_video.assert_called_once_with("v123")

def test_cli_categories():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.categories.return_value = {
            "categories": [{"name": "Music", "count": 10}, {"name": "Gaming", "count": 5}]
        }

        runner = CliRunner()
        result = runner.invoke(main, ["categories"])
        assert result.exit_code == 0
        assert "Music" in result.output
        assert "Gaming" in result.output
        assert "10" in result.output

def test_cli_recent_comments():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.recent_comments.return_value = {
            "comments": [{"agent_name": "a1", "video_id": "v1", "content": "Nice video"}]
        }

        runner = CliRunner()
        result = runner.invoke(main, ["recent-comments"])
        assert result.exit_code == 0
        assert "a1" in result.output
        assert "Nice video" in result.output

def test_cli_stats():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.stats.return_value = {
            "videos": 100,
            "agents": 50,
            "humans": 10,
            "total_views": 1000,
            "top_agents": [{"agent_name": "top1", "video_count": 20, "total_views": 500}]
        }

        runner = CliRunner()
        result = runner.invoke(main, ["stats"])
        assert result.exit_code == 0
        assert "BoTTube Platform Stats" in result.output
        assert "100" in result.output
        assert "top1" in result.output
