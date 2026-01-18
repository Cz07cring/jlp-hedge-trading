# Configuration Guide

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LICENSE_KEY` | ✅ | - | License key from jlp.finance |
| `CLOUD_API_URL` | ❌ | `https://jlp.finance` | SaaS platform URL (license, data sync) |
| `HEDGE_API_URL` | ❌ | `https://api.jlp.finance` | Hedge calculation API |
| `CLOUD_ENABLED` | ❌ | `true` | Enable cloud features |
| `REPORT_INTERVAL` | ❌ | `300` | Data reporting interval (seconds) |
| `LOG_LEVEL` | ❌ | `INFO` | Log level |
| `TZ` | ❌ | `Asia/Shanghai` | Timezone |

## accounts.json Structure

```json
{
  "accounts": [
    {
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
          "order_timeout": 5.0,
          "split_order_enabled": true,
          "split_order_threshold": 500.0
        }
      }
    }
  ],
  "global": {
    "hedge_api_url": "https://api.jlp.finance",
    "rebalance_interval": 600,
    "rebalance_threshold": 0.02
  },
  "cloud": {
    "enabled": true,
    "api_url": "https://jlp.finance",
    "license_key": "YOUR_LICENSE_KEY"
  }
}
```

## Trading Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `rebalance_interval` | Rebalance check interval (seconds) | 600 |
| `rebalance_threshold` | Position deviation threshold to trigger rebalance | 0.02 (2%) |
| `max_funding_rate` | Maximum acceptable funding rate | 0.001 (0.1%) |
| `min_margin_ratio` | Minimum margin ratio warning | 0.1 (10%) |

## Maker Order Settings

| Parameter | Description | Default |
|-----------|-------------|---------|
| `enabled` | Enable maker (limit) orders | true |
| `order_timeout` | Single order timeout (seconds) | 5.0 |
| `split_order_enabled` | Split large orders | true |
| `split_order_threshold` | Split threshold (USD) | 500.0 |

## Notifications

All notifications (Telegram, WeChat) are managed through the SaaS dashboard.

Configure at: [jlp.finance/hedge/config](https://jlp.finance/hedge/config)

The local executor only handles trading - no notification code runs locally.

## Get Your Credentials

1. **License Key**: [jlp.finance/settings/license](https://jlp.finance/settings/license)
2. **AsterDex API**: [asterdex.com/api-management](https://www.asterdex.com/api-management)
