# -*- coding = utf-8 -*-
# @Time: 2025-12-06 15:50:02
# @Author: Donvink wuwukai
# @Site:
# @File: trade_calculator.py
# @Software: PyCharm
from collections import deque
from typing import Callable, List

from poly_position_watcher.common.enums import Side
from poly_position_watcher.schema.position_model import (
    PositionResult,
    PositionDetails,
    TradeMessage,
)


def _default_fee_calc(size: float, price: float, fee_rate_bps: float) -> float:
    fee_multiplier = fee_rate_bps / 1000 if fee_rate_bps else 0.0
    fee = 0.25 * (price * (1 - price)) ** 2 * fee_multiplier
    return (1 - fee) * size


def calculate_position_from_trades(
    trades: List[TradeMessage],
    user_address: str,
    enable_fee_calc: bool = False,
    fee_calc_fn: Callable[[float, float, float], float] | None = None,
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

    def apply_fee(size: float, price: float, fee_rate_bps: float) -> float:
        if not enable_fee_calc or fee_rate_bps <= 0:
            return size
        calc = fee_calc_fn or _default_fee_calc
        return calc(size, price, fee_rate_bps)

    # --- 1. 解析所有交易 ---
    for trade in trades:
        is_maker_order = False

        # maker 部分
        for order in trade.maker_orders:
            if order.maker_address.upper() != user_address.upper():
                continue
            is_maker_order = True
            size = apply_fee(order.size, order.price, order.fee_rate_bps)

            if order.side == Side.BUY:
                buy_events.append((size, order.price, trade.match_time))
            else:
                sell_events.append((-size, order.price, trade.match_time))

        # taker 部分
        if not is_maker_order and trade.maker_address.upper() == user_address.upper():
            size = apply_fee(trade.size, trade.price, trade.fee_rate_bps)
            if trade.side == Side.BUY:
                buy_events.append((size, trade.price, trade.match_time))
            else:
                sell_events.append((-size, trade.price, trade.match_time))

    # --- 2. 时间排序 ---
    all_events = sorted(buy_events + sell_events, key=lambda x: x[2])

    # --- 3. FIFO 撮合 ---
    buy_queue = deque()
    realized_pnl = 0.0

    for size, price, _ in all_events:
        size = clean(size)  # ← 新增：修正

        if size > 0:
            # 买入加入队列
            buy_queue.append([size, price])

        else:
            # 卖出（size 为负）
            sell_size = clean(-size)

            while sell_size > EPS and buy_queue:
                lot_size, lot_price = buy_queue[0]

                if lot_size <= sell_size + EPS:
                    # 完全消耗
                    realized_pnl += (price - lot_price) * lot_size
                    sell_size -= lot_size
                    buy_queue.popleft()
                else:
                    # 部分消耗
                    realized_pnl += (price - lot_price) * sell_size
                    buy_queue[0][0] = clean(lot_size - sell_size)
                    sell_size = 0.0

            # 如果还有卖不完 → 变成空头
            if sell_size > EPS:
                buy_queue.appendleft([-sell_size, price])

    # --- 4. 计算最终持仓 ---
    total_size = clean(sum(q[0] for q in buy_queue))
    cost_basis = clean(sum(clean(q[0]) * q[1] for q in buy_queue))

    # 若因误差产生 0.0000003 的 ghost position → 完全清掉
    if abs(total_size) < EPS:
        total_size = 0.0
        cost_basis = 0.0

    avg_price = cost_basis / total_size if total_size != 0 else 0.0

    return PositionResult(
        size=total_size,
        avg_price=avg_price,
        realized_pnl=realized_pnl,
        amount=cost_basis,
        is_long=total_size > 0,
        is_short=total_size < 0,
        details=PositionDetails(
            buy_events=len(buy_events),
            sell_events=len(sell_events),
            total_trades=len(all_events),
        ),
        last_update=max([i.match_time for i in trades]) if trades else None,
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
