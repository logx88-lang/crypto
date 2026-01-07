"""Tests for bot functionality."""

import pytest
import asyncio
from decimal import Decimal

from src.config import Config
from src.bot import MultiExchangeBot
from src.exchanges import create_exchange


@pytest.mark.asyncio
async def test_config_loading():
    """Test configuration loading."""
    config = Config()
    assert config is not None
    assert config.mode in ["TEST", "LIVE"]


@pytest.mark.asyncio
async def test_exchange_creation():
    """Test exchange creation."""
    config = {"name": "GRVT", "testnet": True, "symbols": ["BTC-USD-PERP"]}
    credentials = {"api_key": "test", "api_secret": "test", "private_key": "test"}

    exchange = create_exchange("grvt", config, credentials)
    assert exchange is not None
    assert exchange.name == "GRVT"


@pytest.mark.asyncio
async def test_bot_initialization():
    """Test bot initialization."""
    config = Config()
    bot = MultiExchangeBot(config)

    assert bot is not None
    assert not bot.is_running


# Add more tests as needed
