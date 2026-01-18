# 502 Bad Gateway 错误解决方案

## 问题描述

净值报告服务在采集数据时，访问 Hedge API (`http://localhost:3000/api/v1/hedge-positions`) 返回 502 错误：

```
Server error '502 Bad Gateway' for url 'http://localhost:3000/api/v1/hedge-positions?jlp_amount=468.432'
```

## 问题影响

当 Hedge API 不可用时：
- JLP 价格无法获取，显示为 0
- 账户净值计算错误（只有 USDT 余额，缺少 JLP 价值）
- 本金、对冲比例等指标显示为 0
- 报告发送失败或数据不准确

## 根本原因

Hedge API 服务 (`jlp-hedge-python`) 没有正常运行，可能原因：
1. 服务崩溃或未启动
2. 端口被占用
3. 服务内部错误
4. 依赖的外部 API 超时

---

## 解决方案

### 方案 A：修复 Hedge API 服务（推荐）

#### 1. 检查服务状态
```bash
pm2 status
```

#### 2. 查看错误日志
```bash
pm2 logs jlp-hedge-api --lines 100
```

#### 3. 重启服务
```bash
pm2 restart jlp-hedge-api
```

#### 4. 如果服务不存在，重新启动
```bash
cd /home/ubuntu/jlp套利/jlp-hedge-python

pm2 start /home/ubuntu/anaconda3/envs/bwb/bin/uvicorn \
  --name jlp-hedge-api \
  --interpreter /home/ubuntu/anaconda3/envs/bwb/bin/python \
  --cwd "/home/ubuntu/jlp套利/jlp-hedge-python" \
  -- app.main:app --port 3000 --host 0.0.0.0
```

#### 5. 验证服务正常
```bash
curl http://localhost:3000/api/v1/hedge-positions?jlp_amount=100
```

---

### 方案 B：添加代码容错机制 ✅ 已实施

在 `collector.py` 中增加以下功能：

#### 1. JLP 价格缓存
- 成功获取价格时，保存到本地缓存文件
- API 失败时，使用缓存的价格作为备用

#### 2. 重试机制
- API 请求失败时自动重试 3 次
- 每次重试间隔 2 秒

#### 3. 优雅降级
- 如果缓存也没有，继续采集其他数据
- 在报告中标注 "JLP 价格获取失败，使用缓存值"

#### 代码修改示意：

```python
# collector.py 修改

import json
from pathlib import Path

CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "jlp_price_cache.json"

class EquityCollector:

    def _load_cached_jlp_price(self) -> Decimal:
        """加载缓存的 JLP 价格"""
        try:
            if CACHE_FILE.exists():
                with open(CACHE_FILE, "r") as f:
                    data = json.load(f)
                    return Decimal(str(data.get("price", "0")))
        except Exception:
            pass
        return Decimal("0")

    def _save_jlp_price_cache(self, price: Decimal):
        """保存 JLP 价格到缓存"""
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w") as f:
                json.dump({
                    "price": str(price),
                    "updated_at": datetime.now().isoformat()
                }, f)
        except Exception as e:
            logger.warning(f"保存价格缓存失败: {e}")

    async def _fetch_jlp_price(self, jlp_amount: Decimal, max_retries: int = 3) -> Decimal:
        """获取 JLP 价格（带重试和缓存）"""
        import httpx

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"{self.hedge_api_url}/api/v1/hedge-positions",
                        params={"jlp_amount": float(jlp_amount)}
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("success"):
                            jlp_stats = data.get("data", {}).get("jlp_stats", {})
                            price = Decimal(str(jlp_stats.get("virtual_price", "0")))
                            if price > 0:
                                self._save_jlp_price_cache(price)
                                return price
            except Exception as e:
                logger.warning(f"获取 JLP 价格失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)

        # 使用缓存价格
        cached_price = self._load_cached_jlp_price()
        if cached_price > 0:
            logger.warning(f"使用缓存的 JLP 价格: ${cached_price}")
            return cached_price

        logger.error("无法获取 JLP 价格，缓存也不可用")
        return Decimal("0")
```

---

### 方案 C：使用备用数据源

如果 Hedge API 经常不稳定，可以考虑：

1. **直接从 Jupiter 获取 JLP 价格**
   - Jupiter API: `https://price.jup.ag/v4/price?ids=JLP`

2. **从 Solana 链上读取**
   - 使用 Solana RPC 直接查询 JLP Pool 数据

---

## 推荐方案

1. **短期**：先执行方案 A，重启 Hedge API 服务
2. **中期**：实施方案 B，添加缓存和重试机制
3. **长期**：考虑方案 C，增加备用数据源

---

## 监控建议

1. **添加 PM2 监控**
```bash
pm2 install pm2-logrotate
pm2 save
pm2 startup
```

2. **设置自动重启**
```bash
pm2 start ... --max-restarts 10 --restart-delay 5000
```

3. **添加健康检查**
在报告服务启动时，先检查 Hedge API 是否可用：
```python
async def health_check():
    try:
        resp = await httpx.get("http://localhost:3000/health", timeout=5)
        return resp.status_code == 200
    except:
        return False
```
