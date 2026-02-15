from unittest.mock import patch, MagicMock
import json
import pytest
from click.testing import CliRunner
from bottube.cli import main
from bottube import __version__

def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert f"bottube, version {__version__}" in result.output

def test_cli_health():
    # Mock the client.health() call
    mock_health = {"status": "ok", "version": "1.5.0"}

    with patch("bottube.cli.BoTTubeClient") as mock_client_class:
        mock_client_instance = mock_client_class.return_value
        mock_client_instance.health.return_value = mock_health

        runner = CliRunner()
        # We pass --url and --key to ensure they don't break anything
        result = runner.invoke(main, ["--url", "https://api.test", "--key", "test-key", "health"])

        assert result.exit_code == 0
        assert '"status": "ok"' in result.output
        assert '"version": "1.5.0"' in result.output

        # Verify the client was initialized with correct params
        mock_client_class.assert_called_once_with(
            base_url="https://api.test",
            api_key="test-key",
            verify_ssl=True
        )
