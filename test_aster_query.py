#!/usr/bin/env python3
"""
AsterDex API 查询测试脚本

测试内容:
1. 账户余额查询
2. 持仓查询
3. 市场行情查询
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from clients.asterdex_client import AsterDexClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_queries():
    """测试 AsterDex API 查询"""
    logger.info("=" * 60)
    logger.info("  AsterDex API 查询测试")
    logger.info("=" * 60)
    
    # 使用测试配置
    client = AsterDexClient(
        user_address="2hGZfrnnowiHv7c8jfMJpBtn46tqQCd4NUPr1NzAPxgu",
        api_key="c2f346c55dc18e231610f27dd76cb527f0520c372d8ac671da97704707d49ca3",
        api_secret="d73d4e6950115f9676c8ebbdfc3ac7e993414762d1a6ab651fef99ba56001cd6",
        chain="solana",
    )
    
    # 1. 获取账户信息
    logger.info("\n[1] 获取账户信息...")
    try:
        account_info = await client.get_account()
        logger.info(f"  账户信息: {account_info}")
    except Exception as e:
        logger.error(f"  获取账户信息失败: {e}")
    
    # 2. 获取余额
    logger.info("\n[2] 获取余额...")
    try:
        balances = await client.get_balance()
        if balances:
            for bal in balances:
                logger.info(f"  {bal.asset}: 余额={bal.balance}, 可用={bal.available_balance}")
        else:
            logger.info("  无余额数据")
    except Exception as e:
        logger.error(f"  获取余额失败: {e}")
    
    # 3. 获取持仓
    logger.info("\n[3] 获取持仓...")
    try:
        positions = await client.get_positions()
        if positions:
            for pos in positions:
                if pos.quantity != 0:
                    logger.info(f"  {pos.symbol}: 数量={pos.quantity}, 入场价={pos.entry_price}, 未实现盈亏={pos.unrealized_pnl}")
        else:
            logger.info("  无持仓")
    except Exception as e:
        logger.error(f"  获取持仓失败: {e}")
    
    # 4. 获取市场行情
    logger.info("\n[4] 获取市场行情...")
    try:
        for symbol in ["SOLUSDT", "ETHUSDT", "BTCUSDT"]:
            ticker = await client.get_ticker_price(symbol)
            mark = await client.get_mark_price(symbol)
            funding = await client.get_funding_rate(symbol)
            logger.info(f"  {symbol}:")
            logger.info(f"    - 最新价: {ticker.get('price')}")
            logger.info(f"    - 标记价: {mark.get('markPrice')}")
            logger.info(f"    - 资金费率: {funding.funding_rate}")
    except Exception as e:
        logger.error(f"  获取行情失败: {e}")
    
    # 5. 获取深度
    logger.info("\n[5] 获取深度 (SOLUSDT)...")
    try:
        depth = await client.get_depth("SOLUSDT", limit=5)
        logger.info(f"  买盘: {depth.get('bids', [])[:3]}")
        logger.info(f"  卖盘: {depth.get('asks', [])[:3]}")
    except Exception as e:
        logger.error(f"  获取深度失败: {e}")
    
    logger.info("\n" + "=" * 60)
    logger.info("  查询测试完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_queries())
