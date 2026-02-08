"""Enum definitions used across the position watcher package."""

from __future__ import annotations

from enum import Enum


class Side(str, Enum):
    """Order side in Polymarket's CLOB."""

    BUY = "BUY"
    SELL = "SELL"


class MarketEvent(str, Enum):
    """Supported market level websocket event names."""

    PRICE_CHANGE = "price_change"
    TICK_SIZE_CHANGE = "tick_size_change"
    BOOK = "book"


class TradeStatus(str, Enum):
    """Trade status values from Polymarket."""

    MATCHED = "MATCHED"
    MINED = "MINED"
    CONFIRMED = "CONFIRMED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
