from unittest.mock import patch, MagicMock
import pytest
from click.testing import CliRunner
from bottube.cli import main

def test_cli_login_success():
    mock_profile = {
        "agent_name": "test_agent",
        "display_name": "Test Agent",
        "bio": "I am a test bot",
        "is_ai": True,
        "video_count": 5,
        "total_views": 100,
        "rtc_balance": 10.5
    }

    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.whoami.return_value = mock_profile

        runner = CliRunner()
        # Mock click.prompt to return the API key
        with patch("click.prompt", return_value="test-api-key"):
            result = runner.invoke(main, ["login"])

            assert result.exit_code == 0
            assert "Login successful" in result.output
            assert "Authenticated as test_agent" in result.output

            # Verify client state was updated and whoami called for validation
            assert mock_client_instance.api_key == "test-api-key"
            mock_client_instance.whoami.assert_called_once()
            # Verify credentials were saved
            mock_client_instance._save_credentials.assert_called_once_with("test_agent", "test-api-key")

def test_cli_login_failure():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        # Mock whoami to raise an exception for invalid key
        from bottube.client import BoTTubeError
        mock_client_instance.whoami.side_effect = BoTTubeError("Invalid API key", status_code=401)

        runner = CliRunner()
        with patch("click.prompt", return_value="invalid-key"):
            result = runner.invoke(main, ["login"])

            assert result.exit_code != 0
            assert "Error: Invalid API key" in result.output
            mock_client_instance._save_credentials.assert_not_called()

def test_cli_whoami():
    mock_profile = {
        "agent_name": "test_agent",
        "display_name": "Test Agent",
        "bio": "I am a test bot",
        "is_ai": True,
        "video_count": 12,
        "total_views": 1234,
        "rtc_balance": 42.0,
        "comment_count": 5,
        "total_likes": 10
    }

    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.whoami.return_value = mock_profile

        runner = CliRunner()
        result = runner.invoke(main, ["--key", "valid-key", "whoami"])

        assert result.exit_code == 0
        assert "Test Agent" in result.output
        assert "@test_agent" in result.output
        assert "AI" in result.output
        assert "12" in result.output # videos
        assert "1234" in result.output # views
        assert "42.0" in result.output # RTC
        assert "I am a test bot" in result.output
