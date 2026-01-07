"""Pacifica exchange adapter."""

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


class PacificaExchange(BaseExchange):
    """Pacifica exchange implementation."""

    def __init__(self, config: Dict[str, Any], credentials: Dict[str, str]):
        """Initialize Pacifica adapter."""
        super().__init__(config, credentials)
        self.base_url = "https://api.pacifica.exchange" if not self.testnet else "https://testnet.pacifica.exchange"
        self.session: Optional[aiohttp.ClientSession] = None

    async def connect(self):
        """Connect to Pacifica."""
        logger.info(f"Connecting to Pacifica ({self.base_url})...")
        self.session = aiohttp.ClientSession(
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.credentials.get('api_key', '')}",
            }
        )
        self._connected = True
        logger.info("Connected to Pacifica")

    async def disconnect(self):
        """Disconnect from Pacifica."""
        if self.session:
            await self.session.close()
        self._connected = False
        logger.info("Disconnected from Pacifica")

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make API request."""
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
        """Create order on Pacifica."""
        logger.info(f"Creating {side.value} {order_type.value} order: {size} {symbol} @ {price}")

        # TODO: Implement actual Pacifica API call
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
        """Cancel order on Pacifica."""
        logger.info(f"Cancelling order {order_id} for {symbol}")
        return True

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel all orders on Pacifica."""
        logger.info(f"Cancelling all orders for {symbol or 'all symbols'}")
        return 0

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get open orders from Pacifica."""
        return []

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position from Pacifica."""
        return None

    async def close_position(self, symbol: str) -> bool:
        """Close position on Pacifica."""
        logger.info(f"Closing position for {symbol}")
        return True

    async def get_balance(self) -> Balance:
        """Get balance from Pacifica."""
        return Balance(
            total=Decimal("10000"),
            available=Decimal("10000"),
            used=Decimal("0"),
        )

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get ticker from Pacifica."""
        import time
        return Ticker(
            symbol=symbol,
            bid=Decimal("50000"),
            ask=Decimal("50001"),
            last=Decimal("50000.5"),
            timestamp=int(time.time() * 1000),
        )

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage on Pacifica."""
        logger.info(f"Setting leverage to {leverage}x for {symbol}")
        return True

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to Pacifica format (e.g., BTC -> BTC_USD_PERP)."""
        if "_" in symbol:
            return symbol
        return f"{symbol}_USD_PERP"
