from unittest.mock import patch, MagicMock
import os
import pytest
from click.testing import CliRunner
from bottube.cli import main

@pytest.fixture
def temp_video(tmp_path):
    v = tmp_path / "test_video.mp4"
    v.write_bytes(b"fake video content")
    return str(v)

def test_upload_dry_run(temp_video):
    runner = CliRunner()
    # Mocking BoTTubeClient to ensure it's not actually called
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        result = runner.invoke(main, ["upload", temp_video, "--title", "Test Title", "--dry-run"])

        assert result.exit_code == 0
        assert "Dry Run Summary" in result.output
        assert "Test Title" in result.output
        # Path might be truncated by rich, so we check for the prefix or just skip the exact path match
        assert "File:" in result.output

        # Verify client.upload was NOT called
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.upload.assert_not_called()

def test_upload_file_not_found():
    runner = CliRunner()
    result = runner.invoke(main, ["upload", "non_existent_file.mp4"])
    assert result.exit_code != 0
    assert "Error" in result.output
    assert "does not exist" in result.output

def test_upload_too_large(tmp_path):
    v = tmp_path / "large_video.mp4"
    # 501 MB
    with open(v, "wb") as f:
        f.seek(501 * 1024 * 1024)
        f.write(b"\0")

    runner = CliRunner()
    result = runner.invoke(main, ["upload", str(v)])
    assert result.exit_code != 0
    assert "Error" in result.output
    assert "exceeds 500MB" in result.output

@patch("bottube.cli.Progress")
def test_upload_success(mock_progress, temp_video):
    runner = CliRunner()
    mock_upload_response = {"video_id": "v123", "watch_url": "https://bottube.ai/watch/v123"}

    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.upload.return_value = mock_upload_response

        result = runner.invoke(main, ["upload", temp_video, "--title", "Real Upload"])

        assert result.exit_code == 0
        assert "Upload successful" in result.output
        assert "v123" in result.output

        # Verify client.upload was called with correct arguments
        mock_client_instance.upload.assert_called_once()
        args, kwargs = mock_client_instance.upload.call_args
        assert kwargs["video_path"] == temp_video
        assert kwargs["title"] == "Real Upload"

        # Verify progress bar was used
        mock_progress.assert_called()

def test_upload_dry_run_with_thumbnail(temp_video, tmp_path):
    thumb = tmp_path / "thumb.png"
    thumb.write_text("fake thumb")
    runner = CliRunner()
    result = runner.invoke(main, ["upload", temp_video, "--thumbnail", str(thumb), "--dry-run"])
    assert result.exit_code == 0
    assert "Thumbnail:" in result.output

def test_upload_bottube_error(temp_video):
    from bottube.client import BoTTubeError
    runner = CliRunner()
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.upload.side_effect = BoTTubeError("Upload failed", status_code=500)
        result = runner.invoke(main, ["upload", temp_video])
        assert result.exit_code != 0
        assert "Error: Upload failed" in result.output

def test_upload_unexpected_error(temp_video):
    runner = CliRunner()
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.upload.side_effect = RuntimeError("Crash")
        result = runner.invoke(main, ["upload", temp_video])
        assert result.exit_code != 0
        assert "Unexpected error: Crash" in result.output
