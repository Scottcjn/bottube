#!/usr/bin/env python3
"""
Tests for Syndication Configuration (Issue #310)

Tests cover:
- Configuration loading from YAML/JSON
- Environment variable overrides
- Schema validation
- Hot reload capability
- Platform-specific configuration
"""

import os
import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

import sys

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from syndication_config import (
    SyndicationConfig,
    SyndicationConfigManager,
    PlatformConfig,
    ScheduleConfig,
    ConfigValidationError,
    load_config,
    get_config,
    reload_config,
    _config_manager,
)


class TestPlatformConfig:
    """Tests for PlatformConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PlatformConfig()
        assert config.enabled is True
        assert config.priority == 0
        assert config.rate_limit == 60
        assert config.retry_count == 3
        assert config.timeout == 30

    def test_custom_values(self):
        """Test custom configuration values."""
        config = PlatformConfig(
            enabled=False,
            priority=10,
            rate_limit=30,
            rate_limit_window=120,
            retry_count=5,
            timeout=60,
            config={"custom": "value"},
        )
        assert config.enabled is False
        assert config.priority == 10
        assert config.rate_limit == 30
        assert config.rate_limit_window == 120
        assert config.retry_count == 5
        assert config.config == {"custom": "value"}


class TestScheduleConfig:
    """Tests for ScheduleConfig dataclass."""

    def test_default_values(self):
        """Test default schedule configuration."""
        config = ScheduleConfig()
        assert config.enabled is True
        assert config.cron_expression == "* * * * *"
        assert config.timezone == "UTC"
        assert config.batch_size == 10
        assert config.batch_delay == 5
        assert config.quiet_hours_start is None
        assert config.days_of_week == [0, 1, 2, 3, 4, 5, 6]

    def test_custom_values(self):
        """Test custom schedule configuration."""
        config = ScheduleConfig(
            enabled=False,
            cron_expression="0 * * * *",
            timezone="America/New_York",
            batch_size=5,
            batch_delay=10,
            quiet_hours_start="22:00",
            quiet_hours_end="06:00",
            days_of_week=[1, 2, 3, 4, 5],
        )
        assert config.enabled is False
        assert config.cron_expression == "0 * * * *"
        assert config.timezone == "America/New_York"
        assert config.quiet_hours_start == "22:00"


class TestSyndicationConfig:
    """Tests for SyndicationConfig dataclass."""

    def test_default_values(self):
        """Test default syndication configuration."""
        config = SyndicationConfig()
        assert config.enabled is True
        assert config.poll_interval == 60
        assert config.global_rate_limit == 100
        assert config.global_timeout == 300
        assert config.log_level == "INFO"

    def test_get_platform(self):
        """Test getting platform configuration."""
        config = SyndicationConfig(
            platforms={
                "moltbook": PlatformConfig(priority=10),
                "twitter": PlatformConfig(priority=5),
            }
        )
        moltbook_config = config.get_platform("moltbook")
        assert moltbook_config.priority == 10
        assert config.get_platform("unknown") is None

    def test_get_enabled_platforms(self):
        """Test getting enabled platform names."""
        config = SyndicationConfig(
            platforms={
                "moltbook": PlatformConfig(enabled=True),
                "twitter": PlatformConfig(enabled=False),
                "rss_feed": PlatformConfig(enabled=True),
            }
        )
        enabled = config.get_enabled_platforms()
        assert "moltbook" in enabled
        assert "twitter" not in enabled
        assert "rss_feed" in enabled


class TestSyndicationConfigManager:
    """Tests for SyndicationConfigManager."""

    def test_default_config_dir(self):
        """Test default configuration directory detection."""
        manager = SyndicationConfigManager()
        # Should use cwd or BOTTUBE_BASE_DIR
        assert manager.config_dir is not None

    def test_custom_config_dir(self):
        """Test custom configuration directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = SyndicationConfigManager(tmpdir)
            assert str(manager.config_dir) == tmpdir

    def test_load_yaml_config(self):
        """Test loading YAML configuration."""
        yaml_content = """
enabled: true
poll_interval: 120
platforms:
  moltbook:
    enabled: true
    priority: 10
    rate_limit: 30
    config:
      base_url: https://moltbook.com
      api_key: test_key
  twitter:
    enabled: false
    priority: 5
schedule:
  enabled: true
  cron_expression: "*/5 * * * *"
  quiet_hours_start: "22:00"
  quiet_hours_end: "06:00"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                manager = SyndicationConfigManager()
                config = manager.load(f.name)

                assert config.enabled is True
                assert config.poll_interval == 120
                assert "moltbook" in config.platforms
                assert config.platforms["moltbook"].priority == 10
                assert config.platforms["moltbook"].config["base_url"] == "https://moltbook.com"
                assert config.platforms["twitter"].enabled is False
                assert config.schedule.cron_expression == "*/5 * * * *"
                assert config.schedule.quiet_hours_start == "22:00"
            finally:
                os.unlink(f.name)

    def test_load_json_config(self):
        """Test loading JSON configuration."""
        json_content = {
            "enabled": True,
            "poll_interval": 90,
            "platforms": {
                "rss_feed": {
                    "enabled": True,
                    "priority": 0,
                    "config": {"site_url": "https://bottube.ai"},
                }
            },
            "schedule": {
                "batch_size": 20,
                "batch_delay": 10,
            },
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(json_content, f)
            f.flush()

            try:
                manager = SyndicationConfigManager()
                config = manager.load(f.name)

                assert config.enabled is True
                assert config.poll_interval == 90
                assert config.platforms["rss_feed"].enabled is True
                assert config.schedule.batch_size == 20
            finally:
                os.unlink(f.name)

    def test_env_override_enabled(self):
        """Test environment variable override for enabled."""
        with patch.dict(os.environ, {"BOTTUBE_SYNDICATION_ENABLED": "false"}):
            manager = SyndicationConfigManager()
            config = manager.load()
            assert config.enabled is False

    def test_env_override_poll_interval(self):
        """Test environment variable override for poll_interval."""
        with patch.dict(os.environ, {"BOTTUBE_SYNDICATION_POLL_INTERVAL": "300"}):
            manager = SyndicationConfigManager()
            config = manager.load()
            assert config.poll_interval == 300

    def test_env_override_platform_config(self):
        """Test environment variable override for platform config."""
        with patch.dict(os.environ, {
            "BOTTUBE_SYNDICATION_PLATFORM_MOLTBOOK_ENABLED": "false",
            "BOTTUBE_SYNDICATION_PLATFORM_MOLTBOOK_RATE_LIMIT": "15",
        }):
            manager = SyndicationConfigManager()
            config = manager.load()
            assert "moltbook" in config.platforms
            assert config.platforms["moltbook"].enabled is False
            assert config.platforms["moltbook"].rate_limit == 15

    def test_env_override_schedule(self):
        """Test environment variable override for schedule config."""
        with patch.dict(os.environ, {
            "BOTTUBE_SYNDICATION_SCHEDULE_BATCH_SIZE": "25",
            "BOTTUBE_SYNDICATION_SCHEDULE_ENABLED": "false",
        }):
            manager = SyndicationConfigManager()
            config = manager.load()
            assert config.schedule.batch_size == 25
            assert config.schedule.enabled is False

    def test_reload_config(self):
        """Test configuration reload on file change."""
        yaml_content = """
