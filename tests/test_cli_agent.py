from unittest.mock import patch, MagicMock
import pytest
from click.testing import CliRunner
from bottube.cli import main

def test_agent_info_self():
    mock_profile = {
        "agent_name": "test_agent",
        "display_name": "Test Agent",
        "bio": "I am a test agent",
        "is_ai": True,
        "video_count": 5,
        "total_views": 100,
        "total_likes": 50,
        "comment_count": 10,
        "rtc_balance": 123.4567,
        "metadata": {"version": "1.0", "engine": "gpt-4"}
    }

    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.whoami.return_value = mock_profile

        runner = CliRunner()
        result = runner.invoke(main, ["agent", "info"])

        assert result.exit_code == 0
        assert "Agent Profile: Test Agent" in result.output
        assert "@test_agent" in result.output
        assert "AI Agent" in result.output
        assert "I am a test agent" in result.output
        assert "version" in result.output
        assert "1.0" in result.output
        assert "engine" in result.output
        assert "gpt-4" in result.output

def test_agent_info_specific():
    mock_profile = {
        "agent_name": "other_agent",
        "display_name": "Other Agent",
        "bio": "I am another agent",
        "is_ai": False,
        "video_count": 2,
        "total_views": 20,
        "total_likes": 5,
        "comment_count": 1,
        "rtc_balance": 0.0,
    }

    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.get_agent.return_value = mock_profile

        runner = CliRunner()
        result = runner.invoke(main, ["agent", "info", "other_agent"])

        assert result.exit_code == 0
        assert "Agent Profile: Other Agent" in result.output
        assert "@other_agent" in result.output
        assert "Human" in result.output
        mock_client_instance.get_agent.assert_called_once_with("other_agent")

def test_agent_stats():
    mock_profile = {
        "agent_name": "test_agent",
        "display_name": "Test Agent",
        "video_count": 5,
        "total_views": 100,
        "total_likes": 50,
        "comment_count": 10,
        "rtc_balance": 123.4567,
    }

    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.whoami.return_value = mock_profile

        runner = CliRunner()
        result = runner.invoke(main, ["agent", "stats"])

        assert result.exit_code == 0
        assert "Statistics" in result.output
        assert "5" in result.output  # video_count
        assert "100" in result.output # total_views
        assert "50" in result.output  # total_likes
        assert "10" in result.output  # comment_count
        assert "123.4567 RTC" in result.output

def test_agent_info_json():
    mock_profile = {"agent_name": "test_agent", "display_name": "Test Agent"}

    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.whoami.return_value = mock_profile

        runner = CliRunner()
        result = runner.invoke(main, ["agent", "info", "--json"])

        assert result.exit_code == 0
        assert '"agent_name": "test_agent"' in result.output
