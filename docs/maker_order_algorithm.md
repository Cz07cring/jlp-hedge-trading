# Maker 订单算法方案

## 一、背景与目标

### 1.1 当前问题
- 使用市价单 (Market Order) 执行调仓，支付高额 Taker 手续费
- 每 10 分钟检测调仓，频繁市价单导致手续费成本累积

### 1.2 目标
- 全部使用 **Maker 订单** (GTX/Post-Only) 执行调仓
- 通过智能挂单算法追踪盘口，提高成交率
- 降低手续费成本 50-60%

---

## 二、核心算法设计

### 2.1 算法流程

```
┌─────────────────────────────────────────────────────────────────┐
│                      Maker 订单执行流程                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐                                                │
│  │ 1. 获取调仓  │                                                │
│  │    目标数量  │                                                │
│  └──────┬──────┘                                                │
│         ▼                                                       │
│  ┌─────────────┐                                                │
│  │ 2. 获取盘口  │  bid1 / ask1                                   │
│  └──────┬──────┘                                                │
│         ▼                                                       │
│  ┌─────────────────────────────────────────┐                    │
│  │ 3. 挂单 (GTX/Post-Only)                  │                    │
│  │    - 开空(卖): 挂 ask1 (卖一价)           │                    │
│  │    - 平空(买): 挂 bid1 (买一价)           │                    │
│  └──────┬──────┘                                                │
│         ▼                                                       │
│  ┌─────────────────────────────────────────┐                    │
│  │ 4. 等待成交 (最长 5 秒)                   │                    │
│  │    - 每 200ms 检查订单状态                │                    │
│  └──────┬──────┘                                                │
│         ▼                                                       │
│  ┌─────────────────────────────────────────┐                    │
│  │           订单状态判断                    │                    │
│  ├─────────────────────────────────────────┤                    │
│  │  完全成交 ──────────────────→ 结束 ✓     │                    │
│  │                                          │                    │
│  │  部分成交 + 超时 ──→ 剩余部分重新挂单     │                    │
│  │                                          │                    │
│  │  未成交 + 超时 ────→ 撤单，重新获取盘口   │                    │
│  │                      └──→ 回到步骤 2     │                    │
│  │                                          │                    │
│  │  盘口变化 > 容忍度 ─→ 立即撤单重挂        │                    │
│  └─────────────────────────────────────────┘                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 挂单价格策略

#### 基础策略：挂盘口第一档

| 操作 | 挂单价格 | 说明 |
|------|----------|------|
| 开空 (卖出开仓) | ask1 (卖一价) | 挂在卖方队列最前，等待买方吃单 |
| 平空 (买入平仓) | bid1 (买一价) | 挂在买方队列最前，等待卖方吃单 |

#### 激进策略（可选）：穿越盘口

当需要更快成交时，可以选择穿越一个 tick：

| 操作 | 挂单价格 | 说明 |
|------|----------|------|
| 开空 (卖出开仓) | bid1 + 1 tick | 比买一高一点，更容易成交但仍是 Maker |
| 平空 (买入平仓) | ask1 - 1 tick | 比卖一低一点，更容易成交但仍是 Maker |

**推荐**：先使用基础策略，如果成交率不理想再考虑激进策略。

### 2.3 追价策略

**追价条件**：盘口向有利方向移动时追价

| 场景 | 有利方向 | 追价行为 |
|------|----------|----------|
| 开空 (卖) | 价格上涨 (ask1 上移) | 撤单，以新 ask1 重挂 |
| 平空 (买) | 价格下跌 (bid1 下移) | 撤单，以新 bid1 重挂 |

**不利方向移动时**：
- 保持当前挂单不动，等待价格回归
- 超时后（5秒）撤单重挂

---

## 三、关键参数配置

```python
class MakerOrderConfig:
    # 单次挂单超时时间 (秒)
    order_timeout: float = 5.0

    # 订单状态检查间隔 (毫秒)
    check_interval_ms: int = 200

    # 盘口变化容忍度 (超过此比例立即撤单重挂)
    price_tolerance: float = 0.0002  # 0.02%

    # 最大循环次数 (防止无限挂单)
    max_iterations: int = 120  # 5秒 × 120 = 10分钟

    # 总超时时间 (秒)，超时后本次调仓结束，等待下个周期
    total_timeout: float = 600  # 10分钟

    # 部分成交阈值，达到此比例视为成功
    partial_fill_threshold: float = 0.95  # 95%

    # 最小剩余数量，小于此值放弃继续挂单
    min_remaining_ratio: float = 0.05  # 5%
