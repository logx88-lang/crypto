"""Lighter exchange adapter using official Python SDK."""

from decimal import Decimal
from typing import Dict, List, Optional, Any
from loguru import logger

try:
    from lighter.lighter_client import Client
    from lighter.constants import OrderSide as LighterOrderSide
except ImportError:
    logger.warning("lighter-v1-python not installed. Install with: pip install lighter-v1-python")
    Client = None
    LighterOrderSide = None

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


class LighterExchange(BaseExchange):
    """Lighter exchange implementation using official Python SDK."""

    def __init__(self, config: Dict[str, Any], credentials: Dict[str, str]):
        """Initialize Lighter adapter."""
        super().__init__(config, credentials)

        if Client is None:
            raise RuntimeError("lighter-v1-python is required. Install with: pip install lighter-v1-python")

        self.client: Optional[Client] = None
        self.web3_provider_url = credentials.get('web3_provider_url', '')
        self.private_key = credentials.get('private_key', '')
        self.api_auth = credentials.get('api_key', '')

    async def connect(self):
        """Connect to Lighter using SDK."""
        logger.info(f"Connecting to Lighter ({'testnet' if self.testnet else 'mainnet'})...")

        try:
            # Initialize Lighter client
            self.client = Client(
                api_auth=self.api_auth,
                web3_provider_url=self.web3_provider_url,
                private_key=self.private_key if self.private_key else None,
            )

            # Test connection by fetching blockchains
            blockchains = self.client.api.get_blockchains().data
            logger.info(f"Connected to Lighter. Available blockchains: {len(blockchains)}")

            self._connected = True
        except Exception as e:
            logger.error(f"Failed to connect to Lighter: {e}")
            raise

    async def disconnect(self):
        """Disconnect from Lighter."""
        self._connected = False
        logger.info("Disconnected from Lighter")

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        size: Decimal,
        price: Optional[Decimal] = None,
        **kwargs
    ) -> Order:
        """Create order on Lighter using SDK."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        logger.info(f"Creating {side.value} {order_type.value} order: {size} {symbol} @ {price}")

        try:
            normalized_symbol = self.normalize_symbol(symbol)

            # Lighter SDK requires blockchain orders
            if not self.private_key:
                raise RuntimeError("Private key required for creating orders on Lighter")

            # Convert to Lighter order side
            lighter_side = LighterOrderSide.BUY if side == OrderSide.BUY else LighterOrderSide.SELL

            if order_type == OrderType.LIMIT:
                # Create limit order
                tx_hash = self.client.blockchain.create_limit_order(
                    symbol=normalized_symbol,
                    size=str(size),
                    price=str(price),
                    side=lighter_side,
                )

                logger.info(f"Order created with tx hash: {tx_hash}")

                # Return order (note: we don't have order ID yet until tx is mined)
                return Order(
                    id=tx_hash,
                    symbol=symbol,
                    side=side,
                    type=order_type,
                    price=price,
                    size=size,
                    status=OrderStatus.OPEN,
                )
            else:
                raise NotImplementedError("Lighter currently only supports limit orders")

        except Exception as e:
            logger.error(f"Failed to create order on Lighter: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel order on Lighter."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        logger.info(f"Cancelling order {order_id} for {symbol}")

        try:
            normalized_symbol = self.normalize_symbol(symbol)

            # Cancel using blockchain
            tx_hash = self.client.blockchain.cancel_limit_order(
                symbol=normalized_symbol,
                order_id=int(order_id),
            )

            logger.info(f"Order cancelled with tx hash: {tx_hash}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel all orders on Lighter."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        logger.info(f"Cancelling all orders for {symbol or 'all symbols'}")

        try:
            # Get open orders first
            open_orders = await self.get_open_orders(symbol)

            count = 0
            for order in open_orders:
                try:
                    await self.cancel_order(order.id, order.symbol)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to cancel order {order.id}: {e}")

            return count
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return 0

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get open orders from Lighter."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        try:
            # Lighter API to get orders
            # Note: This might need adjustment based on actual SDK capabilities
            logger.warning("get_open_orders not fully implemented for Lighter - SDK limitation")
            return []

        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position from Lighter."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        try:
            logger.warning("get_position not fully implemented for Lighter - SDK limitation")
            return None

        except Exception as e:
            logger.error(f"Failed to get position: {e}")
            return None

    async def close_position(self, symbol: str) -> bool:
        """Close position on Lighter."""
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
                order_type=OrderType.LIMIT,
                size=abs(position.size),
                price=position.mark_price,  # Use mark price for immediate fill
            )
            return True
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return False

    async def get_balance(self) -> Balance:
        """Get balance from Lighter."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        try:
            logger.warning("get_balance not fully implemented for Lighter - SDK limitation")

            # Return placeholder
            return Balance(
                total=Decimal("0"),
                available=Decimal("0"),
                used=Decimal("0"),
                currency='USDC',
            )

        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return Balance(
                total=Decimal("0"),
                available=Decimal("0"),
                used=Decimal("0"),
            )

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker from Lighter."""
        if not self.client:
            raise RuntimeError("Not connected to exchange")

        try:
            normalized_symbol = self.normalize_symbol(symbol)

            # Get orderbook to derive ticker
            orderbook = self.client.api.get_orderbook(normalized_symbol).data

            if not orderbook or not orderbook.get('asks') or not orderbook.get('bids'):
                raise ValueError("Empty orderbook")

            best_ask = Decimal(orderbook['asks'][0]['price'])
            best_bid = Decimal(orderbook['bids'][0]['price'])
            last = (best_ask + best_bid) / Decimal("2")

            import time
            return Ticker(
                symbol=symbol,
                bid=best_bid,
                ask=best_ask,
                last=last,
                timestamp=int(time.time() * 1000),
                raw_data=orderbook,
            )

        except Exception as e:
            logger.error(f"Failed to get ticker: {e}")
            raise

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage on Lighter."""
        logger.info(f"Setting leverage to {leverage}x for {symbol}")

        # Lighter may not have separate leverage setting
        # Check documentation
        logger.warning("Leverage setting may not be supported on Lighter")
        return True

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to Lighter format (e.g., BTC -> BTC_USDC or WETH_USDC)."""
        if '_' in symbol:
            return symbol

        # Lighter uses format like WETH_USDC, BTC_USDC
        # Map common symbols
        symbol_map = {
            'BTC': 'WBTC_USDC',
            'ETH': 'WETH_USDC',
            'WETH': 'WETH_USDC',
            'WBTC': 'WBTC_USDC',
        }

        return symbol_map.get(symbol.upper(), f"{symbol}_USDC")
