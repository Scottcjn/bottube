import pytest
import runpy
import sys
import json
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from bottube.cli import main
from bottube.client import BoTTubeError

def test_cli_main_entry_point():
    """Cover the 'if __name__ == "__main__": main()' block."""
    with patch.object(sys, 'argv', ['bottube', '--version']):
        try:
            # We use run_name="__main__" to trigger the block
            runpy.run_path("/Users/zhaohaodong/.bounty-hunter/tasks/Scottcjn_bottube_119/repo/bottube/cli.py", run_name="__main__")
        except SystemExit:
            pass

# --- Error Handling & Exceptions ---

def test_cli_whoami_unexpected_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.whoami.side_effect = Exception("Fatal crash")
        runner = CliRunner()
        result = runner.invoke(main, ["whoami"])
        assert result.exit_code != 0
        assert "Unexpected error: Fatal crash" in result.output

def test_cli_register_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.register.side_effect = BoTTubeError("Conflict")
        runner = CliRunner()
        result = runner.invoke(main, ["register", "bot"])
        assert result.exit_code != 0
        assert "Error: Conflict" in result.output

def test_cli_describe_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.describe.side_effect = BoTTubeError("Not Found")
        runner = CliRunner()
        result = runner.invoke(main, ["describe", "v1"])
        assert result.exit_code != 0
        assert "Error: Not Found" in result.output

def test_cli_trending_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.trending.side_effect = BoTTubeError("Server error")
        runner = CliRunner()
        result = runner.invoke(main, ["trending"])
        assert result.exit_code != 0
        assert "Error: Server error" in result.output

def test_cli_comment_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.comment.side_effect = BoTTubeError("Forbidden")
        runner = CliRunner()
        result = runner.invoke(main, ["comment", "v1", "text"])
        assert result.exit_code != 0

def test_cli_like_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.like.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["like", "v1"])
        assert result.exit_code != 0

def test_cli_dislike_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.dislike.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["dislike", "v1"])
        assert result.exit_code != 0

def test_cli_earnings_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_earnings.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["earnings"])
        assert result.exit_code != 0

def test_cli_agent_info_unexpected_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.whoami.side_effect = Exception("Crash")
        runner = CliRunner()
        result = runner.invoke(main, ["agent", "info"])
        assert result.exit_code != 0

def test_cli_agent_stats_unexpected_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.whoami.side_effect = Exception("Crash")
        runner = CliRunner()
        result = runner.invoke(main, ["agent", "stats"])
        assert result.exit_code != 0

def test_cli_subscribe_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.subscribe.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["subscribe", "a"])
        assert result.exit_code != 0

def test_cli_unsubscribe_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.unsubscribe.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["unsubscribe", "a"])
        assert result.exit_code != 0

def test_cli_subscriptions_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.subscriptions.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["subscriptions"])
        assert result.exit_code != 0

def test_cli_feed_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_feed.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["feed"])
        assert result.exit_code != 0

def test_cli_notifications_list_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.notifications.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["notifications", "list"])
        assert result.exit_code != 0

def test_cli_notifications_count_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.notification_count.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["notifications", "count"])
        assert result.exit_code != 0

def test_cli_notifications_read_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.mark_notifications_read.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["notifications", "read"])
        assert result.exit_code != 0

def test_cli_profile_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.update_profile.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["profile", "--bio", "x"])
        assert result.exit_code != 0

def test_cli_avatar_bottube_error(tmp_path):
    f = tmp_path / "i.png"
    f.write_text("...")
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.upload_avatar.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["avatar", str(f)])
        assert result.exit_code != 0

def test_cli_delete_cancel():
    runner = CliRunner()
    result = runner.invoke(main, ["delete", "v1"], input="n\n")
    assert result.exit_code == 0

def test_cli_delete_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.delete_video.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["delete", "v1"], input="y\n")
        assert result.exit_code != 0

def test_cli_categories_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.categories.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["categories"])
        assert result.exit_code != 0

def test_cli_recent_comments_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.recent_comments.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["recent-comments"])
        assert result.exit_code != 0

def test_cli_tip_send_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.tip.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["tip", "send", "v1", "1.0"])
        assert result.exit_code != 0

def test_cli_tip_list_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_tips.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["tip", "list", "v1"])
        assert result.exit_code != 0

def test_cli_tip_leaderboard_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.tip_leaderboard.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["tip", "leaderboard"])
        assert result.exit_code != 0

def test_cli_stats_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.stats.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["stats"])
        assert result.exit_code != 0

def test_cli_playlists_list_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.my_playlists.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["playlists", "list"])
        assert result.exit_code != 0

def test_cli_playlists_create_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.create_playlist.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["playlists", "create", "t"])
        assert result.exit_code != 0

def test_cli_playlists_add_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.add_to_playlist.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["playlists", "add", "pl", "v"])
        assert result.exit_code != 0

def test_cli_webhooks_list_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.list_webhooks.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["webhooks", "list"])
        assert result.exit_code != 0

def test_cli_webhooks_create_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.create_webhook.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["webhooks", "create", "url"])
        assert result.exit_code != 0

def test_cli_webhooks_delete_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.delete_webhook.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["webhooks", "delete", "1"])
        assert result.exit_code != 0

def test_cli_unvote_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.unvote.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["unvote", "v1"])
        assert result.exit_code != 0

def test_cli_agent_subscribers_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.whoami.return_value = {"agent_name": "a"}
        mock_instance.subscribers.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["agent", "subscribers"])
        assert result.exit_code != 0

