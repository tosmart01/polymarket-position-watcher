from __future__ import annotations

import math
import unittest

from poly_position_watcher.common.enums import Side
from poly_position_watcher.schema.position_model import TradeMessage
from poly_position_watcher.trade_calculator import calculate_position_from_trades


USER_ADDRESS = "0x123"
MARKET_ID = "0xmarket"
TOKEN_ID = "0xtoken"
FEE_SCHEDULE = {
    "rate": 0.0175,
    "exponent": 1,
    "takerOnly": True,
    "rebateRate": 0.25,
}


def build_taker_trade(
    *,
    trade_id: str,
    side: str,
    size: float,
    price: float,
    match_time: int,
) -> TradeMessage:
    return TradeMessage(
        type="TRADE",
        event_type="trade",
        asset_id=TOKEN_ID,
        id=trade_id,
        maker_orders=[],
        transaction_hash=f"0xhash-{trade_id}",
        market=MARKET_ID,
        maker_address=USER_ADDRESS,
        outcome="YES",
        owner=USER_ADDRESS,
        price=price,
        side=side,
        size=size,
        status="CONFIRMED",
        taker_order_id=f"0xorder-{trade_id}",
        timestamp=match_time,
        match_time=match_time,
        last_update=match_time,
        trade_owner=USER_ADDRESS,
        trader_side="TAKER",
        fee_rate_bps=0,
        market_slug="test-market",
    )


def expected_fee(size: float, price: float, rate: float) -> float:
    return round(size * rate * price * (1 - price), 5)


class TradeCalculatorFeeTests(unittest.TestCase):
    def test_maker_trade_does_not_apply_taker_only_fee(self) -> None:
        trade = TradeMessage(
            type="TRADE",
            event_type="trade",
            asset_id="outer-asset-id",
            id="maker-1",
            maker_orders=[
                {
                    "order_id": "order-user",
                    "owner": "owner-user",
                    "maker_address": USER_ADDRESS,
                    "matched_amount": "1947.37",
                    "price": "0.57",
                    "fee_rate_bps": "1000",
                    "asset_id": TOKEN_ID,
                    "outcome": "Up",
                    "side": "BUY",
                },
                {
                    "order_id": "order-other",
                    "owner": "owner-other",
                    "maker_address": "0xother",
                    "matched_amount": "5",
                    "price": "0.45",
                    "fee_rate_bps": "1000",
                    "asset_id": "other-token",
                    "outcome": "Down",
                    "side": "BUY",
                },
            ],
            transaction_hash="0xhash-maker",
            market=MARKET_ID,
            maker_address="0xouter-maker",
            outcome="OuterOutcome",
            owner="outer-owner",
            price=0.57,
            side=Side.BUY.value,
            size=1947.37,
            status="CONFIRMED",
            taker_order_id="0xtaker-order",
            timestamp=1,
            match_time=1,
            last_update=1,
            trade_owner="outer-owner",
            trader_side="MAKER",
            fee_rate_bps=1000,
            market_slug="test-market",
        )

        result = calculate_position_from_trades(
            [trade],
            user_address=USER_ADDRESS,
            enable_fee_calc=True,
            fee_schedule_by_market={MARKET_ID: FEE_SCHEDULE},
        )

        self.assertTrue(math.isclose(result.fee_amount, 0.0, rel_tol=0, abs_tol=1e-9))
        self.assertTrue(math.isclose(result.size, 1947.37, rel_tol=0, abs_tol=1e-9))
        self.assertTrue(
            math.isclose(result.original_size, 1947.37, rel_tol=0, abs_tol=1e-9)
        )
        self.assertTrue(
            math.isclose(result.amount, 1947.37 * 0.57, rel_tol=0, abs_tol=1e-9)
        )

    def test_taker_buy_deducts_fee_in_shares(self) -> None:
        trade = build_taker_trade(
            trade_id="buy-1",
            side=Side.BUY.value,
            size=100.0,
            price=0.25,
            match_time=1,
        )

        result = calculate_position_from_trades(
            [trade],
            user_address=USER_ADDRESS,
            enable_fee_calc=True,
            fee_schedule_by_market={MARKET_ID: FEE_SCHEDULE},
        )

        fee_amount = expected_fee(100.0, 0.25, 0.0175)
        expected_size = 100.0 - fee_amount / 0.25

        self.assertTrue(math.isclose(result.fee_amount, fee_amount, rel_tol=0, abs_tol=1e-9))
        self.assertTrue(math.isclose(result.size, expected_size, rel_tol=0, abs_tol=1e-9))
        self.assertTrue(math.isclose(result.original_size, 100.0, rel_tol=0, abs_tol=1e-9))
        self.assertTrue(math.isclose(result.amount, 25.0, rel_tol=0, abs_tol=1e-9))
        self.assertTrue(
            math.isclose(result.avg_price, 25.0 / expected_size, rel_tol=0, abs_tol=1e-9)
        )

    def test_taker_sell_keeps_share_count_and_charges_usdc(self) -> None:
        trade = build_taker_trade(
            trade_id="sell-1",
            side=Side.SELL.value,
            size=100.0,
            price=0.25,
            match_time=1,
        )

        result = calculate_position_from_trades(
            [trade],
            user_address=USER_ADDRESS,
            enable_fee_calc=True,
            fee_schedule_by_market={MARKET_ID: FEE_SCHEDULE},
        )

        fee_amount = expected_fee(100.0, 0.25, 0.0175)
        net_proceeds = 100.0 * 0.25 - fee_amount

        self.assertTrue(math.isclose(result.fee_amount, fee_amount, rel_tol=0, abs_tol=1e-9))
        self.assertTrue(math.isclose(result.size, -100.0, rel_tol=0, abs_tol=1e-9))
        self.assertTrue(math.isclose(result.original_size, -100.0, rel_tol=0, abs_tol=1e-9))
        self.assertTrue(math.isclose(result.amount, -net_proceeds, rel_tol=0, abs_tol=1e-9))
        self.assertTrue(math.isclose(result.avg_price, net_proceeds / 100.0, rel_tol=0, abs_tol=1e-9))

    def test_round_trip_uses_net_sell_proceeds_for_realized_pnl(self) -> None:
        buy_trade = build_taker_trade(
            trade_id="buy-1",
            side=Side.BUY.value,
            size=100.0,
            price=0.25,
            match_time=1,
        )
        buy_fee = expected_fee(100.0, 0.25, 0.0175)
        net_buy_size = 100.0 - buy_fee / 0.25

        sell_trade = build_taker_trade(
            trade_id="sell-1",
            side=Side.SELL.value,
            size=net_buy_size,
            price=0.4,
            match_time=2,
        )

        result = calculate_position_from_trades(
            [buy_trade, sell_trade],
            user_address=USER_ADDRESS,
            enable_fee_calc=True,
            fee_schedule_by_market={MARKET_ID: FEE_SCHEDULE},
        )

        sell_fee = expected_fee(net_buy_size, 0.4, 0.0175)
        expected_realized_pnl = (net_buy_size * 0.4 - sell_fee) - 25.0

        self.assertTrue(math.isclose(result.size, 0.0, rel_tol=0, abs_tol=1e-9))
        self.assertTrue(
            math.isclose(result.realized_pnl, expected_realized_pnl, rel_tol=0, abs_tol=1e-9)
        )
        self.assertTrue(
            math.isclose(result.fee_amount, buy_fee + sell_fee, rel_tol=0, abs_tol=1e-9)
        )


if __name__ == "__main__":
    unittest.main()