```

---

## 四、订单状态处理

### 4.1 完全成交

```
目标: 1.0 SOL
成交: 1.0 SOL
状态: SUCCESS ✓

→ 结束，记录成交结果
```

### 4.2 部分成交 + 超时

```
目标: 1.0 SOL
成交: 0.7 SOL (5秒内)
剩余: 0.3 SOL

→ 撤销当前订单
→ 剩余 0.3 SOL 重新挂单
→ 继续循环
```

### 4.3 部分成交 + 剩余过小

```
目标: 1.0 SOL
成交: 0.98 SOL
剩余: 0.02 SOL (< 5% 且 < 最小下单量)

→ 视为成功，放弃剩余
→ 状态: SUCCESS (98% filled)
```

### 4.4 未成交 + 超时

```
目标: 1.0 SOL
成交: 0 SOL (5秒内)

→ 撤销当前订单
→ 重新获取盘口
→ 以新价格重新挂单
```

### 4.5 总超时

```
目标: 1.0 SOL
成交: 0.5 SOL (10分钟后仍未完成)

→ 记录部分成交结果
→ 状态: PARTIAL (50% filled)
→ 等待下个调仓周期处理剩余
```

---

## 五、盘口监控与撤单逻辑

### 5.1 实时盘口监控

```python
async def monitor_orderbook(symbol: str):
    """
    持续监控盘口变化
    """
    while order_active:
        depth = await client.get_depth(symbol, limit=5)
        current_bid1 = depth['bids'][0][0]
        current_ask1 = depth['asks'][0][0]

        # 检查是否需要撤单重挂
        if should_replace_order(current_bid1, current_ask1):
            await cancel_and_replace()

        await asyncio.sleep(0.2)  # 200ms
```

### 5.2 撤单重挂条件

```python
def should_replace_order(current_best_price, order_price, side):
    """
    判断是否需要撤单重挂
    """
    price_change = abs(current_best_price - order_price) / order_price

    # 条件1: 价格变化超过容忍度
    if price_change > price_tolerance:
        return True

    # 条件2: 价格向有利方向移动 (追价)
    if side == 'SELL' and current_best_price > order_price:
        # 开空时价格上涨，追价
        return True
    if side == 'BUY' and current_best_price < order_price:
        # 平空时价格下跌，追价
        return True

    return False
```

---

## 六、异常处理

### 6.1 盘口异常

| 异常情况 | 处理方式 |
|----------|----------|
| 盘口为空 | 等待 1 秒后重试，最多 3 次 |
| 买卖价差过大 (> 1%) | 记录警告，使用中间价挂单 |
| API 超时 | 重试 3 次，仍失败则跳过本次调仓 |

### 6.2 订单异常

| 异常情况 | 处理方式 |
|----------|----------|
| 挂单被拒绝 (GTX 失败) | 等待盘口更新后重试 |
| 订单已不存在 | 检查成交记录，可能已成交 |
| 撤单失败 | 检查订单状态，可能已成交 |
| 余额不足 | 终止，记录错误 |

### 6.3 网络异常

```python
async def safe_place_order(symbol, side, quantity, price):
    """
    带重试的下单
    """
    for attempt in range(3):
        try:
            return await client.place_order(
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                quantity=quantity,
                price=price,
                time_in_force=TimeInForce.GTX,  # Post-Only
            )
        except NetworkError:
            if attempt < 2:
                await asyncio.sleep(0.5)
            else:
                raise
```

---

## 七、代码结构

```
services/
├── order_executor.py           # 原有入口，调用 MakerOrderExecutor
├── maker_order_executor.py     # 新增：Maker 订单执行器
└── maker_order_config.py       # 新增：配置参数

class MakerOrderExecutor:
    """Maker 订单执行器"""

    async def execute_delta(delta: PositionDelta) -> ExecutionResult:
        """执行单个调仓"""

    async def _execute_maker_order(
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        position_side: PositionSide,
    ) -> MakerOrderResult:
        """执行 Maker 订单的核心循环"""

    async def _get_best_price(symbol: str, side: OrderSide) -> Decimal:
        """获取最佳挂单价格"""

    async def _place_gtx_order(...) -> OrderResult:
        """下 GTX 订单"""

    async def _monitor_order(order_id: str, timeout: float) -> OrderStatus:
        """监控订单状态"""

    async def _cancel_order(order_id: str) -> bool:
        """撤销订单"""
