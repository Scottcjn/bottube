import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from bottube.cli import main

def test_cli_playlists_list():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.my_playlists.return_value = {
            "playlists": [{"playlist_id": "pl1", "title": "My List", "item_count": 5, "visibility": "public"}]
        }

        runner = CliRunner()
        result = runner.invoke(main, ["playlists", "list"])
        assert result.exit_code == 0
        assert "My List" in result.output
        assert "pl1" in result.output

def test_cli_playlists_create():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.create_playlist.return_value = {"playlist_id": "pl2"}

        runner = CliRunner()
        result = runner.invoke(main, ["playlists", "create", "New Playlist", "--visibility", "private"])
        assert result.exit_code == 0
        assert "Playlist created!" in result.output
        assert "pl2" in result.output
        mock_instance.create_playlist.assert_called_once_with("New Playlist", description="", visibility="private")

def test_cli_playlists_add():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value

        runner = CliRunner()
        result = runner.invoke(main, ["playlists", "add", "pl1", "v123"])
        assert result.exit_code == 0
        assert "Added!" in result.output
        mock_instance.add_to_playlist.assert_called_once_with("pl1", "v123")

def test_cli_webhooks_list():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.list_webhooks.return_value = {
            "webhooks": [{"id": 1, "url": "http://hook.com", "events": ["upload"]}]
        }

        runner = CliRunner()
        result = runner.invoke(main, ["webhooks", "list"])
        assert result.exit_code == 0
        assert "http://hook.com" in result.output
        assert "upload" in result.output

def test_cli_webhooks_create():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.create_webhook.return_value = {"id": 2}

        runner = CliRunner()
        result = runner.invoke(main, ["webhooks", "create", "http://new.com", "--events", "comment,like"])
        assert result.exit_code == 0
        assert "Webhook registered!" in result.output
        assert "2" in result.output
        mock_instance.create_webhook.assert_called_once_with("http://new.com", events=["comment", "like"])

def test_cli_tip_send():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.tip.return_value = {"amount": 1.5, "to": "creator"}

        runner = CliRunner()
        result = runner.invoke(main, ["tip", "send", "v123", "1.5", "-m", "Great!"])
        assert result.exit_code == 0
        assert "Tipped 1.5000 RTC" in result.output
        assert "@creator" in result.output

def test_cli_notifications_list():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.notifications.return_value = {
            "notifications": [{"type": "like", "message": "Someone liked", "read": False}],
            "unread_count": 1
        }

        runner = CliRunner()
        result = runner.invoke(main, ["notifications", "list"])
        assert result.exit_code == 0
        assert "Someone liked" in result.output
        assert "like" in result.output
