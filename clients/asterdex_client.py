"""
AsterDex 永续合约 API 客户端

实现账户查询、持仓查询、下单等功能
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
import httpx

from utils.signer import AsterDexSigner

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """订单类型"""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"


class PositionSide(Enum):
    """持仓方向"""
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"


class TimeInForce(Enum):
    """有效期类型"""
    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    GTX = "GTX"  # Good Till Crossing (Post Only)


@dataclass
class Balance:
    """账户余额"""
    asset: str
    balance: Decimal
    available_balance: Decimal
    cross_wallet_balance: Decimal
    cross_unrealized_pnl: Decimal


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    position_side: str
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    leverage: int
    margin_type: str
    isolated_margin: Decimal


@dataclass
class OrderResult:
    """下单结果"""
    success: bool
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    type: Optional[str] = None
    quantity: Optional[Decimal] = None
    price: Optional[Decimal] = None
    filled_quantity: Optional[Decimal] = None
    status: Optional[str] = None
    error: Optional[str] = None


@dataclass
class FundingRate:
    """资金费率"""
    symbol: str
    funding_rate: Decimal
    funding_time: int
    mark_price: Decimal


class AsterDexError(Exception):
    """AsterDex API 错误"""

    def __init__(self, message: str, code: Optional[int] = None):
        self.message = message
        self.code = code
        super().__init__(self.message)


class AsterDexClient:
    """AsterDex 永续合约 API 客户端 - 支持 EVM 和 Solana 两种模式"""

    def __init__(
        self,
        user_address: str,
        # EVM 模式参数
        signer_address: Optional[str] = None,
        private_key: Optional[str] = None,
        # Solana/HMAC 模式参数
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        # 通用参数
        chain: str = "evm",
        base_url: str = "https://fapi.asterdex.com",
        timeout: float = 10.0,
        max_retries: int = 3,
    ):
        """
        初始化客户端

        EVM 模式:
            user_address: 主钱包地址 (EOA)
            signer_address: API 钱包地址
            private_key: API 钱包私钥

        Solana/HMAC 模式:
            user_address: Solana 钱包地址
            api_key: API 密钥
            api_secret: API 秘密密钥
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.chain = chain.lower()

        # 根据链类型选择 API 版本: Solana 用 v1, EVM 用 v3
        self.api_version = "v1" if self.chain == "solana" else "v3"

        # 初始化签名器
        self.signer = AsterDexSigner(
            user_address=user_address,
            signer_address=signer_address,
            private_key=private_key,
            api_key=api_key,
            api_secret=api_secret,
            chain=chain,
        )

        logger.info(f"AsterDex 客户端初始化: base_url={base_url}, chain={chain}, api={self.api_version}, mode={self.signer.mode}")

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = True,
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法 (GET, POST, DELETE)
            endpoint: API 端点
            params: 请求参数
            signed: 是否需要签名

        Returns:
            API 响应数据
        """
        url = f"{self.base_url}{endpoint}"
        params = params or {}

        # 签名
        if signed:
            params = self.signer.sign_simple(params)

        # 获取签名器提供的请求头 (HMAC 模式需要 X-MBX-APIKEY)
        base_headers = self.signer.get_headers()

        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    if method == "GET":
                        response = await client.get(url, params=params, headers=base_headers)
                    elif method == "POST":
                        # AsterDex 要求 POST 使用 form-urlencoded 格式
                        headers = {"Content-Type": "application/x-www-form-urlencoded"}
                        headers.update(base_headers)
                        response = await client.post(url, data=params, headers=headers)
                    elif method == "DELETE":
                        response = await client.delete(url, params=params, headers=base_headers)
                    else:
                        raise ValueError(f"不支持的 HTTP 方法: {method}")

                    # 检查响应状态
                    if response.status_code == 429:
                        raise AsterDexError("请求频率超限", code=429)
                    elif response.status_code == 418:
                        raise AsterDexError("IP 被临时封禁", code=418)
                    elif response.status_code >= 400:
                        error_data = response.json() if response.text else {}
                        raise AsterDexError(
                            error_data.get("msg", f"HTTP {response.status_code}"),
                            code=error_data.get("code", response.status_code)
                        )

                    data = response.json()
                    logger.debug(f"API 响应: {endpoint} -> {data}")
                    return data

            except httpx.TimeoutException:
                last_error = AsterDexError(f"请求超时 ({self.timeout}s)")
                logger.warning(f"请求超时 (尝试 {attempt}/{self.max_retries})")

            except httpx.ConnectError as e:
                last_error = AsterDexError(f"连接失败: {e}")
                logger.warning(f"连接失败 (尝试 {attempt}/{self.max_retries})")

            except AsterDexError:
                raise

            except Exception as e:
                last_error = AsterDexError(f"未知错误: {e}")
                logger.error(f"未知错误 (尝试 {attempt}/{self.max_retries}): {e}")

            # 重试等待
            if attempt < self.max_retries:
                wait_time = 2 ** (attempt - 1)
                await asyncio.sleep(wait_time)

        raise last_error or AsterDexError("请求失败")

    # ==================== 行情接口 (无需签名) ====================

    async def get_ticker_price(self, symbol: str) -> Dict[str, Any]:
        """
        获取最新价格

        Args:
            symbol: 交易对 (如 SOLUSDT)

        Returns:
            价格数据
        """
        return await self._request(
            "GET",
            f"/fapi/{self.api_version}/ticker/price",
            {"symbol": symbol},
            signed=False
        )

    async def get_mark_price(self, symbol: str) -> Dict[str, Any]:
        """
        获取标记价格

        Args:
            symbol: 交易对

        Returns:
            标记价格数据
        """
        return await self._request(
            "GET",
            f"/fapi/{self.api_version}/premiumIndex",
            {"symbol": symbol},
            signed=False
        )

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """
        获取资金费率

        Args:
            symbol: 交易对

        Returns:
            FundingRate: 资金费率信息
        """
        data = await self._request(
            "GET",
            f"/fapi/{self.api_version}/premiumIndex",
            {"symbol": symbol},
            signed=False
        )

        return FundingRate(
            symbol=data.get("symbol", symbol),
            funding_rate=Decimal(str(data.get("lastFundingRate", "0"))),
            funding_time=int(data.get("nextFundingTime", 0)),
            mark_price=Decimal(str(data.get("markPrice", "0")))
        )

    async def get_depth(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """
        获取深度数据

        Args:
            symbol: 交易对
            limit: 深度档位

        Returns:
            深度数据
        """
        return await self._request(
            "GET",
            f"/fapi/{self.api_version}/depth",
            {"symbol": symbol, "limit": limit},
            signed=False
        )

    # ==================== 账户接口 ====================

    async def get_balance(self) -> List[Balance]:
        """
        获取账户余额

        Returns:
            List[Balance]: 余额列表
        """
        data = await self._request("GET", f"/fapi/{self.api_version}/balance", {})

        balances = []
        for item in data:
            # v1 和 v3 API 返回字段名不同
            balance = Decimal(str(item.get("balance", "0")))
            # v1: withdrawAvailable, v3: availableBalance
            available = Decimal(str(item.get("availableBalance") or item.get("withdrawAvailable", "0")))
            cross_wallet = Decimal(str(item.get("crossWalletBalance", "0")))
            cross_pnl = Decimal(str(item.get("crossUnPnl", "0")))

            balances.append(Balance(
                asset=item["asset"],
                balance=balance,
                available_balance=available,
                cross_wallet_balance=cross_wallet,
                cross_unrealized_pnl=cross_pnl
            ))

        return balances

    async def get_account(self) -> Dict[str, Any]:
        """
        获取账户信息

        Returns:
            账户详情
        """
        return await self._request("GET", f"/fapi/{self.api_version}/account", {})

    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """
        获取持仓信息

        Args:
            symbol: 交易对 (可选，不传则返回所有持仓)

        Returns:
            List[Position]: 持仓列表
        """
        params = {}
        if symbol:
            params["symbol"] = symbol

        data = await self._request("GET", f"/fapi/{self.api_version}/positionRisk", params)

        positions = []
        for item in data:
            qty = Decimal(str(item.get("positionAmt", "0")))
            if qty == 0:
                continue  # 跳过空仓位

            positions.append(Position(
                symbol=item["symbol"],
                position_side=item.get("positionSide", "BOTH"),
                quantity=qty,
                entry_price=Decimal(str(item.get("entryPrice", "0"))),
                mark_price=Decimal(str(item.get("markPrice", "0"))),
                unrealized_pnl=Decimal(str(item.get("unRealizedProfit", "0"))),
                leverage=int(item.get("leverage", 1)),
                margin_type=item.get("marginType", "cross"),
                isolated_margin=Decimal(str(item.get("isolatedMargin", "0")))
            ))

        return positions

    # ==================== 交易接口 ====================

    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        设置杠杆倍数

        Args:
            symbol: 交易对
            leverage: 杠杆倍数

        Returns:
            设置结果
        """
        return await self._request(
            "POST",
            f"/fapi/{self.api_version}/leverage",
            {"symbol": symbol, "leverage": leverage}
        )

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        position_side: PositionSide = PositionSide.BOTH,
        time_in_force: TimeInForce = TimeInForce.GTC,
        reduce_only: bool = False,
        client_order_id: Optional[str] = None,
    ) -> OrderResult:
        """
        下单

        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            quantity: 数量
            price: 价格 (限价单必填)
            position_side: 持仓方向
            time_in_force: 有效期类型
            reduce_only: 是否只减仓
            client_order_id: 客户端订单ID

        Returns:
            OrderResult: 下单结果
        """
        params = {
            "symbol": symbol,
            "side": side.value,
            "type": order_type.value,
            "quantity": str(quantity),
        }

        # v3 API 支持 positionSide，v1 不支持
        if self.api_version == "v3":
            params["positionSide"] = position_side.value

        # reduceOnly 两个版本都支持 (平仓时可绕过最小名义价值限制)
        if reduce_only:
            params["reduceOnly"] = "true"

        if order_type == OrderType.LIMIT:
            if price is None:
                return OrderResult(success=False, error="限价单必须指定价格")
            params["price"] = str(price)
            params["timeInForce"] = time_in_force.value

        if client_order_id:
            params["newClientOrderId"] = client_order_id

        try:
            data = await self._request("POST", f"/fapi/{self.api_version}/order", params)

            # 解析成交数量 (市价单可能立即成交)
            orig_qty = Decimal(str(data.get("origQty", "0")))
            exec_qty = Decimal(str(data.get("executedQty", "0")))

            # 对于市价单，如果 executedQty 为 0，可能还没返回成交信息，用 origQty 作为预估
            if order_type == OrderType.MARKET and exec_qty == 0:
                exec_qty = orig_qty

            logger.info(f"下单成功: {data.get('symbol')} {data.get('side')} qty={orig_qty} filled={exec_qty} status={data.get('status')}")

            return OrderResult(
                success=True,
                order_id=str(data.get("orderId", "")),
                client_order_id=data.get("clientOrderId"),
                symbol=data.get("symbol"),
                side=data.get("side"),
                type=data.get("type"),
                quantity=orig_qty,
                price=Decimal(str(data.get("price", "0"))),
                filled_quantity=exec_qty,
                status=data.get("status"),
            )

        except AsterDexError as e:
            logger.error(f"下单失败: {e.message}")
            return OrderResult(success=False, error=e.message)

    async def cancel_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> bool:
        """
        撤销订单

        Args:
            symbol: 交易对
            order_id: 订单ID
            client_order_id: 客户端订单ID

        Returns:
            bool: 是否成功
        """
        params = {"symbol": symbol}

        if order_id:
            params["orderId"] = order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("必须指定 order_id 或 client_order_id")

        try:
            await self._request("DELETE", f"/fapi/{self.api_version}/order", params)
            return True
        except AsterDexError as e:
            logger.error(f"撤单失败: {e.message}")
            return False

    async def get_order(
        self,
        symbol: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        查询订单

        Args:
            symbol: 交易对
            order_id: 订单ID
            client_order_id: 客户端订单ID

        Returns:
            订单详情
        """
        params = {"symbol": symbol}

        if order_id:
            params["orderId"] = order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("必须指定 order_id 或 client_order_id")

        return await self._request("GET", f"/fapi/{self.api_version}/order", params)

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取当前挂单

        Args:
            symbol: 交易对 (可选)

        Returns:
            挂单列表
        """
        params = {}
        if symbol:
            params["symbol"] = symbol

        return await self._request("GET", f"/fapi/{self.api_version}/openOrders", params)

    # ==================== 便捷方法 ====================

    async def market_sell(
        self,
        symbol: str,
        quantity: Decimal,
        position_side: PositionSide = PositionSide.SHORT,
        reduce_only: bool = False,
    ) -> OrderResult:
        """
        市价卖出 (开空/平多)

        Args:
            symbol: 交易对
            quantity: 数量
            position_side: 持仓方向
            reduce_only: 是否只减仓

        Returns:
            OrderResult: 下单结果
        """
        return await self.place_order(
            symbol=symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=quantity,
            position_side=position_side,
            reduce_only=reduce_only,
        )

    async def market_buy(
        self,
        symbol: str,
        quantity: Decimal,
        position_side: PositionSide = PositionSide.LONG,
        reduce_only: bool = False,
    ) -> OrderResult:
        """
        市价买入 (开多/平空)

        Args:
            symbol: 交易对
            quantity: 数量
            position_side: 持仓方向
            reduce_only: 是否只减仓

        Returns:
            OrderResult: 下单结果
        """
        return await self.place_order(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=quantity,
            position_side=position_side,
            reduce_only=reduce_only,
        )
