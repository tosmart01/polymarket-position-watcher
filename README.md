# poly-position-watcher

English README (default). For Chinese: [README.zh.md](README.zh.md)

---

⚠️ **Fee notice (taker fee / maker rebate)**

Some Polymarket markets have enabled a taker fee / maker rebate mechanism. The official API returns `feeRateBps` for order placement on those markets, but **historical trade endpoints (e.g. `get_trades`) do not return explicit fee fields or fee deductions**.

Therefore:

- This library computes positions based on trade price and size and **does not deduct fee costs**.
- If you executed **taker trades**, fees may have been charged but will not appear in `get_trades`.
- Returned positions, cost basis, and unrealized PnL **exclude fees**.
- In fee-enabled markets, **actual PnL will differ** from this library's results (especially with high-frequency or heavy taker activity).

If you need precise net cost or net PnL:
- compute fees yourself from CLOB fee-rate or on-chain events,
- or treat this library as a **pre-fee (fee-excluded)** estimate,
- and deduct fees based on your strategy/market.

---

## Overview

`poly-position-watcher` is a lightweight position and order watcher:

- Track real-time `TRADE` and `ORDER` events via WebSocket
- Unify HTTP history and WebSocket incremental data into one Pydantic model set
- Maintain in-memory positions and order states per `token_id`, with blocking read APIs
- Provide an extensible HTTP polling context as a WebSocket fallback
- Built-in FIFO position calculator with mark-to-market valuation and PnL

## Installation

```bash
pip install poly-position-watcher
# pip install poly-position-watcher --index-url https://pypi.org/simple
```

If installing from source, clone this repo and run `pip install -e .`.

## Quick start

```python
from py_clob_client.client import ClobClient
from poly_position_watcher import PositionWatcherService, OrderMessage, UserPosition

client = ClobClient(
    base_url="https://clob.polymarket.com",
    key="<wallet-key>",
    secret="<wallet-secret>",
)

with PositionWatcherService(
    client=client,
    init_positions=True,  # Initialize positions via official API
    enable_http_fallback=True,  # Enable HTTP polling fallback
    add_init_positions_to_http=True,  # Auto-add condition_ids from init positions to HTTP monitoring
) as service:
    # Non-blocking: Get current positions and orders (returns immediately)
    position: UserPosition = service.get_position("<token_id>")
    order: OrderMessage = service.get_order("<order_id>")
    print(position)
    print(order)
    
    # Blocking: Wait for position/order updates (with timeout)
    position: UserPosition = service.blocking_get_position("<token_id>", timeout=5)
    order: OrderMessage = service.blocking_get_order("<order_id>", timeout=3)
    print(position)
    print(order)
    
    # Optional: If you open new positions/orders and want to monitor them via HTTP fallback
    # service.add_http_listen(market_ids=["<condition_id>"], order_ids=["<order_id>"])
    # service.remove_http_listen(market_ids=["<condition_id>"], order_ids=["<order_id>"])
    # service.clear_http()  # Clear all monitoring items, threads continue running
```

### Full example (`examples/http_bootstrap_example.py`)

Example output:

```shell
OrderMessage(
  type: 'update',
  event_type: 'order',
  asset_id: '7718951783559279583290056782453440...',
  associate_trades: ['8bf02a75-5...'],
  id: '0x74a71abb9efe59c994e0...',
  market: '0x3b7e9926575eb7fae2...',
  order_owner: None,
  original_size: 37.5,
  outcome: 'Up',
  owner: '',
  price: 0.52,
  side: 'BUY',
  size_matched: 37.5,
  timestamp: 0.0,
  filled: True,
  status: 'MATCHED',
  created_at: datetime.datetime(2025, 12, 8, 9, 44, 50, tzinfo=TzInfo(0))
)
UserPosition(
  price: 0.0,
  size: 0.0,
  volume: 0.0,
  token_id: '',
  last_update: 0.0,
  market_id: None,
  outcome: None,
  created_at: None
)
```

### Position Initialization

When `init_positions=True`, the service will:
- Fetch current positions via the official Polymarket API (`/positions`)
- Create fake trades from position data to maintain compatibility with existing trade-based calculations
- Skip positions with `currentValue = 0` (empty positions)
- Optionally add condition IDs to HTTP monitoring if `add_init_positions_to_http=True`

The HTTP fallback polling threads run persistently throughout the `with` statement lifecycle. You can dynamically add/remove markets and orders without restarting threads.

> Note: If you start the watcher before any positions exist, set `init_positions=False`. The HTTP fallback can be enabled independently and will start with empty monitoring sets if needed.

## Configuration

### Service Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `init_positions` | bool | False | Initialize positions via official Polymarket API on startup |
| `enable_http_fallback` | bool | False | Enable persistent HTTP polling threads as WebSocket fallback |
| `http_poll_interval` | float | 3.0 | HTTP polling interval in seconds |
| `add_init_positions_to_http` | bool | False | Automatically add condition IDs from initialized positions to HTTP monitoring |

### Environment Variables

| Environment variable | Description |
| --- | --- |
| `poly_position_watcher_LOG_LEVEL` | Log level, default `INFO` |

To set a proxy for WebSocket connections, build a dict before creating `PositionWatcherService` and pass it as `wss_proxies`:

```python
PROXY = {"http_proxy_host": "127.0.0.1", "http_proxy_port": 7890}
service = PositionWatcherService(client, wss_proxies=PROXY)
```

## Dependencies

- [`py-clob-client`](https://github.com/Polymarket/py-clob-client)
- [`pydantic`](https://docs.pydantic.dev/)
- [`websocket-client`](https://github.com/websocket-client/websocket-client)
- [`requests`](https://requests.readthedocs.io/en/latest/)

## Layout

```
poly_position_watcher/
├── api_worker.py          # HTTP backfill and context management
├── position_service.py    # Core entry; maintains position/order caches
├── trade_calculator.py    # Position calculation utils
├── wss_worker.py          # WebSocket client implementation
├── common/                # Logging and enums
└── schema/                # Pydantic models
```

## License

MIT
