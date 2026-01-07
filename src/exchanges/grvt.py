"""GRVT exchange adapter using official Python SDK."""

import os
import asyncio
from decimal import Decimal
from typing import Dict, List, Optional, Any, Callable
from loguru import logger

try:
    from grvt import GrvtCcxtPro
except ImportError:
    logger.warning("grvt-pysdk not installed. Install with: pip install grvt-pysdk")
    GrvtCcxtPro = None

from .base import (
    BaseExchange,
    Order,
    Position,
    Balance,
    Ticker,
    OrderSide,
    OrderType,
    OrderStatus,
)


class GRVTExchange(BaseExchange):
    """GRVT exchange implementation using official Python SDK."""

    def __init__(self, config: Dict[str, Any], credentials: Dict[str, str]):
        """Initialize GRVT adapter."""
        super().__init__(config, credentials)

        if GrvtCcxtPro is None:
            raise RuntimeError("grvt-pysdk is required. Install with: pip install grvt-pysdk")

        # Set environment variables for SDK
        os.environ['GRVT_PRIVATE_KEY'] = credentials.get('private_key', '')
        os.environ['GRVT_API_KEY'] = credentials.get('api_key', '')
        os.environ['GRVT_TRADING_ACCOUNT_ID'] = credentials.get('trading_account_id', '')
        os.environ['GRVT_ENV'] = 'testnet' if self.testnet else 'prod'
        os.environ['GRVT_END_POINT_VERSION'] = 'v1'
        os.environ['GRVT_WS_STREAM_VERSION'] = 'v1'

        self.client: Optional[GrvtCcxtPro] = None

    async def connect(self):
        """Connect to GRVT using SDK."""
        logger.info(f"Connecting to GRVT ({'testnet' if self.testnet else 'mainnet'})...")

        try:
            # Initialize CCXT Pro client (async)
            self.client = GrvtCcxtPro()

            # Test connection by fetching markets
            markets = await self.client.load_markets()
            logger.info(f"Connected to GRVT. Available markets: {len(markets)}")

            self._connected = True
        except Exception as e:
            logger.error(f"Failed to connect to GRVT: {e}")
            raise

    async def disconnect(self):
        """Disconnect from GRVT."""
        # Cancel WebSocket tasks
        for task in self._ws_tasks:
            task.cancel()
        self._ws_tasks.clear()

        if self.client:
            await self.client.close()

        self._connected = False
        self._ws_connected = False
        logger.info("Disconnected from GRVT")

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        size: Decimal,
        price: Optional[Decimal] = None,
        **kwargs
    ) -> Order:
        """Create order on GRVT using SDK."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        logger.info(f"Creating {side.value} {order_type.value} order: {size} {symbol} @ {price}")

        try:
            normalized_symbol = self.normalize_symbol(symbol)

            # CCXT parameters
            ccxt_side = 'buy' if side == OrderSide.BUY else 'sell'
            ccxt_type = 'limit' if order_type == OrderType.LIMIT else 'market'

            # Create order using CCXT interface
            if order_type == OrderType.LIMIT:
                order_result = await self.client.create_order(
                    symbol=normalized_symbol,
                    type=ccxt_type,
                    side=ccxt_side,
                    amount=float(size),
                    price=float(price) if price else None,
                )
            else:
                order_result = await self.client.create_order(
                    symbol=normalized_symbol,
                    type=ccxt_type,
                    side=ccxt_side,
                    amount=float(size),
                )

            # Convert to our Order format
            return self._parse_order(order_result)

        except Exception as e:
            logger.error(f"Failed to create order on GRVT: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel order on GRVT."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        logger.info(f"Cancelling order {order_id} for {symbol}")

        try:
            normalized_symbol = self.normalize_symbol(symbol)
            await self.client.cancel_order(order_id, normalized_symbol)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel all orders on GRVT."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        logger.info(f"Cancelling all orders for {symbol or 'all symbols'}")

        try:
            if symbol:
                normalized_symbol = self.normalize_symbol(symbol)
                orders = await self.client.fetch_open_orders(normalized_symbol)
            else:
                orders = await self.client.fetch_open_orders()

            count = 0
            for order in orders:
                try:
                    await self.client.cancel_order(order['id'], order['symbol'])
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to cancel order {order['id']}: {e}")

            return count
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return 0

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get open orders from GRVT."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        try:
            if symbol:
                normalized_symbol = self.normalize_symbol(symbol)
                orders = await self.client.fetch_open_orders(normalized_symbol)
            else:
                orders = await self.client.fetch_open_orders()

            return [self._parse_order(order) for order in orders]
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position from GRVT."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        try:
            normalized_symbol = self.normalize_symbol(symbol)
            positions = await self.client.fetch_positions([normalized_symbol])

            if not positions:
                return None

            pos = positions[0]

            # Parse position data
            return Position(
                symbol=symbol,
                size=Decimal(str(pos.get('contracts', 0))),
                entry_price=Decimal(str(pos.get('entryPrice', 0))),
                mark_price=Decimal(str(pos.get('markPrice', 0))),
                unrealized_pnl=Decimal(str(pos.get('unrealizedPnl', 0))),
                leverage=int(pos.get('leverage', 1)),
                side='long' if float(pos.get('contracts', 0)) > 0 else 'short',
                raw_data=pos,
            )
        except Exception as e:
            logger.error(f"Failed to get position: {e}")
            return None

    async def close_position(self, symbol: str) -> bool:
        """Close position on GRVT."""
        logger.info(f"Closing position for {symbol}")

        try:
            position = await self.get_position(symbol)
            if not position or position.size == Decimal("0"):
                logger.info("No position to close")
                return True

            # Create opposite order to close position
            close_side = OrderSide.SELL if position.side == 'long' else OrderSide.BUY
            await self.create_order(
                symbol=symbol,
                side=close_side,
                order_type=OrderType.MARKET,
                size=abs(position.size),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return False

    async def get_balance(self) -> Balance:
        """Get balance from GRVT."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        try:
            balance = await self.client.fetch_balance()

            # GRVT uses USD as collateral
            usd_balance = balance.get('USD', {})

            return Balance(
                total=Decimal(str(usd_balance.get('total', 0))),
                available=Decimal(str(usd_balance.get('free', 0))),
                used=Decimal(str(usd_balance.get('used', 0))),
                currency='USD',
                raw_data=balance,
            )
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return Balance(
                total=Decimal("0"),
                available=Decimal("0"),
                used=Decimal("0"),
            )

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker from GRVT."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        try:
            normalized_symbol = self.normalize_symbol(symbol)
            ticker = await self.client.fetch_ticker(normalized_symbol)

            return Ticker(
                symbol=symbol,
                bid=Decimal(str(ticker.get('bid', 0))),
                ask=Decimal(str(ticker.get('ask', 0))),
                last=Decimal(str(ticker.get('last', 0))),
                timestamp=int(ticker.get('timestamp', 0)),
                raw_data=ticker,
            )
        except Exception as e:
            logger.error(f"Failed to get ticker: {e}")
            raise

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage on GRVT."""
        logger.info(f"Setting leverage to {leverage}x for {symbol}")

        try:
            if not self.client:
                raise RuntimeError("Not connected to exchange")

            normalized_symbol = self.normalize_symbol(symbol)
            await self.client.set_leverage(leverage, normalized_symbol)
            return True
        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            return False

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to GRVT format (e.g., BTC -> BTC/USD:USD)."""
        if '/' in symbol or ':' in symbol:
            return symbol

        # GRVT uses format: BASE/QUOTE:SETTLE
        # For perpetuals: BTC/USD:USD
        return f"{symbol}/USD:USD"

    def _parse_order(self, order_data: Dict) -> Order:
        """Parse CCXT order to our Order format."""
        return Order(
            id=order_data['id'],
            symbol=order_data['symbol'],
            side=OrderSide.BUY if order_data['side'] == 'buy' else OrderSide.SELL,
            type=OrderType.LIMIT if order_data['type'] == 'limit' else OrderType.MARKET,
            price=Decimal(str(order_data.get('price', 0))),
            size=Decimal(str(order_data.get('amount', 0))),
            status=self._parse_order_status(order_data.get('status', 'unknown')),
            filled_size=Decimal(str(order_data.get('filled', 0))),
            timestamp=order_data.get('timestamp'),
            raw_data=order_data,
        )

    def _parse_order_status(self, status: str) -> OrderStatus:
        """Parse CCXT order status to our OrderStatus enum."""
        status_map = {
            'open': OrderStatus.OPEN,
            'closed': OrderStatus.FILLED,
            'canceled': OrderStatus.CANCELLED,
            'cancelled': OrderStatus.CANCELLED,
            'rejected': OrderStatus.REJECTED,
        }
        return status_map.get(status.lower(), OrderStatus.OPEN)

    # WebSocket Methods

    async def subscribe_ticker(self, symbol: str, callback: Optional[Callable[[Ticker], None]] = None):
        """Subscribe to ticker updates via WebSocket using CCXT Pro.

        Args:
            symbol: Trading pair symbol
            callback: Optional callback function to receive ticker updates
        """
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        normalized_symbol = self.normalize_symbol(symbol)

        # Register callback
        if callback:
            if symbol not in self._ticker_callbacks:
                self._ticker_callbacks[symbol] = []
            self._ticker_callbacks[symbol].append(callback)

        # Start WebSocket task
        task = asyncio.create_task(self._watch_ticker(symbol, normalized_symbol))
        self._ws_tasks.append(task)
        self._ws_connected = True

        logger.info(f"Subscribed to ticker updates for {symbol} via WebSocket")

    async def _watch_ticker(self, symbol: str, normalized_symbol: str):
        """Watch ticker updates continuously.

        Args:
            symbol: Original symbol
            normalized_symbol: Exchange-normalized symbol
        """
        try:
            while self._connected:
                # CCXT Pro watch_ticker method
                ticker_data = await self.client.watch_ticker(normalized_symbol)

                ticker = Ticker(
                    symbol=symbol,
                    bid=Decimal(str(ticker_data.get('bid', 0))),
                    ask=Decimal(str(ticker_data.get('ask', 0))),
                    last=Decimal(str(ticker_data.get('last', 0))),
                    timestamp=int(ticker_data.get('timestamp', 0)),
                    raw_data=ticker_data,
                )

                # Update cache and notify callbacks
                self._update_ticker_cache(symbol, ticker)

        except asyncio.CancelledError:
            logger.info(f"Ticker watch cancelled for {symbol}")
        except Exception as e:
            logger.error(f"Error watching ticker for {symbol}: {e}")
            self._ws_connected = False

    async def unsubscribe_ticker(self, symbol: str):
        """Unsubscribe from ticker updates.

        Args:
            symbol: Trading pair symbol
        """
        # Remove callbacks
        if symbol in self._ticker_callbacks:
            del self._ticker_callbacks[symbol]

        logger.info(f"Unsubscribed from ticker updates for {symbol}")
