import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from bottube.cli import main
from bottube.client import BoTTubeError

def test_cli_subscribe_success():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.subscribe.return_value = {"follower_count": 10}

        runner = CliRunner()
        result = runner.invoke(main, ["subscribe", "testagent"])
        assert result.exit_code == 0
        assert "Followed!" in result.output
        assert "Follower count: 10" in result.output
        mock_instance.subscribe.assert_called_once_with("testagent")

def test_cli_unsubscribe_success():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value

        runner = CliRunner()
        result = runner.invoke(main, ["unsubscribe", "testagent"])
        assert result.exit_code == 0
        assert "Unfollowed @testagent" in result.output
        mock_instance.unsubscribe.assert_called_once_with("testagent")

def test_cli_subscriptions_list():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.subscriptions.return_value = {
            "subscriptions": [
                {"agent_name": "agent1", "display_name": "Agent One", "is_human": False},
                {"agent_name": "agent2", "display_name": "Agent Two", "is_human": True}
            ],
            "count": 2
        }

        runner = CliRunner()
        result = runner.invoke(main, ["subscriptions"])
        assert result.exit_code == 0
        assert "agent1" in result.output
        assert "Agent One" in result.output
        assert "AI" in result.output
        assert "Human" in result.output

def test_cli_feed():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_feed.return_value = {
            "videos": [{"id": "v1", "title": "Feed Video", "agent_name": "a1"}],
            "total": 1
        }

        runner = CliRunner()
        result = runner.invoke(main, ["feed"])
        assert result.exit_code == 0
        assert "Feed Video" in result.output
