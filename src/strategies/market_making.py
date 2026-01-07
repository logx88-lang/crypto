"""Market making strategy implementation."""

import asyncio
from decimal import Decimal
from typing import Dict, Any, List, Optional
from loguru import logger

from .base import BaseStrategy
from ..exchanges.base import BaseExchange, Order, OrderSide, OrderType, Ticker


class MarketMakingStrategy(BaseStrategy):
    """Market making strategy with spread-based orders."""

    def __init__(self, exchange: BaseExchange, config: Dict[str, Any]):
        """Initialize market making strategy.

        Args:
            exchange: Exchange instance
            config: Strategy configuration including:
                - symbol: Trading pair
                - spread_bps: Spread in basis points
                - order_size: Size per order
                - drift_threshold: Price drift threshold for rebalancing
                - order_levels: Number of order levels
        """
        super().__init__(exchange, config)
        self.symbol = config.get("symbol")
        self.spread_bps = config.get("spread_bps", 10)
        self.order_size = Decimal(str(config.get("order_size", 0.001)))
        self.drift_threshold = config.get("drift_threshold", 5)
        self.order_levels = config.get("order_levels", 1)

        self.current_orders: List[Order] = []
        self.last_mid_price: Optional[Decimal] = None

    async def initialize(self):
        """Initialize strategy."""
        logger.info(f"Initializing market making for {self.symbol} on {self.exchange.name}")

        # Set leverage
        leverage = self.config.get("leverage", 5)
        await self.exchange.set_leverage(self.symbol, leverage)

        # Cancel any existing orders
        await self.exchange.cancel_all_orders(self.symbol)

        logger.info(f"Market making initialized with {self.spread_bps} bps spread")

    async def run_cycle(self):
        """Run one cycle of market making."""
        try:
            # Get current market price
            ticker = await self.exchange.get_ticker(self.symbol)
            mid_price = (ticker.bid + ticker.ask) / Decimal("2")

            logger.debug(f"{self.symbol} mid price: {mid_price}")

            # Check if we need to rebalance
            if self._should_rebalance(mid_price):
                logger.info(f"Price drifted, rebalancing orders...")
                await self._cancel_all_orders()
                await self._place_orders(mid_price)
                self.last_mid_price = mid_price
            else:
                # Check order status and replace if needed
                await self._check_and_replace_orders(mid_price)

        except Exception as e:
            logger.error(f"Error in market making cycle: {e}")

    async def cleanup(self):
        """Cleanup strategy."""
        logger.info("Cleaning up market making strategy...")
        await self._cancel_all_orders()

        # Optionally close position
        if self.config.get("auto_close_position", False):
            position = await self.exchange.get_position(self.symbol)
            if position and position.size != Decimal("0"):
                logger.info(f"Closing position: {position.size}")
                await self.exchange.close_position(self.symbol)

    def _should_rebalance(self, current_price: Decimal) -> bool:
        """Check if orders should be rebalanced.

        Args:
            current_price: Current mid price

        Returns:
            True if rebalancing is needed
        """
        if self.last_mid_price is None:
            return True

        # Calculate price drift in basis points
        drift_bps = abs(
            (current_price - self.last_mid_price) / self.last_mid_price * Decimal("10000")
        )

        return drift_bps >= Decimal(str(self.drift_threshold))

    async def _place_orders(self, mid_price: Decimal):
        """Place buy and sell orders around mid price.

        Args:
            mid_price: Current mid price
        """
        spread_multiplier = Decimal(str(self.spread_bps)) / Decimal("10000")

        for level in range(self.order_levels):
            # Calculate spread for this level
            level_spread = spread_multiplier * (level + 1)

            # Buy order below mid price
            buy_price = mid_price * (Decimal("1") - level_spread)
            buy_price = self._round_price(buy_price)

            # Sell order above mid price
            sell_price = mid_price * (Decimal("1") + level_spread)
            sell_price = self._round_price(sell_price)

            try:
                # Place buy order
                buy_order = await self.exchange.create_order(
                    symbol=self.symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    size=self.order_size,
                    price=buy_price,
                )
                self.current_orders.append(buy_order)
                logger.info(f"Placed buy order: {buy_order.size} @ {buy_order.price}")

                # Place sell order
                sell_order = await self.exchange.create_order(
                    symbol=self.symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    size=self.order_size,
                    price=sell_price,
                )
                self.current_orders.append(sell_order)
                logger.info(f"Placed sell order: {sell_order.size} @ {sell_order.price}")

            except Exception as e:
                logger.error(f"Failed to place order at level {level}: {e}")

    async def _cancel_all_orders(self):
        """Cancel all current orders."""
        if not self.current_orders:
            return

        logger.info(f"Cancelling {len(self.current_orders)} orders...")

        for order in self.current_orders:
            try:
                await self.exchange.cancel_order(order.id, order.symbol)
            except Exception as e:
                logger.error(f"Failed to cancel order {order.id}: {e}")

        self.current_orders.clear()

    async def _check_and_replace_orders(self, mid_price: Decimal):
        """Check order status and replace filled orders.

        Args:
            mid_price: Current mid price
        """
        # Get open orders from exchange
        open_orders = await self.exchange.get_open_orders(self.symbol)
        open_order_ids = {order.id for order in open_orders}

        # Find filled orders
        filled_orders = [
            order for order in self.current_orders if order.id not in open_order_ids
        ]

        if filled_orders:
            logger.info(f"{len(filled_orders)} orders filled, replacing...")
            # Remove filled orders from tracking
            self.current_orders = [
                order for order in self.current_orders if order.id in open_order_ids
            ]
            # Place new orders
            await self._place_orders(mid_price)

    def _round_price(self, price: Decimal, tick_size: Decimal = Decimal("0.5")) -> Decimal:
        """Round price to tick size.

        Args:
            price: Price to round
            tick_size: Tick size for rounding

        Returns:
            Rounded price
        """
        return (price / tick_size).quantize(Decimal("1")) * tick_size
