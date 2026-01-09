# poly-position-watcher

⚠️ **手续费（Fee / Taker Fee）注意事项**

Polymarket 在部分市场已启用了 taker fee / maker rebate 机制。官方 API 对这些 market 会返回 `feeRateBps` 给下单时使用，但 **历史成交接口如 `get_trades` 并不会返回具体的手续费字段或手续费扣除明细**。

因此：

- 本仓位库基于成交价格与数量计算仓位、未实现 **手续费成本的扣除**；
- 如果执行的是 **taker 交易**，该交易可能实际产生手续费但不会在 `get_trades` 中体现；
- 所以本库返回的仓位、成本价、浮动盈亏等 **不包含任何手续费影响**；
- 在有手续费的市场中，这将导致 **实际 PnL 相对于本库计算值存在偏差**（特别是高频交易或大量 taker 行为）。

👉 如果你需要精确的净成本或净 PnL，请自行：
- 从 CLOB fee-rate 或链上事件自行计算手续费，
- 或将本库的结果视作 **pre-fee (fee-excluded)** 估算值；
- 并根据你的策略/市场自行扣除 fee 估算。


---

## 概览

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
from poly_position_watcher import PositionWatcherService, OrderMessage, UserPosition

client = ClobClient(
    base_url="https://clob.polymarket.com",
    key="<wallet-key>",
    secret="<wallet-secret>",
)

with PositionWatcherService(client=client) as service:
    # 可选：HTTP 轮询兜底历史仓位
    with service.http_listen(markets=["<condition_id>"], bootstrap_http=True):
        position: UserPosition = service.get_position("<token_id>")
        position: UserPosition = service.blocking_get_position("<token_id>", timeout=5)
        order: OrderMessage = service.get_order("<order_id>")
        order: OrderMessage = service.blocking_get_order("<order_id>", timeout=3)
        print(position)
        print(order)
```

### 完整示例（`examples/http_bootstrap_example.py`）


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
