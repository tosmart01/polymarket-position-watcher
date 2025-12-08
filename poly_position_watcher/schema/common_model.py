# -*- coding = utf-8 -*-
# @Time: 2025/10/13 10:03
# @Author: pinbar
# @Site:
# @File: schema.py
# @Software: PyCharm
import time
from typing import Optional
from pydantic import BaseModel, model_validator, Field

from poly_position_watcher.common.enums import Side
from poly_position_watcher.schema.base import PrettyPrintBaseModel


class OrderSummary(BaseModel):
    price: float = None
    size: float = None
    size_cumsum: float = None


class OrderBookSummary(BaseModel):
    market: str = None
    period: Optional[str] = None
    asset_id: str = None
    timestamp: float = None
    bids: Optional[list[OrderSummary]] = None
    asks: Optional[list[OrderSummary]] = None
    min_order_size: str = None
    neg_risk: bool = None
    tick_size: str = None
    hash: str = None

    def flush_cumsum(self):
        tick_size = len(self.tick_size) - 2
        for item in [[*self.bids], [*self.asks]]:
            cumsum = 0
            for row in item[::-1]:
                row.size = float(row.size)
                row.price = round(float(row.price), tick_size)
                cumsum += row.size
                row.size_cumsum = cumsum

    def set_price(self, item: dict, timestamp):
        tick_size = len(self.tick_size) - 2
        new_price = round(float(item["price"]), tick_size)
        for row in [*self.asks, *self.bids]:
            if row.price == new_price:
                row.size = float(item["size"])
        self.timestamp = timestamp
        self.flush_cumsum()

    @model_validator(mode="before")
    @classmethod
    def validate_fields(cls, values: dict):
        if isinstance(values, dict):
            if timestamp := values.get("timestamp"):
                values["timestamp"] = int(timestamp) / 1000
            tick_size = len(values.get("tick_size")) - 2
            for item in [values.get("bids", []), values.get("asks", [])]:
                cumsum = 0
                for row in item[::-1]:
                    row["size"] = float(row["size"])
                    row["price"] = round(float(row["price"]), tick_size)
                    cumsum += row["size"]
                    row["size_cumsum"] = cumsum
        return values

    def print_order_book(
        self,
    ) -> str:
        """漂亮打印盘口，不依赖第三方库，返回字符串"""
        depth = 8
        bids = self.bids[-depth:]
        asks = self.asks[-depth:]

        lines = []
        lines.append("\n📊 Order Book Summary")
        lines.append(f"Min Order Size: {self.min_order_size}")
        lines.append(f"Tick Size: {self.tick_size}")
        lines.append(f"{'Price':>10} | {'Size':>12} | {'Size_Cumsum':>12}")
        lines.append("-" * 30)

        # 卖单从高到低打印（视觉上上方高价）
        for ask in asks:
            lines.append(
                f"{ask.price:>10.3f} | {ask.size:>12,.2f} | {ask.size_cumsum:>12,.2f}"
            )

        lines.append("-" * 30)

        for bid in reversed(bids):
            lines.append(
                f"{bid.price:>10.3f} | {bid.size:>12,.2f} | {bid.size_cumsum:>12,.2f}"
            )

        lines.append("-" * 30)
        lines.append("")

        return "\n".join(lines)


class UserPosition(PrettyPrintBaseModel):
    buy_price: Optional[float] = 0
    sell_price: Optional[float] = 0
    original_size: Optional[float] = 0
    buy_size_matched: Optional[float] = 0
    status: Optional[str] = None
    remaining_size: Optional[float] = 0
    sell_size_matched: Optional[float] = 0


class MarketOrder(BaseModel):
    order_id: Optional[str] = None
    slug: str = None
    token_id: str = None
    shares: float = None
    side: Side = None
    amount: float = None
    take_profit: float = 0
    price: float = None
    tick_size: str = None
    neg_risk: bool = None


class StreakPosition(PrettyPrintBaseModel):
    shares: float = None
    origin_shares: float = None
    price: float = None
    real_price: float = None
    volume: float = None
    real_volume: float = None
    combine_now: str = ""
    side: str = ""
    market: str = ""
    streak_len: int = 2


class PeakData(BaseModel):
    """峰值数据模型"""

    is_peak: bool
    peak_idx: int = None
    peak_value: float = None
    left: float = None
    center: float = None
    right: float = None
    center_token_id: Optional[str] = Field(None, description="中心token ID")
    right_token_id: Optional[str] = Field(None, description="右侧token ID")
    left_token_id: Optional[str] = Field(None, description="左侧token ID")
    last_update: float = Field(default_factory=time.time)
