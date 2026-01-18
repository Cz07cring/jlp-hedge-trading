"""
风险监控模块

监控:
1. 保证金率
2. 资金费率
3. 仓位偏差
4. 每日盈亏
"""

from __future__ import annotations

import logging
import aiohttp
from typing import List, Optional
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from clients.asterdex_client import AsterDexClient

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(Enum):
    """告警类型"""
    MARGIN_LOW = "margin_low"
    FUNDING_HIGH = "funding_high"
    POSITION_DEVIATION = "position_deviation"
    DAILY_LOSS = "daily_loss"
    API_ERROR = "api_error"


@dataclass
class RiskAlert:
    """风险告警"""
    alert_type: AlertType
    level: AlertLevel
    symbol: Optional[str]
    message: str
    value: float
    threshold: float
    timestamp: datetime


@dataclass
class RiskMetrics:
    """风险指标"""
    margin_ratio: float  # 保证金率
    total_unrealized_pnl: Decimal  # 总未实现盈亏
    daily_pnl: Decimal  # 今日盈亏
    funding_rates: dict  # 资金费率 {symbol: rate}
    position_deviation: float  # 仓位偏差
    alerts: List[RiskAlert]  # 告警列表


class RiskMonitor:
    """风险监控器"""

    # 监控的交易对
    MONITORED_SYMBOLS = ["SOLUSDT", "ETHUSDT", "BTCUSDT"]

    def __init__(
        self,
        asterdex_client: AsterDexClient,
        hedge_api_url: str = "https://api.jlp.finance",
        max_funding_rate: float = 0.001,
        min_margin_ratio: float = 0.1,
        max_position_deviation: float = 0.05,
        max_daily_loss: float = 0.02,
    ):
        """
        初始化风险监控器

        Args:
            asterdex_client: AsterDex 客户端
            hedge_api_url: Hedge API 地址
            max_funding_rate: 最大资金费率阈值 (0.1%)
            min_margin_ratio: 最低保证金率 (10%)
            max_position_deviation: 最大仓位偏差 (5%)
            max_daily_loss: 最大单日亏损 (2%)
        """
        self.client = asterdex_client
        self.hedge_api_url = hedge_api_url
        self.max_funding_rate = max_funding_rate
        self.min_margin_ratio = min_margin_ratio
        self.max_position_deviation = max_position_deviation
        self.max_daily_loss = max_daily_loss

        # 记录初始净值 (用于计算日盈亏)
        self.initial_equity: Optional[Decimal] = None
        self.last_check_date: Optional[str] = None

        # JLP 价格缓存
        self._jlp_price_cache: Optional[Decimal] = None

        logger.info(
            f"风险监控初始化: "
            f"max_funding={max_funding_rate}, "
            f"min_margin={min_margin_ratio}, "
            f"max_deviation={max_position_deviation}"
        )

    async def check_margin_ratio(self) -> tuple[float, Optional[RiskAlert]]:
        """
        检查保证金率

        Returns:
            (margin_ratio, alert)
        """
        try:
            account = await self.client.get_account()

            # 计算总权益
            # 方式1: 使用 availableBalance (API 已经换算好的可用余额)
            # 方式2: 使用 totalInitialMargin (总初始保证金，代表持仓价值)
            #
            # 对于 JLP 作为保证金的情况，使用 totalInitialMargin + availableBalance
            # 因为 totalInitialMargin 代表已占用的保证金，availableBalance 是剩余可用的

            total_initial_margin = Decimal(str(account.get("totalInitialMargin", "0")))
            available_balance = Decimal(str(account.get("availableBalance", "0")))

            # 总权益 = 已占用保证金 + 可用余额
            total_equity = total_initial_margin + available_balance

            total_maint_margin = Decimal(str(account.get("totalMaintMargin", "0")))

            if total_equity > 0:
                # 维持保证金率 = 维持保证金 / 账户权益 (与 AsterDex 网页一致)
                # 这个值越低越安全，接近 100% 时面临爆仓
                margin_ratio = float(total_maint_margin / total_equity)
            else:
                margin_ratio = 1.0  # 权益为0，危险

            alert = None
            # min_margin_ratio 现在表示最大允许的维持保证金率
            # 例如 0.5 表示维持保证金率超过 50% 时告警
            if margin_ratio > self.min_margin_ratio:
                alert = RiskAlert(
                    alert_type=AlertType.MARGIN_LOW,
                    level=AlertLevel.CRITICAL,
                    symbol=None,
                    message=f"保证金率过高: {margin_ratio:.2%} (权益: ${total_equity:.2f})",
                    value=margin_ratio,
                    threshold=self.min_margin_ratio,
                    timestamp=datetime.now(),
                )
                logger.warning(f"⚠️ 保证金率告警: {margin_ratio:.2%} (接近爆仓)")
            else:
                logger.info(f"保证金率: {margin_ratio:.2%} (权益: ${total_equity:.2f}, 维持保证金: ${total_maint_margin:.2f})")

            return margin_ratio, alert

        except Exception as e:
            logger.error(f"检查保证金率失败: {e}")
            return 0.0, RiskAlert(
                alert_type=AlertType.API_ERROR,
                level=AlertLevel.WARNING,
                symbol=None,
                message=f"获取保证金信息失败: {e}",
                value=0,
                threshold=0,
                timestamp=datetime.now(),
            )

    async def check_funding_rates(self) -> tuple[dict, List[RiskAlert]]:
        """
        检查资金费率

        Returns:
            (funding_rates, alerts)
        """
        funding_rates = {}
        alerts = []

        for symbol in self.MONITORED_SYMBOLS:
            try:
                funding = await self.client.get_funding_rate(symbol)
                rate = float(funding.funding_rate)
                funding_rates[symbol] = rate

                # 检查是否超过阈值 (做空时，负费率需要支付)
                if rate < -self.max_funding_rate:
                    alert = RiskAlert(
                        alert_type=AlertType.FUNDING_HIGH,
                        level=AlertLevel.WARNING,
                        symbol=symbol,
                        message=f"{symbol} 负资金费率过高: {rate:.4%}",
                        value=rate,
                        threshold=-self.max_funding_rate,
                        timestamp=datetime.now(),
                    )
                    alerts.append(alert)
                    logger.warning(f"⚠️ {symbol} 资金费率告警: {rate:.4%}")

            except Exception as e:
                logger.error(f"获取 {symbol} 资金费率失败: {e}")

        return funding_rates, alerts

    async def _get_jlp_price(self, jlp_amount: Decimal) -> Decimal:
        """
        从 Hedge API 获取 JLP 价格

        Args:
            jlp_amount: JLP 数量

        Returns:
            Decimal: JLP 价格
        """
        try:
            url = f"{self.hedge_api_url}/api/v1/hedge-positions"
            params = {"jlp_amount": float(jlp_amount)}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            jlp_stats = data.get("data", {}).get("jlp_stats", {})
                            price = Decimal(str(jlp_stats.get("virtual_price", "0")))
                            if price > 0:
                                self._jlp_price_cache = price
                                return price
        except Exception as e:
            logger.debug(f"获取 JLP 价格失败: {e}")

        # 使用缓存
        if self._jlp_price_cache and self._jlp_price_cache > 0:
            return self._jlp_price_cache

        return Decimal("0")

    async def get_account_equity(self) -> Decimal:
        """
        计算账户净值 = JLP价值 + USDT钱包余额 + 未实现盈亏

        Returns:
            Decimal: 账户净值
        """
        try:
            # 获取账户信息
            account = await self.client.get_account()
            total_unrealized_pnl = Decimal(str(account.get("totalUnrealizedProfit", "0")))

            # 获取 JLP 余额
            balances = await self.client.get_balance()
            jlp_amount = Decimal("0")
            for balance in balances:
                if balance.asset.upper() == "JLP":
                    jlp_amount = balance.balance
                    break

            # 获取 JLP 价格
            jlp_price = await self._get_jlp_price(jlp_amount)
            jlp_value = jlp_amount * jlp_price

            # 获取 USDT 钱包余额
            usdt_wallet_balance = Decimal("0")
            assets = account.get("assets", [])
            for asset in assets:
                if asset.get("asset") == "USDT":
                    usdt_wallet_balance = Decimal(str(asset.get("walletBalance", "0")))
                    break

            # 账户净值 = JLP价值 + USDT钱包余额 + 未实现盈亏
            equity = jlp_value + usdt_wallet_balance + total_unrealized_pnl

            return equity

        except Exception as e:
            logger.error(f"计算账户净值失败: {e}")
            return Decimal("0")

    async def check_daily_pnl(self) -> tuple[Decimal, Optional[RiskAlert]]:
        """
        检查每日盈亏

        使用完整净值计算: JLP价值 + USDT余额 + 未实现盈亏

        Returns:
            (daily_pnl, alert)
        """
        try:
            # 获取完整账户净值
            current_equity = await self.get_account_equity()

            if current_equity <= 0:
                logger.warning("账户净值为0，跳过日盈亏检查")
                return Decimal("0"), None

            today = datetime.now().strftime("%Y-%m-%d")

            # 新的一天，重置初始净值
            if self.last_check_date != today:
                self.initial_equity = current_equity
                self.last_check_date = today
                logger.info(f"新的一天，重置初始净值: ${current_equity:.2f}")
                return Decimal("0"), None

            if self.initial_equity is None or self.initial_equity <= 0:
                self.initial_equity = current_equity
                return Decimal("0"), None

            # 计算日盈亏
            daily_pnl = current_equity - self.initial_equity
            daily_pnl_pct = float(daily_pnl / self.initial_equity) if self.initial_equity > 0 else 0

            # 防止误报：如果变化超过50%，可能是数据问题
            if abs(daily_pnl_pct) > 0.5:
                logger.warning(
                    f"日盈亏计算异常 ({daily_pnl_pct:.2%})，重置基准。"
                    f"初始: ${self.initial_equity:.2f}, 当前: ${current_equity:.2f}"
                )
                self.initial_equity = current_equity
                return Decimal("0"), None

            alert = None
            if daily_pnl_pct < -self.max_daily_loss:
                alert = RiskAlert(
                    alert_type=AlertType.DAILY_LOSS,
                    level=AlertLevel.CRITICAL,
                    symbol=None,
                    message=f"单日亏损过大: {daily_pnl_pct:.2%}",
                    value=daily_pnl_pct,
                    threshold=-self.max_daily_loss,
                    timestamp=datetime.now(),
                )
                logger.warning(f"⚠️ 日亏损告警: {daily_pnl_pct:.2%}")

            return daily_pnl, alert

        except Exception as e:
            logger.error(f"检查日盈亏失败: {e}")
            return Decimal("0"), None

    async def check_unrealized_pnl(self) -> Decimal:
        """获取未实现盈亏"""
        try:
            positions = await self.client.get_positions()
            total_pnl = sum(pos.unrealized_pnl for pos in positions)
            return total_pnl
        except Exception as e:
            logger.error(f"获取未实现盈亏失败: {e}")
            return Decimal("0")

    async def check_all(self, position_deviation: float = 0.0) -> RiskMetrics:
        """
        执行全面风险检查

        Args:
            position_deviation: 仓位偏差 (由 PositionManager 提供)

        Returns:
            RiskMetrics: 风险指标
        """
        alerts = []

        # 1. 检查保证金率
        margin_ratio, margin_alert = await self.check_margin_ratio()
        if margin_alert:
            alerts.append(margin_alert)

        # 2. 检查资金费率
        funding_rates, funding_alerts = await self.check_funding_rates()
        alerts.extend(funding_alerts)

        # 3. 检查日盈亏
        daily_pnl, pnl_alert = await self.check_daily_pnl()
        if pnl_alert:
            alerts.append(pnl_alert)

        # 4. 获取未实现盈亏
        unrealized_pnl = await self.check_unrealized_pnl()

        # 5. 检查仓位偏差
        if position_deviation > self.max_position_deviation:
            alerts.append(RiskAlert(
                alert_type=AlertType.POSITION_DEVIATION,
                level=AlertLevel.WARNING,
                symbol=None,
                message=f"仓位偏差过大: {position_deviation:.2%}",
                value=position_deviation,
                threshold=self.max_position_deviation,
                timestamp=datetime.now(),
            ))

        return RiskMetrics(
            margin_ratio=margin_ratio,
            total_unrealized_pnl=unrealized_pnl,
            daily_pnl=daily_pnl,
            funding_rates=funding_rates,
            position_deviation=position_deviation,
            alerts=alerts,
        )

    def has_critical_alert(self, metrics: RiskMetrics) -> bool:
        """检查是否有严重告警"""
        return any(
            alert.level == AlertLevel.CRITICAL
            for alert in metrics.alerts
        )

    def format_alerts(self, alerts: List[RiskAlert]) -> str:
        """格式化告警信息"""
        if not alerts:
            return "无告警"

        lines = []
        for alert in alerts:
            level_icon = {
                AlertLevel.INFO: "ℹ️",
                AlertLevel.WARNING: "⚠️",
                AlertLevel.CRITICAL: "🚨",
            }.get(alert.level, "")

            lines.append(f"{level_icon} {alert.message}")

        return "\n".join(lines)
