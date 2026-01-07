"""Base abstract class for exchange adapters."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal


class OrderSide(Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type enumeration."""
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(Enum):
    """Order status enumeration."""
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    """Order representation."""
    id: str
    symbol: str
    side: OrderSide
    type: OrderType
    price: Decimal
    size: Decimal
    status: OrderStatus
    filled_size: Decimal = Decimal("0")
    timestamp: Optional[int] = None
    raw_data: Optional[Dict] = None


@dataclass
class Position:
    """Position representation."""
    symbol: str
    size: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    leverage: int
    side: str  # "long" or "short"
    raw_data: Optional[Dict] = None


@dataclass
class Balance:
    """Balance/Collateral representation."""
    total: Decimal
    available: Decimal
    used: Decimal
    currency: str = "USD"
    raw_data: Optional[Dict] = None


@dataclass
class Ticker:
    """Market ticker data."""
    symbol: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    timestamp: int
    raw_data: Optional[Dict] = None


class BaseExchange(ABC):
    """Abstract base class for exchange implementations."""

    def __init__(self, config: Dict[str, Any], credentials: Dict[str, str]):
        """Initialize exchange adapter.

        Args:
            config: Exchange configuration
            credentials: API credentials
        """
        self.config = config
        self.credentials = credentials
        self.name = config.get("name", "Unknown")
        self.testnet = config.get("testnet", True)
        self._connected = False

    @abstractmethod
    async def connect(self):
        """Connect to exchange."""
        pass

    @abstractmethod
    async def disconnect(self):
        """Disconnect from exchange."""
        pass

    @abstractmethod
    async def create_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        size: Decimal,
        price: Optional[Decimal] = None,
        **kwargs
    ) -> Order:
        """Create a new order.

        Args:
            symbol: Trading pair symbol
            side: Order side (buy/sell)
            order_type: Order type (limit/market)
            size: Order size
            price: Order price (required for limit orders)
            **kwargs: Additional exchange-specific parameters

        Returns:
            Created order
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order.

        Args:
            order_id: Order ID to cancel
            symbol: Trading pair symbol

        Returns:
            True if cancelled successfully
        """
        pass

    @abstractmethod
    async def cancel_all_orders(self, symbol: Optional[str] = None) -> int:
        """Cancel all orders.

        Args:
            symbol: Trading pair symbol (if None, cancel all symbols)

        Returns:
            Number of cancelled orders
        """
        pass

    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get open orders.

        Args:
            symbol: Trading pair symbol (if None, get all symbols)

        Returns:
            List of open orders
        """
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position.

        Args:
            symbol: Trading pair symbol

        Returns:
            Position if exists, None otherwise
        """
        pass

    @abstractmethod
    async def close_position(self, symbol: str) -> bool:
        """Close position.

        Args:
            symbol: Trading pair symbol

        Returns:
            True if closed successfully
        """
        pass

    @abstractmethod
    async def get_balance(self) -> Balance:
        """Get account balance/collateral.

        Returns:
            Account balance
        """
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """Get market ticker.

        Args:
            symbol: Trading pair symbol

        Returns:
            Market ticker data
        """
        pass

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for symbol.

        Args:
            symbol: Trading pair symbol
            leverage: Leverage value

        Returns:
            True if set successfully
        """
        pass

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to exchange format.

        Args:
            symbol: Generic symbol (e.g., "BTC")

        Returns:
            Exchange-specific symbol format
        """
        # Override in subclass if needed
        return symbol

    @property
    def is_connected(self) -> bool:
        """Check if connected to exchange."""
        return self._connected
