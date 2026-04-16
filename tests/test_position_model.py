from __future__ import annotations

import unittest
from unittest.mock import patch

from poly_position_watcher.position_service import PositionStore
from poly_position_watcher.schema.position_model import OrderMessage, TradeMessage, UserPosition


def build_trade(trade_id: str, status: str = "FAILED", size: float = 10.0) -> TradeMessage:
    return TradeMessage(
        type="TRADE",
        event_type="trade",
        asset_id="0xtoken",
        id=trade_id,
        maker_orders=[],
        transaction_hash=f"0xhash-{trade_id}",
        market="0xmarket",
        maker_address="0xuser",
        outcome="YES",
        owner="0xuser",
        price=0.25,
        side="BUY",
        size=size,
        status=status,
        taker_order_id=f"0xorder-{trade_id}",
        timestamp=1,
        match_time=1,
        last_update=1,
        trade_owner="0xuser",
        trader_side="TAKER",
        fee_rate_bps=0,
        market_slug="test-market",
    )


def build_order(
    order_id: str,
    *,
    asset_id: str = "0xtoken",
    associate_trades: list[str] | None = None,
) -> OrderMessage:
    return OrderMessage(
        type="update",
        event_type="order",
        asset_id=asset_id,
        associate_trades=associate_trades,
        id=order_id,
        market="0xmarket",
        outcome="YES",
        owner="0xuser",
        price=0.25,
        side="BUY",
        size_matched=10.0,
        timestamp=1,
        status="LIVE",
        market_slug="test-market",
    )


class UserPositionTests(unittest.TestCase):
    def test_failed_trade_ids_are_exposed_in_string_output(self) -> None:
        position = UserPosition(
            price=0.25,
            size=10.0,
            original_size=10.0,
            volume=2.5,
            fee_amount=0.0,
            sellable_size=10.0,
            token_id="0xtoken",
            last_update=1,
            market_id="0xmarket",
            outcome="YES",
            has_failed=True,
            failed_trades=[build_trade("failed-1"), build_trade("failed-2")],
        )

        self.assertEqual(position.failed_trade_ids, ["failed-1", "failed-2"])
        rendered = str(position)
        self.assertIn("failed_trades: ['failed-1', 'failed-2']", rendered)
        self.assertNotIn("transaction_hash", rendered)

    def test_failed_trade_warning_logs_once_per_token_and_trade_id(self) -> None:
        store = PositionStore(user_address="0xuser")
        trades = [
            build_trade("confirmed-1", status="CONFIRMED", size=5.0),
            build_trade("failed-1", status="FAILED", size=10.0),
        ]

        with patch("poly_position_watcher.position_service.logger.warning") as warning:
            store.build_position(trades=trades, token_id="0xtoken", outcome="YES")
            store.build_position(trades=trades, token_id="0xtoken", outcome="YES")

        warning.assert_called_once_with(
            "Found failed trades, total size: {}, ids: {}",
            10.0,
            ["failed-1"],
        )

    def test_get_position_by_order_ids_uses_order_trade_links(self) -> None:
        store = PositionStore(user_address="0xuser")
        trade_a = build_trade("trade-a", status="CONFIRMED", size=3.0)
        trade_a.taker_order_id = "order-a"
        trade_b = build_trade("trade-b", status="CONFIRMED", size=5.0)
        trade_b.taker_order_id = "order-b"
        store.append_trade(trade_a)
        store.append_trade(trade_b)
        store.append_order(build_order("order-a", associate_trades=["trade-a"]))
        store.append_order(build_order("order-b", associate_trades=["trade-b"]))

        position_a = store.get_position_by_order_ids(["order-a"])
        combined_positions = store.get_positions_by_order_ids(["order-a", "order-b"])

        self.assertIsNotNone(position_a)
        self.assertEqual(position_a.token_id, "0xtoken")
        self.assertEqual(position_a.size, 3.0)
        self.assertIn("0xtoken", combined_positions)
        self.assertEqual(combined_positions["0xtoken"].size, 8.0)

    def test_get_position_by_order_ids_falls_back_to_trade_index_when_order_missing_associate_trades(self) -> None:
        store = PositionStore(user_address="0xuser")
        trade = build_trade("trade-a", status="CONFIRMED", size=4.0)
        trade.taker_order_id = "order-a"
        store.append_trade(trade)
        store.append_order(build_order("order-a", associate_trades=None))

        position = store.get_position_by_order_ids(["order-a"])

        self.assertIsNotNone(position)
        self.assertEqual(position.size, 4.0)

    def test_trade_index_only_uses_current_user_related_order_ids(self) -> None:
        store = PositionStore(user_address="0xuser")
        trade = TradeMessage(
            type="TRADE",
            event_type="trade",
            asset_id="0xup-token",
            id="trade-realistic",
            maker_orders=[
                {
                    "order_id": "irrelevant-order-1",
                    "owner": "other-owner",
                    "maker_address": "0xother1",
                    "matched_amount": "20",
                    "price": "0.45",
                    "fee_rate_bps": "1000",
                    "asset_id": "0xdown-token",
                    "outcome": "Down",
                    "side": "BUY",
                },
                {
                    "order_id": "user-maker-order",
                    "owner": "user-owner",
                    "maker_address": "0xuser",
                    "matched_amount": "6",
                    "price": "0.55",
                    "fee_rate_bps": "1000",
                    "asset_id": "0xup-token",
                    "outcome": "Up",
                    "side": "SELL",
                },
                {
                    "order_id": "irrelevant-order-2",
                    "owner": "other-owner-2",
                    "maker_address": "0xother2",
                    "matched_amount": "40",
                    "price": "0.41",
                    "fee_rate_bps": "1000",
                    "asset_id": "0xdown-token",
                    "outcome": "Down",
                    "side": "BUY",
                },
            ],
            transaction_hash="0xhash-realistic",
            market="0xmarket",
            maker_address="0xouter-not-user",
            outcome="Up",
            owner="outer-owner",
            price=0.59,
            side="BUY",
            size=6.0,
            status="CONFIRMED",
            taker_order_id="outer-taker-order",
            timestamp=1,
            match_time=1,
            last_update=1,
            trade_owner="outer-owner",
            trader_side="MAKER",
            fee_rate_bps=1000,
            market_slug="test-market",
        )
        store.append_trade(trade)

        self.assertEqual(store.get_position_by_order_ids(["user-maker-order"]).size, -6.0)
        self.assertIsNone(store.get_position_by_order_ids(["irrelevant-order-1"]))
        self.assertIsNone(store.get_position_by_order_ids(["irrelevant-order-2"]))
        self.assertIsNone(store.get_position_by_order_ids(["outer-taker-order"]))


if __name__ == "__main__":
    unittest.main()