def test_cli_wallet_show_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_wallet.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["wallet", "show"])
        assert result.exit_code != 0

def test_cli_wallet_update_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.update_wallet.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["wallet", "update", "--rtc", "addr"])
        assert result.exit_code != 0

def test_cli_crosspost_moltbook_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.crosspost_moltbook.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["crosspost", "moltbook", "v1"])
        assert result.exit_code != 0

def test_cli_crosspost_x_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.crosspost_x.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["crosspost", "x", "v1"])
        assert result.exit_code != 0

def test_cli_playlists_show_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_playlist.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["playlists", "show", "pl"])
        assert result.exit_code != 0

def test_cli_playlists_update_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.update_playlist.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["playlists", "update", "pl", "--title", "t"])
        assert result.exit_code != 0

def test_cli_playlists_delete_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.delete_playlist.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["playlists", "delete", "pl"], input="y\n")
        assert result.exit_code != 0

def test_cli_playlists_remove_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.remove_from_playlist.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["playlists", "remove", "pl", "v"])
        assert result.exit_code != 0

def test_cli_webhooks_test_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.test_webhook.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["webhooks", "test", "1"])
        assert result.exit_code != 0

def test_cli_comment_like_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.like_comment.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["comments", "like", "1"])
        assert result.exit_code != 0

def test_cli_comment_dislike_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.dislike_comment.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["comments", "dislike", "1"])
        assert result.exit_code != 0

def test_cli_verify_x_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.verify_x_claim.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["verify-x", "user"])
        assert result.exit_code != 0

def test_cli_upload_bottube_error(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_text("...")
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.upload.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["upload", str(f)])
        assert result.exit_code != 0

def test_cli_upload_unexpected_error(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_text("...")
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.upload.side_effect = Exception("Crash")
        runner = CliRunner()
        result = runner.invoke(main, ["upload", str(f)])
        assert result.exit_code != 0

def test_cli_videos_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.list_videos.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["videos"])
        assert result.exit_code != 0

def test_cli_videos_unexpected_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.list_videos.side_effect = Exception("Crash")
        runner = CliRunner()
        result = runner.invoke(main, ["videos"])
        assert result.exit_code != 0

def test_cli_search_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.search.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["search", "q"])
        assert result.exit_code != 0

def test_cli_search_unexpected_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.search.side_effect = Exception("Crash")
        runner = CliRunner()
        result = runner.invoke(main, ["search", "q"])
        assert result.exit_code != 0

def test_cli_watch_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.watch.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["watch", "v1"])
        assert result.exit_code != 0

def test_cli_screenshot_bottube_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.screenshot_watch.side_effect = BoTTubeError("Error")
        runner = CliRunner()
        result = runner.invoke(main, ["screenshot", "v1"])
        assert result.exit_code != 0

def test_cli_screenshot_unexpected_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.screenshot_watch.side_effect = Exception("Crash")
        runner = CliRunner()
        result = runner.invoke(main, ["screenshot", "v1"])
        assert result.exit_code != 0

# --- Specific Output Branch Coverage ---

def test_cli_dislike_output_coverage():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.dislike.return_value = {"likes": 10}
        runner = CliRunner()
        result = runner.invoke(main, ["dislike", "v1"])
        assert "Disliked." in result.output
        assert "10" in result.output

def test_cli_subscribe_output_coverage():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.subscribe.return_value = {"follower_count": 5}
        runner = CliRunner()
        result = runner.invoke(main, ["subscribe", "bot"])
        assert "Followed!" in result.output
        assert "5" in result.output

def test_cli_feed_table_coverage():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.get_feed.return_value = {
            "videos": [{"id": "v1", "title": "T", "agent_name": "a", "views": 1, "likes": 1, "created_at": "2026-01-01"}],
            "total": 1, "page": 1, "per_page": 20
        }
        runner = CliRunner()
        result = runner.invoke(main, ["feed"])
        assert "Your Feed" in result.output
        assert "v1" in result.output

def test_cli_delete_success_coverage():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.delete_video.return_value = {"title": "Del"}
        runner = CliRunner()
        result = runner.invoke(main, ["delete", "v1"], input="y\n")
        assert "Deleted: Del (v1)" in result.output

def test_cli_wallet_update_no_args():
    runner = CliRunner()
    result = runner.invoke(main, ["wallet", "update"])
    assert "Provide at least one address" in result.output

def test_cli_upload_success_coverage(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_text("...")
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.upload.return_value = {"video_id": "vid", "watch_url": "url"}
        runner = CliRunner()
        result = runner.invoke(main, ["upload", str(f)])
        assert "Upload successful!" in result.output
        assert "vid" in result.output

def test_cli_videos_table_coverage():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.list_videos.return_value = {
            "videos": [{"id": "v1", "title": "T", "agent_name": "a", "views": 1, "likes": 1, "created_at": "2026-01-01"}],
            "total": 1, "page": 1, "per_page": 20
        }
        runner = CliRunner()
        result = runner.invoke(main, ["videos"])
        assert "Videos" in result.output
        assert "v1" in result.output

def test_cli_webhooks_delete_success_coverage():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        runner = CliRunner()
        result = runner.invoke(main, ["webhooks", "delete", "123"])
        assert "Webhook #123 removed" in result.output

def test_cli_notifications_list_empty_coverage():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.notifications.return_value = {"notifications": [], "unread_count": 0}
        runner = CliRunner()
        result = runner.invoke(main, ["notifications", "list"])
        assert "No notifications." in result.output
