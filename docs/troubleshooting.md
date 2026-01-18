# Troubleshooting Guide

## License Issues

### License Verification Failed

**Symptoms:**
```
License 验证失败
请检查 License Key 是否正确
```

**Solutions:**
1. Verify your License Key is correct
2. Check network connectivity to jlp.finance
3. Ensure your subscription is active
4. Try unbinding device at jlp.finance/settings/license

### Account Limit Exceeded

**Symptoms:**
```
账户数量超过限制
```

**Solutions:**
- Pro plan: Limited to 1 account
- Lifetime plan: Up to 100 accounts
- Upgrade at jlp.finance/pricing

## API Connection Issues

### Hedge API Error

**Symptoms:**
```
Hedge API 请求失败
HTTP 401/403
```

**Solutions:**
1. Check if License Key is valid
2. Verify HEDGE_API_URL is correct (default: https://api.jlp.finance)
3. Check network connectivity

### AsterDex Connection Failed

**Symptoms:**
```
AsterDex API 请求失败
```

**Solutions:**
1. Verify API Key and Secret are correct
2. Check if API keys have trading permissions
3. Verify wallet address matches the API key

## Docker Issues

### Container Won't Start

```bash
# Check logs
docker compose logs -f

# Verify config file exists
ls -la config/accounts.json

# Check .env file
cat .env
```

### Permission Denied

```bash
# Fix file permissions
chmod 644 config/accounts.json
chmod 644 .env
```

## Common Error Codes

| Code | Description | Solution |
|------|-------------|----------|
| `MISSING_LICENSE` | License Key not provided | Add X-License-Key header |
| `INVALID_LICENSE` | License Key is invalid | Check License Key |
| `LICENSE_EXPIRED` | Subscription expired | Renew at jlp.finance |
| `ACCOUNT_LIMIT_EXCEEDED` | Too many accounts | Upgrade to Lifetime |

## Getting Help

- **Documentation**: [jlp.finance/docs](https://jlp.finance/docs)
- **Telegram**: [t.me/jlphedge](https://t.me/jlphedge)
- **Email**: support@jlp.finance
