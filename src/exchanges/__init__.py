"""Exchange adapters for multi-exchange bot."""

from .base import BaseExchange, Order, Position, Balance, Ticker, OrderSide, OrderType, OrderStatus
from .grvt import GRVTExchange
from .lighter import LighterExchange
from .variational import VariationalExchange
from .pacifica import PacificaExchange

__all__ = [
    "BaseExchange",
    "Order",
    "Position",
    "Balance",
    "Ticker",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "GRVTExchange",
    "LighterExchange",
    "VariationalExchange",
    "PacificaExchange",
]


def create_exchange(exchange_name: str, config: dict, credentials: dict) -> BaseExchange:
    """Factory function to create exchange instances.

    Args:
        exchange_name: Name of exchange (grvt, lighter, variational, pacifica)
        config: Exchange configuration
        credentials: API credentials

    Returns:
        Exchange instance

    Raises:
        ValueError: If exchange name is not supported
    """
    exchanges = {
        "grvt": GRVTExchange,
        "lighter": LighterExchange,
        "variational": VariationalExchange,
        "pacifica": PacificaExchange,
    }

    exchange_class = exchanges.get(exchange_name.lower())
    if not exchange_class:
        raise ValueError(f"Unsupported exchange: {exchange_name}")

    return exchange_class(config, credentials)
