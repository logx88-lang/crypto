"""Main bot class for multi-exchange trading."""

import asyncio
from typing import Dict, List, Optional
from loguru import logger

from .config import Config
from .exchanges import create_exchange, BaseExchange
from .strategies import MarketMakingStrategy


class MultiExchangeBot:
    """Multi-exchange trading bot."""

    def __init__(self, config: Config):
        """Initialize bot.

        Args:
            config: Bot configuration
        """
        self.config = config
        self.exchanges: Dict[str, BaseExchange] = {}
        self.strategies: List[MarketMakingStrategy] = []
        self._running = False
        self._tasks: List[asyncio.Task] = []

    async def initialize(self):
        """Initialize bot and connect to exchanges."""
        logger.info("Initializing multi-exchange bot...")

        # Get enabled exchanges
        enabled_exchanges = self.config.get_enabled_exchanges()
        logger.info(f"Enabled exchanges: {enabled_exchanges}")

        # Initialize each exchange
        for exchange_name in enabled_exchanges:
            try:
                await self._initialize_exchange(exchange_name)
            except Exception as e:
                logger.error(f"Failed to initialize {exchange_name}: {e}")

        logger.info(f"Initialized {len(self.exchanges)} exchanges")

    async def _initialize_exchange(self, exchange_name: str):
        """Initialize a single exchange.

        Args:
            exchange_name: Name of exchange
        """
        logger.info(f"Initializing {exchange_name}...")

        # Get exchange config and credentials
        exchange_config = self.config.get_exchange_config(exchange_name)
        credentials = self.config.get_exchange_credentials(exchange_name)

        # Create exchange instance
        exchange = create_exchange(exchange_name, exchange_config, credentials)

        # Connect to exchange
        await exchange.connect()

        # Store exchange
        self.exchanges[exchange_name] = exchange

        # Create strategies for each symbol
        symbols = exchange_config.get("symbols", [])
        for symbol in symbols:
            strategy_config = {
                "symbol": symbol,
                **exchange_config.get("config", {}),
                **self.config.trading_params,
            }

            strategy = MarketMakingStrategy(exchange, strategy_config)
            self.strategies.append(strategy)

        logger.info(
            f"Initialized {exchange_name} with {len(symbols)} symbols: {symbols}"
        )

    async def start(self):
        """Start the bot."""
        logger.info("Starting bot...")

        if not self.exchanges:
            logger.error("No exchanges initialized!")
            return

        self._running = True

        # Start all strategies
        for strategy in self.strategies:
            await strategy.start()

        # Create tasks for each strategy
        for strategy in self.strategies:
            task = asyncio.create_task(self._run_strategy(strategy))
            self._tasks.append(task)

        logger.info(f"Started {len(self.strategies)} strategies")

        # Start monitoring task
        monitor_task = asyncio.create_task(self._monitor())
        self._tasks.append(monitor_task)

    async def _run_strategy(self, strategy: MarketMakingStrategy):
        """Run a single strategy continuously.

        Args:
            strategy: Strategy to run
        """
        refresh_interval = self.config.trading_params.get("order_refresh_interval", 60)

        while self._running:
            try:
                await strategy.run_cycle()
                await asyncio.sleep(refresh_interval)
            except Exception as e:
                logger.error(
                    f"Error in strategy {strategy.name} for {strategy.symbol}: {e}"
                )
                await asyncio.sleep(refresh_interval)

    async def _monitor(self):
        """Monitor bot health and metrics."""
        health_check_interval = self.config.monitoring_params.get(
            "health_check_interval", 300
        )

        while self._running:
            try:
                await self._health_check()
                await asyncio.sleep(health_check_interval)
            except Exception as e:
                logger.error(f"Error in monitoring: {e}")
                await asyncio.sleep(health_check_interval)

    async def _health_check(self):
        """Perform health check on exchanges and strategies."""
        logger.debug("Running health check...")

        for exchange_name, exchange in self.exchanges.items():
            try:
                if not exchange.is_connected:
                    logger.warning(f"{exchange_name} disconnected, reconnecting...")
                    await exchange.connect()

                # Get balance
                balance = await exchange.get_balance()
                logger.info(
                    f"{exchange_name} balance - Total: {balance.total}, Available: {balance.available}"
                )

            except Exception as e:
                logger.error(f"Health check failed for {exchange_name}: {e}")

    async def stop(self):
        """Stop the bot."""
        logger.info("Stopping bot...")
        self._running = False

        # Stop all strategies
        for strategy in self.strategies:
            try:
                await strategy.stop()
            except Exception as e:
                logger.error(f"Error stopping strategy: {e}")

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Disconnect from exchanges
        for exchange_name, exchange in self.exchanges.items():
            try:
                await exchange.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting from {exchange_name}: {e}")

        logger.info("Bot stopped")

    async def run(self):
        """Run the bot (blocking call)."""
        try:
            await self.initialize()
            await self.start()

            # Keep running until interrupted
            while self._running:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
        finally:
            await self.stop()

    @property
    def is_running(self) -> bool:
        """Check if bot is running."""
        return self._running

    def get_status(self) -> Dict:
        """Get bot status.

        Returns:
            Status dictionary
        """
        return {
            "running": self._running,
            "exchanges": list(self.exchanges.keys()),
            "strategies": len(self.strategies),
            "mode": self.config.mode,
        }
