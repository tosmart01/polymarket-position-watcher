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
from typing import Dict, List

from poly_position_watcher.common.enums import Side
from poly_position_watcher.common.logger import logger
from poly_position_watcher.api_worker import APIWorker, HttpFallbackManager

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
        if trade.maker_address.upper() == self.user_address.upper():
            return trade.outcome, trade.asset_id
        for order in trade.maker_orders:
            if order.maker_address.upper() == self.user_address.upper():
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
        is_failed = any(trade.status == "FAILED" for trade in trades)
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
            is_failed=is_failed,
            market_slug=trades[0].market_slug
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
            init_positions: bool = False,
            enable_http_fallback: bool = False,
            http_poll_interval: float = 3,
            add_init_positions_to_http: bool = False,
    ):
        """
        :param client: ClobClient instance
        :param ws_idle_timeout: WebSocket idle timeout
        :param wss_proxies: WebSocket proxy configuration
        :param init_positions: Whether to initialize positions via official API
        :param enable_http_fallback: Whether to enable HTTP fallback polling
        :param http_poll_interval: HTTP polling interval in seconds
        :param add_init_positions_to_http: Whether to add condition_ids from init_positions to HTTP monitoring
        
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

        # New parameters
        self.init_positions = init_positions
        self.enable_http_fallback = enable_http_fallback
        self.http_poll_interval = http_poll_interval
        self.add_init_positions_to_http = add_init_positions_to_http

        # Setup API worker
        self.api_worker = APIWorker(self.client, self.user_address)

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

        # HTTP fallback manager (if enabled)
        self._http_fallback: HttpFallbackManager | None = None
        if self.enable_http_fallback:
            self._http_fallback = HttpFallbackManager(self, http_poll_interval)

    # -------------------------------------------------------------------------
    # Context: start/stop entire service
    # -------------------------------------------------------------------------
    def __enter__(self):
        # Initialize positions if requested
        init_condition_ids = []
        if self.init_positions:
            try:
                initialize_trades = self.api_worker.fetch_trades_from_positions(self.user_address)
                if not initialize_trades:
                    return
                for token_id, trades in initialize_trades.items():
                    self.position_store.init_trades(trades)
                positions_info = '\n'.join([
                    f"slug={pos.market_slug}, price={pos.price}, size={pos.size:.4f},"
                    f"volume={pos.volume:.4f}, token_id={pos.token_id}, outcome={pos.outcome}"
                    for pos in self.position_store.positions.values()
                ])
                logger.info(f"Initialized positions:\n{positions_info}")
            except Exception as e:
                logger.error(f"Failed to initialize positions: {e}")

        # Start WebSocket
        self.start()

        # Start HTTP fallback if enabled (threads start even if sets are empty)
        if self.enable_http_fallback and self._http_fallback:
            self._http_fallback.start()

            # Add init positions' condition_ids to HTTP monitoring if requested
            if self.add_init_positions_to_http and init_condition_ids:
                self._http_fallback.add(market_ids=init_condition_ids)
                logger.info(f"Added {len(init_condition_ids)} condition_ids from init_positions to HTTP monitoring")

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Stop HTTP fallback threads
        if self._http_fallback:
            self._http_fallback.stop()
        self.stop()
        return False

    # -------------------------------------------------------------------------
    # Start / Stop
    # -------------------------------------------------------------------------
    def start(self):
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
            # 若超时未收到任何仓位更新，则返回上一次position 方便上层统一处理
            return self.get_position(token_id)

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

    # -------------------------------------------------------------------------
    # HTTP Fallback Management (delegates to HttpFallbackManager)
    # -------------------------------------------------------------------------
    def add_http_listen(self, order_ids: list[str] = None, market_ids: list[str] = None):
        """
        Add markets/orders to HTTP fallback polling.
        
        :param order_ids: List of order IDs to monitor
        :param market_ids: List of market (condition) IDs to monitor
        """
        if not self.enable_http_fallback or not self._http_fallback:
            logger.warning("HTTP fallback is not enabled. Enable it in __init__ to use this method.")
            return

        self._http_fallback.add(market_ids=market_ids, order_ids=order_ids)

    def remove_http_listen(self, order_ids: list[str] = None, market_ids: list[str] = None):
        """
        Remove markets/orders from HTTP fallback polling.
        
        :param order_ids: List of order IDs to remove
        :param market_ids: List of market (condition) IDs to remove
        """
        if not self.enable_http_fallback or not self._http_fallback:
            return

        self._http_fallback.remove(market_ids=market_ids, order_ids=order_ids)

    def clear_http(self):
        """Clear all HTTP fallback monitoring (threads keep running)."""
        if not self.enable_http_fallback or not self._http_fallback:
            return

        self._http_fallback.clear()
