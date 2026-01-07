"""Multi-exchange trading bot."""

from .bot import MultiExchangeBot
from .config import Config, get_config

__version__ = "0.1.0"

__all__ = ["MultiExchangeBot", "Config", "get_config"]
