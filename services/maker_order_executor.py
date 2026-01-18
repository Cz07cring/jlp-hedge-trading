"""
Maker 订单执行器

实现纯 Maker 挂单算法:
1. 使用 GTX (Post-Only) 限价单
2. 追踪盘口，频繁撤单重挂
3. 有利追价，不利等待
4. 部分成交后继续挂剩余
"""

import logging
import asyncio
import time
import uuid
import random
from typing import Optional, Tuple, List
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
from services.maker_order_config import MakerOrderConfig

logger = logging.getLogger(__name__)


class MakerExecutionStatus(Enum):
    """Maker 订单执行状态"""
    SUCCESS = "success"           # 完全成交
    PARTIAL = "partial"           # 部分成交 (超时)
    FAILED = "failed"             # 失败
    SKIPPED = "skipped"           # 跳过 (数量太小)


@dataclass
class MakerExecutionResult:
    """Maker 订单执行结果"""
    symbol: str
    status: MakerExecutionStatus
    target_quantity: Decimal
    filled_quantity: Decimal
    average_price: Decimal
    iterations: int                # 撤单重挂次数
    elapsed_seconds: float         # 总耗时
    error: Optional[str] = None


class MakerOrderExecutor:
    """Maker 订单执行器"""

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
        config: Optional[MakerOrderConfig] = None,
    ):
        """
        初始化 Maker 订单执行器

        Args:
            asterdex_client: AsterDex 客户端
            config: 配置参数
        """
        self.client = asterdex_client
        self.config = config or MakerOrderConfig()

        logger.info(
            f"Maker 订单执行器初始化: "
            f"order_timeout={self.config.order_timeout}s, "
            f"total_timeout={self.config.total_timeout}s, "
            f"price_tolerance={self.config.price_tolerance:.4%}"
        )

    def _get_trading_pair(self, symbol: str) -> str:
        """获取交易对名称"""
        return self.SYMBOL_MAPPING.get(symbol, f"{symbol}USDT")

    def _round_quantity(self, trading_pair: str, quantity: Decimal) -> Decimal:
        """根据交易对精度要求格式化数量"""
        precision = self.QUANTITY_PRECISION.get(trading_pair, 2)
        factor = Decimal(10) ** precision
        rounded = (quantity * factor).to_integral_value() / factor

        min_qty = self.MIN_QUANTITY.get(trading_pair, Decimal("0.001"))
        if rounded < min_qty:
            return Decimal("0")

        return rounded

    def _round_price(self, trading_pair: str, price: Decimal) -> Decimal:
        """根据交易对精度要求格式化价格"""
        precision = self.config.price_precision.get(trading_pair, 2)
        factor = Decimal(10) ** precision
        return (price * factor).to_integral_value() / factor

    def _split_order(
        self,
        trading_pair: str,
        quantity: Decimal,
        price: Decimal,
    ) -> List[Decimal]:
        """
        拆分大额订单

        Args:
            trading_pair: 交易对
            quantity: 总数量
            price: 当前价格

        Returns:
            List[Decimal]: 拆分后的数量列表
        """
        if not self.config.split_order_enabled:
            return [quantity]

        # 计算订单价值
        order_value = float(quantity * price)

        # 小于阈值，不拆分
        if order_value < self.config.split_order_threshold:
            return [quantity]

        # 计算需要拆分成多少笔
        min_val = self.config.split_order_min_value
        max_val = self.config.split_order_max_value

        split_quantities = []
        remaining_value = order_value

        while remaining_value > 0:
            if remaining_value <= max_val:
                # 剩余金额不足最大值，全部下单
                split_value = remaining_value
            elif self.config.split_order_random:
                # 随机金额
                split_value = random.uniform(min_val, max_val)
            else:
                # 固定金额
                split_value = (min_val + max_val) / 2

            # 计算对应的数量
            split_qty = Decimal(str(split_value)) / price
            split_qty = self._round_quantity(trading_pair, split_qty)

            if split_qty > 0:
                # 不能超过剩余数量
                remaining_qty = Decimal(str(remaining_value)) / price
                if split_qty > remaining_qty:
                    split_qty = self._round_quantity(trading_pair, remaining_qty)

                if split_qty > 0:
                    split_quantities.append(split_qty)
                    remaining_value -= float(split_qty * price)
            else:
                break

        if not split_quantities:
            return [quantity]

        logger.info(
            f"[Maker] {trading_pair} 拆单: ${order_value:.2f} -> "
            f"{len(split_quantities)} 笔, 数量: {[float(q) for q in split_quantities]}"
        )

        return split_quantities

    async def _get_orderbook(self, trading_pair: str) -> Tuple[Decimal, Decimal]:
        """
        获取盘口 bid1/ask1

        Returns:
            Tuple[bid1, ask1]
        """
        depth = await self.client.get_depth(trading_pair, limit=5)

        bids = depth.get("bids", [])
        asks = depth.get("asks", [])

        if not bids or not asks:
            raise ValueError(f"{trading_pair} 盘口数据为空")

        bid1 = Decimal(str(bids[0][0]))
        ask1 = Decimal(str(asks[0][0]))

        return bid1, ask1

    def _should_replace_order(
        self,
        side: OrderSide,
        order_price: Decimal,
        current_best_price: Decimal,
    ) -> Tuple[bool, str]:
        """
        判断是否需要撤单重挂

        Args:
            side: 订单方向
            order_price: 当前挂单价格
            current_best_price: 当前盘口最优价

        Returns:
            Tuple[是否需要重挂, 原因]
        """
        if order_price == 0:
            return False, ""

        price_change = abs(current_best_price - order_price) / order_price

        # 有利追价
        if side == OrderSide.SELL:
            # 开空: 价格上涨是有利的 (可以卖更高价)
            if current_best_price > order_price:
                return True, f"追价: ask1 上涨 {order_price} -> {current_best_price}"
        else:
            # 平空: 价格下跌是有利的 (可以买更低价)
            if current_best_price < order_price:
                return True, f"追价: bid1 下跌 {order_price} -> {current_best_price}"

        # 盘口变化超过容忍度
        if price_change > self.config.price_tolerance:
            return True, f"盘口变化 {price_change:.4%} > {self.config.price_tolerance:.4%}"

        return False, ""

    async def _get_order_status(
        self,
        trading_pair: str,
        order_id: str,
    ) -> Tuple[str, Decimal]:
        """
        获取订单状态和已成交数量

        Returns:
            Tuple[状态, 已成交数量]
        """
        try:
            order = await self.client.get_order(trading_pair, order_id=order_id)
            status = order.get("status", "UNKNOWN")
            filled = Decimal(str(order.get("executedQty", "0")))
            return status, filled
        except Exception as e:
            error_msg = str(e)
            # 订单不存在，可能已成交或已撤销
            if "Unknown order" in error_msg or "Order does not exist" in error_msg:
                logger.info(f"订单 {order_id} 已不存在，可能已成交")
                return "NOT_FOUND", Decimal("0")
            logger.warning(f"查询订单状态失败: {e}")
            return "UNKNOWN", Decimal("0")

    async def _place_maker_order(
        self,
        trading_pair: str,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        position_side: PositionSide,
        reduce_only: bool = False,
    ) -> OrderResult:
        """
        下 Maker 订单 (GTX/Post-Only)
        """
        client_order_id = f"maker_{uuid.uuid4().hex[:16]}"

        result = await self.client.place_order(
            symbol=trading_pair,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            position_side=position_side,
            time_in_force=TimeInForce.GTX,  # Post-Only
            reduce_only=reduce_only,
            client_order_id=client_order_id,
        )

        return result

    async def _execute_maker_loop(
        self,
        trading_pair: str,
        side: OrderSide,
        target_quantity: Decimal,
        position_side: PositionSide,
        reduce_only: bool = False,
    ) -> MakerExecutionResult:
        """
        Maker 订单执行核心循环

        Args:
            trading_pair: 交易对
            side: 订单方向 (BUY/SELL)
            target_quantity: 目标数量
            position_side: 持仓方向
            reduce_only: 是否只减仓

        Returns:
            MakerExecutionResult: 执行结果
        """
        start_time = time.time()
        total_filled = Decimal("0")
        total_value = Decimal("0")  # 用于计算均价
        remaining = target_quantity
        iterations = 0
        current_order_id: Optional[str] = None
        current_order_price = Decimal("0")

        logger.info(
            f"[Maker] 开始执行: {trading_pair} {side.value} "
            f"数量={target_quantity} reduce_only={reduce_only}"
        )

        try:
            while remaining > 0 and iterations < self.config.max_iterations:
                elapsed = time.time() - start_time

                # 检查总超时
                if elapsed > self.config.total_timeout:
                    logger.warning(
                        f"[Maker] {trading_pair} 总超时 ({elapsed:.1f}s), "
                        f"已成交 {total_filled}/{target_quantity}"
                    )
                    break

                # 获取盘口
                try:
                    bid1, ask1 = await self._get_orderbook(trading_pair)
                except Exception as e:
                    logger.warning(f"[Maker] 获取盘口失败: {e}, 等待重试")
                    await asyncio.sleep(1)
                    continue

                # 确定挂单价格
                if side == OrderSide.SELL:
                    best_price = ask1  # 开空挂卖一
                else:
                    best_price = bid1  # 平空挂买一

                best_price = self._round_price(trading_pair, best_price)

                # 如果已有挂单，检查是否需要撤单重挂
                if current_order_id:
                    should_replace, reason = self._should_replace_order(
                        side, current_order_price, best_price
                    )

                    if should_replace:
                        # 先查询订单状态，获取已成交数量
                        status, filled = await self._get_order_status(
                            trading_pair, current_order_id
                        )

                        if status in ["FILLED", "CANCELED", "EXPIRED", "REJECTED"]:
                            # 订单已结束
                            if filled > 0:
                                total_filled += filled
                                total_value += filled * current_order_price
                                remaining -= filled
                                logger.info(
                                    f"[Maker] {trading_pair} 订单已结束, "
                                    f"成交 {filled}, 剩余 {remaining}"
                                )
                            current_order_id = None
                            current_order_price = Decimal("0")
                            continue

                        if status == "NOT_FOUND":
                            # 订单不存在，假设已完全成交
                            logger.info(
                                f"[Maker] {trading_pair} 订单已不存在，假设已成交 {remaining}"
                            )
                            total_filled += remaining
                            total_value += remaining * current_order_price
                            remaining = Decimal("0")
                            current_order_id = None
                            current_order_price = Decimal("0")
                            continue

                        # 撤单
                        logger.info(f"[Maker] {trading_pair} 撤单: {reason}")
                        cancelled = await self.client.cancel_order(
                            trading_pair, order_id=current_order_id
                        )

                        if cancelled:
                            # 更新已成交数量
                            if filled > 0:
                                total_filled += filled
                                total_value += filled * current_order_price
                                remaining -= filled
                            iterations += 1
                            current_order_id = None
                            current_order_price = Decimal("0")
                        else:
                            # 撤单失败，可能已成交，查询最新状态
                            status2, filled2 = await self._get_order_status(
                                trading_pair, current_order_id
                            )
                            if status2 == "FILLED" or status2 == "NOT_FOUND":
                                # 订单已成交
                                actual_filled = filled2 if filled2 > 0 else remaining
                                total_filled += actual_filled
                                total_value += actual_filled * current_order_price
                                remaining -= actual_filled
                                logger.info(
                                    f"[Maker] {trading_pair} 撤单失败但订单已成交: {actual_filled}"
                                )
                            current_order_id = None
                            current_order_price = Decimal("0")
                            iterations += 1
                            continue

                # 检查剩余数量是否太小
                rounded_remaining = self._round_quantity(trading_pair, remaining)
                if rounded_remaining == 0:
                    logger.info(
                        f"[Maker] {trading_pair} 剩余数量 {remaining} 小于最小下单量, "
                        f"已成交 {total_filled}/{target_quantity}"
                    )
                    break

                # 没有挂单或刚撤单，下新单
                if current_order_id is None:
                    result = await self._place_maker_order(
                        trading_pair=trading_pair,
                        side=side,
                        quantity=rounded_remaining,
                        price=best_price,
                        position_side=position_side,
                        reduce_only=reduce_only,
                    )

                    if result.success:
                        current_order_id = result.order_id
                        current_order_price = best_price
                        logger.info(
                            f"[Maker] {trading_pair} 挂单: "
                            f"{side.value} {rounded_remaining} @ {best_price}"
                        )

                        # 如果是 GTX 被拒绝 (变成 taker)，订单不会成功
                        if result.status == "REJECTED":
                            logger.warning(
                                f"[Maker] {trading_pair} GTX 被拒绝, 盘口可能已变化"
                            )
                            current_order_id = None
                            current_order_price = Decimal("0")
                            await asyncio.sleep(0.1)
                            continue

                    else:
                        logger.warning(
                            f"[Maker] {trading_pair} 下单失败: {result.error}"
                        )
                        # 等待后重试
                        await asyncio.sleep(0.5)
                        continue

                # 等待并检查订单状态
                order_start = time.time()
                while time.time() - order_start < self.config.order_timeout:
                    await asyncio.sleep(self.config.check_interval_ms / 1000)

                    # 检查订单状态
                    status, filled = await self._get_order_status(
                        trading_pair, current_order_id
                    )

                    if status == "FILLED":
                        # 完全成交
                        total_filled += filled
                        total_value += filled * current_order_price
                        remaining -= filled
                        current_order_id = None
                        current_order_price = Decimal("0")
                        logger.info(
                            f"[Maker] {trading_pair} 完全成交: {filled}, "
                            f"总成交 {total_filled}/{target_quantity}"
                        )
                        break

                    elif status in ["CANCELED", "EXPIRED", "REJECTED"]:
                        # 订单已结束
                        if filled > 0:
                            total_filled += filled
                            total_value += filled * current_order_price
                            remaining -= filled
                        current_order_id = None
                        current_order_price = Decimal("0")
                        break

                    elif status == "NOT_FOUND":
                        # 订单不存在，假设已成交
                        logger.info(
                            f"[Maker] {trading_pair} 订单已不存在，假设已成交 {remaining}"
                        )
                        total_filled += remaining
                        total_value += remaining * current_order_price
                        remaining = Decimal("0")
                        current_order_id = None
                        current_order_price = Decimal("0")
                        break

                    elif status == "PARTIALLY_FILLED":
                        # 部分成交，检查盘口是否需要重挂
                        try:
                            new_bid1, new_ask1 = await self._get_orderbook(trading_pair)
                            new_best = new_ask1 if side == OrderSide.SELL else new_bid1
                            should_replace, _ = self._should_replace_order(
                                side, current_order_price, new_best
                            )
                            if should_replace:
                                break  # 跳出等待循环，进入撤单重挂
                        except Exception:
                            pass

                # 单次挂单超时，撤单重挂
                if current_order_id and time.time() - order_start >= self.config.order_timeout:
                    logger.info(
                        f"[Maker] {trading_pair} 单次超时 ({self.config.order_timeout}s), 撤单重挂"
                    )
                    # 获取最新成交数量
                    status, filled = await self._get_order_status(
                        trading_pair, current_order_id
                    )

                    # 如果订单已不存在，假设已成交
                    if status == "NOT_FOUND":
                        logger.info(
                            f"[Maker] {trading_pair} 订单已不存在，假设已成交 {remaining}"
                        )
                        total_filled += remaining
                        total_value += remaining * current_order_price
                        remaining = Decimal("0")
                        current_order_id = None
                        current_order_price = Decimal("0")
                        continue

                    # 如果已完全成交
                    if status == "FILLED":
                        total_filled += filled
                        total_value += filled * current_order_price
                        remaining -= filled
                        current_order_id = None
                        current_order_price = Decimal("0")
                        logger.info(
                            f"[Maker] {trading_pair} 超时前已成交: {filled}"
                        )
                        continue

                    # 撤单
                    cancelled = await self.client.cancel_order(
                        trading_pair, order_id=current_order_id
                    )

                    if not cancelled:
                        # 撤单失败，可能已成交
                        status2, filled2 = await self._get_order_status(
                            trading_pair, current_order_id
                        )
                        if status2 == "FILLED" or status2 == "NOT_FOUND":
                            actual_filled = filled2 if filled2 > 0 else remaining
                            total_filled += actual_filled
                            total_value += actual_filled * current_order_price
                            remaining -= actual_filled
                            logger.info(
                                f"[Maker] {trading_pair} 撤单失败但订单已成交: {actual_filled}"
                            )
                        current_order_id = None
                        current_order_price = Decimal("0")
                        iterations += 1
                        continue

                    # 撤单成功，更新成交数量
                    if filled > 0:
                        total_filled += filled
                        total_value += filled * current_order_price
                        remaining -= filled

                    iterations += 1
                    current_order_id = None
                    current_order_price = Decimal("0")

        except Exception as e:
            logger.error(f"[Maker] {trading_pair} 执行异常: {e}")
            # 尝试撤销当前订单
            if current_order_id:
                try:
                    await self.client.cancel_order(trading_pair, order_id=current_order_id)
                except Exception:
                    pass

            return MakerExecutionResult(
                symbol=trading_pair,
                status=MakerExecutionStatus.FAILED,
                target_quantity=target_quantity,
                filled_quantity=total_filled,
                average_price=total_value / total_filled if total_filled > 0 else Decimal("0"),
                iterations=iterations,
                elapsed_seconds=time.time() - start_time,
                error=str(e),
            )

        # 计算结果
        elapsed = time.time() - start_time
        fill_ratio = total_filled / target_quantity if target_quantity > 0 else Decimal("0")
        avg_price = total_value / total_filled if total_filled > 0 else Decimal("0")

        if fill_ratio >= Decimal(str(self.config.partial_fill_threshold)):
            status = MakerExecutionStatus.SUCCESS
        elif total_filled > 0:
            status = MakerExecutionStatus.PARTIAL
        else:
            status = MakerExecutionStatus.FAILED

        logger.info(
            f"[Maker] {trading_pair} 执行完成: "
            f"成交 {total_filled}/{target_quantity} ({float(fill_ratio):.1%}), "
            f"均价 {avg_price}, 耗时 {elapsed:.1f}s, 重挂 {iterations} 次"
        )

        return MakerExecutionResult(
            symbol=trading_pair,
            status=status,
            target_quantity=target_quantity,
            filled_quantity=total_filled,
            average_price=avg_price,
            iterations=iterations,
            elapsed_seconds=elapsed,
        )

    async def execute_delta(self, delta: PositionDelta) -> MakerExecutionResult:
        """
        执行单个调仓 (支持拆单)

        Args:
            delta: 仓位差异

        Returns:
            MakerExecutionResult: 执行结果
        """
        symbol = delta.symbol
        trading_pair = self._get_trading_pair(symbol)
        quantity = abs(delta.delta)

        # 检查最小数量
        rounded_qty = self._round_quantity(trading_pair, quantity)
        if rounded_qty == 0:
            logger.info(f"[Maker] {symbol} 数量 {quantity} 小于最小下单量，跳过")
            return MakerExecutionResult(
                symbol=trading_pair,
                status=MakerExecutionStatus.SKIPPED,
                target_quantity=quantity,
                filled_quantity=Decimal("0"),
                average_price=Decimal("0"),
                iterations=0,
                elapsed_seconds=0,
                error="数量小于最小下单量",
            )

        logger.info(f"[Maker] 执行调仓: {symbol} delta={delta.delta:+.6f}")

        # 获取当前价格用于拆单计算
        try:
            bid1, ask1 = await self._get_orderbook(trading_pair)
            current_price = ask1 if delta.delta > 0 else bid1
        except Exception:
            # 获取价格失败，不拆单
            current_price = Decimal("0")

        # 拆分订单
        if current_price > 0:
            split_quantities = self._split_order(trading_pair, rounded_qty, current_price)
        else:
            split_quantities = [rounded_qty]

        # 执行拆分后的订单
        total_filled = Decimal("0")
        total_value = Decimal("0")
        total_iterations = 0
        start_time = time.time()

        side = OrderSide.SELL if delta.delta > 0 else OrderSide.BUY
        reduce_only = delta.delta < 0

        for i, split_qty in enumerate(split_quantities):
            if len(split_quantities) > 1:
                logger.info(
                    f"[Maker] {trading_pair} 执行第 {i+1}/{len(split_quantities)} 笔: {split_qty}"
                )

            result = await self._execute_maker_loop(
                trading_pair=trading_pair,
                side=side,
                target_quantity=split_qty,
                position_side=PositionSide.SHORT,
                reduce_only=reduce_only,
            )

            total_filled += result.filled_quantity
            total_value += result.filled_quantity * result.average_price
            total_iterations += result.iterations

            # 如果有失败，停止继续执行
            if result.status == MakerExecutionStatus.FAILED:
                logger.warning(
                    f"[Maker] {trading_pair} 第 {i+1} 笔失败，停止后续执行"
                )
                break

        # 汇总结果
        elapsed = time.time() - start_time
        fill_ratio = total_filled / rounded_qty if rounded_qty > 0 else Decimal("0")
        avg_price = total_value / total_filled if total_filled > 0 else Decimal("0")

        if fill_ratio >= Decimal(str(self.config.partial_fill_threshold)):
            status = MakerExecutionStatus.SUCCESS
        elif total_filled > 0:
            status = MakerExecutionStatus.PARTIAL
        else:
            status = MakerExecutionStatus.FAILED

        if len(split_quantities) > 1:
            logger.info(
                f"[Maker] {trading_pair} 拆单完成: "
                f"成交 {total_filled}/{rounded_qty} ({float(fill_ratio):.1%}), "
                f"均价 {avg_price}, 总耗时 {elapsed:.1f}s"
            )

        return MakerExecutionResult(
            symbol=trading_pair,
            status=status,
            target_quantity=rounded_qty,
            filled_quantity=total_filled,
            average_price=avg_price,
            iterations=total_iterations,
            elapsed_seconds=elapsed,
        )

    async def execute_all(
        self,
        deltas: list,
    ) -> list:
        """
        执行所有调仓

        Args:
            deltas: 仓位差异列表

        Returns:
            List[MakerExecutionResult]: 执行结果列表
        """
        if not deltas:
            logger.info("[Maker] 无需调仓")
            return []

        logger.info(f"[Maker] 开始执行 {len(deltas)} 个调仓订单")

        results = []
        for delta in deltas:
            result = await self.execute_delta(delta)
            results.append(result)

            # 记录结果
            if result.status == MakerExecutionStatus.SUCCESS:
                logger.info(f"✓ {result.symbol}: Maker 成交 {result.filled_quantity}")
            elif result.status == MakerExecutionStatus.PARTIAL:
                logger.warning(
                    f"△ {result.symbol}: Maker 部分成交 "
                    f"{result.filled_quantity}/{result.target_quantity}"
                )
            elif result.status == MakerExecutionStatus.SKIPPED:
                logger.info(f"○ {result.symbol}: 跳过 - {result.error}")
            else:
                logger.error(f"✗ {result.symbol}: 失败 - {result.error}")

        # 汇总
        success_count = sum(
            1 for r in results if r.status == MakerExecutionStatus.SUCCESS
        )
        partial_count = sum(
            1 for r in results if r.status == MakerExecutionStatus.PARTIAL
        )
        skipped_count = sum(
            1 for r in results if r.status == MakerExecutionStatus.SKIPPED
        )
        failed_count = sum(
            1 for r in results if r.status == MakerExecutionStatus.FAILED
        )

        logger.info(
            f"[Maker] 执行完成: 成功={success_count}, 部分={partial_count}, "
            f"跳过={skipped_count}, 失败={failed_count}"
        )

        return results
