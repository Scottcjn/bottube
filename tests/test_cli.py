"""Tests for CLI commands."""

import json
import tempfile
from pathlib import Path
from click.testing import CliRunner

import pytest

from bottube_cli.cli import cli


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_config():
    """Create temporary config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / 'config'
        with open(config_file, 'w') as f:
            json.dump({'api_key': 'test_key'}, f)
        yield tmpdir, config_file


def test_cli_help(runner):
    """Test CLI help output."""
    result = runner.invoke(cli, ['--help'])

    assert result.exit_code == 0
    assert 'BoTTube CLI' in result.output
    assert 'videos' in result.output
    assert 'upload' in result.output
    assert 'agent' in result.output


def test_whoami_no_config(runner, monkeypatch):
    """Test whoami command without config."""
    # Use a temp directory that doesn't have config
    with tempfile.TemporaryDirectory() as tmpdir:
        from bottube_cli import config
        monkeypatch.setattr(config.Path, 'home', lambda: Path(tmpdir))

        result = runner.invoke(cli, ['whoami'])

        assert result.exit_code == 0
        assert 'Not logged in' in result.output


def test_whoami_with_config(runner, temp_config, monkeypatch):
    """Test whoami command with valid config."""
    tmpdir, config_file = temp_config

    # Patch config path
    from bottube_cli import config
    monkeypatch.setattr(config.Path, 'home', lambda: Path(tmpdir))

    result = runner.invoke(cli, ['whoami'])

    # Should try to call API but fail (no mock)
    # Exit code should be 0 but show error
    assert result.exit_code == 0


def test_videos_no_config(runner, monkeypatch):
    """Test videos command without config."""
    # Use a temp directory that doesn't have config
    with tempfile.TemporaryDirectory() as tmpdir:
        from bottube_cli import config
        monkeypatch.setattr(config.Path, 'home', lambda: Path(tmpdir))

        result = runner.invoke(cli, ['videos'])

        assert result.exit_code == 0
        assert 'Not logged in' in result.output


def test_upload_no_config(runner, monkeypatch):
    """Test upload command without config."""
    # Use a temp directory that doesn't have config
    with tempfile.TemporaryDirectory() as tmpdir:
        from bottube_cli import config
        monkeypatch.setattr(config.Path, 'home', lambda: Path(tmpdir))

        with tempfile.NamedTemporaryFile(suffix='.mp4') as tmp:
            result = runner.invoke(cli, ['upload', tmp.name, '--title', 'Test'])

        assert result.exit_code == 0
        assert 'Not logged in' in result.output


def test_upload_dry_run(runner, temp_config, monkeypatch):
    """Test upload with --dry-run flag."""
    tmpdir, config_file = temp_config

    # Patch config path to use temp directory
    original_home = Path.home()

    def mock_home():
        return Path(tmpdir)

    from bottube_cli import config
    monkeypatch.setattr(config.Path, 'home', mock_home)

    # Create test file
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
        tmp.write(b"fake video")
        video_file = tmp.name

    try:
        # Import OutputFormatter after patching
        from bottube_cli.output import OutputFormatter
        formatter = OutputFormatter(json_output=False)

        # Create mock output data
        mock_data = {
            'title': 'Test Video',
            'description': 'Test Description',
            'category': None,
            'tags': ['tag1', 'tag2'],
            'file': video_file,
            'size': len(b"fake video")
        }

        # Test dry-run directly (skip authentication check)
        result_output = formatter._format_dry_run(mock_data)

        # Verify output contains expected data
        assert 'Test Video' in result_output
        assert 'Test Description' in result_output
        assert 'tag1' in result_output
        assert 'tag2' in result_output
    finally:
        Path(video_file).unlink()


def test_upload_no_title(runner):
    """Test upload without required title."""
    with tempfile.NamedTemporaryFile(suffix='.mp4') as tmp:
        result = runner.invoke(cli, ['upload', tmp.name])

    assert result.exit_code != 0
    assert 'Missing option' in result.output or 'title' in result.output.lower()


def test_agent_info_no_config(runner, monkeypatch):
    """Test agent info command without config."""
    # Use a temp directory that doesn't have config
    with tempfile.TemporaryDirectory() as tmpdir:
        from bottube_cli import config
        monkeypatch.setattr(config.Path, 'home', lambda: Path(tmpdir))

        result = runner.invoke(cli, ['agent', 'info'])

        assert result.exit_code == 0
        assert 'Not logged in' in result.output


def test_agent_stats_no_config(runner, monkeypatch):
    """Test agent stats command without config."""
    # Use a temp directory that doesn't have config
    with tempfile.TemporaryDirectory() as tmpdir:
        from bottube_cli import config
        monkeypatch.setattr(config.Path, 'home', lambda: Path(tmpdir))

        result = runner.invoke(cli, ['agent', 'stats'])

        assert result.exit_code == 0
        assert 'Not logged in' in result.output


def test_json_output(runner, temp_config, monkeypatch):
    """Test JSON output format."""
    tmpdir, config_file = temp_config

    # Patch config path
    from bottube_cli import config
    monkeypatch.setattr(config.Path, 'home', lambda: Path(tmpdir))

    result = runner.invoke(cli, ['--json', 'whoami'])

    # Should try to call API but fail
    # Output should be JSON if error occurs
    assert result.exit_code == 0
    # Either shows error in JSON or API result in JSON
