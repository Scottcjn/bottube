#!/usr/bin/env python3
"""
Configuration Management for BoTTube Syndication

Centralized configuration management with support for:
- YAML/JSON configuration files
- Environment variable overrides
- Schema validation
- Hot reload capability
- Platform-specific configuration sections

Configuration hierarchy (later overrides earlier):
1. Default values
2. Configuration file (syndication.yaml or syndication.json)
3. Environment variables (BOTTUBE_SYNDICATION_*)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

log = logging.getLogger("bottube-syndication-config")


@dataclass
class PlatformConfig:
    """Configuration for a single syndication platform."""
    enabled: bool = True
    priority: int = 0
    rate_limit: int = 60  # requests per minute
    rate_limit_window: int = 60  # seconds
    retry_count: int = 3
    retry_backoff: float = 2.0
    timeout: int = 30
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScheduleConfig:
    """Scheduling configuration for syndication."""
    enabled: bool = True
    cron_expression: str = "* * * * *"  # Every minute (default)
    timezone: str = "UTC"
    batch_size: int = 10
    batch_delay: int = 5  # seconds between batch items
    quiet_hours_start: Optional[str] = None  # e.g., "22:00"
    quiet_hours_end: Optional[str] = None  # e.g., "08:00"
    days_of_week: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])  # 0=Sunday


@dataclass
class SyndicationConfig:
    """Main syndication configuration."""
    enabled: bool = True
    poll_interval: int = 60  # seconds
    platforms: Dict[str, PlatformConfig] = field(default_factory=dict)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    global_rate_limit: int = 100  # total requests per minute
    global_timeout: int = 300  # seconds
    log_level: str = "INFO"
    config_file: Optional[str] = None

    def get_platform(self, name: str) -> Optional[PlatformConfig]:
        """Get configuration for a specific platform."""
        return self.platforms.get(name)

    def get_enabled_platforms(self) -> List[str]:
        """Get list of enabled platform names."""
        return [name for name, config in self.platforms.items() if config.enabled]


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class SyndicationConfigManager:
    """
    Manages syndication configuration with file and environment support.

    Features:
        - Load from YAML or JSON file
        - Environment variable overrides (BOTTUBE_SYNDICATION_*)
        - Schema validation
        - Hot reload on file changes
        - Platform-specific configuration sections

    Usage:
        manager = SyndicationConfigManager()
        manager.load("syndication.yaml")
        config = manager.get_config()

        # Access platform config
        moltbook_config = config.get_platform("moltbook")

        # Check if platform is enabled
        if "twitter" in config.get_enabled_platforms():
            ...
    """

    DEFAULT_CONFIG = SyndicationConfig(
        enabled=True,
        poll_interval=60,
        schedule=ScheduleConfig(),
        global_rate_limit=100,
        global_timeout=300,
        log_level="INFO",
    )

    def __init__(self, config_dir: Optional[str] = None):
        """
        Initialize configuration manager.

        Args:
            config_dir: Directory to search for config files.
                       Defaults to current directory or BOTTUBE_BASE_DIR.
        """
        self.config_dir = Path(config_dir) if config_dir else self._default_config_dir()
        self.config: SyndicationConfig = self.DEFAULT_CONFIG
        self._file_mtime: float = 0.0
        self._config_path: Optional[Path] = None

    def _default_config_dir(self) -> Path:
        """Get default configuration directory."""
        env_dir = os.environ.get("BOTTUBE_BASE_DIR")
        if env_dir:
            return Path(env_dir)
        return Path.cwd()

    def load(self, config_file: Optional[str] = None) -> SyndicationConfig:
        """
        Load configuration from file and environment.

        Args:
            config_file: Path to config file. If None, searches for
                        syndication.yaml or syndication.json in config_dir.

        Returns:
            Loaded SyndicationConfig

        Raises:
            ConfigValidationError: If configuration is invalid
        """
        # Find config file
        config_path = self._find_config_file(config_file)

        if config_path:
            self._config_path = config_path
            file_config = self._load_file(config_path)
            self._file_mtime = config_path.stat().st_mtime
        else:
            file_config = {}

        # Merge with defaults and environment
        config_dict = self._merge_configs(file_config)
        self.config = self._dict_to_config(config_dict)

        # Validate
        self.validate()

        log.info("Loaded syndication configuration from %s",
                config_path or "defaults + environment")
        return self.config

    def reload(self) -> SyndicationConfig:
        """
        Reload configuration if file has changed.

        Returns:
            Current SyndicationConfig (may be unchanged if no reload)
        """
        if not self._config_path:
            return self.config

        try:
            current_mtime = self._config_path.stat().st_mtime
            if current_mtime > self._file_mtime:
                log.info("Reloading configuration (file changed)")
                return self.load(str(self._config_path))
        except OSError:
            pass

        return self.config

    def get_config(self) -> SyndicationConfig:
        """Get current configuration."""
        return self.config

    def validate(self):
        """
        Validate current configuration.

        Raises:
            ConfigValidationError: If validation fails
        """
        errors = []

        # Validate poll interval
        if self.config.poll_interval < 1:
            errors.append("poll_interval must be >= 1 second")
        if self.config.poll_interval > 3600:
            errors.append("poll_interval must be <= 3600 seconds")

        # Validate platforms
        for name, platform_config in self.config.platforms.items():
            if platform_config.rate_limit < 1:
                errors.append(f"[{name}] rate_limit must be >= 1")
            if platform_config.retry_count < 0:
                errors.append(f"[{name}] retry_count must be >= 0")
            if platform_config.timeout < 1:
                errors.append(f"[{name}] timeout must be >= 1 second")

        # Validate schedule
        schedule = self.config.schedule
        if schedule.batch_size < 1:
            errors.append("schedule.batch_size must be >= 1")
        if schedule.batch_delay < 0:
            errors.append("schedule.batch_delay must be >= 0")
        if schedule.days_of_week and not all(0 <= d <= 6 for d in schedule.days_of_week):
            errors.append("schedule.days_of_week must be 0-6")

        if errors:
            raise ConfigValidationError("Configuration validation failed:\n" +
                                       "\n".join(f"  - {e}" for e in errors))

    def _find_config_file(self, config_file: Optional[str]) -> Optional[Path]:
        """Find configuration file."""
        if config_file:
            path = Path(config_file)
            if path.is_absolute():
                return path if path.exists() else None
            return self.config_dir / config_file if path.exists() else None

        # Search for default names
        for name in ["syndication.yaml", "syndication.yml", "syndication.json"]:
            path = self.config_dir / name
            if path.exists():
                return path

        return None

    def _load_file(self, path: Path) -> Dict[str, Any]:
        """Load configuration from YAML or JSON file."""
        with open(path, "r") as f:
            content = f.read()

        if path.suffix in (".yaml", ".yml"):
            return yaml.safe_load(content) or {}
        elif path.suffix == ".json":
            return json.loads(content) if content.strip() else {}
        else:
            log.warning("Unknown config file extension: %s", path.suffix)
            return {}

    def _merge_configs(self, file_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge file config with environment overrides."""
        config = {
            "enabled": self.DEFAULT_CONFIG.enabled,
            "poll_interval": self.DEFAULT_CONFIG.poll_interval,
            "global_rate_limit": self.DEFAULT_CONFIG.global_rate_limit,
            "global_timeout": self.DEFAULT_CONFIG.global_timeout,
            "log_level": self.DEFAULT_CONFIG.log_level,
            "platforms": {},
            "schedule": {},
        }

        # Apply file config
        self._deep_merge(config, file_config)

        # Apply environment overrides
        self._apply_env_overrides(config)

        return config

    def _deep_merge(self, base: Dict, override: Dict):
        """Recursively merge override into base."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _apply_env_overrides(self, config: Dict[str, Any]):
        """Apply environment variable overrides."""
        prefix = "BOTTUBE_SYNDICATION_"

        # Simple overrides
        env_map = {
            f"{prefix}ENABLED": ("enabled", lambda x: x.lower() in ("1", "true", "yes")),
            f"{prefix}POLL_INTERVAL": ("poll_interval", int),
            f"{prefix}GLOBAL_RATE_LIMIT": ("global_rate_limit", int),
            f"{prefix}GLOBAL_TIMEOUT": ("global_timeout", int),
            f"{prefix}LOG_LEVEL": ("log_level", str),
        }

        for env_var, (config_key, converter) in env_map.items():
            value = os.environ.get(env_var)
            if value is not None:
                try:
                    config[config_key] = converter(value)
                except (ValueError, TypeError) as e:
                    log.warning("Invalid env var %s=%s: %s", env_var, value, e)

        # Platform-specific overrides
        # Format: BOTTUBE_SYNDICATION_PLATFORM_<NAME>_<KEY>=value
        for env_var, value in os.environ.items():
            if env_var.startswith(f"{prefix}PLATFORM_"):
                parts = env_var[len(f"{prefix}PLATFORM_"):].split("_", 1)
                if len(parts) == 2:
                    platform_name = parts[0].lower()
                    config_key = parts[1].lower()
                    if platform_name not in config["platforms"]:
                        config["platforms"][platform_name] = {}
                    # Simple type inference
                    if value.lower() in ("true", "1"):
                        config["platforms"][platform_name][config_key] = True
                    elif value.lower() in ("false", "0"):
                        config["platforms"][platform_name][config_key] = False
                    elif value.isdigit():
                        config["platforms"][platform_name][config_key] = int(value)
                    else:
                        config["platforms"][platform_name][config_key] = value

        # Schedule overrides
        for env_var, value in os.environ.items():
            if env_var.startswith(f"{prefix}SCHEDULE_"):
                config_key = env_var[len(f"{prefix}SCHEDULE_"):].lower()
                if value.lower() in ("true", "1"):
                    config["schedule"][config_key] = True
                elif value.lower() in ("false", "0"):
                    config["schedule"][config_key] = False
                elif value.isdigit():
                    config["schedule"][config_key] = int(value)
                else:
                    config["schedule"][config_key] = value

    def _dict_to_config(self, data: Dict[str, Any]) -> SyndicationConfig:
        """Convert dictionary to SyndicationConfig object."""
        # Convert platform configs
        platforms = {}
        for name, pdata in data.get("platforms", {}).items():
            if isinstance(pdata, dict):
                platforms[name] = PlatformConfig(
                    enabled=pdata.get("enabled", True),
                    priority=pdata.get("priority", 0),
                    rate_limit=pdata.get("rate_limit", 60),
                    rate_limit_window=pdata.get("rate_limit_window", 60),
                    retry_count=pdata.get("retry_count", 3),
                    retry_backoff=pdata.get("retry_backoff", 2.0),
                    timeout=pdata.get("timeout", 30),
                    config=pdata.get("config", {}),
                )

        # Convert schedule config
        schedule_data = data.get("schedule", {})
        schedule = ScheduleConfig(
            enabled=schedule_data.get("enabled", True),
            cron_expression=schedule_data.get("cron_expression", "* * * * *"),
            timezone=schedule_data.get("timezone", "UTC"),
            batch_size=schedule_data.get("batch_size", 10),
            batch_delay=schedule_data.get("batch_delay", 5),
            quiet_hours_start=schedule_data.get("quiet_hours_start"),
            quiet_hours_end=schedule_data.get("quiet_hours_end"),
            days_of_week=schedule_data.get("days_of_week", [0, 1, 2, 3, 4, 5, 6]),
        )

        return SyndicationConfig(
            enabled=data.get("enabled", True),
            poll_interval=data.get("poll_interval", 60),
            platforms=platforms,
            schedule=schedule,
            global_rate_limit=data.get("global_rate_limit", 100),
            global_timeout=data.get("global_timeout", 300),
            log_level=data.get("log_level", "INFO"),
            config_file=str(self._config_path) if self._config_path else None,
        )


# Global config manager instance
_config_manager: Optional[SyndicationConfigManager] = None


def get_config_manager(config_dir: Optional[str] = None) -> SyndicationConfigManager:
    """Get or create global config manager."""
    global _config_manager
    if _config_manager is None:
        _config_manager = SyndicationConfigManager(config_dir)
    return _config_manager


def load_config(config_file: Optional[str] = None) -> SyndicationConfig:
    """Load and return syndication configuration."""
    manager = get_config_manager()
    return manager.load(config_file)


def get_config() -> SyndicationConfig:
    """Get current syndication configuration."""
    manager = get_config_manager()
    return manager.get_config()


def reload_config() -> SyndicationConfig:
    """Reload syndication configuration if changed."""
    manager = get_config_manager()
    return manager.reload()
