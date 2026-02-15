from unittest.mock import patch, MagicMock
import json
import pytest
from click.testing import CliRunner
from bottube.cli import main

@pytest.fixture
def mock_videos():
    return {
        "videos": [
            {
                "id": "vid123",
                "title": "First Video",
                "agent_name": "bot1",
                "views": 100,
                "likes": 10,
                "created_at": "2026-02-15T12:00:00Z"
            },
            {
                "id": "vid456",
                "title": "Second Video",
                "agent_name": "bot2",
                "views": 200,
                "likes": 20,
                "created_at": "2026-02-14T12:00:00Z"
            }
        ],
        "total": 2,
        "page": 1,
        "per_page": 20
    }

def test_cli_videos_table(mock_videos):
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.list_videos.return_value = mock_videos

        runner = CliRunner()
        result = runner.invoke(main, ["videos"])

        assert result.exit_code == 0
        assert "First Video" in result.output
        assert "vid123" in result.output
        assert "bot1" in result.output
        assert "100" in result.output
        assert "10" in result.output

        mock_client_instance.list_videos.assert_called_once_with(
            agent=None,
            category=None,
            per_page=20
        )

def test_cli_videos_json(mock_videos):
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.list_videos.return_value = mock_videos

        runner = CliRunner()
        result = runner.invoke(main, ["videos", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["videos"][0]["id"] == "vid123"

def test_cli_videos_options(mock_videos):
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.list_videos.return_value = mock_videos

        runner = CliRunner()
        result = runner.invoke(main, ["videos", "--agent", "testbot", "--category", "tech", "--limit", "5"])

        assert result.exit_code == 0
        mock_client_instance.list_videos.assert_called_once_with(
            agent="testbot",
            category="tech",
            per_page=5
        )

def test_cli_search(mock_videos):
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.search.return_value = mock_videos

        runner = CliRunner()
        result = runner.invoke(main, ["search", "query test"])

        assert result.exit_code == 0
        assert "First Video" in result.output
        mock_client_instance.search.assert_called_once_with(query="query test")

def test_cli_search_json(mock_videos):
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.search.return_value = mock_videos

        runner = CliRunner()
        result = runner.invoke(main, ["search", "test", "--json"])
        assert result.exit_code == 0
        assert '"id": "vid123"' in result.output

def test_cli_videos_error():
    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_instance = mock_client_class.return_value
        mock_instance.list_videos.side_effect = Exception("API Down")

        runner = CliRunner()
        result = runner.invoke(main, ["videos"])
        assert result.exit_code != 0
        assert "Unexpected error: API Down" in result.output
