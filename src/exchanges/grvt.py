"""GRVT exchange adapter."""

import aiohttp
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


class GRVTExchange(BaseExchange):
    """GRVT exchange implementation."""

    def __init__(self, config: Dict[str, Any], credentials: Dict[str, str]):
        """Initialize GRVT adapter."""
        super().__init__(config, credentials)
        self.base_url = "https://api.grvt.io" if not self.testnet else "https://testnet.grvt.io"
        self.session: Optional[aiohttp.ClientSession] = None

    async def connect(self):
        """Connect to GRVT."""
        logger.info(f"Connecting to GRVT ({self.base_url})...")
        self.session = aiohttp.ClientSession(
            headers={
                "Content-Type": "application/json",
                "X-API-KEY": self.credentials.get("api_key", ""),
            }
        )
        self._connected = True
        logger.info("Connected to GRVT")

    async def disconnect(self):
        """Disconnect from GRVT."""
        if self.session:
            await self.session.close()
        self._connected = False
        logger.info("Disconnected from GRVT")

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make API request.

        Args:
            method: HTTP method
            endpoint: API endpoint
            **kwargs: Additional request parameters

        Returns:
            Response data
        """
        if not self.session:
            raise RuntimeError("Not connected to exchange")

        url = f"{self.base_url}{endpoint}"
        async with self.session.request(method, url, **kwargs) as response:
            response.raise_for_status()
            return await response.json()

    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        size: Decimal,
        price: Optional[Decimal] = None,
        **kwargs
    ) -> Order:
        """Create order on GRVT."""
        logger.info(f"Creating {side.value} {order_type.value} order: {size} {symbol} @ {price}")

        # TODO: Implement actual GRVT API call
        # This is a placeholder implementation
        # You'll need to consult GRVT API documentation for exact format

        payload = {
            "symbol": self.normalize_symbol(symbol),
            "side": side.value,
            "type": order_type.value,
            "quantity": str(size),
        }

        if price:
            payload["price"] = str(price)

        try:
            # response = await self._request("POST", "/v1/order", json=payload)
            # For now, return mock order
            return Order(
                id="mock_order_id",
                symbol=symbol,
                side=side,
                type=order_type,
                price=price or Decimal("0"),
                size=size,
                status=OrderStatus.OPEN,
            )
        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            raise

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel order on GRVT."""
        logger.info(f"Cancelling order {order_id} for {symbol}")
        # TODO: Implement actual API call
        return True

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel all orders on GRVT."""
        logger.info(f"Cancelling all orders for {symbol or 'all symbols'}")
        # TODO: Implement actual API call
        return 0

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get open orders from GRVT."""
        # TODO: Implement actual API call
        return []

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position from GRVT."""
        # TODO: Implement actual API call
        return None

    async def close_position(self, symbol: str) -> bool:
        """Close position on GRVT."""
        logger.info(f"Closing position for {symbol}")
        # TODO: Implement actual API call
        return True

    async def get_balance(self) -> Balance:
        """Get balance from GRVT."""
        # TODO: Implement actual API call
        return Balance(
            total=Decimal("10000"),
            available=Decimal("10000"),
            used=Decimal("0"),
        )

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker from GRVT."""
        # TODO: Implement actual API call
        import time
        return Ticker(
            symbol=symbol,
            bid=Decimal("50000"),
            ask=Decimal("50001"),
            last=Decimal("50000.5"),
            timestamp=int(time.time() * 1000),
        )

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage on GRVT."""
        logger.info(f"Setting leverage to {leverage}x for {symbol}")
        # TODO: Implement actual API call
        return True

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to GRVT format (e.g., BTC -> BTC-USD-PERP)."""
        if "-" in symbol:
            return symbol
        return f"{symbol}-USD-PERP"
