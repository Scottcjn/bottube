"""Configuration management for BoTTube CLI."""

import json
import os
from pathlib import Path
from typing import Optional


class ConfigManager:
    """Manage CLI configuration."""

    def __init__(self):
        """Initialize config manager."""
        self.config_dir = Path.home() / '.bottube'
        self.config_file = self.config_dir / 'config'

    def get_api_key(self) -> Optional[str]:
        """Get stored API key."""
        if not self.config_file.exists():
            return None

        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                return config.get('api_key')
        except (json.JSONDecodeError, IOError):
            return None

    def save_api_key(self, api_key: str) -> None:
        """Save API key to config."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

        config = {'api_key': api_key}

        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)

        # Set restrictive permissions
        os.chmod(self.config_file, 0o600)

    def clear_config(self) -> None:
        """Clear all configuration."""
        if self.config_file.exists():
            self.config_file.unlink()

    def get_config_dir(self) -> Path:
        """Get config directory path."""
        return self.config_dir
