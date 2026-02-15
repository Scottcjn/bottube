import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from bottube.cli import main

def test_cli_register_success():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.register.return_value = "new-api-key"

        runner = CliRunner()
        result = runner.invoke(main, ["register", "new-bot", "--display-name", "New Bot"])
        assert result.exit_code == 0
        assert "Registered!" in result.output
        assert "new-api-key" in result.output
        mock_instance.register.assert_called_once_with("new-bot", display_name="New Bot", bio="")

def test_cli_describe_video():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.describe.return_value = {
            "title": "Cool Video",
            "agent_name": "tester",
            "description": "desc",
            "scene_description": "scene",
            "comments": [{"agent": "bot1", "text": "nice"}],
            "comment_count": 1
        }

        runner = CliRunner()
        result = runner.invoke(main, ["describe", "v123"])
        assert result.exit_code == 0
        assert "Cool Video" in result.output
        assert "@tester" in result.output
        assert "nice" in result.output

def test_cli_trending():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.trending.return_value = {
            "videos": [{"id": "v1", "title": "Trending Now", "agent_name": "topbot"}]
        }

        runner = CliRunner()
        result = runner.invoke(main, ["trending"])
        assert result.exit_code == 0
        assert "Trending Now" in result.output

def test_cli_comment():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value

        runner = CliRunner()
        result = runner.invoke(main, ["comment", "v123", "Nice work!"])
        assert result.exit_code == 0
        assert "Comment posted on v123" in result.output
        mock_instance.comment.assert_called_once_with("v123", "Nice work!")

def test_cli_like_video():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.like.return_value = {"likes": 42}

        runner = CliRunner()
        result = runner.invoke(main, ["like", "v123"])
        assert result.exit_code == 0
        assert "Liked!" in result.output
        assert "42" in result.output

def test_cli_wallet_view():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_wallet.return_value = {
            "rtc_balance": 100.5,
            "wallets": {"rtc": "addr1", "sol": "addr2"}
        }

        runner = CliRunner()
        result = runner.invoke(main, ["wallet"])
        assert result.exit_code == 0
        assert "100.500000 RTC" in result.output
        assert "RTC" in result.output
        assert "addr1" in result.output

def test_cli_earnings_list():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_earnings.return_value = {
            "rtc_balance": 50.0,
            "earnings": [{"amount": 5.0, "reason": "view reward", "video_id": "v1"}]
        }

        runner = CliRunner()
        result = runner.invoke(main, ["earnings"])
        assert result.exit_code == 0
        assert "50.000000 RTC" in result.output
        assert "view reward" in result.output
