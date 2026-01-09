"""Minimal example for bootstrapping existing orders/positions."""
from __future__ import annotations

import os

from py_clob_client.client import ClobClient

from poly_position_watcher import PositionWatcherService


def build_client() -> ClobClient:
    """Create a ClobClient using environment secrets."""
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=os.getenv("POLY_API_KEY"),
        chain_id=137,
        signature_type=1,
        funder=os.getenv("POLYMARKET_PROXY_ADDRESS"),
    )
    api_creds = client.create_or_derive_api_creds()
    client.set_api_creds(api_creds)
    return client


def main() -> None:
    client = build_client()

    market_ids = ["0xca595a16069e6cd9bce150ecd5cec487b848d9040412547c88e87553af24f620"]
    order_ids = ["0xa58ffaf62f6b78c9dcdcf6a3fb7537e216b49c997..."]
    token_id = "45011460110592496504859016909655199515278476710837825147676454435935473238039"
    wss_proxy = {
        "http_proxy_host": "127.0.0.1",
        "http_proxy_port": 8118,
        "proxy_type": "http",
    }

    # 单一 with 语句：初始化仓位并通过 HTTP 兜底监控
    with PositionWatcherService(
            client=client,
            wss_proxies=wss_proxy,
            init_positions=True,  # 通过官方 API 初始化现有仓位
            enable_http_fallback=True,  # 启用 HTTP 兜底（线程常驻运行）
            http_poll_interval=3,  # HTTP 轮询间隔（秒）
            add_init_positions_to_http=True,  # 将初始化仓位得到的 condition_id 加入 HTTP 监控
    ) as service:
        # 非阻塞获取
        position = service.get_position(token_id)
        order = service.get_order(order_ids[0])

        # 等待并获取订单和仓位
        order = service.blocking_get_order(order_ids[0], timeout=5)
        position = service.blocking_get_position(
            token_id=token_id,
            timeout=5,
        )
        print(order)
        print(position)

        # 动态添加 HTTP 监控的市场和订单（HTTP 线程已经在运行）
        service.add_http_listen(market_ids=market_ids, order_ids=order_ids)
        # 可以动态移除或清空 HTTP 监控（线程继续运行）
        service.remove_http_listen(market_ids=market_ids, order_ids=order_ids)
        service.clear_http()  # 清空所有监控项，但线程继续运行


if __name__ == "__main__":
    main()
