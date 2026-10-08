from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from poly_position_watcher.api_worker import APIWorker


def position(token_id="token-1", **changes):
    return {
        "token_id": token_id,
        "condition_id": "condition-1",
        "current_size": 10,
        "current_value": 5,
        "redeemable": False,
        "slug": "market-slug",
        **changes,
    }


def page(rows, cursor=None):
    return Mock(json=Mock(return_value={
        "data": rows,
        "pagination": {"next_cursor": cursor},
    }))


class APIWorkerTests(unittest.TestCase):
    def setUp(self):
        self.worker = APIWorker(client=Mock(), maker_address="0xuser")

    @patch("poly_position_watcher.api_worker.requests.get")
    def test_paginates_past_fully_redeemable_page(self, get):
        kept = position()
        get.side_effect = [
            page([position(redeemable=True)], "next-page"),
            page([kept]),
        ]

        self.assertEqual(self.worker.fetch_positions("0xuser"), [kept])
        first, second = get.call_args_list
        self.assertEqual(first.args[0], "https://data-api.polymarket.com/v2/positions")
        self.assertEqual(first.kwargs["params"], {
            "user": "0xuser", "status": "OPEN", "filter_type": "TOKENS",
            "filter_amount": 1, "limit": 100,
            "sort_by": "CURRENT_VALUE", "sort_direction": "DESC",
        })
        self.assertEqual(second.kwargs["params"], {
            **first.kwargs["params"], "cursor": "next-page",
        })
        for response_call in get.call_args_list:
            self.assertEqual(response_call.kwargs["timeout"], 30)

    @patch("poly_position_watcher.api_worker.requests.get")
    def test_empty_positions(self, get):
        get.return_value = page([])
        self.assertEqual(self.worker.fetch_positions("0xuser"), [])
        get.assert_called_once()

    @patch("poly_position_watcher.api_worker.requests.get")
    def test_later_page_failure_does_not_return_incomplete_positions(self, get):
        failed = page([])
        failed.raise_for_status.side_effect = requests.HTTPError("503")
        get.side_effect = [page([position()], "next-page"), failed]
        self.assertEqual(self.worker.fetch_positions("0xuser"), [])

    @patch("poly_position_watcher.api_worker.requests.get")
    def test_repeated_cursor_stops_walk(self, get):
        get.return_value = page([position()], "same-cursor")
        self.assertEqual(self.worker.fetch_positions("0xuser"), [])
        self.assertEqual(get.call_count, 2)

    def test_v2_positions_initialize_clob_trades_with_market_filter(self):
        trade = SimpleNamespace(market_slug="")
        self.worker.fetch_positions = Mock(return_value=[
            position(),
            position("empty", current_size=0),
            position("worthless", current_value=0),
        ])
        self.worker.fetch_trades = Mock(return_value=[trade])

        result = self.worker.fetch_trades_from_positions("0xuser")

        self.assertEqual(result, {"token-1": [trade]})
        self.worker.fetch_trades.assert_called_once_with(market="condition-1")
        self.assertEqual(trade.market_slug, "market-slug")

    def test_extracts_v2_condition_ids(self):
        self.worker.fetch_positions = Mock(return_value=[position()])
        self.assertEqual(self.worker.get_condition_ids_from_positions("0xuser"), ["condition-1"])


if __name__ == "__main__":
    unittest.main()
