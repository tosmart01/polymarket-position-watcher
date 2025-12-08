"""High level service for monitoring Polymarket positions in real time."""

from .position_service import PositionWatcherService
from .schema.position_model import UserPosition, TradeMessage, OrderMessage
from .trade_calculator import calculate_position_from_trades, calculate_position_with_price
from ._version import __version__

__all__ = [
    "PositionWatcherService",
    "calculate_position_from_trades",
    "calculate_position_with_price",
    "UserPosition",
    "TradeMessage",
    "OrderMessage",
    "__version__",
]
