"""
Delta-Neutral 对冲策略

核心逻辑:
1. 获取 JLP 余额
2. 计算目标对冲仓位
3. 对比当前仓位
4. 执行调仓
5. 风险监控
6. 数据上报（云端模式）
"""

import logging
import asyncio
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from clients.asterdex_client import AsterDexClient
from services.position_manager import PositionManager
from services.order_executor import OrderExecutor, ExecutionStatus
from services.maker_order_config import MakerOrderConfig
from services.risk_monitor import RiskMonitor, AlertLevel
from config.settings import AccountConfig, GlobalConfig

# 类型提示，避免循环导入
if TYPE_CHECKING:
    from cloud.client import CloudClient
    from cloud.data_reporter import DataReporter

logger = logging.getLogger(__name__)


class DeltaNeutralStrategy:
    """Delta-Neutral 对冲策略"""

    def __init__(
        self,
        account_config: AccountConfig,
        global_config: GlobalConfig,
        cloud_client: Optional["CloudClient"] = None,
        data_reporter: Optional["DataReporter"] = None,
    ):
        """
        初始化策略

        Args:
            account_config: 账户配置
            global_config: 全局配置
            cloud_client: 云端客户端（可选）
            data_reporter: 数据上报器（可选）
        """
        self.account_name = account_config.name
        self.account_config = account_config
        self.global_config = global_config
        
        # 云端组件
        self.cloud_client = cloud_client
        self.data_reporter = data_reporter

        # 初始化 AsterDex 客户端 (支持 EVM 和 Solana 两种模式)
        asterdex_cfg = account_config.asterdex
        self.client = AsterDexClient(
            user_address=asterdex_cfg.user_address,
            signer_address=asterdex_cfg.signer_address,
            private_key=asterdex_cfg.private_key,
            api_key=asterdex_cfg.api_key,
            api_secret=asterdex_cfg.api_secret,
            chain=asterdex_cfg.chain,
            base_url=global_config.asterdex_base_url,
        )

        # 初始化仓位管理器
        # 从 cloud_client 获取 license_key 用于调用 Hedge API
        license_key = cloud_client.config.license_key if cloud_client else ""
        self.position_manager = PositionManager(
            asterdex_client=self.client,
            hedge_api_url=global_config.hedge_api_url,
            rebalance_threshold=global_config.rebalance_threshold,
            min_order_sizes=account_config.trading.min_order_size,
            license_key=license_key,
        )

        # 初始化订单执行器
        maker_settings = account_config.trading.maker_order
        use_maker = maker_settings.enabled

        if use_maker:
            # 使用 Maker 模式
            maker_config = MakerOrderConfig(
                order_timeout=maker_settings.order_timeout,
                total_timeout=maker_settings.total_timeout,
                check_interval_ms=maker_settings.check_interval_ms,
                price_tolerance=maker_settings.price_tolerance,
                max_iterations=maker_settings.max_iterations,
                # 拆单配置
                split_order_enabled=getattr(maker_settings, 'split_order_enabled', True),
                split_order_threshold=getattr(maker_settings, 'split_order_threshold', 500.0),
                split_order_min_value=getattr(maker_settings, 'split_order_min_value', 100.0),
                split_order_max_value=getattr(maker_settings, 'split_order_max_value', 300.0),
            )
            self.order_executor = OrderExecutor(
                asterdex_client=self.client,
                use_maker_order=True,
                maker_config=maker_config,
            )
            logger.info(f"[{self.account_name}] 使用 Maker 挂单模式 (拆单: {maker_config.split_order_enabled})")
        else:
            # 使用市价单模式
            self.order_executor = OrderExecutor(
                asterdex_client=self.client,
                slippage=account_config.trading.slippage,
                use_market_order=True,
            )
            logger.info(f"[{self.account_name}] 使用市价单模式")

        # 初始化风险监控
        self.risk_monitor = RiskMonitor(
            asterdex_client=self.client,
            hedge_api_url=global_config.hedge_api_url,
            max_funding_rate=global_config.max_funding_rate,
            min_margin_ratio=global_config.min_margin_ratio,
            max_daily_loss=global_config.max_daily_loss,
        )

        # 运行状态
        self.is_running = False
        self.last_rebalance_time: Optional[datetime] = None
        self.rebalance_count = 0

        logger.info(f"策略初始化完成: {self.account_name}")

    async def initialize(self):
        """策略初始化 (设置杠杆等)"""
        logger.info(f"[{self.account_name}] 初始化策略...")

        leverage = self.account_config.trading.leverage

        # 设置杠杆
        for symbol in ["SOLUSDT", "ETHUSDT", "BTCUSDT"]:
            try:
                await self.client.set_leverage(symbol, leverage)
                logger.info(f"设置 {symbol} 杠杆为 {leverage}x")
            except Exception as e:
                logger.warning(f"设置 {symbol} 杠杆失败: {e}")

        # 获取初始 JLP 余额
        jlp_amount = await self.position_manager.get_jlp_balance()
        logger.info(f"JLP 余额: {jlp_amount}")
        
        # 上报启动状态到云端
        if self.data_reporter:
            self.data_reporter.add_alert(
                alert_type="startup",
                level="info",
                title=f"策略启动 - {self.account_name}",
                message=f"JLP 余额: {jlp_amount:.4f}",
            )

    async def run_once(self) -> bool:
        """
        执行一次调仓检查

        Returns:
            bool: 是否执行成功
        """
        logger.info(f"[{self.account_name}] 开始调仓检查...")

        try:
            # 1. 获取对冲状态
            status = await self.position_manager.get_hedge_status()

            if status.jlp_amount <= 0:
                logger.warning("JLP 余额为 0，跳过调仓")
                return True

            logger.info(
                f"JLP: {status.jlp_amount:.4f} (${status.jlp_value_usd:.2f}), "
                f"对冲比例: {status.hedge_ratio:.2%}"
            )

            # 2. 过滤需要调仓的差异
            significant_deltas = self.position_manager.filter_significant_deltas(
                status.deltas,
                status.target_positions,
            )

            # 3. 执行调仓
            if significant_deltas:
                logger.info(f"需要调仓 {len(significant_deltas)} 个品种")

                results = await self.order_executor.execute_all(
                    list(significant_deltas.values())
                )

                # 统计失败数量
                failed_count = sum(1 for r in results if r.status == ExecutionStatus.FAILED)

                if failed_count > 0:
                    logger.warning(f"有 {failed_count} 个订单执行失败")

                self.rebalance_count += 1
                
                # 上报调仓和订单数据到云端
                if self.data_reporter:
                    for delta in significant_deltas.values():
                        self.data_reporter.add_rebalance(
                            symbol=f"{delta.symbol}USDT",
                            side="sell" if delta.delta < 0 else "buy",
                            amount=abs(float(delta.delta)),
                            status="success" if failed_count == 0 else "partial",
                            before_position=float(delta.current) if hasattr(delta, 'current') else None,
                            after_position=float(delta.target) if hasattr(delta, 'target') else None,
                            reason="rebalance",
                        )
                    
                    # 上报订单数据
                    for result in results:
                        if hasattr(result, 'order_id') and result.order_id:
                            self.data_reporter.add_order(
                                order_id=result.order_id,
                                symbol=f"{result.symbol}USDT" if hasattr(result, 'symbol') else "UNKNOWN",
                                side=result.side if hasattr(result, 'side') else "unknown",
                                order_type="maker" if self.order_executor.use_maker_order else "market",
                                amount=float(result.quantity) if hasattr(result, 'quantity') else 0,
                                status="filled" if result.status == ExecutionStatus.SUCCESS else "failed",
                                filled_amount=float(result.filled_quantity) if hasattr(result, 'filled_quantity') else None,
                                avg_price=float(result.avg_price) if hasattr(result, 'avg_price') else None,
                                error_message=result.error if hasattr(result, 'error') else None,
                            )
            else:
                logger.info("仓位偏差在阈值内，无需调仓")

            # 4. 风险检查
            position_deviation = 0.0
            if status.total_target_value > 0:
                position_deviation = abs(
                    1 - float(status.total_current_value / status.total_target_value)
                )

            risk_metrics = await self.risk_monitor.check_all(position_deviation)

            # 处理告警（上报到云端）
            if risk_metrics.alerts:
                for alert in risk_metrics.alerts:
                    logger.warning(f"风险告警: [{alert.level.value}] {alert.alert_type.value} - {alert.message}")
                    
                    # 上报告警到云端
                    if self.data_reporter:
                        self.data_reporter.add_alert(
                            alert_type=alert.alert_type.value,
                            level=alert.level.value,
                            title=f"风险告警 - {self.account_name}",
                            message=alert.message,
                        )
                    
                    # 严重告警：考虑紧急平仓
                    if alert.level == AlertLevel.CRITICAL and alert.alert_type.value == "margin_low":
                        logger.critical("保证金率过低，建议人工介入！")

            self.last_rebalance_time = datetime.now()
            
            # 上报净值数据到云端
            if self.data_reporter:
                self.data_reporter.update_equity(
                    jlp_amount=float(status.jlp_amount),
                    jlp_price=float(status.jlp_price),
                    jlp_value_usd=float(status.jlp_value_usd),
                    total_equity_usd=float(status.jlp_value_usd),  # 使用 JLP 价值作为总净值
                    unrealized_pnl=0,  # TODO: 从账户获取
                    margin_ratio=float(risk_metrics.margin_ratio) if risk_metrics else 0,
                    hedge_ratio=float(status.hedge_ratio),
                    positions={
                        delta.symbol: {
                            "target": float(delta.target) if hasattr(delta, 'target') else 0,
                            "current": float(delta.current) if hasattr(delta, 'current') else 0,
                            "delta": float(delta.delta),
                        }
                        for delta in status.deltas.values()
                    } if status.deltas else {},
                )
            
            return True

        except Exception as e:
            logger.exception(f"[{self.account_name}] 调仓失败: {e}")
            
            # 上报告警到云端
            if self.data_reporter:
                self.data_reporter.add_alert(
                    alert_type="execution_failed",
                    level="critical",
                    title=f"调仓执行失败 - {self.account_name}",
                    message=str(e),
                )
            
            return False

    async def run_loop(self):
        """运行主循环"""
        self.is_running = True
        interval = self.global_config.rebalance_interval

        logger.info(f"[{self.account_name}] 开始主循环，间隔 {interval} 秒")

        while self.is_running:
            try:
                await self.run_once()
            except Exception as e:
                logger.exception(f"[{self.account_name}] 循环执行异常: {e}")

            # 等待下一次
            await asyncio.sleep(interval)

    def stop(self):
        """停止策略"""
        logger.info(f"[{self.account_name}] 停止策略...")
        self.is_running = False

    async def get_status(self) -> dict:
        """获取策略状态"""
        try:
            status = await self.position_manager.get_hedge_status()
            risk_metrics = await self.risk_monitor.check_all()

            return {
                "account_name": self.account_name,
                "is_running": self.is_running,
                "jlp_amount": float(status.jlp_amount),
                "jlp_value_usd": float(status.jlp_value_usd),
                "hedge_ratio": status.hedge_ratio,
                "target_positions": {
                    symbol: {
                        "amount": float(pos.amount),
                        "value_usd": float(pos.value_usd),
                    }
                    for symbol, pos in status.target_positions.items()
                },
                "current_positions": {
                    symbol: {
                        "amount": float(abs(pos.quantity)),
                        "unrealized_pnl": float(pos.unrealized_pnl),
                    }
                    for symbol, pos in status.current_positions.items()
                },
                "margin_ratio": risk_metrics.margin_ratio,
                "daily_pnl": float(risk_metrics.daily_pnl),
                "funding_rates": risk_metrics.funding_rates,
                "alerts": [
                    {
                        "type": alert.alert_type.value,
                        "level": alert.level.value,
                        "message": alert.message,
                    }
                    for alert in risk_metrics.alerts
                ],
                "last_rebalance": self.last_rebalance_time.isoformat() if self.last_rebalance_time else None,
                "rebalance_count": self.rebalance_count,
            }
        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return {
                "account_name": self.account_name,
                "error": str(e),
            }
