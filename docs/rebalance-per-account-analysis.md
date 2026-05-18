# JLP 多账户调仓差异 — 深度分析

## 一、结论摘要

每个账户的「调仓优化」表现不同，**既有容错机制的影响，也有账户级配置与仓位结构的差异**：

| 维度 | 是否导致“每账户不同” | 说明 |
|------|----------------------|------|
| 容错：调仓阈值 (rebalance_threshold) | 否 | 全局统一，仅决定「偏差多大才触发调仓」 |
| 容错：最小下单量 (min_order_size) | 是 | 按账户配置，决定「多小的 delta 被过滤掉」 |
| 仓位与目标 (JLP/CEX 持仓) | 是 | 每账户不同，导致 delta / deviation_pct 不同 |
| Maker/拆单/滑点等执行参数 | 是 | 按账户配置，执行路径与成交结果不同 |
| 执行层最小量 (MIN_QUANTITY) | 部分 | 代码中写死，与账户 min_order_size 可能不一致 |

---

## 二、配置与数据流总览

### 2.1 配置来源

```
accounts.json
├── accounts[]                    # 每账户一份
│   ├── name, enabled
│   ├── asterdex (链/地址/API)
│   └── trading
│       ├── leverage, slippage
│       ├── min_order_size        # 按账户，SOL/ETH/BTC
│       └── maker_order           # 按账户
│           ├── enabled, order_timeout, total_timeout
│           ├── price_tolerance, max_iterations
│           └── split_order_*     # 拆单阈值/单笔金额
│
└── global                        # 所有账户共用
    ├── hedge_api_url
    ├── rebalance_interval        # 调仓检查间隔
    ├── rebalance_threshold       # 调仓阈值 (如 0.02 = 2%)
    ├── max_funding_rate, min_margin_ratio, max_daily_loss
    └── ...
```

- **全局 (global)**：`rebalance_threshold`、`rebalance_interval`、风控参数、Hedge API 地址等，所有账户一致。
- **账户级 (trading)**：`min_order_size`、`maker_order`（含 `price_tolerance`、拆单参数）、`slippage`、`leverage`，可逐账户不同。

### 2.2 策略与组件初始化（每账户一份）

每个启用账户对应一个 `DeltaNeutralStrategy`，内部为**该账户**创建：

- `AsterDexClient`：该账户的链/地址/API
- `PositionManager(..., rebalance_threshold=global_config.rebalance_threshold, min_order_sizes=account_config.trading.min_order_size)`
- `OrderExecutor`：市价单用 `account_config.trading.slippage`；Maker 用 `account_config.trading.maker_order` 构造的 `MakerOrderConfig`
- `RiskMonitor`：用 global 风控参数

因此：**“是否触发调仓”的阈值是全局的；“多小的单子不调”和“怎么执行”是按账户的。**

---

## 三、调仓决策链路（为何有的账户调、有的不调）

### 3.1 单账户单次检查流程

```
run_once() [DeltaNeutralStrategy]
  → get_hedge_status() [PositionManager]
       → get_jlp_balance()           # 本账户 JLP
       → get_target_positions(jlp)   # Hedge API: jlp_amount → 目标仓位
       → get_current_positions()     # 本账户 CEX 当前仓位
       → calculate_deltas(target, current)
  → filter_significant_deltas(deltas, target_positions)
  → 若有 significant_deltas → order_executor.execute_all(...)
```

### 3.2 目标仓位与 delta 的账户差异

- **目标仓位**：只依赖 `jlp_amount`。同一 `jlp_amount` 下，Hedge API 返回的目标一致；不同账户 JLP 不同 → 目标不同。
- **当前仓位**：来自本账户 CEX 持仓，各账户必然不同。
- **delta**：`target - current`，按 symbol 计算；**deviation_pct = |delta| / target.amount**（target.amount 为该 symbol 目标数量）。

因此：**即使 rebalance_threshold 相同，各账户的 deviation_pct 分布不同**，有的账户会超过阈值、有的不会。

### 3.3 容错 1：调仓阈值 (rebalance_threshold)

- **位置**：`PositionManager.filter_significant_deltas`
- **逻辑**：`deviation_pct < self.rebalance_threshold` → 该 symbol 不加入本次调仓列表。
- **取值**：`global_config.rebalance_threshold`（如 0.02），**全局一致**。
- **作用**：形成「容错带」：偏差在 2% 以内不调，减少频繁小额调仓与手续费。

```python
# position_manager.py 304-316
if target.amount > 0:
    deviation_pct = abs(delta.delta) / target.amount
if deviation_pct < self.rebalance_threshold:
    continue  # 跳过
```

### 3.4 容错 2：最小下单量 (min_order_sizes)

- **位置**：同上，`filter_significant_deltas`
- **逻辑**：`abs(delta.delta) < min_order_sizes[symbol]` → 该 symbol 不调仓。
- **取值**：`account_config.trading.min_order_size`（SOL/ETH/BTC），**按账户**。
- **作用**：避免「理论需要调仓但数量小于交易所/策略最小单位」的无效单；**不同账户可设不同最小量，从而同一 delta 在 A 账户被过滤、在 B 账户可能保留**。

