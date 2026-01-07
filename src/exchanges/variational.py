"""Variational exchange adapter using REST API.

Note: Variational API is currently in pre-launch phase.
API key generation may not be available yet.
"""

import aiohttp
import hmac
import hashlib
import time
from decimal import Decimal
from typing import Dict, List, Optional, Any
from loguru import logger

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


class VariationalExchange(BaseExchange):
    """Variational exchange implementation using REST API."""

    def __init__(self, config: Dict[str, Any], credentials: Dict[str, str]):
        """Initialize Variational adapter."""
        super().__init__(config, credentials)
        # Variational API endpoint (adjust based on actual documentation)
        self.base_url = "https://api.variational.io/v1" if not self.testnet else "https://api-testnet.variational.io/v1"
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_key = credentials.get("api_key", "")
        self.api_secret = credentials.get("api_secret", "")

    async def connect(self):
        """Connect to Variational."""
        logger.info(f"Connecting to Variational ({self.base_url})...")

        # Check if API key is available
        if not self.api_key:
            logger.warning("Variational API key not configured. Note: API may be in pre-launch phase.")

        self.session = aiohttp.ClientSession(
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        self._connected = True
        logger.info("Connected to Variational")

    async def disconnect(self):
        """Disconnect from Variational."""
        if self.session:
            await self.session.close()
        self._connected = False
        logger.info("Disconnected from Variational")

    def _generate_signature(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """Generate HMAC signature for authentication."""
        if not self.api_secret:
            return ""

        message = f"{timestamp}{method}{path}{body}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make authenticated API request."""
        if not self.session:
            raise RuntimeError("Not connected to exchange")

        url = f"{self.base_url}{endpoint}"
        timestamp = str(int(time.time() * 1000))

        # Add authentication headers
        headers = kwargs.pop('headers', {})
        if self.api_key:
            body = kwargs.get('json', {})
            body_str = str(body) if body else ""
            signature = self._generate_signature(timestamp, method, endpoint, body_str)

            headers.update({
                "X-API-KEY": self.api_key,
                "X-TIMESTAMP": timestamp,
                "X-SIGNATURE": signature,
            })

        try:
            async with self.session.request(method, url, headers=headers, **kwargs) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as e:
            logger.error(f"API request failed: {e.status} - {e.message}")
            raise

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        size: Decimal,
        price: Optional[Decimal] = None,
        **kwargs
    ) -> Order:
        """Create order on Variational."""
        logger.info(f"Creating {side.value} {order_type.value} order: {size} {symbol} @ {price}")

        try:
            normalized_symbol = self.normalize_symbol(symbol)

            payload = {
                "symbol": normalized_symbol,
                "side": side.value.upper(),
                "type": order_type.value.upper(),
                "quantity": str(size),
            }

            if price and order_type == OrderType.LIMIT:
                payload["price"] = str(price)

            # Note: Actual endpoint may vary - check Variational API docs
            response = await self._request("POST", "/orders", json=payload)

            return Order(
                id=response.get("orderId", response.get("id", "unknown")),
                symbol=symbol,
                side=side,
                type=order_type,
                price=price or Decimal("0"),
                size=size,
                status=OrderStatus.OPEN,
                raw_data=response,
            )

        except Exception as e:
            logger.error(f"Failed to create order on Variational: {e}")
            # Return mock order if API not available
            logger.warning("Returning mock order - API may not be available")
            return Order(
                id="mock_order_id",
                symbol=symbol,
                side=side,
                type=order_type,
                price=price or Decimal("0"),
                size=size,
                status=OrderStatus.OPEN,
            )

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel order on Variational."""
        logger.info(f"Cancelling order {order_id} for {symbol}")

        try:
            await self._request("DELETE", f"/orders/{order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel all orders on Variational."""
        logger.info(f"Cancelling all orders for {symbol or 'all symbols'}")

        try:
            params = {"symbol": self.normalize_symbol(symbol)} if symbol else {}
            response = await self._request("DELETE", "/orders", params=params)
            return response.get("cancelledCount", 0)
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return 0

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get open orders from Variational."""
        try:
            params = {"symbol": self.normalize_symbol(symbol)} if symbol else {}
            response = await self._request("GET", "/orders", params=params)

            orders = []
            for order_data in response.get("orders", []):
                orders.append(self._parse_order(order_data))

            return orders
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position from Variational."""
        try:
            normalized_symbol = self.normalize_symbol(symbol)
            response = await self._request("GET", f"/positions/{normalized_symbol}")

            if not response or response.get("size") == 0:
                return None

            return Position(
                symbol=symbol,
                size=Decimal(str(response.get("size", 0))),
                entry_price=Decimal(str(response.get("entryPrice", 0))),
                mark_price=Decimal(str(response.get("markPrice", 0))),
                unrealized_pnl=Decimal(str(response.get("unrealizedPnl", 0))),
                leverage=int(response.get("leverage", 1)),
                side='long' if float(response.get("size", 0)) > 0 else 'short',
                raw_data=response,
            )
        except Exception as e:
            logger.error(f"Failed to get position: {e}")
            return None

    async def close_position(self, symbol: str) -> bool:
        """Close position on Variational."""
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
        """Get balance from Variational."""
        try:
            response = await self._request("GET", "/account/balance")

            return Balance(
                total=Decimal(str(response.get("total", 0))),
                available=Decimal(str(response.get("available", 0))),
                used=Decimal(str(response.get("used", 0))),
                currency=response.get("currency", "USD"),
                raw_data=response,
            )
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return Balance(
                total=Decimal("0"),
                available=Decimal("0"),
                used=Decimal("0"),
            )

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker from Variational."""
        try:
            normalized_symbol = self.normalize_symbol(symbol)
            response = await self._request("GET", f"/market/ticker/{normalized_symbol}")

            return Ticker(
                symbol=symbol,
                bid=Decimal(str(response.get("bid", 0))),
                ask=Decimal(str(response.get("ask", 0))),
                last=Decimal(str(response.get("last", 0))),
                timestamp=int(response.get("timestamp", time.time() * 1000)),
                raw_data=response,
            )
        except Exception as e:
            logger.error(f"Failed to get ticker: {e}")
            # Return mock data if API not available
            import time as t
            return Ticker(
                symbol=symbol,
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                last=Decimal("50000.5"),
                timestamp=int(t.time() * 1000),
            )

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage on Variational."""
        logger.info(f"Setting leverage to {leverage}x for {symbol}")

        try:
            normalized_symbol = self.normalize_symbol(symbol)
            await self._request("POST", "/account/leverage", json={
                "symbol": normalized_symbol,
                "leverage": leverage,
            })
            return True
        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            return False

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to Variational format (e.g., BTC -> BTCUSD)."""
        if "USD" in symbol or "PERP" in symbol:
            return symbol

        # Variational typically uses BTCUSD, ETHUSD format
        return f"{symbol}USD"

    def _parse_order(self, order_data: Dict) -> Order:
        """Parse API order response to our Order format."""
        return Order(
            id=order_data.get("id", order_data.get("orderId", "unknown")),
            symbol=order_data.get("symbol", ""),
            side=OrderSide.BUY if order_data.get("side", "").lower() == "buy" else OrderSide.SELL,
            type=OrderType.LIMIT if order_data.get("type", "").lower() == "limit" else OrderType.MARKET,
            price=Decimal(str(order_data.get("price", 0))),
            size=Decimal(str(order_data.get("quantity", order_data.get("size", 0)))),
            status=self._parse_order_status(order_data.get("status", "open")),
            filled_size=Decimal(str(order_data.get("filledQuantity", 0))),
            timestamp=order_data.get("timestamp"),
            raw_data=order_data,
        )

    def _parse_order_status(self, status: str) -> OrderStatus:
        """Parse order status string to OrderStatus enum."""
        status_map = {
            'open': OrderStatus.OPEN,
            'filled': OrderStatus.FILLED,
            'canceled': OrderStatus.CANCELLED,
            'cancelled': OrderStatus.CANCELLED,
            'rejected': OrderStatus.REJECTED,
        }
        return status_map.get(status.lower(), OrderStatus.OPEN)
