"""验证私钥对应的地址"""

from eth_account import Account

# 你提供的两组私钥
keys = [
    "0xde677fbfec61b50baf7ac75415698a074e8a0e6845868b4b1c3ea2902a00bfd1",
    "0x696f46ab5fd5e93412057e3380779d06d04041f11adf200dbb8aeb753e8c68a0",
]

print("=" * 60)
print("  验证私钥对应的地址")
print("=" * 60)

for i, pk in enumerate(keys, 1):
    account = Account.from_key(pk)
    print(f"\n私钥 {i}: {pk[:10]}...{pk[-6:]}")
    print(f"对应地址: {account.address}")

print("\n" + "=" * 60)
print("请使用正确的 signer_address（上面推导出的地址）")
print("=" * 60)
