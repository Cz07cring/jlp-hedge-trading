# JLP Hedge Trading

**Delta-Neutral Hedging Executor for JLP Tokens**

[English](#english) | [中文](#中文)

---

<a name="english"></a>
## 🇺🇸 English

### Overview

JLP Hedge Trading is an automated delta-neutral hedging system for JLP (Jupiter Liquidity Pool) tokens. It hedges your JLP exposure by opening short positions on AsterDex, allowing you to earn JLP APR yield while minimizing directional risk.

### Features

- **Delta Neutral Hedging** - Automatically calculate and hedge SOL/ETH/BTC exposure from JLP holdings
- **Maker Order Execution** - Use GTX (Post-Only) limit orders to reduce trading fees
- **Large Order Splitting** - Automatically split large orders to minimize market impact
- **Cloud Sync** - Real-time data reporting, remote configuration, and alerts

### Quick Start

#### 🐳 Option 1: Docker (Recommended)

```bash
# 1. Create directories
mkdir -p ~/jlp-hedge/{config,data,logs}
cd ~/jlp-hedge

# 2. Download docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/Cz07cring/jlp-hedge-trading/main/docker-compose.yml -o docker-compose.yml

# 3. Create config file (use Config Generator at jlp.finance/download)
# Edit config/accounts.json with your credentials

# 4. Create .env file
echo "LICENSE_KEY=JLP-XXXX-XXXX-XXXX-XXXX" > .env

# 5. Start service
docker compose up -d

# View logs
docker compose logs -f
```

#### 📦 Option 2: Quick Install Script

```bash
curl -fsSL https://jlp.finance/install.sh | bash
```

#### 🐍 Option 3: Python Manual Installation

```bash
git clone https://github.com/Cz07cring/jlp-hedge-trading.git
cd jlp-hedge-trading

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp config/accounts.example.json config/accounts.json
# Edit config/accounts.json

python main.py
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LICENSE_KEY` | ✅ | - | License key from jlp.finance |
| `CLOUD_API_URL` | ❌ | `https://jlp.finance` | Cloud API endpoint |
| `CLOUD_ENABLED` | ❌ | `true` | Enable cloud features |
| `REPORT_INTERVAL` | ❌ | `300` | Data reporting interval (seconds) |
| `LOG_LEVEL` | ❌ | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |
| `TZ` | ❌ | `Asia/Shanghai` | Timezone |

### Configuration

```json
{
  "accounts": [{
    "name": "Main Account",
    "enabled": true,
    "asterdex": {
      "chain": "solana",
      "user_address": "YOUR_WALLET_ADDRESS",
      "api_key": "YOUR_API_KEY",
      "api_secret": "YOUR_API_SECRET"
    },
    "trading": {
      "leverage": 1,
      "slippage": 0.001,
      "maker_order": {
        "enabled": true,
        "order_timeout": 1.0
      }
    }
  }],
  "cloud": {
    "enabled": true,
    "api_url": "https://jlp.finance",
    "license_key": "YOUR_LICENSE_KEY"
  }
}
```

💡 **Tip**: Use the [Config Generator](https://jlp.finance/download) to easily create your configuration.

### Cloud Features

Connect to [JLP Hedge SaaS](https://jlp.finance) for:

| Feature | Description |
|---------|-------------|
| 📊 Real-time Dashboard | Monitor equity, profits, and positions online |
| 🔔 Notifications | Telegram / WeChat alerts |
| ⚙️ Remote Config | Adjust strategy parameters online |
| 📈 Historical Data | Equity curves and rebalance history |
| 🔄 Multi-Account | Lifetime plan supports up to 100 accounts |

### Pricing

| Plan | Price | Accounts | Description |
|------|-------|----------|-------------|
| Pro (Monthly) | $29/mo | 1 | Individual users |
| Pro (Yearly) | $199/yr | 1 | Save money |
| Lifetime | $599 | 100 | Multi-account support |

### Security

- ✅ **Local API Keys** - Sensitive credentials stored only on your server
- ✅ **Open Source** - Full code available for audit
- ✅ **Cloud Optional** - Can run completely offline
- ✅ **Non-root User** - Docker runs as non-root for security

### Links

- 🌐 **Website**: [jlp.finance](https://jlp.finance)
- 📊 **Dashboard**: [jlp.finance/dashboard](https://jlp.finance/dashboard)
- 📖 **Documentation**: [jlp.finance/docs](https://jlp.finance/docs)
- ⚙️ **Config Generator**: [jlp.finance/download](https://jlp.finance/download)

---

<a name="中文"></a>
## 🇨🇳 中文

### 概述

JLP Hedge Trading 是一个 JLP (Jupiter Liquidity Pool) 代币的 Delta 中性对冲系统。通过在 AsterDex 做空对冲 JLP 的风险敞口，让您在降低方向性风险的同时赚取 JLP APR 收益。

### 功能特性

- **Delta 中性对冲** - 自动计算 JLP 持仓的 SOL/ETH/BTC 敞口，在 AsterDex 开空单对冲
- **Maker 订单执行** - 使用 GTX (Post-Only) 限价单，降低交易手续费
- **大单拆分** - 自动拆分大额订单，减少市场冲击
- **云端同步** - 实时数据上报、远程配置、通知告警

### 快速开始

#### 🐳 方式一：Docker 部署（推荐）

```bash
# 1. 创建目录
mkdir -p ~/jlp-hedge/{config,data,logs}
cd ~/jlp-hedge

# 2. 下载 docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/Cz07cring/jlp-hedge-trading/main/docker-compose.yml -o docker-compose.yml

# 3. 创建配置文件（推荐使用 jlp.finance/download 的配置生成器）
# 编辑 config/accounts.json 填入你的凭证

# 4. 创建 .env 文件
echo "LICENSE_KEY=JLP-XXXX-XXXX-XXXX-XXXX" > .env

# 5. 启动服务
docker compose up -d

# 查看日志
docker compose logs -f
```

#### 📦 方式二：一键安装脚本

```bash
curl -fsSL https://jlp.finance/install.sh | bash
```

脚本会自动：检查 Docker → 创建目录 → 下载配置 → 引导填写凭证 → 启动服务

#### 🐍 方式三：Python 手动安装

```bash
git clone https://github.com/Cz07cring/jlp-hedge-trading.git
cd jlp-hedge-trading

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp config/accounts.example.json config/accounts.json
# 编辑 config/accounts.json

python main.py
```

### 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `LICENSE_KEY` | ✅ | - | License Key（从 SaaS 获取） |
| `CLOUD_API_URL` | ❌ | `https://jlp.finance` | 云端 API 地址 |
| `CLOUD_ENABLED` | ❌ | `true` | 启用云端功能 |
| `REPORT_INTERVAL` | ❌ | `300` | 数据上报间隔（秒） |
| `LOG_LEVEL` | ❌ | `INFO` | 日志级别 |
| `TZ` | ❌ | `Asia/Shanghai` | 时区 |

### 配置说明

```json
{
  "accounts": [{
    "name": "主账户",
    "enabled": true,
    "asterdex": {
      "chain": "solana",
      "user_address": "你的钱包地址",
      "api_key": "你的 API Key",
      "api_secret": "你的 API Secret"
    },
    "trading": {
      "leverage": 1,
      "slippage": 0.001,
      "maker_order": {
        "enabled": true,
        "order_timeout": 1.0
      }
    }
  }],
  "cloud": {
    "enabled": true,
    "api_url": "https://jlp.finance",
    "license_key": "你的 License Key"
  }
}
```

💡 **提示**：访问 [配置生成器](https://jlp.finance/download) 一键生成完整配置。

### 参数说明

| 参数 | 说明 |
|------|------|
| `rebalance_interval` | 调仓检查间隔（秒），默认 600 |
| `rebalance_threshold` | 触发调仓的偏差阈值，默认 0.02 (2%) |
| `max_funding_rate` | 最大资金费率限制，默认 0.001 (0.1%) |
| `min_margin_ratio` | 最低保证金率警告，默认 0.5 (50%) |
| `maker_order.enabled` | 是否使用 Maker 挂单模式 |
| `split_order_enabled` | 是否启用大单拆分 |
| `split_order_threshold` | 拆单阈值（USD） |

### 云端功能

连接 [JLP Hedge SaaS](https://jlp.finance) 获得：

| 功能 | 说明 |
|------|------|
| 📊 实时仪表盘 | 在线查看净值、收益、持仓 |
| 🔔 通知推送 | Telegram / 企业微信告警 |
| ⚙️ 远程配置 | 在线调整策略参数 |
| 📈 历史数据 | 净值曲线、调仓记录 |
| 🔄 多账户管理 | 终身版支持多账户 |

### 订阅计划

| 计划 | 价格 | 账户数 | 说明 |
|------|------|--------|------|
| 专业版（月付） | $29/月 | 1 | 个人用户 |
| 专业版（年付） | $199/年 | 1 | 个人用户（省钱） |
| 终身版 | $599 | 100 | 多账户支持 |

### 安全说明

- ✅ **API Key 本地存储** - 敏感信息只存在你的服务器
- ✅ **开源代码** - 完整代码可审查
- ✅ **云端可选** - 可完全离线运行
- ✅ **非 root 运行** - Docker 以非特权用户运行

### 常见问题

**License 验证失败**
1. 检查 License Key 是否正确
2. 检查网络是否能访问 jlp.finance
3. 检查订阅是否已过期

**数据不上报**
1. 检查 `cloud.enabled` 是否为 `true`
2. 检查 `LICENSE_KEY` 环境变量
3. 查看日志是否有错误

### 相关链接

- 🌐 **官网**: [jlp.finance](https://jlp.finance)
- 📊 **仪表盘**: [jlp.finance/dashboard](https://jlp.finance/dashboard)
- 📖 **文档**: [jlp.finance/docs](https://jlp.finance/docs)
- ⚙️ **配置生成器**: [jlp.finance/download](https://jlp.finance/download)

---

## Project Structure | 项目结构

```
jlp-hedge-trading/
├── clients/                 # API clients | API 客户端
│   └── asterdex_client.py   # AsterDex API
├── cloud/                   # Cloud module | 云端模块
│   ├── client.py            # Cloud API client | 云端 API 客户端
│   ├── license_manager.py   # License management | License 管理
│   ├── data_reporter.py     # Data reporting | 数据上报
│   └── config_sync.py       # Config sync | 配置同步
├── services/                # Business services | 业务服务
│   ├── order_executor.py    # Order execution | 订单执行
│   └── maker_order_executor.py
├── strategies/              # Trading strategies | 交易策略
│   └── delta_neutral.py     # Delta Neutral strategy
├── config/                  # Configuration | 配置文件
│   └── accounts.example.json
├── main.py                  # Main entry | 主程序
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Support | 支持

- 📧 Email: support@jlp.finance
- 💬 Telegram: [JLP Hedge Community](https://t.me/jlphedge)

## License

MIT

---

© 2024 JLP Hedge. All rights reserved.
