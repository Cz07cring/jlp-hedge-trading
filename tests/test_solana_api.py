"""
测试 Solana 链的 AsterDex API (HMAC 签名)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import httpx
from utils.signer import AsterDexSigner

# Solana 配置
USER_ADDRESS = "2hGZfrnnowiHv7c8jfMJpBtn46tqQCd4NUPr1NzAPxgu"
API_KEY = "c2f346c55dc18e231610f27dd76cb527f0520c372d8ac671da97704707d49ca3"
API_SECRET = "d73d4e6950115f9676c8ebbdfc3ac7e993414762d1a6ab651fef99ba56001cd6"
BASE_URL = "https://fapi.asterdex.com"

# 创建带有超时和重试的客户端
def get_client():
    return httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
    )


async def test_public_api():
    """测试公开 API (无需签名)"""
    print("\n=== 测试公开 API ===")

    for attempt in range(3):
        try:
            async with get_client() as client:
                # 获取价格
                resp = await client.get(f"{BASE_URL}/fapi/v3/ticker/price", params={"symbol": "SOLUSDT"})
                print(f"GET ticker/price: {resp.status_code}")
                print(f"  Response: {resp.text[:200]}")
                return
        except httpx.ConnectError as e:
            print(f"  连接失败 (尝试 {attempt + 1}/3): {e}")
            if attempt < 2:
                await asyncio.sleep(2)
        except Exception as e:
            print(f"  错误: {e}")
            return
    print("  公开 API 测试失败")


async def test_signed_api():
    """测试签名 API (HMAC 模式) - 使用 v1 API"""
    print("\n=== 测试签名 API (HMAC/Solana v1 模式) ===")

    signer = AsterDexSigner(
        user_address=USER_ADDRESS,
        api_key=API_KEY,
        api_secret=API_SECRET,
        chain="solana"
    )

    print(f"签名模式: {signer.mode}")

    # 测试 GET 请求 (balance) - 使用 v1 API
    print("\n[1] 测试 GET /fapi/v1/balance")
    params = signer.sign({})
    headers = signer.get_headers()
    print(f"  请求头: {headers}")
    print(f"  签名参数: {params}")

    for attempt in range(3):
        try:
            async with get_client() as client:
                resp = await client.get(f"{BASE_URL}/fapi/v1/balance", params=params, headers=headers)
                print(f"  Status: {resp.status_code}")
                print(f"  Response: {resp.text[:500]}")
                break
        except httpx.ConnectError as e:
            print(f"  连接失败 (尝试 {attempt + 1}/3): {e}")
            if attempt < 2:
                await asyncio.sleep(2)
                params = signer.sign({})

    # 测试 POST 请求 (leverage) - 使用 v1 API
    print("\n[2] 测试 POST /fapi/v1/leverage")
    params = signer.sign({"symbol": "SOLUSDT", "leverage": 1})
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    headers.update(signer.get_headers())
    print(f"  请求头: {headers}")

    for attempt in range(3):
        try:
            async with get_client() as client:
                resp = await client.post(f"{BASE_URL}/fapi/v1/leverage", data=params, headers=headers)
                print(f"  Status: {resp.status_code}")
                print(f"  Response: {resp.text[:500]}")
                break
        except httpx.ConnectError as e:
            print(f"  连接失败 (尝试 {attempt + 1}/3): {e}")
            if attempt < 2:
                await asyncio.sleep(2)
                params = signer.sign({"symbol": "SOLUSDT", "leverage": 1})


async def main():
    print("=" * 60)
    print("  AsterDex Solana API 测试 (HMAC 签名)")
    print("=" * 60)
    print(f"\nUser (Solana): {USER_ADDRESS}")
    print(f"API Key: {API_KEY[:16]}...")

    await test_public_api()
    await test_signed_api()

    print("\n" + "=" * 60)
    print("  测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