```

---

## 八、日志与监控

### 8.1 关键日志

```python
# 挂单
logger.info(f"[Maker] {symbol} 挂单: {side} {quantity} @ {price}")

# 撤单重挂
logger.info(f"[Maker] {symbol} 撤单重挂: 旧价 {old_price} → 新价 {new_price}")

# 部分成交
logger.info(f"[Maker] {symbol} 部分成交: {filled}/{quantity}")

# 完成
logger.info(f"[Maker] {symbol} 完成: 成交 {filled}, 耗时 {elapsed}s, 重挂 {replace_count} 次")
```

### 8.2 统计指标

| 指标 | 说明 |
|------|------|
| 平均成交时间 | 从下单到完全成交的平均时间 |
| 撤单重挂次数 | 每笔订单平均撤单重挂次数 |
| 成交率 | 完全成交 / 总订单数 |
| 部分成交率 | 部分成交金额 / 目标金额 |
| 节省手续费 | 相比市价单节省的费用估算 |

---

## 九、手续费对比

假设 AsterDex 费率：

| 类型 | 费率 |
|------|------|
| Taker (市价单) | 0.05% |
| Maker (限价单) | 0.02% |

**示例计算**：

每日调仓金额 $10,000 计算：
- 市价单手续费: $10,000 × 0.05% = $5.00
- Maker 手续费: $10,000 × 0.02% = $2.00
- **每日节省: $3.00 (60%)**

每月节省: $90
每年节省: $1,080

---

## 十、配置建议

### 10.1 默认配置（推荐）

```python
config = MakerOrderConfig(
    order_timeout=5.0,           # 单次挂单 5 秒超时
    check_interval_ms=200,       # 200ms 检查一次
    price_tolerance=0.0002,      # 0.02% 价格容忍度
    max_iterations=120,          # 最多循环 120 次
    total_timeout=600,           # 总超时 10 分钟
)
```

### 10.2 激进配置（高频调仓）

```python
config = MakerOrderConfig(
    order_timeout=3.0,           # 单次挂单 3 秒超时
    check_interval_ms=100,       # 100ms 检查一次
    price_tolerance=0.0001,      # 0.01% 价格容忍度
    max_iterations=200,          # 最多循环 200 次
    total_timeout=300,           # 总超时 5 分钟
)
```

### 10.3 保守配置（低频调仓）

```python
config = MakerOrderConfig(
    order_timeout=10.0,          # 单次挂单 10 秒超时
    check_interval_ms=500,       # 500ms 检查一次
    price_tolerance=0.0005,      # 0.05% 价格容忍度
    max_iterations=60,           # 最多循环 60 次
    total_timeout=600,           # 总超时 10 分钟
)
```

---

## 十一、实现计划

1. **Phase 1**: 实现 `MakerOrderExecutor` 基础框架
2. **Phase 2**: 实现盘口监控与撤单重挂逻辑
3. **Phase 3**: 实现部分成交处理
4. **Phase 4**: 添加日志与监控指标
5. **Phase 5**: 测试与调优

---

## 十二、FAQ

**Q1: 为什么不降级为市价单？**

A: 保持全 Maker 策略可以：
- 确保最低手续费
- 避免滑点
- 在极端行情时不会高价追单

**Q2: 如果一直无法成交怎么办？**

A:
- 算法会持续撤单重挂追踪盘口
- 总超时（10分钟）后放弃，等待下个调仓周期
- 下个周期会重新计算 delta，继续尝试

**Q3: 部分成交的剩余部分如何处理？**

A:
- 如果剩余 > 5% 且 > 最小下单量：继续挂单
- 如果剩余 < 5% 或 < 最小下单量：视为成功，放弃剩余
- 总超时后仍有剩余：记录 PARTIAL 状态，下周期处理

**Q4: 网络延迟会影响成交吗？**

A:
- 200ms 检查间隔可以容忍一定延迟
- GTX 订单确保不会变成 Taker
- 最坏情况是错过一些成交机会，但不会多付手续费
