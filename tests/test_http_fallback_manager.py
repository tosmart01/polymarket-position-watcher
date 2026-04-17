from __future__ import annotations

import unittest

from poly_position_watcher.api_worker import APIWorker, HttpFallbackManager


class DummyPositionStore:
    positions = {}
    orders = {}


class DummyService:
    def __init__(self) -> None:
        self.api_worker = object()
        self.position_store = DummyPositionStore()


class HttpFallbackManagerTests(unittest.TestCase):
    def test_default_group_keeps_old_api_compatible(self) -> None:
        manager = HttpFallbackManager(DummyService(), http_poll_interval=1)

        manager.add(market_ids=["market-1"], order_ids=["order-1"])

        self.assertEqual(
            manager.market_groups[HttpFallbackManager.DEFAULT_GROUP],
            {"market-1"},
        )
        self.assertEqual(
            manager.order_groups[HttpFallbackManager.DEFAULT_GROUP],
            {"order-1"},
        )

    def test_group_sets_are_aggregated_across_namespaces(self) -> None:
        manager = HttpFallbackManager(DummyService(), http_poll_interval=1)

        manager.set_group(group="strategy-a", market_ids=["market-a"], order_ids=["order-a"])
        manager.set_group(group="strategy-b", market_ids=["market-b"], order_ids=["order-b"])

        self.assertEqual(manager._aggregated_markets_locked(), {"market-a", "market-b"})
        self.assertEqual(manager._aggregated_orders_locked(), {"order-a", "order-b"})

    def test_clear_one_group_does_not_affect_others(self) -> None:
        manager = HttpFallbackManager(DummyService(), http_poll_interval=1)

        manager.set_group(group="strategy-a", market_ids=["market-a"], order_ids=["order-a"])
        manager.set_group(group="strategy-b", market_ids=["market-b"], order_ids=["order-b"])
        manager.clear(group="strategy-a")

        self.assertNotIn("strategy-a", manager.market_groups)
        self.assertNotIn("strategy-a", manager.order_groups)
        self.assertEqual(manager.market_groups["strategy-b"], {"market-b"})
        self.assertEqual(manager.order_groups["strategy-b"], {"order-b"})

    def test_remove_only_touches_target_group(self) -> None:
        manager = HttpFallbackManager(DummyService(), http_poll_interval=1)

        manager.add(group="strategy-a", market_ids=["market-a"], order_ids=["order-a"])
        manager.add(group="strategy-b", market_ids=["market-a"], order_ids=["order-a"])
        manager.remove(group="strategy-a", market_ids=["market-a"], order_ids=["order-a"])

        self.assertNotIn("strategy-a", manager.market_groups)
        self.assertNotIn("strategy-a", manager.order_groups)
        self.assertEqual(manager.market_groups["strategy-b"], {"market-a"})
        self.assertEqual(manager.order_groups["strategy-b"], {"order-a"})


if __name__ == "__main__":
    unittest.main()
