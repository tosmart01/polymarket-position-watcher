# -*- coding = utf-8 -*-
# @Time: 2025/12/3 15:35
# @Author: pinbar
# @Site:
# @File: position_service.py
# @Software: PyCharm
from __future__ import annotations

import threading
from datetime import datetime
from queue import Queue, Empty
from collections import defaultdict
from typing import Dict

from poly_position_watcher.common.enums import Side
from poly_position_watcher.common.logger import logger
from poly_position_watcher.api_worker import HttpListenerContext

from poly_position_watcher.schema.position_model import (
    UserPosition,
    TradeMessage,
    OrderMessage,
)
from poly_position_watcher.trade_calculator import calculate_position_from_trades
from poly_position_watcher.wss_worker import PolymarketUserWS


class PositionStore:
    """
    Keeps an in-memory view of per-market trades and exposes aggregated positions.
    """

    def __init__(self, user_address: str):
        self.user_address = user_address
        self.trades_by_token: Dict[str, Dict[str, TradeMessage]] = defaultdict(dict)
        self.positions: Dict[str, UserPosition] = {}
        self.orders: Dict[str, OrderMessage] = {}
        self._lock = threading.RLock()
        self.queue_dict: Dict[str, Queue] = {}

    def get_token_id_from_trade(self, trade: TradeMessage) -> tuple[str, str] | None:
        if trade.maker_address == self.user_address:
            return trade.outcome, trade.asset_id
        for order in trade.maker_orders:
            if order.maker_address == self.user_address:
                return order.outcome, order.asset_id

    def _put(self, _id: str, item: UserPosition | OrderMessage) -> None:
        if _id not in self.queue_dict:
            self.queue_dict[_id] = Queue()
        self.queue_dict[_id].put(item)

    def _clear_q(self, _id: str) -> None:
        if _id in self.queue_dict:
            self.queue_dict[_id] = Queue()

    def _get(self, _id: str, timeout=None) -> OrderMessage | UserPosition | None:
        with self._lock:
            if _id not in self.queue_dict:
                self.queue_dict[_id] = Queue()
        return self.queue_dict[_id].get(timeout=timeout)

    def append_trade(self, trade: TradeMessage):
        """
        Stores a new trade snapshot.
        If duplicate trade ids arrive, the payload with the latest update timestamp wins.
        """
        with self._lock:
            result = self.get_token_id_from_trade(trade)
            if result is None:
                logger.debug(
                    "Skip trade without matching maker/taker context: {}", trade.id
                )
                return
            outcome, token_id = result
            trades_map = self.trades_by_token[token_id]
            existing = trades_map.get(trade.id)
            if existing and trade.match_time <= existing.match_time:
                return
            else:
                trades_map[trade.id] = trade
            user_pos = self.build_position(
                trades=list(trades_map.values()), token_id=token_id, outcome=outcome
            )
            self.positions[token_id] = user_pos
            self._put(token_id, user_pos)

    def init_trades(self, trades: list[TradeMessage]):
        with self._lock:
            if not trades:
                return
            result = self.get_token_id_from_trade(trades[0])
            if result is None:
                logger.debug(
                    "Skip trade without matching maker/taker context: {}", trades[0].id
                )
                return
            outcome, token_id = result
            trades_map = self.trades_by_token[token_id]
            for trade in trades:
                trades_map[trade.id] = trade
            user_pos = self.build_position(
                trades=list(trades_map.values()), token_id=token_id, outcome=outcome
            )
            self._clear_q(token_id)
            self.positions[token_id] = user_pos
            self._put(token_id, user_pos)

    def append_order(self, order: OrderMessage | None):
        """
        Stores a new order snapshot.
        If duplicate trade ids arrive, the payload with the latest update timestamp wins.
        """
        with self._lock:
            existing = self.orders.get(order.id)
            if (
                    existing
                    and order.size_matched <= existing.size_matched
                    and order.status == existing.status
            ):
                return
            if abs(order.size_matched - order.original_size) < 0.5:
                order.filled = True
            self.orders[order.id] = order
            self._put(order.id, order)

    def build_position(
            self, trades: list[TradeMessage], token_id, outcome: str
    ) -> UserPosition | None:
        position_result = calculate_position_from_trades(
            trades, user_address=self.user_address
        )
        current = UserPosition(
            price=position_result.avg_price,
            size=position_result.size,
            volume=position_result.amount,
            token_id=token_id,
            last_update=position_result.last_update,
            market_id=trades[0].market,
            outcome=outcome,
            created_at=datetime.fromtimestamp(position_result.last_update),
        )
        return current
        # if exists_pos := self.positions.get(token_id):
        #     if exists_pos.last_update < current.last_update:
        #         return current
        # else:
        #     return current

    def get_token_position(self, token_id: str) -> UserPosition:
        return self.positions.get(token_id)

    def get_token_order(self, token_id: str) -> list[OrderMessage]:
        orders = []
        for key, value in self.orders.items():
            if value.asset_id == token_id:
                orders.append(value)
        return orders

    def get_order_by_id(self, order_id: str) -> OrderMessage:
        return self.orders.get(order_id)

    def blocking_get_token_position(
            self, token_id: str, timeout: float = None
    ) -> UserPosition:
        return self._get(token_id, timeout)

    def blocking_get_order_by_id(
            self, order_id: str, timeout: float = None
    ) -> OrderMessage:
        return self._get(order_id, timeout)

    @staticmethod
    def _calculate_size(order, size: float, volume: float):
        if order.side == Side.BUY:
            size += order.size
            volume += order.size * order.price
        elif order.side == Side.SELL:
            size -= order.size
            volume -= order.size * order.price
        return size, volume


