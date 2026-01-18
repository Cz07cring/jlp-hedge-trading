# JLP Hedge Trading

JLP (Jupiter Liquidity Pool) 对冲套利系统，通过在 AsterDex 做空对冲 JLP 的风险敞口，赚取 JLP APR 收益和资金费率。

## 功能特性

- **Delta Neutral 对冲**：自动计算 JLP 持仓的 SOL/ETH/BTC 敞口，在 AsterDex 开空单对冲
- **Maker 订单执行**：使用 GTX (Post-Only) 限价单，降低交易手续费
- **大单拆分**：自动拆分大额订单，减少市场冲击
- **云端同步**：实时数据上报、远程配置、通知告警

## 快速开始

### 🐳 方式一：Docker 部署（推荐）

**1. 创建目录**
```bash
mkdir -p ~/jlp-hedge/{config,data,logs}
cd ~/jlp-hedge
```

**2. 下载配置文件**
```bash
# 下载 docker-compose.yml
curl -fsSL https://jlp.finance/docker-compose.yml -o docker-compose.yml

# 或者手动创建（推荐使用配置生成器）
# 访问 https://jlp.finance/download 获取完整配置
```

**3. 配置账户**

编辑 `config/accounts.json`，填入你的凭证：
```json
{
  "accounts": [{
    "name": "Main Account",
    "enabled": true,
    "asterdex": {
      "chain": "solana",
      "user_address": "你的钱包地址",
      "api_key": "AsterDex API Key",
      "api_secret": "AsterDex API Secret"
    }
  }],
  "cloud": {
    "enabled": true,
    "api_url": "https://jlp.finance",
    "license_key": "你的 License Key"
  }
}
```

💡 **提示**：访问 [jlp.finance/download](https://jlp.finance/download) 使用配置生成器，一键生成完整配置。

**4. 设置环境变量**
```bash
# 创建 .env 文件
cat > .env << 'EOF'
LICENSE_KEY=JLP-XXXX-XXXX-XXXX-XXXX
EOF
```

**5. 启动服务**
```bash
docker compose up -d

# 查看日志
docker compose logs -f

# 停止服务
docker compose down
```

### 📦 方式二：一键安装脚本

```bash
curl -fsSL https://jlp.finance/install.sh | bash
```

脚本会自动：
- 检查 Docker 安装
- 创建目录结构
- 下载配置模板
- 引导你填写凭证
- 启动服务

### 🐍 方式三：Python 手动安装

```bash
# 克隆项目
git clone https://github.com/ring07c/jlp-hedge-trading.git
cd jlp-hedge-trading

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置
cp config/accounts.example.json config/accounts.json
# 编辑 config/accounts.json

# 运行
python main.py
```

## 环境变量

Docker 部署支持以下环境变量（优先级高于配置文件）：

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `LICENSE_KEY` | ✅ | - | License Key（从 SaaS 获取） |
| `CLOUD_API_URL` | ❌ | `https://jlp.finance` | 云端 API 地址 |
| `CLOUD_ENABLED` | ❌ | `true` | 启用云端功能 |
| `REPORT_INTERVAL` | ❌ | `300` | 数据上报间隔（秒） |
| `LOG_LEVEL` | ❌ | `INFO` | 日志级别 |
| `TZ` | ❌ | `Asia/Shanghai` | 时区 |

## 配置说明

### accounts.json 结构

```json
{
  "accounts": [
    {
      "name": "账户名",
      "enabled": true,
      "asterdex": {
        "chain": "solana",
        "user_address": "钱包地址",
        "api_key": "API Key",
        "api_secret": "API Secret"
      },
      "trading": {
        "leverage": 1,
        "slippage": 0.001,
        "maker_order": {
          "enabled": true,
          "order_timeout": 1.0,
          "split_order_enabled": true,
          "split_order_threshold": 1500.0
        }
      }
    }
  ],
  "global": {
    "rebalance_interval": 600,
    "rebalance_threshold": 0.02,
    "max_funding_rate": 0.001,
    "min_margin_ratio": 0.5
  },
  "cloud": {
    "enabled": true,
    "api_url": "https://jlp.finance",
    "license_key": "JLP-XXXX-XXXX-XXXX-XXXX",
    "report_interval": 300
  }
}
```

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

## 项目结构

```
jlp-hedge-trading/
├── clients/                 # API 客户端
│   └── asterdex_client.py   # AsterDex API
├── cloud/                   # 云端模块
│   ├── client.py            # 云端 API 客户端
│   ├── license_manager.py   # License 管理
│   ├── data_reporter.py     # 数据上报
│   └── config_sync.py       # 配置同步
├── services/                # 业务服务
│   ├── order_executor.py    # 订单执行
│   └── maker_order_executor.py
├── strategies/              # 交易策略
│   └── delta_neutral.py     # Delta Neutral
├── config/                  # 配置文件
│   └── accounts.example.json
├── main.py                  # 主程序
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 云端功能

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

## 命令参考

```bash
# 运行主程序
python main.py

# 单次调仓检查
python main.py --once

# 查看状态
python main.py --status

# 测试云端连接
python main.py --test-cloud
```

## 安全说明

- ✅ **API Key 本地存储**：敏感信息只存在你的服务器
- ✅ **开源代码**：完整代码可审查
- ✅ **云端可选**：可完全离线运行
- ✅ **只读 License**：License 仅用于验证订阅

## 常见问题

### License 验证失败
1. 检查 License Key 是否正确
2. 检查网络是否能访问 jlp.finance
3. 检查订阅是否已过期

### 数据不上报
1. 检查 `cloud.enabled` 是否为 `true`
2. 检查 `LICENSE_KEY` 环境变量
3. 查看日志是否有错误

### 多账户被限制
- 专业版仅支持 1 个账户
- 升级到终身版支持多账户
- 服务端会拒绝超限账户的数据

## License

MIT
