"""
测试签名是否正确
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import httpx
from utils.signer import AsterDexSigner

# 配置
USER_ADDRESS = "0xa6Fb4eCc638Fe37F4a6d7a1035dEFDb1eF8cccDc"
SIGNER_ADDRESS = "0x7225c1B9561474E19c2eD77D23bC97dC769838C3"
PRIVATE_KEY = "0xde677fbfec61b50baf7ac75415698a074e8a0e6845868b4b1c3ea2902a00bfd1"
BASE_URL = "https://fapi.asterdex.com"


async def test_public_api():
    """测试公开 API (无需签名)"""
    print("\n=== 测试公开 API ===")

    async with httpx.AsyncClient() as client:
        # 获取价格
        resp = await client.get(f"{BASE_URL}/fapi/v3/ticker/price", params={"symbol": "SOLUSDT"})
        print(f"GET ticker/price: {resp.status_code}")
        print(f"  Response: {resp.text[:200]}")


async def test_signed_api():
    """测试签名 API"""
    print("\n=== 测试签名 API ===")

    signer = AsterDexSigner(USER_ADDRESS, SIGNER_ADDRESS, PRIVATE_KEY)

    # 测试 GET 请求 (balance)
    print("\n[1] 测试 GET /fapi/v3/balance")
    params = signer.sign({})
    print(f"  签名参数: {params}")

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BASE_URL}/fapi/v3/balance", params=params)
        print(f"  Status: {resp.status_code}")
        print(f"  Response: {resp.text[:500]}")

    # 测试 POST 请求 (leverage)
    print("\n[2] 测试 POST /fapi/v3/leverage")
    params = signer.sign({"symbol": "SOLUSDT", "leverage": 1})
    print(f"  签名参数: {params}")

    async with httpx.AsyncClient() as client:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = await client.post(f"{BASE_URL}/fapi/v3/leverage", data=params, headers=headers)
        print(f"  Status: {resp.status_code}")
        print(f"  Response: {resp.text[:500]}")


async def main():
    print("=" * 60)
    print("  AsterDex 签名测试")
    print("=" * 60)
    print(f"\nUser: {USER_ADDRESS}")
    print(f"Signer: {SIGNER_ADDRESS}")

    await test_public_api()
    await test_signed_api()

    print("\n" + "=" * 60)
    print("  如果看到 'No agent found' 错误:")
    print("  请确认已在 AsterDex 网页端将 signer 地址添加为 API 钱包")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
