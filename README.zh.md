# poly-position-watcher

## 概览

`poly-position-watcher` 专注实时仓位与订单监控：

- WSS 实时追踪 `TRADE` 与 `ORDER`（仓位 + 订单）
- HTTP 轮询兜底，保证可用性
- 可选手续费计算（开关 + 自定义公式）

**说明：WSS 断线会自动检测并重连。**

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
    enable_fee_calc=True,  # 可选：启用手续费计算
    # fee_calc_fn=custom_fee_fn,  # 可选：覆盖手续费公式
) as service:
    # 非阻塞：获取当前仓位和订单（立即返回）
    position: UserPosition = service.get_position("<token_id>")
    order: OrderMessage = service.get_order("<order_id>")
    print(position)
    print(order)
    service.show_positions(limit=10)
    service.show_orders(limit=10)
    
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

## 友好打印

```python
service.show_positions(limit=10)
service.show_orders(limit=10)
```

![Positions Table](asset/show_position.png)

## ⚠️ **手续费（Fee / Taker Fee）注意事项**
Polymarket 在部分市场启用 taker fee / maker rebate。本库 **已完整支持手续费计算**，并可按需控制：

- 通过 `enable_fee_calc=True` 开启，基于 trades/orders 的 `feeRateBps` 计算
- 通过 `fee_calc_fn` 自定义手续费公式
- 不开启（默认）则按 pre-fee 方式计算

默认手续费公式（未传 `fee_calc_fn` 时）：
`fee = 0.25 * (p * (1 - p)) ** 2 * (fee_rate_bps / 1000)`，`new_size = (1 - fee) * size`。

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
| `enable_fee_calc` | bool | False | 使用 trades/orders 的 `feeRateBps` 进行手续费调整 |
| `fee_calc_fn` | callable | None | 自定义手续费函数：`(size, price, fee_rate_bps) -> new_size` |

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
