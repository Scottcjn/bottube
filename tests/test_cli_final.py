import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from bottube.cli import main

def test_cli_unvote():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        runner = CliRunner()
        result = runner.invoke(main, ["unvote", "v123"])
        assert result.exit_code == 0
        assert "Vote removed" in result.output
        mock_instance.unvote.assert_called_once_with("v123")

def test_cli_agent_subscribers():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.subscribers.return_value = {
            "subscribers": [{"agent_name": "sub1", "display_name": "Subscriber One"}]
        }
        runner = CliRunner()
        result = runner.invoke(main, ["agent", "subscribers", "testbot"])
        assert result.exit_code == 0
        assert "sub1" in result.output
        mock_instance.subscribers.assert_called_once_with("testbot")

def test_cli_wallet_group():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_wallet.return_value = {"rtc_balance": 1.0, "wallets": {}}
        mock_instance.update_wallet.return_value = {"updated_fields": ["rtc"]}

        runner = CliRunner()
        # Test show
        res_show = runner.invoke(main, ["wallet", "show"])
        assert res_show.exit_code == 0
        assert "1.000000 RTC" in res_show.output

        # Test update
        res_upd = runner.invoke(main, ["wallet", "update", "--rtc", "new_addr"])
        assert res_upd.exit_code == 0
        assert "Wallet updated!" in res_upd.output
        mock_instance.update_wallet.assert_called_once_with(rtc="new_addr")

def test_cli_crosspost():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.crosspost_x.return_value = {"tweet_url": "http://x.com/123"}

        runner = CliRunner()
        result = runner.invoke(main, ["crosspost", "x", "v123", "--text", "Check this out"])
        assert result.exit_code == 0
        assert "Posted to X!" in result.output
        mock_instance.crosspost_x.assert_called_once_with("v123", text="Check this out")

def test_cli_playlists_extended():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_playlist.return_value = {"title": "Test PL", "videos": []}

        runner = CliRunner()
        # Test show
        res_show = runner.invoke(main, ["playlists", "show", "pl1"])
        assert res_show.exit_code == 0
        assert "Playlist: Test PL" in res_show.output

        # Test delete
        res_del = runner.invoke(main, ["playlists", "delete", "pl1"], input="y\n")
        assert res_del.exit_code == 0
        assert "Playlist deleted" in res_del.output
        mock_instance.delete_playlist.assert_called_once_with("pl1")

def test_cli_webhooks_test():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        runner = CliRunner()
        result = runner.invoke(main, ["webhooks", "test", "1"])
        assert result.exit_code == 0
        assert "Test event sent" in result.output
        mock_instance.test_webhook.assert_called_once_with(1)

def test_cli_comment_voting():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        runner = CliRunner()
        result = runner.invoke(main, ["comments", "like", "456"])
        assert result.exit_code == 0
        assert "Liked comment #456" in result.output
        mock_instance.like_comment.assert_called_once_with(456)

def test_cli_verify_x():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        runner = CliRunner()
        result = runner.invoke(main, ["verify-x", "testuser"])
        assert result.exit_code == 0
        assert "@testuser verified" in result.output
        mock_instance.verify_x_claim.assert_called_once_with("testuser")

def test_cli_watch():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.watch.return_value = {"title": "Test Video", "views": 10}
        runner = CliRunner()
        result = runner.invoke(main, ["watch", "v123"])
        assert result.exit_code == 0
        assert "Watched!" in result.output
        assert "Test Video" in result.output
        mock_instance.watch.assert_called_once_with("v123")

def test_cli_screenshot():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.screenshot_watch.return_value = "/tmp/shot.png"
        runner = CliRunner()
        result = runner.invoke(main, ["screenshot", "v123", "--output", "out.png"])
        assert result.exit_code == 0
        assert "Screenshot saved!" in result.output
        assert "out.png" in result.output or "/tmp/shot.png" in result.output
        mock_instance.screenshot_watch.assert_called_once_with("v123", output_path="out.png")
