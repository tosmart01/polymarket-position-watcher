from __future__ import annotations

import unittest

from poly_position_watcher.schema.position_model import TradeMessage, UserPosition


def build_failed_trade(trade_id: str) -> TradeMessage:
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
        size=10.0,
        status="FAILED",
        taker_order_id=f"0xorder-{trade_id}",
        timestamp=1,
        match_time=1,
        last_update=1,
        trade_owner="0xuser",
        trader_side="TAKER",
        fee_rate_bps=0,
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
            failed_trades=[build_failed_trade("failed-1"), build_failed_trade("failed-2")],
        )

        self.assertEqual(position.failed_trade_ids, ["failed-1", "failed-2"])
        rendered = str(position)
        self.assertIn("failed_trades: ['failed-1', 'failed-2']", rendered)
        self.assertNotIn("transaction_hash", rendered)


if __name__ == "__main__":
    unittest.main()
