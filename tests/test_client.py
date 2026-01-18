"""
AsterDex 客户端测试

用于验证 API 连接和签名是否正确
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import load_config
from clients.asterdex_client import AsterDexClient


async def test_client():
    """测试 AsterDex 客户端"""
    print("\n" + "=" * 60)
    print("  AsterDex API 测试")
    print("=" * 60)

    # 加载配置
    config = load_config()
    accounts = config.get_enabled_accounts()

    if not accounts:
        print("❌ 没有启用的账户")
        return

    account = accounts[0]
    print(f"\n使用账户: {account.name}")
    print(f"User: {account.asterdex.user_address}")
    print(f"Signer: {account.asterdex.signer_address}")

    # 创建客户端
    client = AsterDexClient(
        user_address=account.asterdex.user_address,
        signer_address=account.asterdex.signer_address,
        private_key=account.asterdex.private_key,
        base_url=config.global_config.asterdex_base_url,
    )

    # 测试 1: 获取价格 (无需签名)
    print("\n[1] 测试获取价格...")
    try:
        price_data = await client.get_ticker_price("SOLUSDT")
        print(f"  ✓ SOL 价格: ${price_data.get('price', 'N/A')}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")

    # 测试 2: 获取资金费率
    print("\n[2] 测试获取资金费率...")
    try:
        funding = await client.get_funding_rate("SOLUSDT")
        print(f"  ✓ SOL 资金费率: {float(funding.funding_rate):.6%}")
        print(f"  ✓ 标记价格: ${funding.mark_price}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")

    # 测试 3: 获取深度
    print("\n[3] 测试获取深度...")
    try:
        depth = await client.get_depth("SOLUSDT", limit=5)
        bids = depth.get("bids", [])[:3]
        asks = depth.get("asks", [])[:3]
        print(f"  ✓ 买盘: {bids}")
        print(f"  ✓ 卖盘: {asks}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")

    # 测试 4: 获取余额 (需要签名)
    print("\n[4] 测试获取余额 (需要签名)...")
    try:
        balances = await client.get_balance()
        print(f"  ✓ 获取到 {len(balances)} 个资产")
        for bal in balances[:5]:
            if float(bal.balance) > 0:
                print(f"    {bal.asset}: {bal.balance} (可用: {bal.available_balance})")
    except Exception as e:
        print(f"  ✗ 失败: {e}")

    # 测试 5: 获取持仓
    print("\n[5] 测试获取持仓...")
    try:
        positions = await client.get_positions()
        print(f"  ✓ 获取到 {len(positions)} 个持仓")
        for pos in positions:
            print(
                f"    {pos.symbol}: {pos.quantity} @ {pos.entry_price} "
                f"(PnL: {pos.unrealized_pnl})"
            )
    except Exception as e:
        print(f"  ✗ 失败: {e}")

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_client())
