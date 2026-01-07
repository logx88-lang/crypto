"""Base abstract class for trading strategies."""

from abc import ABC, abstractmethod
from typing import Dict, Any
from loguru import logger

from ..exchanges.base import BaseExchange


class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""

    def __init__(self, exchange: BaseExchange, config: Dict[str, Any]):
        """Initialize strategy.

        Args:
            exchange: Exchange instance
            config: Strategy configuration
        """
        self.exchange = exchange
        self.config = config
        self.name = self.__class__.__name__
        self._running = False

    @abstractmethod
    async def initialize(self):
        """Initialize strategy (called once before running)."""
        pass

    @abstractmethod
    async def run_cycle(self):
        """Run one cycle of the strategy."""
        pass

    @abstractmethod
    async def cleanup(self):
        """Cleanup resources (called when stopping)."""
        pass

    async def start(self):
        """Start the strategy."""
        logger.info(f"Starting strategy: {self.name}")
        await self.initialize()
        self._running = True

    async def stop(self):
        """Stop the strategy."""
        logger.info(f"Stopping strategy: {self.name}")
        self._running = False
        await self.cleanup()

    @property
    def is_running(self) -> bool:
        """Check if strategy is running."""
        return self._running
