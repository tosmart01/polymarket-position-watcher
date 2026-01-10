# poly-position-watcher

## 概览

`poly-position-watcher` 简单的仓位 | 订单监控实现：

- 通过 WebSocket 追踪实时 `TRADE` 与 `ORDER` 事件
- 把 HTTP API 的历史数据和 WebSocket 增量数据统一成同一套 Pydantic 模型
- 在内存中维护每个 `token_id` 的仓位、订单状态及阻塞式读取接口
- 提供易于扩展的 HTTP 轮询上下文（在 WebSocket 之外兜底同步）
- 内置 FIFO 仓位计算器，支持带市价估值与盈亏指标

**当前项目已内置 WebSocket（WSS）异常检测与自动重连机制。当出现网络波动、连接中断或服务端主动断开等情况时，程序会自动进行重连处理，无需用户手动干预或额外配置。使用方无需关心 WSS 连接的稳定性问题，只需关注业务逻辑即可。**

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

with PositionWatcherService(
    client=client,
    init_positions=True,  # 通过官方 API 初始化仓位
    enable_http_fallback=True,  # 启用 HTTP 兜底轮询
    add_init_positions_to_http=True,  # 自动将初始化仓位的 condition_id 加入 HTTP 监控
) as service:
    # 非阻塞：获取当前仓位和订单（立即返回）
    position: UserPosition = service.get_position("<token_id>")
    order: OrderMessage = service.get_order("<order_id>")
    print(position)
    print(order)
    
    # 阻塞：等待仓位/订单更新（带超时）
    position: UserPosition = service.blocking_get_position("<token_id>", timeout=5)
    order: OrderMessage = service.blocking_get_order("<order_id>", timeout=3)
    print(position)
    print(order)
    
    # 可选：如果你新开了仓位/订单，需要通过 HTTP 兜底监控它们时，可以使用以下 API
    # service.add_http_listen(market_ids=["<condition_id>"], order_ids=["<order_id>"])
    # service.remove_http_listen(market_ids=["<condition_id>"], order_ids=["<order_id>"])
    # service.clear_http()  # 清空所有监控项，但线程继续运行
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

**完整示例（`examples/http_bootstrap_example.py`）**

## ⚠️ **手续费（Fee / Taker Fee）注意事项**
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

## 仓位初始化

当 `init_positions=True` 时，服务会：
- 通过官方 Polymarket API (`/positions`) 获取当前仓位
- 从仓位数据创建假交易以保持与现有基于交易的计算逻辑兼容
- 跳过 `currentValue = 0` 的仓位（空仓位）
- 如果 `add_init_positions_to_http=True`，可选择性地将 condition ID 添加到 HTTP 监控中

HTTP 兜底轮询线程在整个 `with` 语句生命周期内持续运行。可以动态添加/移除市场和订单，无需重启线程。

> ⚠️ 注意：如果你在仓位产生之前启动监控器，设置 `init_positions=False`。HTTP 兜底可以独立启用，如果需要，将以空的监控集合启动。

## 配置

### 服务参数

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `init_positions` | bool | False | 启动时通过官方 Polymarket API 初始化仓位 |
| `enable_http_fallback` | bool | False | 启用持久化 HTTP 轮询线程作为 WebSocket 兜底 |
| `http_poll_interval` | float | 3.0 | HTTP 轮询间隔（秒） |
| `add_init_positions_to_http` | bool | False | 自动将初始化仓位的 condition ID 添加到 HTTP 监控中 |

### 环境变量

| 环境变量 | 说明 |
| --- | --- |
| `poly_position_watcher_LOG_LEVEL` | 调整日志级别，默认为 `INFO` |

若需要为 WebSocket 连接设置代理，可在实例化 `PositionWatcherService` 前自行构造一个字典并通过 `wss_proxies` 传入，例如：

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
