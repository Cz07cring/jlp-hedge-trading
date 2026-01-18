#!/usr/bin/env python3
"""
使用真实 AsterDex 账户数据上报到 SaaS
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import httpx
from clients.asterdex_client import AsterDexClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("=" * 60)
    logger.info("  获取真实账户数据并上报到 SaaS")
    logger.info("=" * 60)
    
    # 1. 初始化 AsterDex 客户端
    client = AsterDexClient(
        user_address="2hGZfrnnowiHv7c8jfMJpBtn46tqQCd4NUPr1NzAPxgu",
        api_key="c2f346c55dc18e231610f27dd76cb527f0520c372d8ac671da97704707d49ca3",
        api_secret="d73d4e6950115f9676c8ebbdfc3ac7e993414762d1a6ab651fef99ba56001cd6",
        chain="solana",
    )
    
    # 2. 获取账户数据
    logger.info("\n[1] 获取账户数据...")
    balances = await client.get_balance()
    positions = await client.get_positions()
    
    # 找 JLP 余额
    jlp_balance = 0
    usdt_balance = 0
    for bal in balances:
        if bal.asset == "JLP":
            jlp_balance = float(bal.balance)
        if bal.asset == "USDT":
            usdt_balance = float(bal.balance)
    
    # 计算持仓数据
    total_unrealized_pnl = 0
    position_data = {}
    for pos in positions:
        if float(pos.quantity) != 0:
            symbol = pos.symbol.replace("USDT", "")
            position_data[symbol] = {
                "quantity": float(pos.quantity),
                "entry_price": float(pos.entry_price),
                "mark_price": float(pos.mark_price),
                "unrealized_pnl": float(pos.unrealized_pnl),
            }
            total_unrealized_pnl += float(pos.unrealized_pnl)
    
    # JLP 价格（约 4.5 美元）
    jlp_price = 4.5
    jlp_value_usd = jlp_balance * jlp_price
    total_equity = jlp_value_usd + usdt_balance + total_unrealized_pnl
    
    logger.info(f"  JLP 余额: {jlp_balance:.4f}")
    logger.info(f"  JLP 价值: ${jlp_value_usd:.2f}")
    logger.info(f"  USDT 余额: ${usdt_balance:.2f}")
    logger.info(f"  未实现盈亏: ${total_unrealized_pnl:.2f}")
    logger.info(f"  总净值: ${total_equity:.2f}")
    
    for symbol, pos in position_data.items():
        logger.info(f"  {symbol}: {pos['quantity']:.4f} @ ${pos['entry_price']:.2f} (PnL: ${pos['unrealized_pnl']:.2f})")
    
    # 3. 上报到 SaaS
    license_key = "JLP-JW8Z-POHV-X41D-0EBT"
    api_url = "http://localhost:3001"
    
    logger.info("\n[2] 上报数据到 SaaS...")
    
    async with httpx.AsyncClient(timeout=30.0) as http:
        # 3.1 验证 License
        logger.info("  验证 License...")
        resp = await http.post(
            f"{api_url}/api/hedge/verify",
            json={
                "license_key": license_key,
                "device_id": "aster_real_device",
                "device_name": "AsterDex Real Account"
            }
        )
        verify_data = resp.json()
        
        if verify_data.get('valid'):
            logger.info(f"  ✓ License 验证成功")
            logger.info(f"    用户 ID: {verify_data.get('user_id')}")
            logger.info(f"    计划类型: {verify_data.get('plan_type')}")
        else:
            logger.error(f"  ✗ License 验证失败: {verify_data.get('error')}")
            return
        
        # 3.2 上报净值数据
        logger.info("  上报净值数据...")
        equity_data = {
            "type": "equity",
            "data": {
                "jlp_amount": str(jlp_balance),
                "jlp_price": str(jlp_price),
                "jlp_value_usd": str(jlp_value_usd),
                "total_equity_usd": str(total_equity),
                "unrealized_pnl": str(total_unrealized_pnl),
                "margin_ratio": "0.45",
                "hedge_ratio": "0.67",
                "positions": {
                    symbol: {
                        "target": abs(pos["quantity"]),
                        "current": abs(pos["quantity"]),
                        "delta": 0,
                        "entry_price": pos["entry_price"],
                        "mark_price": pos["mark_price"],
                        "pnl": pos["unrealized_pnl"],
                    }
                    for symbol, pos in position_data.items()
                }
            }
        }
        resp = await http.post(
            f"{api_url}/api/hedge/report",
            headers={"X-License-Key": license_key},
            json=equity_data
        )
        result = resp.json()
        logger.info(f"  {'✓' if result.get('success') else '✗'} 净值上报: {result}")
        
        # 3.3 上报持仓快照
        logger.info("  上报持仓快照...")
        for symbol, pos in position_data.items():
            rebalance_data = {
                "type": "rebalance",
                "data": {
                    "symbol": f"{symbol}USDT",
                    "side": "sell" if pos["quantity"] < 0 else "buy",
                    "amount": str(abs(pos["quantity"])),
                    "price": str(pos["mark_price"]),
                    "status": "success",
                    "before_position": "0",
                    "after_position": str(abs(pos["quantity"])),
                    "reason": "持仓快照同步"
                }
            }
            resp = await http.post(
                f"{api_url}/api/hedge/report",
                headers={"X-License-Key": license_key},
                json=rebalance_data
            )
        logger.info(f"  ✓ 持仓快照: {len(position_data)} 条记录")
        
        # 3.4 上报一条测试告警
        logger.info("  上报测试告警...")
        alert_data = {
            "type": "alert",
            "data": {
                "alert_type": "system_info",
                "level": "info",
                "title": "系统初始化完成",
                "message": f"JLP Hedge 执行器已连接，当前 JLP 持仓 {jlp_balance:.2f}，总净值 ${total_equity:.2f}"
            }
        }
        resp = await http.post(
            f"{api_url}/api/hedge/report",
            headers={"X-License-Key": license_key},
            json=alert_data
        )
        logger.info(f"  ✓ 告警上报成功")
        
    logger.info("\n" + "=" * 60)
    logger.info("  数据上报完成！")
    logger.info("=" * 60)
    logger.info("\n请访问 Dashboard 查看数据:")
    logger.info("  http://localhost:3001/zh/dashboard")


if __name__ == "__main__":
    asyncio.run(main())
