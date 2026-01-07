"""Configuration management for multi-exchange bot."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()


class Config:
    """Main configuration class."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration.

        Args:
            config_path: Path to config.yaml file
        """
        self.base_dir = Path(__file__).parent.parent
        self.config_path = config_path or self.base_dir / "config" / "config.yaml"
        self.exchanges_path = self.base_dir / "config" / "exchanges.yaml"

        self.config = self._load_yaml(self.config_path)
        self.exchanges_config = self._load_yaml(self.exchanges_path)

        # Environment variables
        self.mode = os.getenv("MODE", self.config["bot"]["mode"])
        self.log_level = os.getenv("LOG_LEVEL", self.config["bot"]["log_level"])

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load YAML configuration file.

        Args:
            path: Path to YAML file

        Returns:
            Configuration dictionary
        """
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {path}")
            return {}

    @property
    def is_test_mode(self) -> bool:
        """Check if running in test mode."""
        return self.mode.upper() == "TEST"

    @property
    def is_live_mode(self) -> bool:
        """Check if running in live mode."""
        return self.mode.upper() == "LIVE"

    def get_exchange_config(self, exchange_name: str) -> Dict[str, Any]:
        """Get configuration for specific exchange.

        Args:
            exchange_name: Name of exchange (grvt, lighter, etc.)

        Returns:
            Exchange configuration dictionary
        """
        return self.exchanges_config.get("exchanges", {}).get(exchange_name, {})

    def get_enabled_exchanges(self) -> list[str]:
        """Get list of enabled exchanges.

        Returns:
            List of enabled exchange names
        """
        exchanges = self.exchanges_config.get("exchanges", {})
        return [name for name, config in exchanges.items() if config.get("enabled", False)]

    def get_exchange_credentials(self, exchange_name: str) -> Dict[str, str]:
        """Get API credentials for exchange from environment variables.

        Args:
            exchange_name: Name of exchange

        Returns:
            Dictionary with API credentials
        """
        prefix = exchange_name.upper()
        return {
            "api_key": os.getenv(f"{prefix}_API_KEY", ""),
            "api_secret": os.getenv(f"{prefix}_API_SECRET", ""),
            "private_key": os.getenv(f"{prefix}_PRIVATE_KEY", ""),
        }

    @property
    def trading_params(self) -> Dict[str, Any]:
        """Get trading parameters."""
        return self.config.get("trading", {})

    @property
    def risk_params(self) -> Dict[str, Any]:
        """Get risk management parameters."""
        return self.config.get("risk_management", {})

    @property
    def monitoring_params(self) -> Dict[str, Any]:
        """Get monitoring parameters."""
        return self.config.get("monitoring", {})


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance.

    Returns:
        Config instance
    """
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config():
    """Reload configuration from files."""
    global _config
    _config = Config()
