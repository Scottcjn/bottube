"""Tests for configuration management."""

import json
import tempfile
from pathlib import Path

import pytest

from bottube_cli.config import ConfigManager


@pytest.fixture
def temp_config():
    """Create a temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / 'config'
        config = ConfigManager()
        config.config_dir = Path(tmpdir)
        config.config_file = config_file
        yield config


def test_save_and_get_api_key(temp_config):
    """Test saving and retrieving API key."""
    api_key = "test_api_key_123"

    temp_config.save_api_key(api_key)

    assert temp_config.get_api_key() == api_key
    assert temp_config.config_file.exists()


def test_clear_config(temp_config):
    """Test clearing configuration."""
    temp_config.save_api_key("test_key")
    assert temp_config.get_api_key() is not None

    temp_config.clear_config()
    assert temp_config.get_api_key() is None
    assert not temp_config.config_file.exists()


def test_get_api_key_no_config(temp_config):
    """Test getting API key when config doesn't exist."""
    assert temp_config.get_api_key() is None


def test_config_file_permissions(temp_config):
    """Test that config file has restrictive permissions."""
    temp_config.save_api_key("test_key")

    import os
    stat = temp_config.config_file.stat()
    mode = oct(stat.st_mode)[-3:]
    assert mode == "600"
