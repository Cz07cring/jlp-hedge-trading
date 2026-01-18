# JLP Hedge Executor

**Delta Neutral Hedging for JLP Token** | **JLP 代币 Delta 中性对冲执行器**

---

## Overview | 概述

JLP Hedge Executor automatically hedges your JLP (Jupiter Liquidity Pool) token exposure by opening short positions on AsterDex, allowing you to earn JLP APR yield while minimizing directional risk.

JLP Hedge 执行器通过在 AsterDex 开空单自动对冲您的 JLP 代币敞口，让您在降低方向性风险的同时赚取 JLP APR 收益。

## Features | 功能特性

- **Delta Neutral Hedging** - Automatically hedge SOL/ETH/BTC exposure
- **Maker Order Execution** - Use limit orders to reduce trading fees
- **Cloud Dashboard** - Real-time monitoring at [jlp.finance](https://jlp.finance)
- **Multi-Account Support** - Lifetime plan supports up to 100 accounts

---

- **Delta 中性对冲** - 自动对冲 SOL/ETH/BTC 敞口
- **Maker 挂单模式** - 使用限价单降低交易手续费
- **云端仪表盘** - 在 [jlp.finance](https://jlp.finance) 实时监控
- **多账户支持** - 终身版支持最多 100 个账户

## Quick Start | 快速开始

### 1. Get License Key | 获取 License Key

Visit [jlp.finance](https://jlp.finance) to subscribe and get your license key.

访问 [jlp.finance](https://jlp.finance) 订阅并获取您的 License Key。

### 2. Create Config | 创建配置

Use the [Config Generator](https://jlp.finance/download) to generate your configuration files.

使用 [配置生成器](https://jlp.finance/download) 生成您的配置文件。

### 3. Run with Docker | 使用 Docker 运行

```bash
# Create directories | 创建目录
mkdir -p ~/jlp-hedge/{config,data,logs}
cd ~/jlp-hedge

# Run container | 运行容器
docker run -d \
  --name jlp-hedge \
  --restart always \
  -e LICENSE_KEY="YOUR_LICENSE_KEY" \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  ring07c/jlphedge:latest

# View logs | 查看日志
docker logs -f jlp-hedge
```

### 4. Docker Compose (Recommended | 推荐)

```yaml
version: '3.8'
services:
  jlp-hedge:
    image: ring07c/jlphedge:latest
    container_name: jlp-hedge
    restart: unless-stopped
    volumes:
      - ./config:/app/config:ro
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - LICENSE_KEY=YOUR_LICENSE_KEY
      - CLOUD_API_URL=https://jlp.finance
      - LOG_LEVEL=INFO
```

## Environment Variables | 环境变量

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LICENSE_KEY` | Yes | - | License key from jlp.finance |
| `CLOUD_API_URL` | No | `https://jlp.finance` | SaaS platform URL (license, data sync) |
| `HEDGE_API_URL` | No | `https://api.jlp.finance` | Hedge calculation API |
| `CLOUD_ENABLED` | No | `true` | Enable cloud features |
| `LOG_LEVEL` | No | `INFO` | Log level (DEBUG/INFO/WARNING/ERROR) |
| `TZ` | No | `Asia/Shanghai` | Timezone |

## Links | 相关链接

- **Website | 官网**: [jlp.finance](https://jlp.finance)
- **Dashboard | 仪表盘**: [jlp.finance/dashboard](https://jlp.finance/dashboard)
- **Documentation | 文档**: [jlp.finance/docs](https://jlp.finance/docs)
- **Config Generator | 配置生成器**: [jlp.finance/download](https://jlp.finance/download)

## Security | 安全说明

- API keys are stored locally only | API 密钥仅存储在本地
- Open source code for audit | 开源代码可审查
- Cloud features are optional | 云端功能可选
- Runs as non-root user | 以非 root 用户运行

## Support | 支持

- Email: support@jlp.finance
- Telegram: [JLP Hedge Community](https://t.me/jlphedge)

---

**License**: MIT

© 2024 JLP Hedge. All rights reserved.
