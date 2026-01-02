# -*- coding = utf-8 -*-
# @Time: 2025/12/1 16:16
# @Author: pinbar
# @Site:
# @File: wss.py
# @Software: PyCharm
import json
import threading
import time
from typing import Callable, List, Optional

import requests

from websocket import WebSocketApp, WebSocket

from poly_position_watcher.common.enums import MarketEvent
from poly_position_watcher.common.logger import logger
from poly_position_watcher.schema.common_model import OrderBookSummary

WSS_URL = "wss://ws-subscriptions-clob.polymarket.com"
MARKET_CHANNEL = "market"
USER_CHANNEL = "user"


def json_dumps(msg: dict) -> str:
    return json.dumps(msg, indent=4, ensure_ascii=False)


def fetch_order_books(asset_ids: list[str]) -> list[OrderBookSummary]:
    """
    Fetch an initial snapshot for every asset id before subscribing to the WS stream.
    """
    if not asset_ids:
        return []
    url = "https://clob.polymarket.com/books"
    payload = [{"token_id": token_id} for token_id in asset_ids]
    response = requests.post(
        url, json=payload, headers={"Content-Type": "application/json"}
    )
    response.raise_for_status()
    books = response.json()
    return [OrderBookSummary(**book) for book in books]


class PolymarketUserWS:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        markets: Optional[List[str]] = None,
        ping_interval: int = 10,
        ping_timeout: int = 6,
        idle_timeout: Optional[int] = 60 * 60,
        reconnect_delay: int = 5,
        on_message_callback: Optional[Callable[[dict], None]] = None,
        wss_proxies: Optional[dict] = None,
    ):
        """
        :param markets: 订阅的 condition_ids 列表，为 None 或 [] 时表示订阅全部（视后端协议而定）
        :param ping_interval: WebSocket 库自带 PING 间隔（秒）
        :param ping_timeout: WebSocket 库自带 PONG 超时时间（秒），超过这个时间视为连接异常
        :param idle_timeout: 业务层“长时间没有任意消息”的超时（秒）；为 None / 0 时关闭此功能
        :param reconnect_delay: 断线后重连间隔（秒）
        :param on_message_callback: 收到业务消息时的回调函数，参数为 dict
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.markets = markets or []

        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.idle_timeout = idle_timeout
        self.reconnect_delay = reconnect_delay

        self.on_message_callback = on_message_callback
        self._wss_proxies = wss_proxies or {}

        self.ws: Optional[WebSocketApp] = None
        self._stop = False

        # 业务消息 / 任意消息的最近活跃时间
        self._last_activity = time.time()

        # 监控“长时间无消息”的线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop_evt = threading.Event()

    # ---------- 公共方法 ----------

    def start(self):
        """
        阻塞运行，带自动重连。
        使用 websocket-client 自带 ping/pong（ping_interval & ping_timeout）。
        """
        while not self._stop:
            try:
                logger.info("[WS] Connecting...")

                self.ws = WebSocketApp(
                    f"{WSS_URL}/ws/user",
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )

                # 每次新连接重置最近活跃时间
                self._last_activity = time.time()
                self._monitor_stop_evt.clear()

                # 如果配置了 idle_timeout，则启动一个监控线程
                if self.idle_timeout and self.idle_timeout > 0:
                    self._monitor_thread = threading.Thread(
                        target=self._activity_monitor_loop,
                        daemon=True,
                    )
                    self._monitor_thread.start()
                else:
                    self._monitor_thread = None

                # 这里使用库自带的 ping_interval / ping_timeout，负责底层心跳与超时
                self.ws.run_forever(
                    **self._wss_proxies,
                    ping_interval=self.ping_interval,
                    ping_timeout=self.ping_timeout,
                )

            except Exception as e:
                logger.exception("[WS] run_forever error:")

            # 当前连接生命周期结束，停止监控线程
            self._monitor_stop_evt.set()
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=1)

            if self._stop:
                break

            logger.info(
                f"[WS] Disconnected, reconnecting in {self.reconnect_delay}s..."
            )
            time.sleep(self.reconnect_delay)

    def stop(self):
        """
        手动停止
        """
        self._stop = True
        self._monitor_stop_evt.set()
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def _on_open(self, ws: WebSocket):
        logger.info("[WS] Opened")

        auth = {
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "passphrase": self.api_passphrase,
        }

        sub_msg = {
            "type": "USER",  # 文档要求 - 订阅 user channel
            "auth": auth,
        }

        if self.markets:
            sub_msg["markets"] = self.markets
        else:
            sub_msg["markets"] = []

        ws.send(json.dumps(sub_msg))
        logger.info("[WS] Sent subscribe success")

    def _on_message(self, ws: WebSocket, message: str):
        # 收到任何消息都视为有“活跃”
        self._last_activity = time.time()

        # 对方如果返回的是纯文本心跳，可在这里过滤
        # 但 websocket-client 的 ping/pong 是底层帧，不会走到这里
        if str(message) == "PONG":
            return

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            # 对于非 JSON 消息，按需处理或直接打印
            logger.warning("[WS] Non-JSON message: {}", message)
            return

        if self.on_message_callback:
            try:
                self.on_message_callback(data)
            except Exception as e:
                logger.exception("[WS] on_message_callback error:")

    def _on_error(self, ws: WebSocket, error):
        logger.error("[WS] Error: {}", error)
        try:
            ws.close()
        except Exception:
            pass

    def _on_close(self, ws: WebSocket, close_status_code, close_msg):
        logger.info(f"[WS] Closed: code={close_status_code}, msg={close_msg}")

    # ---------- 业务层“长时间无消息”监控 ----------

    def _activity_monitor_loop(self):
        """
        仅在配置了 idle_timeout 时启用：
        如果长时间（idle_timeout 秒）没有收到任何消息，则主动关闭连接，
        交由外层循环进行重连。
        """
        while not self._monitor_stop_evt.is_set():
            now = time.time()
            if now - self._last_activity > self.idle_timeout:
                logger.info(
                    f"[WS] No activity for {self.idle_timeout}s, "
                    f"closing connection to force reconnect..."
                )
                try:
                    if self.ws:
                        self.ws.close()
                except Exception:
                    pass
                # 触发一次关闭即可，退出监控线程
                break

            # 等待 1 秒再检查，可按需要调整粒度
            self._monitor_stop_evt.wait(1)


class OrderBookWS:
    def __init__(
        self,
        asset_ids: list[str],
        url: str = "wss://ws-subscriptions-clob.polymarket.com",
        event_name: str = "",
        ping_interval: int = 10,
        ping_timeout: int = 6,  # 如需用 websocket 内建 ping，可通过 run_forever 传入
        idle_timeout: Optional[int] = 60 * 60,
        reconnect_delay: int = 5,
        callback: Callable = None,
        wss_proxies: Optional[dict] = None,
    ):
        """
        :param asset_ids: 订阅的 asset_id 列表
        :param url: 基础 ws url
        :param event_name: 日志里的事件名，仅用于调试
        :param ping_interval: 自定义业务层 "PING" 间隔（秒）
        :param ping_timeout: 预留，如果想用 websocket 内建 ping/pong，可透传给 run_forever
        :param idle_timeout: 若长时间未收到任何消息（秒），则主动断开重连；为 None/0 表示关闭
        :param reconnect_delay: 断线后重连间隔（秒）
        """
        self.url = url
        self.asset_ids = asset_ids
        self.event_name = event_name

        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.idle_timeout = idle_timeout
        self.reconnect_delay = reconnect_delay

        self.ws: Optional[WebSocketApp] = None
        self._stop = False

        # 活跃时间（收到任意消息时更新）
        self._last_activity = time.time()

        # “长时间无消息”监控线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop_evt = threading.Event()

        self.order_books: dict[str, OrderBookSummary] = {}

        self._furl = url.rstrip("/") + "/ws/" + MARKET_CHANNEL
        self.callback = callback
        self._wss_proxies = wss_proxies or {}

        self.initialize()

    # ---------- 初始化 order book 快照 ----------

    def initialize(self):
        books = fetch_order_books(self.asset_ids)
        for book in books:
            self.order_books[book.asset_id] = book

    # ---------- 公共方法 ----------

    def start(self):
        """
        阻塞运行，带自动重连逻辑。
        """
        while not self._stop:
            try:
                logger.info("[OrderBookWS] Connecting to {} ...", self._furl)

                self.ws = WebSocketApp(
                    self._furl,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open,
                )

                # 重置状态
                self._last_activity = time.time()
                self._monitor_stop_evt.clear()

                # 启动“长时间无消息”监控线程
                if self.idle_timeout and self.idle_timeout > 0:
                    self._monitor_thread = threading.Thread(
                        target=self._activity_monitor_loop,
                        daemon=True,
                    )
                    self._monitor_thread.start()
                else:
                    self._monitor_thread = None

                self.ws.run_forever(
                    ping_interval=self.ping_interval,
                    ping_timeout=self.ping_timeout,
                    **self._wss_proxies,
                )

            except Exception as e:
                logger.exception(
                    "[OrderBookWS] run_forever error",
                )

            # 连接生命周期结束，停止监控线程和 ping 线程
            self._monitor_stop_evt.set()

            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=1)

            if self._stop:
                break

            logger.info(
                f"[OrderBookWS] Disconnected, reconnecting in {self.reconnect_delay}",
            )
            time.sleep(self.reconnect_delay)

    def stop(self):
        """
        手动停止（优雅退出）
        """
        logger.info("[OrderBookWS] Stopping...")
        self._stop = True
        self._monitor_stop_evt.set()

        if self.ws:
            try:
                self.ws.close()
            except Exception:
                logger.exception("[OrderBookWS] error when closing ws")

    # ---------- WebSocket 回调 ----------

    def _on_open(self, ws: WebSocket):
        logger.info("[OrderBookWS] Opened")

        sub_msg = {"assets_ids": self.asset_ids, "type": MARKET_CHANNEL}

        ws.send(json.dumps(sub_msg))
        logger.info("[OrderBookWS] Sent subscribe: {}", json_dumps(sub_msg))

    def _on_callback(self):
        if self.callback is not None:
            try:
                self.callback(self.order_books)
            except Exception:
                logger.exception(f"wss callback error")

    def _on_message(self, ws: WebSocket, message: str):
        # 收到任何消息都算活跃
        self._last_activity = time.time()

        try:
            messages = json.loads(message)
            if not isinstance(messages, list):
                messages = [messages]
        except json.decoder.JSONDecodeError:
            # 非 JSON 消息直接忽略，或者按需处理
            logger.debug(f"[OrderBookWS] Non-JSON message: {message}")
            return

        try:
            for message in messages:
                event = message["event_type"]
                timestamp = int(message["timestamp"]) / 1000

                if event == MarketEvent.PRICE_CHANGE:
                    for price in message["price_changes"]:
                        if price["asset_id"] in self.asset_ids:
                            self.order_books[price["asset_id"]].set_price(
                                price, timestamp
                            )
                elif event == MarketEvent.TICK_SIZE_CHANGE:
                    self.order_books[message["asset_id"]].tick_size = message[
                        "new_tick_size"
                    ]
                elif event == MarketEvent.BOOK:
                    order = self.order_books[message["asset_id"]]
                    self.order_books[message["asset_id"]] = order.model_validate(
                        {**order.model_dump(), **message}
                    )
            self._on_callback()
        except Exception:
            logger.exception(f"[OrderBookWS] receive message error: {message}")
            # 不再 exit(1)，而是交给外层重连

    def _on_error(self, ws: WebSocket, error):
        logger.error(f"[OrderBookWS] Error: {error}")
        # 出现错误时关闭连接，交给外层循环重连
        try:
            ws.close()
        except Exception:
            logger.exception("[OrderBookWS] error when closing on error")

    def _on_close(self, ws: WebSocket, close_status_code, close_msg):
        logger.info(f"[OrderBookWS] Closed: code={close_status_code}, msg={close_msg}")
        # 不再 exit(0)，让 run_forever 返回，外层 while 负责重连

    # ---------- “长时间无消息”监控 ----------

    def _activity_monitor_loop(self):
        """
        如果长时间（idle_timeout 秒）没有收到任何消息，则主动关闭连接，
        交由外层循环进行重连。
        """
        while not self._monitor_stop_evt.is_set() and not self._stop:
            now = time.time()
            if self.idle_timeout and now - self._last_activity > self.idle_timeout:
                logger.info(
                    f"[OrderBookWS] No activity for %ss, closing connection to force reconnect..., {self.idle_timeout}"
                )
                try:
                    if self.ws:
                        self.ws.close()
                except Exception:
                    logger.exception("[OrderBookWS] error when closing in idle monitor")
                break

            # 每秒检查一次
            self._monitor_stop_evt.wait(1)


def handle_user_message(msg: dict):
    # 这里可以根据 type=TRADE / PLACEMENT / UPDATE 等自己做处理
    logger.info("[USER EVENT], type: {}, msg: {}", msg.get("type"), json_dumps(msg))
