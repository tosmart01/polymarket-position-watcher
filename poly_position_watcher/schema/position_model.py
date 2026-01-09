# -*- coding = utf-8 -*-
# @Time: 2025/12/1 16:15
# @Author: pinbar
# @Site:
# @File: model.py
# @Software: PyCharm
from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, field_validator, model_validator

from poly_position_watcher.common.enums import Side
from poly_position_watcher.schema.base import PrettyPrintBaseModel


class MakerOrder(BaseModel):
    asset_id: str
    matched_amount: float
    size: float = 0
    order_id: str
    outcome: str
    owner: str
    price: float
    fee_rate_bps: float
    outcome_index: int | None = None
    maker_address: str
    side: Side

    @field_validator("fee_rate_bps", "price", "matched_amount", "size", mode="before")
    @classmethod
    def validate_float(cls, v: str):
        return float(v)

    @model_validator(mode="after")
    def validate_size(self):
        self.size = self.matched_amount
        return self


class TradeMessage(BaseModel):
    type: Literal["TRADE"] = "Trade"
    event_type: Literal["trade"] = "trade"

    asset_id: str
    id: str
    maker_orders: List[MakerOrder]
    transaction_hash: str
    market: str
    maker_address: str
    outcome: str
    owner: str
    price: float
    side: Side
    size: float
    status: str
    taker_order_id: str
    timestamp: int | None = None
    match_time: int | None = None
    last_update: int | None = None
    trade_owner: Optional[str] = None
    fee_rate_bps: float
    created_at: datetime | None = None
    market_slug: Optional[str] = ""

    @model_validator(mode="after")
    def validate_datetime(self):
        base_ts = self.match_time or self.last_update
        if base_ts:
            self.created_at = datetime.fromtimestamp(base_ts)
        return self

    @field_validator("timestamp", "last_update", "match_time", mode="before")
    @classmethod
    def validate_int(cls, v: str):
        if v in (None, ""):
            return None
        return int(v)

    @field_validator("fee_rate_bps", "price", "size", mode="before")
    @classmethod
    def validate_float(cls, v: str):
        return float(v)


class OrderMessage(PrettyPrintBaseModel):
    type: Optional[str] = None  # Literal["PLACEMENT", "UPDATE", "CANCELLATION"]
    event_type: Optional[str] = None  # Literal["order"]

    asset_id: Optional[str] = None
    associate_trades: Optional[List[str]] = None
    id: Optional[str]
    market: Optional[str] = None
    order_owner: Optional[str] = None
    original_size: float | None = None
    outcome: Optional[str] = None
    owner: Optional[str] = None
    price: float
    side: Literal["BUY", "SELL"]
    size_matched: float
    timestamp: float
    filled: bool = False
    status: Optional[str] = None
    created_at: datetime | None = None

    @field_validator(
        "size_matched", "price", "original_size", "timestamp", mode="before"
    )
    @classmethod
    def validate_float(cls, v: str):
        return float(v)

    @model_validator(mode="after")
    def validate_datetime(self):
        base_ts = self.timestamp
        if base_ts:
            self.created_at = datetime.fromtimestamp(base_ts / 1000)
        return self


class UserPosition(PrettyPrintBaseModel):
    price: float
    size: float
    volume: float
    token_id: Optional[str] = None
    last_update: float
    market_id: Optional[str] = None
    outcome: Optional[str] = None
    created_at: datetime | None = None
    market_slug: Optional[str] = ""
    is_failed: bool = False


class PositionDetails(BaseModel):
    """仓位详细信息"""

    buy_events: int
    sell_events: int
    total_trades: int


class PositionResult(PrettyPrintBaseModel):
    """仓位计算结果"""

    size: float
    avg_price: float
    realized_pnl: float
    amount: float
    position_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    total_pnl: Optional[float] = None
    profit_rate: Optional[float] = None
    is_long: bool
    is_short: bool
    details: PositionDetails
    last_update: float
