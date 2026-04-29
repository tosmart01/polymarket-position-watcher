# -*- coding = utf-8 -*-
# @Time: 2025-12-06 15:50:02
# @Author: Donvink wuwukai
# @Site:
# @File: trade_calculator.py
# @Software: PyCharm
from collections import deque
from typing import Any, Callable, List, Mapping

from poly_position_watcher.common.enums import Side
from poly_position_watcher.common.logger import logger
from poly_position_watcher.schema.position_model import (
    PositionResult,
    PositionDetails,
    TradeMessage,
)

_MISSING_FEE_SCHEDULE_WARNED_MARKETS: set[str] = set()


def _default_fee_calc(
    size: float,
    price: float,
    side: Side | str,
    fee_schedule: Mapping[str, Any],
) -> tuple[float, float]:
    rate = float(fee_schedule.get("rate") or 0.0)
    if size <= 0 or price <= 0 or rate <= 0:
        return size, 0.0

    fee_amount = round(max(size * rate * price * (1 - price), 0.0), 5)
    if fee_amount <= 0:
        return size, 0.0

    return size, fee_amount


def calculate_position_from_trades(
    trades: List[TradeMessage],
    user_address: str,
    enable_fee_calc: bool = False,
    fee_schedule_by_market: Mapping[str, Mapping[str, Any]] | None = None,
    fee_calc_fn: Callable[
        [float, float, Side | str, Mapping[str, Any]],
        tuple[float, float],
    ]
    | None = None,
) -> PositionResult:
    """
    根据交易记录直接计算用户仓位（带浮点误差修正）
    """

    # ==== 新增：统一误差阈值 ====
    EPS = 0.01

    def clean(x: float) -> float:
        return 0.0 if abs(x) < EPS else x

    buy_events = []
    sell_events = []
    total_original_size = 0.0

    def apply_fee(
        size: float,
        price: float,
        side: Side | str,
        market_id: str | None,
        trader_side: str | None,
    ) -> tuple[float, float]:
        fee_schedule = (
            fee_schedule_by_market.get(market_id or "")
            if fee_schedule_by_market
            else None
        )
        if not enable_fee_calc or not fee_schedule:
            if enable_fee_calc and market_id and market_id not in _MISSING_FEE_SCHEDULE_WARNED_MARKETS:
                logger.warning(
                    "Fee calculation enabled but feeSchedule is missing for market {}; fee is skipped until it is registered.",
                    market_id,
                )
                _MISSING_FEE_SCHEDULE_WARNED_MARKETS.add(market_id)
            return size, 0.0
        taker_only = bool(fee_schedule.get("takerOnly", False))
        if taker_only and trader_side != "TAKER":
            return size, 0.0
        calc = fee_calc_fn or _default_fee_calc
        return calc(size, price, side, fee_schedule)

    total_fee_amount = 0.0

    # --- 1. 解析所有交易 ---
    for trade in trades:
        is_maker_order = False

        # maker 部分
        for order in trade.maker_orders:
            if order.maker_address.upper() != user_address.upper():
                continue
            is_maker_order = True
            event_time = trade.event_time
            size, fee_amount = apply_fee(
                order.size,
                order.price,
                order.side,
                trade.market,
                trade.trader_side,
            )
            total_fee_amount += fee_amount

            if order.side == Side.BUY:
                buy_events.append(
                    (size, order.price, event_time, order.size * order.price)
                )
                total_original_size += order.size
            else:
                sell_events.append(
                    (
                        -size,
                        order.price,
                        event_time,
                        size * order.price - fee_amount,
                    )
                )
                total_original_size -= order.size

        # taker 部分
        if not is_maker_order and trade.maker_address.upper() == user_address.upper():
            event_time = trade.event_time
            size, fee_amount = apply_fee(
                trade.size,
                trade.price,
                trade.side,
                trade.market,
                trade.trader_side,
            )
            total_fee_amount += fee_amount
            if trade.side == Side.BUY:
                buy_events.append(
                    (size, trade.price, event_time, trade.size * trade.price)
                )
                total_original_size += trade.size
            else:
                sell_events.append(
                    (
                        -size,
                        trade.price,
                        event_time,
                        size * trade.price - fee_amount,
                    )
                )
                total_original_size -= trade.size

    # --- 2. 时间排序 ---
    all_events = sorted(buy_events + sell_events, key=lambda x: x[2])

    # --- 3. FIFO 撮合 ---
    buy_queue = deque()
    realized_pnl = 0.0

    for size, price, _, cash_amount in all_events:
        size = clean(size)  # ← 新增：修正

        if size > 0:
            # 买入加入队列
            unit_cost = cash_amount / size if size else price
            buy_queue.append([size, unit_cost])

        else:
            # 卖出（size 为负）
            sell_size = clean(-size)
            sell_price = cash_amount / sell_size if sell_size else price

            while sell_size > EPS and buy_queue:
                lot_size, lot_price = buy_queue[0]

                if lot_size <= sell_size + EPS:
                    # 完全消耗
                    realized_pnl += (sell_price - lot_price) * lot_size
                    sell_size -= lot_size
                    buy_queue.popleft()
                else:
                    # 部分消耗
                    realized_pnl += (sell_price - lot_price) * sell_size
                    buy_queue[0][0] = clean(lot_size - sell_size)
                    sell_size = 0.0

            # 如果还有卖不完 → 变成空头
            if sell_size > EPS:
                buy_queue.appendleft([-sell_size, sell_price])

    # --- 4. 计算最终持仓 ---
    total_size = clean(sum(q[0] for q in buy_queue))
    original_size = clean(total_original_size)
    cost_basis = clean(sum(clean(q[0]) * q[1] for q in buy_queue))

    # 若因误差产生 0.0000003 的 ghost position → 完全清掉
    if abs(total_size) < EPS:
        total_size = 0.0
        cost_basis = 0.0
    if abs(original_size) < EPS:
        original_size = 0.0

    avg_price = cost_basis / total_size if total_size != 0 else 0.0

    return PositionResult(
        size=total_size,
        original_size=original_size,
        avg_price=avg_price,
        realized_pnl=realized_pnl,
        amount=cost_basis,
        fee_amount=total_fee_amount,
        is_long=total_size > 0,
        is_short=total_size < 0,
        details=PositionDetails(
            buy_events=len(buy_events),
            sell_events=len(sell_events),
            total_trades=len(all_events),
        ),
        last_update=max((trade.event_time for trade in trades), default=0),
    )


def calculate_position_with_price(
    trades: List[TradeMessage], user_address: str, market_price: float
) -> PositionResult:
    """
    包含市场价格的仓位计算

    Args:
        market_price: 当前市场价格

    Returns:
        额外包含:
        - position_value: 持仓市值
        - unrealized_pnl: 未实现盈亏
        - total_pnl: 总盈亏
    """
    position = calculate_position_from_trades(trades, user_address)
    size = position.size

    if size != 0:
        position_value = size * market_price
        position.position_value = position_value
        cost_basis = position.amount
        unrealized = position_value - cost_basis
        position.unrealized_pnl = unrealized
        position.total_pnl = position.realized_pnl + unrealized
        position.profit_rate = (
            position.total_pnl / cost_basis * 100 if cost_basis else None
        )

    return position