```python
# position_manager.py 319-322
min_size = Decimal(str(self.min_order_sizes.get(symbol, 0.001)))
if abs(delta.delta) < min_size:
    continue  # 跳过
```

### 3.5 小结：谁会被调仓

对某一账户、某一 symbol：

- 必须同时满足：
  1. `deviation_pct >= rebalance_threshold`（全局）
  2. `|delta| >= min_order_sizes[symbol]`（该账户）

因此：

- **容错**：由 1 + 2 共同构成；容错带是「比例 + 绝对量」双重条件。
- **每账户不同**：来自 (1) 各账户 target/current 不同 → deviation_pct 与 delta 不同；(2) 各账户 min_order_size 可不同 → 边界附近行为不同。

---

## 四、执行层差异（同一 delta 如何被执行）

### 4.1 市价单 vs Maker

- **市价单**：用 `account_config.trading.slippage`，快速成交，手续费较高。
- **Maker**：用该账户的 `maker_order`（order_timeout、price_tolerance、max_iterations、拆单等），挂单成交，手续费低，但可能部分成交或超时。

同一 delta，不同账户可能一个走市价、一个走 Maker，或 Maker 参数不同，**执行路径和结果都会不同**。

### 4.2 Maker 相关参数（按账户）

- **price_tolerance**：盘口变化超过该比例会撤单重挂；不同账户可设不同，挂单“粘性”不同。
- **order_timeout / total_timeout / max_iterations**：单笔/总超时与重试次数，影响「本次调仓是否做完、做多少」。
- **split_order_***：是否拆单、阈值、单笔 min/max 金额（及随机/固定），**直接改变挂单笔数、每笔大小和成交节奏**。

这些都会让「调仓优化」在观感上不同（例如有的账户多笔小单、有的少笔大单）。

### 4.3 执行层最小量（与配置的潜在不一致）

- **OrderExecutor / MakerOrderExecutor** 内部使用**写死的** `MIN_QUANTITY`（如 SOL 0.01、ETH/BTC 0.001）做 `_round_quantity` 与「小于则跳过」判断。
- **PositionManager** 使用的是账户配置的 `min_order_sizes`。

因此：

- 若某账户 `min_order_size` 大于执行层 `MIN_QUANTITY`：以 position_manager 为准，小单已在过滤阶段被拦下。
- 若某账户 `min_order_size` 小于执行层 `MIN_QUANTITY`：理论上可能通过过滤，但在执行层被舍入到 0 或跳过，形成**第二道容错**，且与配置不完全一致（执行层不读账户 min_order_size）。

---

## 五、数值示例（说明“每账户不同”）

假设 global `rebalance_threshold = 0.02`，两账户 SOL 目标均为 100：

| 账户 | 当前 SOL | delta | deviation_pct | 账户 min_order_size (SOL) | 是否进入调仓列表 |
|------|----------|-------|----------------|----------------------------|------------------|
| A    | 97       | +3    | 3%             | 0.01                       | 是（>2% 且 >0.01） |
| B    | 98.5     | +1.5  | 1.5%           | 0.01                       | 否（<2%）        |
| C    | 97       | +3    | 3%             | 1.0                        | 是（>1.0）       |
| D    | 97       | +0.5  | 0.5%           | 1.0                        | 否（<1.0，虽比例可调大但被绝对量过滤） |

可见：**同一阈值下，是否调仓由各账户的 current/target 与 min_order_size 共同决定**，因此会出现「有的账户调、有的不调」或「调的种类/数量不同」。

---

## 六、总结表与建议

### 6.1 差异来源归纳

| 来源 | 全局/按账户 | 对“调仓优化不同”的贡献 |
|------|-------------|-------------------------|
| rebalance_threshold | 全局 | 统一容错带；不直接造成账户间差异 |
| min_order_size | 按账户 | 小单过滤边界不同 → 调仓列表不同 |
| JLP 与 CEX 仓位 | 按账户 | delta / deviation_pct 不同 → 是否触发、调多少不同 |
| maker_order / slippage | 按账户 | 执行方式与成交结果不同 |
| 执行层 MIN_QUANTITY | 写死 | 与 min_order_size 可能不一致，形成第二道最小量 |

### 6.2 若希望“更一致”或“更可预期”

- **统一容错感**：保持 `rebalance_threshold` 全局即可；若需某账户更敏感，目前需支持「按账户 override 阈值」（当前代码未支持）。
- **统一最小下单行为**：各账户 `min_order_size` 设为相同，且建议不小于执行层 MIN_QUANTITY（0.01/0.001/0.001），避免“配置允许但执行层跳过”的困惑。
- **统一执行风格**：各账户使用相同的 `maker_order`（或统一用市价单），则执行层面的差异主要只剩仓位与 delta 本身。

### 6.3 相关代码位置

- 配置加载与合并：`config/settings.py`（`load_config`、`AccountConfig.from_dict`、global）
- 策略与 PM/Executor 构造：`strategies/delta_neutral.py`（`__init__`）
- 调仓判定：`services/position_manager.py`（`filter_significant_deltas`、`get_hedge_status`）
- 执行与舍入：`services/order_executor.py`、`services/maker_order_executor.py`（`_round_quantity`、`MIN_QUANTITY`）

---

*文档基于当前代码库整理，用于理解多账户调仓差异与容错机制。*
