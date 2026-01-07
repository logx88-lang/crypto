"""Trading strategies for multi-exchange bot."""

from .base import BaseStrategy
from .market_making import MarketMakingStrategy

__all__ = ["BaseStrategy", "MarketMakingStrategy"]
