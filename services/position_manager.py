"""
仓位管理模块

负责:
1. 获取 JLP 持仓 (从 AsterDex 余额)
2. 获取目标对冲仓位 (从 Hedge API)
3. 获取当前对冲仓位 (从 AsterDex 持仓)
4. 计算仓位差异
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional, List
from decimal import Decimal
from dataclasses import dataclass
import httpx

from clients.asterdex_client import AsterDexClient, Position

logger = logging.getLogger(__name__)


@dataclass
class TargetHedgePosition:
    """目标对冲仓位"""
    symbol: str
    amount: Decimal
    value_usd: Decimal
    price: Decimal
    weight: float


@dataclass
class PositionDelta:
    """仓位差异"""
    symbol: str
    target: Decimal
    current: Decimal
    delta: Decimal  # 正数表示需要加仓(做空更多)，负数表示需要减仓(平空)
    delta_value_usd: Decimal


@dataclass
class HedgeStatus:
    """对冲状态"""
    jlp_amount: Decimal
    jlp_value_usd: Decimal
    target_positions: Dict[str, TargetHedgePosition]
    current_positions: Dict[str, Position]
    deltas: Dict[str, PositionDelta]
    total_target_value: Decimal
    total_current_value: Decimal
    hedge_ratio: float  # 当前对冲比例


class PositionManager:
    """仓位管理器"""

    # JLP 在 AsterDex 的资产名称 (需要确认实际名称)
    JLP_ASSET_NAME = "JLP"

    # 对冲资产映射 (API 返回的 symbol -> AsterDex 交易对)
    SYMBOL_MAPPING = {
        "SOL": "SOLUSDT",
        "ETH": "ETHUSDT",
        "BTC": "BTCUSDT",
    }

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # 秒

    def __init__(
        self,
        asterdex_client: AsterDexClient,
        hedge_api_url: str,
        rebalance_threshold: float = 0.02,
        min_order_sizes: Optional[Dict[str, float]] = None,
        license_key: Optional[str] = None,
    ):
        """
        初始化仓位管理器

        Args:
            asterdex_client: AsterDex 客户端
            hedge_api_url: 对冲计算 API 地址
            rebalance_threshold: 调仓阈值 (2%)
            min_order_sizes: 最小下单量
            license_key: License Key (用于调用 Hedge API)
        """
        self.client = asterdex_client
        self.hedge_api_url = hedge_api_url.rstrip("/")
        self.rebalance_threshold = rebalance_threshold
        self.min_order_sizes = min_order_sizes or {
            "SOL": 0.01,
            "ETH": 0.001,
            "BTC": 0.0001,
        }
        self.license_key = license_key or ""

        logger.info(f"仓位管理器初始化: hedge_api={hedge_api_url}")

    async def get_jlp_balance(self) -> Decimal:
        """
        获取 JLP 持仓数量 (从 AsterDex 余额)

        Returns:
            Decimal: JLP 数量
        """
        balances = await self.client.get_balance()

        for balance in balances:
            if balance.asset.upper() == self.JLP_ASSET_NAME:
                logger.info(f"JLP 余额: {balance.balance}")
                return balance.balance

        logger.warning(f"未找到 {self.JLP_ASSET_NAME} 余额")
        return Decimal("0")

    async def get_target_positions(self, jlp_amount: Decimal) -> Dict[str, TargetHedgePosition]:
        """
        获取目标对冲仓位 (从 Hedge API，带重试机制)

        Args:
            jlp_amount: JLP 持仓数量

        Returns:
            Dict[str, TargetHedgePosition]: 目标仓位 {symbol: position}
        """
        if jlp_amount <= 0:
            logger.warning("JLP 数量为 0，无需对冲")
            return {}

        url = f"{self.hedge_api_url}/api/v1/hedge-positions"
        last_error = None
        
        # 构建请求头（携带 License Key）
        headers = {"User-Agent": "JLP-Hedge-Trading/1.0"}
        if self.license_key:
            headers["X-License-Key"] = self.license_key

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        url, 
                        params={"jlp_amount": float(jlp_amount)},
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()

                if not data.get("success"):
                    error = data.get("error", {})
                    raise Exception(f"Hedge API 错误: {error.get('message', '未知错误')}")

                hedge_data = data.get("data", {})
                positions = hedge_data.get("hedge_positions", {})

                result = {}
                for symbol, pos in positions.items():
                    result[symbol] = TargetHedgePosition(
                        symbol=symbol,
                        amount=Decimal(str(pos["amount"])),
                        value_usd=Decimal(str(pos["value_usd"])),
                        price=Decimal(str(pos["price"])),
                        weight=pos["weight"],
                    )

                logger.info(f"目标对冲仓位: {list(result.keys())}")
                return result

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Hedge API 请求失败 (尝试 {attempt + 1}/{self.MAX_RETRIES}): {e}"
                )
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY)

        # 所有重试都失败
        logger.error(f"Hedge API 请求失败，已重试 {self.MAX_RETRIES} 次: {last_error}")
        raise last_error

    async def get_current_positions(self) -> Dict[str, Position]:
        """
        获取当前对冲仓位 (从 AsterDex)

        Returns:
            Dict[str, Position]: 当前持仓 {symbol: position}
        """
        positions = await self.client.get_positions()

        # 只保留我们关心的交易对
        result = {}
        for pos in positions:
            # 从交易对名称提取 symbol (SOLUSDT -> SOL)
            for symbol, trading_pair in self.SYMBOL_MAPPING.items():
                if pos.symbol == trading_pair:
                    result[symbol] = pos
                    break

        logger.info(f"当前持仓: {list(result.keys())}")
        return result

    def calculate_deltas(
        self,
        target_positions: Dict[str, TargetHedgePosition],
        current_positions: Dict[str, Position],
    ) -> Dict[str, PositionDelta]:
        """
        计算仓位差异

        Args:
            target_positions: 目标仓位
            current_positions: 当前仓位

        Returns:
            Dict[str, PositionDelta]: 仓位差异
        """
        deltas = {}

        for symbol, target in target_positions.items():
            current_pos = current_positions.get(symbol)

            # 当前空头仓位 (取绝对值，因为空头是负数)
            current_amount = Decimal("0")
            if current_pos:
                current_amount = abs(current_pos.quantity)

            # 计算差异
            delta = target.amount - current_amount

            # 计算差异价值
            delta_value = delta * target.price

            deltas[symbol] = PositionDelta(
                symbol=symbol,
                target=target.amount,
                current=current_amount,
                delta=delta,
                delta_value_usd=delta_value,
            )

            logger.debug(
                f"{symbol}: 目标={target.amount:.6f}, "
                f"当前={current_amount:.6f}, 差异={delta:.6f}"
            )

        return deltas

    def filter_significant_deltas(
        self,
        deltas: Dict[str, PositionDelta],
        target_positions: Dict[str, TargetHedgePosition],
    ) -> Dict[str, PositionDelta]:
        """
        过滤出需要调仓的差异 (超过阈值且超过最小下单量)

        Args:
            deltas: 所有差异
            target_positions: 目标仓位

        Returns:
            Dict[str, PositionDelta]: 需要调仓的差异
        """
        significant = {}

        for symbol, delta in deltas.items():
            target = target_positions.get(symbol)
            if not target:
                continue

            # 计算偏差比例
            if target.amount > 0:
                deviation_pct = abs(delta.delta) / target.amount
            else:
                deviation_pct = 0

            # 检查是否超过阈值
            if deviation_pct < self.rebalance_threshold:
                logger.debug(f"{symbol}: 偏差 {deviation_pct:.2%} < {self.rebalance_threshold:.2%}，跳过")
                continue

            # 检查是否超过最小下单量
            min_size = Decimal(str(self.min_order_sizes.get(symbol, 0.001)))
            if abs(delta.delta) < min_size:
                logger.debug(f"{symbol}: 差异 {abs(delta.delta)} < 最小下单量 {min_size}，跳过")
                continue

            significant[symbol] = delta
            logger.info(
                f"{symbol}: 需要调仓 {delta.delta:+.6f} (偏差 {deviation_pct:.2%})"
            )

        return significant

    async def get_hedge_status(self) -> HedgeStatus:
        """
        获取完整的对冲状态

        Returns:
            HedgeStatus: 对冲状态
        """
        # 1. 获取 JLP 余额
        jlp_amount = await self.get_jlp_balance()

        # 2. 获取目标仓位
        target_positions = await self.get_target_positions(jlp_amount)

        # 3. 获取当前仓位
        current_positions = await self.get_current_positions()

        # 4. 计算差异
        deltas = self.calculate_deltas(target_positions, current_positions)

        # 5. 计算汇总数据
        total_target_value = sum(
            pos.value_usd for pos in target_positions.values()
        )
        total_current_value = sum(
            abs(pos.quantity) * pos.mark_price
            for pos in current_positions.values()
        )

        # JLP 价值 (从 target 数据推算)
        jlp_value = Decimal("0")
        if target_positions:
            # 总对冲价值 / 波动性占比 = JLP 总价值
            # 这里简化处理
            total_weight = sum(pos.weight for pos in target_positions.values())
            if total_weight > 0:
                jlp_value = total_target_value / Decimal(str(total_weight))

        # 对冲比例
        hedge_ratio = 0.0
        if total_target_value > 0:
            hedge_ratio = float(total_current_value / total_target_value)

        return HedgeStatus(
            jlp_amount=jlp_amount,
            jlp_value_usd=jlp_value,
            target_positions=target_positions,
            current_positions=current_positions,
            deltas=deltas,
            total_target_value=total_target_value,
            total_current_value=total_current_value,
            hedge_ratio=hedge_ratio,
        )

    async def get_rebalance_orders(self) -> List[PositionDelta]:
        """
        获取需要执行的调仓订单

        Returns:
            List[PositionDelta]: 需要调仓的列表
        """
        status = await self.get_hedge_status()

        # 过滤出需要调仓的
        significant_deltas = self.filter_significant_deltas(
            status.deltas,
            status.target_positions,
        )

        return list(significant_deltas.values())