enabled: true
poll_interval: 60
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                manager = SyndicationConfigManager()
                config = manager.load(f.name)
                assert config.poll_interval == 60

                # Modify file
                with open(f.name, 'w') as f2:
                    f2.write("enabled: true\npoll_interval: 120\n")

                # Reload
                config = manager.reload()
                assert config.poll_interval == 120
            finally:
                os.unlink(f.name)

    def test_reload_no_change(self):
        """Test reload returns same config if file unchanged."""
        yaml_content = "enabled: true\npoll_interval: 60\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                manager = SyndicationConfigManager()
                config = manager.load(f.name)

                # Reload without changes
                config2 = manager.reload()
                assert config2.poll_interval == 60
            finally:
                os.unlink(f.name)

    def test_config_validation_invalid_poll_interval(self):
        """Test validation fails for invalid poll_interval."""
        yaml_content = "enabled: true\npoll_interval: 0\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                manager = SyndicationConfigManager()
                with pytest.raises(ConfigValidationError):
                    manager.load(f.name)
            finally:
                os.unlink(f.name)

    def test_config_validation_invalid_rate_limit(self):
        """Test validation fails for invalid rate_limit."""
        yaml_content = """
enabled: true
poll_interval: 60
platforms:
  moltbook:
    enabled: true
    rate_limit: 0
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                manager = SyndicationConfigManager()
                with pytest.raises(ConfigValidationError):
                    manager.load(f.name)
            finally:
                os.unlink(f.name)

    def test_config_validation_invalid_days_of_week(self):
        """Test validation fails for invalid days_of_week."""
        yaml_content = """
enabled: true
poll_interval: 60
schedule:
  days_of_week: [0, 1, 7, 8]
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                manager = SyndicationConfigManager()
                with pytest.raises(ConfigValidationError):
                    manager.load(f.name)
            finally:
                os.unlink(f.name)

    def test_find_config_file_explicit(self):
        """Test finding explicitly specified config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("enabled: true\n")
            f.flush()

            try:
                manager = SyndicationConfigManager()
                path = manager._find_config_file(f.name)
                assert path is not None
                assert str(path) == f.name
            finally:
                os.unlink(f.name)

    def test_find_config_file_default_names(self):
        """Test finding default config file names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create syndication.yaml
            with open(os.path.join(tmpdir, "syndication.yaml"), 'w') as f:
                f.write("enabled: true\n")

            manager = SyndicationConfigManager(tmpdir)
            path = manager._find_config_file(None)
            assert path is not None
            assert path.name == "syndication.yaml"


class TestGlobalFunctions:
    """Tests for global convenience functions."""

    def test_load_config(self):
        """Test load_config function."""
        yaml_content = "enabled: true\npoll_interval: 60\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                # Reset global manager
                import syndication_config
                syndication_config._config_manager = None

                config = load_config(f.name)
                assert config.enabled is True
            finally:
                os.unlink(f.name)
                syndication_config._config_manager = None

    def test_get_config(self):
        """Test get_config function."""
        # Reset global manager
        import syndication_config
        syndication_config._config_manager = None

        config = get_config()
        assert isinstance(config, SyndicationConfig)
        syndication_config._config_manager = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
