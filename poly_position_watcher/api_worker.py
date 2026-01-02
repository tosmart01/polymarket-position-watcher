# -*- coding = utf-8 -*-
# @Time: 2025/12/1 16:17
# @Author: pinbar
# @Site:
# @File: api_worker.py
# @Software: PyCharm
from __future__ import annotations

import threading
from typing import List, Optional, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, as_completed

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import TradeParams

from poly_position_watcher.schema.position_model import TradeMessage, OrderMessage
from poly_position_watcher.common.logger import logger

if TYPE_CHECKING:
    from poly_position_watcher.position_service import PositionWatcherService

executor = ThreadPoolExecutor(max_workers=3)


class APIWorker:
    """
    Pulls trade history through the CLOB HTTP API using the official SDK.
    The worker normalizes responses into TradeMessage instances so
    downstream consumers can share the same data model as the WebSocket stream.
    """

    def __init__(self, client: ClobClient, maker_address: str):
        self.client = client
        self.maker_address = maker_address

    def fetch_order(self, order_id: str) -> OrderMessage | None:
        if order := self.client.get_order(order_id):
            return self._parse_order(order)

    def fetch_trades(
            self,
            market: Optional[str] = None,
            after: Optional[int] = None,
            before: Optional[int] = None,
    ) -> List[TradeMessage]:
        """
        Fetches historical trades for this maker.

        :param market: Optional condition_id filter.
        :param after: Only return trades updated after this timestamp (ms).
        :param before: Only return trades updated before this timestamp (ms).
        """
        params_kwargs = {"maker_address": self.maker_address}
        if market:
            params_kwargs["market"] = market
        if after:
            params_kwargs["after"] = after
        if before:
            params_kwargs["before"] = before

        params = TradeParams(**params_kwargs)
        raw_trades = self.client.get_trades(params)

        trades: List[TradeMessage] = []
        for raw in raw_trades:
            trades.append(self._parse_trade(raw))
        return trades

    @staticmethod
    def _parse_trade(payload: dict) -> TradeMessage:
        normalized = dict(payload)
        normalized.setdefault("type", "TRADE")
        normalized.setdefault("event_type", "trade")
        return TradeMessage(**normalized)

    @staticmethod
    def _parse_order(payload: dict) -> OrderMessage:
        normalized = dict(payload)
        normalized.setdefault("type", "update")
        normalized.setdefault("event_type", "order")
        normalized.setdefault("timestamp", 0)
        normalized["owner"] = ""
        return OrderMessage(**normalized)


class HttpListenerContext:
    """
    Thread-safe context manager that:
    - applies temporary HTTP listen lists
    - starts HTTP trade/order polling threads on enter
    - stops threads on exit
    - restores previous listening state
    """

    def __init__(
            self,
            service: "PositionWatcherService",
            markets=None,
            orders=None,
            http_poll_interval: float = 3,
            bootstrap_http: bool = False,
    ):
        self.service = service
        self._lock = threading.RLock()
        self.markets: set[str] = set(markets) if markets else set()
        self.orders: set[str] = set(orders) if orders else set()
        self.http_poll_interval = http_poll_interval
        self.bootstrap_http = bootstrap_http
        self.api_worker = APIWorker(self.service.client, self.service.user_address)

        # Local thread control
        self._stop_event = threading.Event()
        self._trade_thread = None
        self._order_thread = None

    # -------------------------
    # Context enter
    # -------------------------
    def __enter__(self):
        if self.bootstrap_http:
            self.sync_trade_from_http(is_init=True)
            self.sync_order_from_http()

        # Start HTTP polling threads
        self._start_threads()
        return self

    # -------------------------
    # add markets/orders safely
    # -------------------------
    def add(self, markets=None, orders=None):
        with self._lock:
            if markets:
                self.markets.update(markets)
            if orders:
                self.orders.update(orders)

    def reset(self, markets: list[str] = None, orders: list[str] = None):
        with self._lock:
            if markets:
                self.markets = set(markets)
            if orders:
                self.orders = set(orders)

    def clear(self):
        with self._lock:
            self.markets = set()
            self.orders = set()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop_threads()

        return False

    # -------------------------
    # internal: start threads
    # -------------------------
    def _start_threads(self):
        self._stop_event.clear()

        self._trade_thread = threading.Thread(
            target=self._trade_loop,
            daemon=True,
        )
        self._order_thread = threading.Thread(
            target=self._order_loop,
            daemon=True,
        )

        self._trade_thread.start()
        self._order_thread.start()

    # -------------------------
    # internal: stop threads
    # -------------------------
    def _stop_threads(self):
        self._stop_event.set()

    def _trade_loop(self):
        while not self._stop_event.wait(self.http_poll_interval):
            self.sync_trade_from_http()
        logger.info(f"{self.markets}, trade loop is stopped")

    def _order_loop(self):
        while not self._stop_event.wait(self.http_poll_interval):
            self.sync_order_from_http()
        logger.info(f"order loop is stopped")

    # -------------------------------------------------------------------------
    # HTTP sync (manual)
    # -------------------------------------------------------------------------
    def sync_trade_from_http(self, is_init: bool = False):
        with self._lock:
            markets = list(self.markets)
        tasks = []
        for market in markets:
            task = executor.submit(self.api_worker.fetch_trades, market)
            task._market_id = market
            tasks.append(task)
        for task in as_completed(tasks):
            try:
                trades = task.result()
            except Exception as e:
                logger.error(f"Failed to http fetch trades market {task._market_id}: {e}")
                continue
            if is_init:
                self.service._init_trades(sorted(trades, key=lambda x: x.match_time))
            else:
                for trade in sorted(trades, key=lambda x: x.match_time):
                    self.service._ingest_trade(trade)

    def sync_order_from_http(self):
        with self._lock:
            order_ids = list(self.orders)
        tasks = []
        for order_id in order_ids:
            task = executor.submit(self.api_worker.fetch_order, order_id)
            task._order_id = order_id
            tasks.append(task)
        for task in as_completed(tasks):
            try:
                order = task.result()
            except Exception as e:
                logger.error(f"Failed to fetch order {task._order_id}: {e}")
                continue
            if order is None:
                exists = self.service.position_store.orders.get(task._order_id)
                if exists:
                    exists.status = "canceled"
                    self.service._ingest_order(exists)
            else:
                self.service._ingest_order(order)
