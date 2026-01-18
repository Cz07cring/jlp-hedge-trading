"""
AsterDex 签名工具

支持两种签名方式:
1. EVM-style (Web3 ECDSA) - 用于 EVM 链 (Ethereum, BSC, Arbitrum)
2. HMAC-SHA256 - 用于 Solana 链

参考: https://github.com/asterdex/api-docs
"""

import time
import json
import hmac
import hashlib
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class AsterDexSigner:
    """AsterDex 签名器 - 支持 EVM 和 Solana 两种模式"""

    def __init__(
        self,
        # EVM 模式参数
        user_address: Optional[str] = None,
        signer_address: Optional[str] = None,
        private_key: Optional[str] = None,
        # HMAC 模式参数 (Solana)
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        # 通用参数
        chain: str = "evm"
    ):
        """
        初始化签名器

        EVM 模式 (Ethereum/BSC/Arbitrum):
            user_address: 主钱包地址 (EOA)
            signer_address: API 钱包地址
            private_key: API 钱包私钥

        HMAC 模式 (Solana):
            api_key: API 密钥
            api_secret: API 秘密密钥
            user_address: Solana 钱包地址 (可选)
        """
        self.chain = chain.lower()
        self.user_address = user_address

        if self.chain == "solana" or (api_key and api_secret):
            # HMAC 模式
            self.mode = "hmac"
            self.api_key = api_key
            self.api_secret = api_secret
            if not api_key or not api_secret:
                raise ValueError("HMAC 模式需要 api_key 和 api_secret")
            logger.info(f"签名器初始化成功 (HMAC 模式): user={user_address}")
        else:
            # EVM 模式
            self.mode = "evm"
            self._init_evm(user_address, signer_address, private_key)

    def _init_evm(self, user_address: str, signer_address: str, private_key: str):
        """初始化 EVM 签名模式"""
        from eth_account import Account
        from web3 import Web3

        self.user = Web3.to_checksum_address(user_address)
        self.signer = Web3.to_checksum_address(signer_address)
        self.private_key = private_key

        # 验证私钥与 signer 地址匹配
        account = Account.from_key(private_key)
        if account.address.lower() != signer_address.lower():
            raise ValueError(
                f"私钥与 signer 地址不匹配: {account.address} != {signer_address}"
            )

        logger.info(f"签名器初始化成功 (EVM 模式): user={self.user}, signer={self.signer}")

    def get_timestamp(self) -> int:
        """获取时间戳 (毫秒)"""
        return int(time.time() * 1000)

    def get_nonce(self) -> int:
        """获取 nonce (微秒)"""
        return int(time.time() * 1_000_000)

    def sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """对请求参数进行签名"""
        if self.mode == "hmac":
            return self._sign_hmac(params)
        else:
            return self._sign_evm(params)

    def _sign_hmac(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        HMAC SHA256 签名 (Solana/v1 API 模式)

        按照官方文档:
        1. 拼接所有参数为查询字符串
        2. 使用 API Secret 作为密钥进行 HMAC SHA256 签名
        3. 不需要 nonce, user, signer 参数
        """
        # 过滤 None 值，创建副本
        my_dict = {key: value for key, value in params.items() if value is not None}

        # 添加时间戳
        my_dict['timestamp'] = self.get_timestamp()
        my_dict['recvWindow'] = 5000

        # 将所有值转为字符串
        str_params = {}
        for k, v in my_dict.items():
            if isinstance(v, bool):
                str_params[k] = str(v).lower()
            else:
                str_params[k] = str(v)

        # 按参数顺序拼接查询字符串 (不排序，按原顺序)
        query_string = urlencode(list(str_params.items()))

        # HMAC SHA256 签名
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # 添加签名
        str_params['signature'] = signature

        logger.debug(f"HMAC 签名完成: query={query_string[:80]}...")

        return str_params

    def _sign_evm(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        EVM-style 签名 (Web3 ECDSA)
        """
        from eth_account import Account
        from eth_account.messages import encode_defunct
        from eth_abi import encode
        from web3 import Web3

        # 过滤 None 值，创建副本
        my_dict = {key: value for key, value in params.items() if value is not None}

        # 添加系统参数
        my_dict['recvWindow'] = 50000
        my_dict['timestamp'] = self.get_timestamp()

        # 生成 nonce
        nonce = self.get_nonce()

        # 将所有值转为字符串
        self._trim_dict(my_dict)

        # 按 key 排序，生成紧凑 JSON
        json_str = json.dumps(my_dict, sort_keys=True, separators=(',', ':'))

        # 使用 eth_abi 编码
        encoded = encode(
            ['string', 'address', 'address', 'uint256'],
            [json_str, self.user, self.signer, nonce]
        )

        # Keccak256 哈希
        keccak_hex = Web3.keccak(encoded).hex()

        # 签名
        signable_msg = encode_defunct(hexstr=keccak_hex)
        signed_message = Account.sign_message(
            signable_message=signable_msg,
            private_key=self.private_key
        )

        # 添加签名相关参数
        my_dict['nonce'] = str(nonce)
        my_dict['user'] = self.user
        my_dict['signer'] = self.signer
        my_dict['signature'] = '0x' + signed_message.signature.hex()

        logger.debug(f"EVM 签名完成: nonce={nonce}")

        return my_dict

    def _trim_dict(self, my_dict: Dict[str, Any]) -> Dict[str, Any]:
        """将字典所有值转为字符串"""
        for key in my_dict:
            value = my_dict[key]
            if isinstance(value, list):
                new_value = []
                for item in value:
                    if isinstance(item, dict):
                        new_value.append(json.dumps(self._trim_dict(item), separators=(',', ':')))
                    else:
                        new_value.append(str(item))
                my_dict[key] = json.dumps(new_value, separators=(',', ':'))
                continue
            if isinstance(value, dict):
                my_dict[key] = json.dumps(self._trim_dict(value), separators=(',', ':'))
                continue
            if isinstance(value, bool):
                my_dict[key] = str(value).lower()
            else:
                my_dict[key] = str(value)
        return my_dict

    def sign_simple(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """sign 的别名"""
        return self.sign(params)

    def get_headers(self) -> Dict[str, str]:
        """获取请求头 (HMAC 模式需要)"""
        if self.mode == "hmac":
            return {"X-MBX-APIKEY": self.api_key}
        return {}
