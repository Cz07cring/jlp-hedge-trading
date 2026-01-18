"""
订单执行模块

负责:
1. 执行调仓订单
2. 滑点控制
3. 订单状态跟踪

支持两种模式:
- 市价单模式 (use_maker_order=False): 快速成交，手续费高
- Maker 模式 (use_maker_order=True): 挂单成交，手续费低
"""

import logging
from typing import List, Dict, Optional
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum

from clients.asterdex_client import (
    AsterDexClient,
    OrderSide,
    OrderType,
    PositionSide,
    TimeInForce,
    OrderResult,
)
from services.position_manager import PositionDelta
from services.maker_order_executor import MakerOrderExecutor, MakerExecutionStatus
from services.maker_order_config import MakerOrderConfig

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """执行状态"""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ExecutionResult:
    """执行结果"""
    symbol: str
    status: ExecutionStatus
    target_quantity: Decimal
    filled_quantity: Decimal
    order_results: List[OrderResult]
    error: Optional[str] = None


class OrderExecutor:
    """订单执行器"""

    # 交易对映射
    SYMBOL_MAPPING = {
        "SOL": "SOLUSDT",
        "ETH": "ETHUSDT",
        "BTC": "BTCUSDT",
    }

    # 数量精度 (小数位数)
    QUANTITY_PRECISION = {
        "SOLUSDT": 2,   # SOL: 0.01
        "ETHUSDT": 3,   # ETH: 0.001
        "BTCUSDT": 3,   # BTC: 0.001
    }

    # 最小下单数量
    MIN_QUANTITY = {
        "SOLUSDT": Decimal("0.01"),
        "ETHUSDT": Decimal("0.001"),
        "BTCUSDT": Decimal("0.001"),
    }

    def __init__(
        self,
        asterdex_client: AsterDexClient,
        slippage: float = 0.001,
        use_market_order: bool = True,
        use_maker_order: bool = False,
        maker_config: Optional[MakerOrderConfig] = None,
    ):
        """
        初始化订单执行器

        Args:
            asterdex_client: AsterDex 客户端
            slippage: 滑点容忍度
            use_market_order: 是否使用市价单 (更快成交)
            use_maker_order: 是否使用 Maker 挂单模式 (手续费低)
            maker_config: Maker 订单配置
        """
        self.client = asterdex_client
        self.slippage = slippage
        self.use_market_order = use_market_order
        self.use_maker_order = use_maker_order

        # 初始化 Maker 执行器
        if use_maker_order:
            self.maker_executor = MakerOrderExecutor(
                asterdex_client=asterdex_client,
                config=maker_config or MakerOrderConfig(),
            )
            logger.info("订单执行器初始化: 使用 Maker 挂单模式")
        else:
            self.maker_executor = None
            logger.info(f"订单执行器初始化: slippage={slippage}, market_order={use_market_order}")

    def _round_quantity(self, trading_pair: str, quantity: Decimal) -> Decimal:
        """
        根据交易对精度要求格式化数量

        Args:
            trading_pair: 交易对
            quantity: 原始数量

        Returns:
            Decimal: 格式化后的数量，如果小于最小下单量则返回 0
        """
        precision = self.QUANTITY_PRECISION.get(trading_pair, 2)
        # 向下取整，避免超过可用余额
        factor = Decimal(10) ** precision
        rounded = (quantity * factor).to_integral_value() / factor

        # 如果小于最小下单量，返回 0 (跳过该订单)
        min_qty = self.MIN_QUANTITY.get(trading_pair, Decimal("0.001"))
        if rounded < min_qty:
            logger.info(f"{trading_pair}: 数量 {rounded} 小于最小下单量 {min_qty}，跳过")
            return Decimal("0")

        return rounded

    def _get_trading_pair(self, symbol: str) -> str:
        """获取交易对名称"""
        return self.SYMBOL_MAPPING.get(symbol, f"{symbol}USDT")

    async def _get_current_price(self, symbol: str) -> Decimal:
        """获取当前价格"""
        trading_pair = self._get_trading_pair(symbol)
        data = await self.client.get_ticker_price(trading_pair)
        return Decimal(str(data.get("price", "0")))

    async def execute_delta(self, delta: PositionDelta) -> ExecutionResult:
        """
        执行单个调仓

        Args:
            delta: 仓位差异

        Returns:
            ExecutionResult: 执行结果
        """
        # 如果启用 Maker 模式，使用 MakerOrderExecutor
        if self.use_maker_order and self.maker_executor:
            maker_result = await self.maker_executor.execute_delta(delta)

            # 转换 MakerExecutionResult -> ExecutionResult
            status_mapping = {
                MakerExecutionStatus.SUCCESS: ExecutionStatus.SUCCESS,
                MakerExecutionStatus.PARTIAL: ExecutionStatus.PARTIAL,
                MakerExecutionStatus.FAILED: ExecutionStatus.FAILED,
                MakerExecutionStatus.SKIPPED: ExecutionStatus.SKIPPED,
            }

            return ExecutionResult(
                symbol=delta.symbol,
                status=status_mapping[maker_result.status],
                target_quantity=maker_result.target_quantity,
                filled_quantity=maker_result.filled_quantity,
                order_results=[],  # Maker 模式不返回单个 OrderResult
                error=maker_result.error,
            )

        # 原有市价单逻辑
        symbol = delta.symbol
        trading_pair = self._get_trading_pair(symbol)
        quantity = abs(delta.delta)

        logger.info(f"执行调仓: {symbol} delta={delta.delta:+.6f}")

        order_results = []

        try:
            if delta.delta > 0:
                # 需要增加空头 -> 卖出开空
                result = await self._open_short(trading_pair, quantity)
            else:
                # 需要减少空头 -> 买入平空
                result = await self._close_short(trading_pair, quantity)

            order_results.append(result)

            if result.success:
                filled = result.filled_quantity or Decimal("0")

                # 检查是否为跳过的订单
                if result.order_id == "SKIPPED":
                    return ExecutionResult(
                        symbol=symbol,
                        status=ExecutionStatus.SKIPPED,
                        target_quantity=quantity,
                        filled_quantity=Decimal("0"),
                        order_results=order_results,
                        error="数量小于最小下单量",
                    )

                if filled >= quantity * Decimal("0.95"):
                    status = ExecutionStatus.SUCCESS
                else:
                    status = ExecutionStatus.PARTIAL
                    logger.warning(
                        f"{symbol}: 部分成交 {filled}/{quantity}"
                    )

                return ExecutionResult(
                    symbol=symbol,
                    status=status,
                    target_quantity=quantity,
                    filled_quantity=filled,
                    order_results=order_results,
                )
            else:
                return ExecutionResult(
                    symbol=symbol,
                    status=ExecutionStatus.FAILED,
                    target_quantity=quantity,
                    filled_quantity=Decimal("0"),
                    order_results=order_results,
                    error=result.error,
                )

        except Exception as e:
            logger.error(f"{symbol} 执行失败: {e}")
            return ExecutionResult(
                symbol=symbol,
                status=ExecutionStatus.FAILED,
                target_quantity=quantity,
                filled_quantity=Decimal("0"),
                order_results=order_results,
                error=str(e),
            )

    async def _open_short(self, trading_pair: str, quantity: Decimal) -> OrderResult:
        """
        开空仓

        Args:
            trading_pair: 交易对
            quantity: 数量

        Returns:
            OrderResult: 订单结果
        """
        # 格式化数量精度
        quantity = self._round_quantity(trading_pair, quantity)

        # 数量为 0 则跳过
        if quantity == 0:
            return OrderResult(
                success=True,
                order_id="SKIPPED",
                symbol=trading_pair,
                filled_quantity=Decimal("0"),
                error="数量小于最小下单量，已跳过",
            )

        logger.info(f"开空: {trading_pair} 数量={quantity}")

        if self.use_market_order:
            # 市价单
            return await self.client.place_order(
                symbol=trading_pair,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=quantity,
                position_side=PositionSide.SHORT,
            )
        else:
            # 限价单 (价格 - 滑点)
            price = await self._get_current_price(trading_pair.replace("USDT", ""))
            limit_price = price * Decimal(str(1 - self.slippage))

            return await self.client.place_order(
                symbol=trading_pair,
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                quantity=quantity,
                price=limit_price,
                position_side=PositionSide.SHORT,
                time_in_force=TimeInForce.IOC,  # 立即成交或取消
            )

    async def _close_short(self, trading_pair: str, quantity: Decimal) -> OrderResult:
        """
        平空仓

        Args:
            trading_pair: 交易对
            quantity: 数量

        Returns:
            OrderResult: 订单结果
        """
        # 格式化数量精度
        quantity = self._round_quantity(trading_pair, quantity)

        # 数量为 0 则跳过
        if quantity == 0:
            return OrderResult(
                success=True,
                order_id="SKIPPED",
                symbol=trading_pair,
                filled_quantity=Decimal("0"),
                error="数量小于最小下单量，已跳过",
            )

        logger.info(f"平空: {trading_pair} 数量={quantity}")

        if self.use_market_order:
            # 市价单
            return await self.client.place_order(
                symbol=trading_pair,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=quantity,
                position_side=PositionSide.SHORT,
                reduce_only=True,
            )
        else:
            # 限价单 (价格 + 滑点)
            price = await self._get_current_price(trading_pair.replace("USDT", ""))
            limit_price = price * Decimal(str(1 + self.slippage))

            return await self.client.place_order(
                symbol=trading_pair,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=quantity,
                price=limit_price,
                position_side=PositionSide.SHORT,
                time_in_force=TimeInForce.IOC,
                reduce_only=True,
            )

    async def execute_all(self, deltas: List[PositionDelta]) -> List[ExecutionResult]:
        """
        执行所有调仓

        Args:
            deltas: 仓位差异列表

        Returns:
            List[ExecutionResult]: 执行结果列表
        """
        if not deltas:
            logger.info("无需调仓")
            return []

        logger.info(f"开始执行 {len(deltas)} 个调仓订单")

        results = []
        for delta in deltas:
            result = await self.execute_delta(delta)
            results.append(result)

            # 记录结果
            if result.status == ExecutionStatus.SUCCESS:
                logger.info(f"✓ {result.symbol}: 成交 {result.filled_quantity}")
            elif result.status == ExecutionStatus.PARTIAL:
                logger.warning(
                    f"△ {result.symbol}: 部分成交 {result.filled_quantity}/{result.target_quantity}"
                )
            elif result.status == ExecutionStatus.SKIPPED:
                logger.info(f"○ {result.symbol}: 跳过 - {result.error}")
            else:
                logger.error(f"✗ {result.symbol}: 失败 - {result.error}")

        # 汇总
        success_count = sum(1 for r in results if r.status == ExecutionStatus.SUCCESS)
        partial_count = sum(1 for r in results if r.status == ExecutionStatus.PARTIAL)
        skipped_count = sum(1 for r in results if r.status == ExecutionStatus.SKIPPED)
        failed_count = sum(1 for r in results if r.status == ExecutionStatus.FAILED)

        logger.info(
            f"执行完成: 成功={success_count}, 部分={partial_count}, 跳过={skipped_count}, 失败={failed_count}"
        )

        return results

    async def close_all_positions(self) -> List[ExecutionResult]:
        """
        平掉所有空头仓位 (紧急情况使用)

        Returns:
            List[ExecutionResult]: 执行结果
        """
        logger.warning("紧急平仓: 平掉所有空头")

        positions = await self.client.get_positions()
        results = []

        for pos in positions:
            if pos.quantity < 0:  # 空头
                quantity = abs(pos.quantity)
                result = await self._close_short(pos.symbol, quantity)

                results.append(ExecutionResult(
                    symbol=pos.symbol,
                    status=ExecutionStatus.SUCCESS if result.success else ExecutionStatus.FAILED,
                    target_quantity=quantity,
                    filled_quantity=result.filled_quantity or Decimal("0"),
                    order_results=[result],
                    error=result.error if not result.success else None,
                ))

        return results
