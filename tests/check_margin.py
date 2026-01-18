"""检查保证金率数据"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from clients.asterdex_client import AsterDexClient

async def main():
    client = AsterDexClient(
        user_address='2hGZfrnnowiHv7c8jfMJpBtn46tqQCd4NUPr1NzAPxgu',
        api_key='c2f346c55dc18e231610f27dd76cb527f0520c372d8ac671da97704707d49ca3',
        api_secret='d73d4e6950115f9676c8ebbdfc3ac7e993414762d1a6ab651fef99ba56001cd6',
        chain='solana'
    )

    print("=== Account Data ===")
    account = await client.get_account()
    for k, v in account.items():
        print(f"  {k}: {v}")

    # 计算保证金率
    total_margin = float(account.get("totalMarginBalance", 0))
    total_maint_margin = float(account.get("totalMaintMargin", 0))

    print(f"\n=== 保证金计算 ===")
    print(f"  totalMarginBalance (总保证金): {total_margin}")
    print(f"  totalMaintMargin (维持保证金): {total_maint_margin}")

    if total_maint_margin > 0:
        ratio = total_margin / total_maint_margin
        print(f"  保证金率: {ratio:.2%}")
    else:
        print(f"  保证金率: 无持仓")

if __name__ == "__main__":
    asyncio.run(main())