class PositionWatcherService:
    """
    High level service:
    - Bootstraps positions via HTTP
    - Maintains updates via WebSocket
    - Provides context-based HTTP listener for temporary polling threads
    """

    def __init__(
            self,
            client,
            ws_idle_timeout=60 * 60,
            wss_proxies: dict | None = None,
    ):
        """
        wss_proxies example: {
            "http_proxy_host": "127.0.0.1",
            "http_proxy_port": 8118,
            "proxy_type": "http",
        }
        """
        self.client = client
        self.user_address = self._resolve_user_address()
        self.position_store = PositionStore(self.user_address)
        self._wss_proxies = wss_proxies or {}
        # Setup WS client
        creds = self.client.creds or self.client.create_or_derive_api_creds()
        self.ws_client = PolymarketUserWS(
            api_key=creds.api_key,
            api_secret=creds.api_secret,
            api_passphrase=creds.api_passphrase,
            idle_timeout=ws_idle_timeout,
            on_message_callback=self._handle_ws_message,
            wss_proxies=self._wss_proxies,
        )

        self._ws_thread = None

    # -------------------------------------------------------------------------
    # Context: start/stop entire service
    # -------------------------------------------------------------------------
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False

    # -------------------------------------------------------------------------
    # Public factory: returns the context manager
    # -------------------------------------------------------------------------
    def http_listen(
            self,
            markets=None,
            orders=None,
            http_poll_interval: float = 3,
            bootstrap_http: bool = False,
    ):
        """
        如果在启动前已经有历史仓位需要: bootstrap_http=True
        """
        return HttpListenerContext(
            self,
            markets,
            orders,
            http_poll_interval=http_poll_interval,
            bootstrap_http=bootstrap_http,
        )

    # -------------------------------------------------------------------------
    # Start / Stop
    # -------------------------------------------------------------------------
    def start(self, bootstrap_http=True):
        # Start WebSocket
        if not self._ws_thread or not self._ws_thread.is_alive():
            self._ws_thread = threading.Thread(target=self.ws_client.start, daemon=True)
            self._ws_thread.start()
            logger.info("Started WebSocket worker.")

    def stop(self):
        self.ws_client.stop()
        # Join WS
        if self._ws_thread:
            self._ws_thread.join(timeout=1)

        logger.info("Position watcher stopped.")

    # -------------------------------------------------------------------------
    # WS handler
    # -------------------------------------------------------------------------
    def _handle_ws_message(self, payload):
        logger.info(f"WS message: {payload.get('type')}")
        if payload.get("type") == "TRADE":
            self._ingest_trade(TradeMessage(**payload))
        else:
            self._ingest_order(OrderMessage(**payload))

    # -------------------------------------------------------------------------
    # Ingestion
    # -------------------------------------------------------------------------
    def _ingest_trade(self, trade):
        self.position_store.append_trade(trade)

    def _init_trades(self, trades: list[TradeMessage]):
        self.position_store.init_trades(trades)

    def _ingest_order(self, order):
        self.position_store.append_order(order)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _resolve_user_address(self):
        funder = getattr(getattr(self.client, "builder", None), "funder", None)
        if funder:
            return funder
        return self.client.get_address()

    def get_position(self, token_id: str) -> UserPosition:
        if position := self.position_store.get_token_position(token_id):
            return position
        return UserPosition(token_id=token_id, price=0, size=0, volume=0, last_update=0)

    def get_order_by_token(self, token_id: str) -> list[OrderMessage]:
        return self.position_store.get_token_order(token_id)

    def get_order(self, order_id: str) -> OrderMessage:
        return self.position_store.get_order_by_id(order_id)

    def blocking_get_position(
            self, token_id: str, timeout: float = None
    ) -> UserPosition | None:
        """
        超时返回None；若无仓位则返回 size=0 的占位 UserPosition
        """
        try:
            return self.position_store.blocking_get_token_position(token_id, timeout)
        except Empty:
            # 若超时未收到任何仓位更新，则返回 size=0 的占位对象，方便上层统一处理
            return UserPosition(
                token_id=token_id, price=0, size=0, volume=0, last_update=0
            )

    def blocking_get_order(
            self, order_id: str, timeout: float = None
    ) -> OrderMessage | None:
        """
        超时返回None（即返回 None，表示没有订单更新）
        """
        try:
            return self.position_store.blocking_get_order_by_id(order_id, timeout)
        except Empty:
            # 超时未拿到订单更新时直接返回 None，由调用方自行判断
            return None
