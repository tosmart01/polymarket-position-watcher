# poly-position-watcher

`poly-position-watcher` 简单的仓位 | 订单监控实现：

- 通过 WebSocket 追踪实时 `TRADE` 与 `ORDER` 事件
- 把 HTTP API 的历史数据和 WebSocket 增量数据统一成同一套 Pydantic 模型
- 在内存中维护每个 `token_id` 的仓位、订单状态及阻塞式读取接口
- 提供易于扩展的 HTTP 轮询上下文（在 WebSocket 之外兜底同步）
- 内置 FIFO 仓位计算器，支持带市价估值与盈亏指标

## 安装

```bash
pip install poly-position-watcher
# pip install poly-position-watcher --index-url https://pypi.org/simple
```

如果你是从源码安装，先克隆本仓库然后执行 `pip install -e .`。

## 快速开始

```python
from py_clob_client.client import ClobClient
from poly_position_watcher import PositionWatcherService

client = ClobClient(
    base_url="https://clob.polymarket.com",
    key="<wallet-key>",
    secret="<wallet-secret>",
)

with PositionWatcherService(client=client) as service:
    # 可选：HTTP 轮询兜底历史仓位
    with service.http_listen(markets=["<condition_id>"], bootstrap_http=True):
        position = service.blocking_get_position("<token_id>", timeout=5)
        order = service.get_order("<order_id>")
        print(position)
        print(order)
```

### 进阶示例（`examples/http_bootstrap_example.py`）

下面是一段更完整的示例脚本（对应 `examples/http_bootstrap_example.py`），演示如何在启动时通过 `http_listen` 获取历史订单 & 仓位，并实时追踪：

```python
from py_clob_client.client import ClobClient
from poly_position_watcher import PositionWatcherService, OrderMessage, UserPosition

client = ClobClient(...)
TARGET_MARKETS = ["0x3b7e9926575eb7fae204d27ee9d3c9db0f34d357e4b8c..."]
TARGET_ORDERS = ["0x74a71abb9efe59c994e0987fa81963aae23d7165f036afb..."]
token_id = ""

with PositionWatcherService(client=client) as service:
    # 如果已经存在历史仓位，需要提前告诉 http_listen 所有关心的 markets / orders 并开启 bootstrap_http
    with service.http_listen(markets=TARGET_MARKETS, orders=TARGET_ORDERS, bootstrap_http=True):
        order: OrderMessage = service.blocking_get_order(TARGET_ORDERS[0], timeout=5)
        position: UserPosition = service.blocking_get_position(
            token_id=token_id,
            timeout=5,
        )
        print(order)
        print(position)

```

示例输出：

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

> ⚠️ 注意：如果你是先启动监控再产生仓位，可令 `bootstrap_http=False` 且 `markets/orders` 参数为空列表即可；只有当已经存在历史仓位/订单需要补偿时才需要提前传入，并开启 `bootstrap_http=True`。

### 只使用 HTTP 轮询

`HttpListenerContext` 可在需要时单独使用：

```python
with service.http_listen(markets=["<condition_id>"], http_poll_interval=2.5) as ctx:
    ctx.add(markets=["other_condition_id"], orders=["<order_id>"])
```

## 可选配置

| 环境变量 | 说明 |
| --- | --- |
| `poly_position_watcher_LOG_LEVEL` | 调整日志级别，默认为 `INFO` |

若需要为 WebSocket 连接设置代理，可在实例化 `PositionWatcherService` 及 `http_listen` 前自行构造一个字典并通过 `wss_proxies` 传入，例如：

```python
PROXY = {"http_proxy_host": "127.0.0.1", "http_proxy_port": 7890}
service = PositionWatcherService(client, wss_proxies=PROXY)
```

## 依赖

- [`py-clob-client`](https://github.com/Polymarket/py-clob-client)
- [`pydantic`](https://docs.pydantic.dev/)
- [`websocket-client`](https://github.com/websocket-client/websocket-client)
- [`requests`](https://requests.readthedocs.io/en/latest/)

## 目录结构

```
poly_position_watcher/
├── api_worker.py          # HTTP 补数与上下文管理
├── position_service.py    # 核心入口，维护仓位/订单缓存
├── trade_calculator.py    # 仓位计算工具
├── wss_worker.py          # WebSocket 客户端实现
├── common/                # 日志与枚举
└── schema/                # Pydantic 数据模型
```

## 许可证

MIT
