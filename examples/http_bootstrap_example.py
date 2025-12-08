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

    TARGET_MARKETS = ["0x3b7e9926575eb7fae204d27ee9d3c9d..."]
    TARGET_ORDERS = ["0xa58ffaf62f6b78c9dcdcf6a3fb7537e216b49c997..."]
    token_id = "45011460110592496504859016909655199515278476710837825147676454435935473238039"
    wss_proxy = {
        "http_proxy_host": "127.0.0.1",
        "http_proxy_port": 8118,
        "proxy_type": "http",
    }
    with PositionWatcherService(client=client, wss_proxies=wss_proxy) as service:
        # 如果已经存在历史仓位，需要提前告诉 http_listen 所有关心的 markets / orders 并开启 bootstrap_http
        with service.http_listen(markets=TARGET_MARKETS, orders=TARGET_ORDERS, bootstrap_http=True):
            order = service.blocking_get_order(TARGET_ORDERS[0], timeout=5)
            position = service.blocking_get_position(
                token_id=token_id,
                timeout=5,
            )
            print(order)
            print(position)


if __name__ == "__main__":
    main()
