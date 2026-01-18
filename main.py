"""
JLP Delta-Neutral 对冲机器人 (SaaS 版本)

主入口文件 - 集成云端功能
"""

from __future__ import annotations

import sys
import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import load_config, get_config
from strategies.delta_neutral import DeltaNeutralStrategy

# 云端模块
from cloud.client import CloudClient, CloudConfig
from cloud.license_manager import LicenseManager
from cloud.data_reporter import DataReporter
from cloud.config_sync import ConfigSync

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class HedgeBot:
    """对冲机器人 (SaaS 版本)"""

    def __init__(self):
        self.strategies: list[DeltaNeutralStrategy] = []
        self.is_running = False
        
        # 云端组件
        self.cloud_client: Optional[CloudClient] = None
        self.license_manager: Optional[LicenseManager] = None
        self.data_reporter: Optional[DataReporter] = None
        self.config_sync: Optional[ConfigSync] = None
        self.cloud_enabled = False

    async def initialize(self):
        """初始化机器人"""
        logger.info("=" * 60)
        logger.info("  JLP Delta-Neutral 对冲机器人 (SaaS 版本)")
        logger.info("=" * 60)

        # 加载配置
        config = get_config()
        
        # 1. 初始化云端功能（如果启用）
        if config.cloud.enabled:
            logger.info("云端功能已启用，正在初始化...")
            
            cloud_config = CloudConfig(
                enabled=config.cloud.enabled,
                api_url=config.cloud.api_url,
                license_key=config.cloud.license_key,
                report_interval=config.cloud.report_interval,
                timeout=config.cloud.timeout,
            )
            
            self.cloud_client = CloudClient(cloud_config)
            self.license_manager = LicenseManager(self.cloud_client)
            
            # 验证 License
            logger.info("正在验证 License...")
            if not await self.license_manager.verify():
                logger.error("=" * 60)
                logger.error("  License 验证失败，程序退出")
                logger.error("  请检查 License Key 是否正确")
                logger.error("  或访问 SaaS 平台获取有效的 License")
                logger.error("=" * 60)
                return False
            
            logger.info(f"License 验证成功！计划类型: {self.license_manager.plan_type}")
            logger.info(f"最大账户数: {self.license_manager.max_accounts}")
            
            # 初始化数据上报器
            self.data_reporter = DataReporter(
                self.cloud_client,
                report_interval=config.cloud.report_interval,
            )
            
            # 初始化配置同步器
            self.config_sync = ConfigSync(
                self.cloud_client,
                sync_interval=config.cloud.sync_interval,
            )
            
            # 设置配置变更回调
            self.config_sync.set_on_config_change(self._on_config_change)
            
            # 同步云端配置
            await self.config_sync.sync()
            logger.info("云端配置同步完成")
            
            self.cloud_enabled = True
        else:
            logger.info("云端功能未启用，使用本地模式运行")
        
        # 2. 加载账户配置
        enabled_accounts = config.get_enabled_accounts()
        if not enabled_accounts:
            logger.error("没有启用的账户，请检查配置文件")
            return False

        logger.info(f"配置文件中有 {len(enabled_accounts)} 个启用的账户")
        
        # 3. 检查账户数量限制（云端模式下）
        if self.cloud_enabled and self.license_manager:
            max_accounts = self.license_manager.get_max_accounts()
            
            if max_accounts == 0:
                logger.error("=" * 60)
                logger.error("  您的订阅计划不支持运行执行器")
                logger.error("  请升级到专业版或终身版")
                logger.error("=" * 60)
                return False
            
            if len(enabled_accounts) > max_accounts:
                logger.warning("=" * 60)
                logger.warning(f"  账户数量超过限制！")
                logger.warning(f"  配置账户: {len(enabled_accounts)} 个")
                logger.warning(f"  计划限制: {max_accounts} 个")
                logger.warning(f"  将只启用前 {max_accounts} 个账户")
                if max_accounts == 1:
                    logger.warning(f"  💡 升级到终身版可支持多账户")
                logger.warning("=" * 60)
                # 限制账户数量
                enabled_accounts = enabled_accounts[:max_accounts]
        
        logger.info(f"将运行 {len(enabled_accounts)} 个账户")

        # 4. 为每个账户创建策略（每个账户独立的云端客户端）
        for account in enabled_accounts:
            # 为每个账户创建独立的 CloudClient（包含账户名，用于服务端限制）
            account_cloud_client = None
            account_data_reporter = None
            
            if self.cloud_enabled:
                account_cloud_client = CloudClient(
                    CloudConfig(
                        enabled=config.cloud.enabled,
                        api_url=config.cloud.api_url,
                        license_key=config.cloud.license_key,
                        report_interval=config.cloud.report_interval,
                        timeout=config.cloud.timeout,
                    ),
                    account_name=account.name,  # 传入账户名（服务端限制关键）
                )
                account_data_reporter = DataReporter(
                    account_cloud_client,
                    report_interval=config.cloud.report_interval,
                )
                logger.info(f"账户 [{account.name}] 云端客户端已创建")
            
            strategy = DeltaNeutralStrategy(
                account_config=account,
                global_config=config.global_config,
                notification_config=config.notification,
                cloud_client=account_cloud_client or self.cloud_client,
                data_reporter=account_data_reporter or self.data_reporter,
            )
            await strategy.initialize()
            self.strategies.append(strategy)

        logger.info("=" * 60)
        logger.info("  机器人初始化完成")
        logger.info("=" * 60)
        return True

    def _on_config_change(self, new_config: dict):
        """配置变更回调"""
        logger.info("检测到云端配置变更，更新策略参数...")
        # TODO: 更新策略参数
        # 这里可以通知各策略更新配置

    async def run(self):
        """运行机器人"""
        if not self.strategies:
            logger.error("没有策略可运行")
            return

        self.is_running = True

        # 设置信号处理
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.stop)

        logger.info("机器人开始运行...")

        # 创建任务列表
        tasks = []
        
        # 策略运行任务
        for strategy in self.strategies:
            tasks.append(asyncio.create_task(strategy.run_loop()))
        
        # 云端后台任务
        if self.cloud_enabled:
            if self.license_manager:
                await self.license_manager.start_background_check()
            if self.data_reporter:
                await self.data_reporter.start_background_report()
            if self.config_sync:
                await self.config_sync.start_background_sync()

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("任务被取消")
        finally:
            # 停止云端任务
            await self._stop_cloud_tasks()

    async def _stop_cloud_tasks(self):
        """停止云端后台任务"""
        if self.license_manager:
            await self.license_manager.stop_background_check()
        if self.data_reporter:
            await self.data_reporter.stop_background_report()
        if self.config_sync:
            await self.config_sync.stop_background_sync()
        if self.cloud_client:
            await self.cloud_client.close()

    def stop(self):
        """停止机器人"""
        logger.info("正在停止机器人...")
        self.is_running = False

        for strategy in self.strategies:
            strategy.stop()

    async def run_once(self):
        """执行一次调仓 (用于测试)"""
        for strategy in self.strategies:
            await strategy.run_once()
        
        # 立即上报数据
        if self.data_reporter:
            await self.data_reporter.report_all_now()

    async def get_status(self) -> dict:
        """获取机器人状态"""
        status = {
            "is_running": self.is_running,
            "cloud_enabled": self.cloud_enabled,
            "strategies": [
                await strategy.get_status()
                for strategy in self.strategies
            ],
        }
        
        # 添加云端状态
        if self.cloud_enabled:
            status["cloud"] = {
                "license": self.license_manager.get_status() if self.license_manager else None,
                "reporter": self.data_reporter.get_status() if self.data_reporter else None,
                "config_sync": self.config_sync.get_status() if self.config_sync else None,
            }
        
        return status


async def test_cloud_connection():
    """测试云端连接（用于调试）"""
    logger.info("=" * 60)
    logger.info("  云端连接测试")
    logger.info("=" * 60)
    
    config = get_config()
    
    if not config.cloud.enabled:
        logger.error("云端功能未启用，请在配置文件中设置 cloud.enabled = true")
        return
    
    cloud_config = CloudConfig(
        enabled=config.cloud.enabled,
        api_url=config.cloud.api_url,
        license_key=config.cloud.license_key,
        timeout=config.cloud.timeout,
    )
    
    client = CloudClient(cloud_config)
    
    # 1. 测试 License 验证
    logger.info("\n[1] 测试 License 验证...")
    license_mgr = LicenseManager(client)
    if await license_mgr.verify():
        logger.info(f"  ✓ License 验证成功")
        logger.info(f"    - 计划类型: {license_mgr.plan_type}")
        logger.info(f"    - 过期时间: {license_mgr.expires_at}")
    else:
        logger.error("  ✗ License 验证失败")
        await client.close()
        return
    
    # 2. 测试获取配置
    logger.info("\n[2] 测试获取云端配置...")
    config_sync = ConfigSync(client)
    if await config_sync.sync():
        logger.info("  ✓ 配置同步成功")
        logger.info(f"    - 调仓阈值: {config_sync.get_rebalance_threshold()}")
        logger.info(f"    - Telegram: {'启用' if config_sync.is_telegram_enabled() else '禁用'}")
        logger.info(f"    - 企业微信: {'启用' if config_sync.is_wecom_enabled() else '禁用'}")
    else:
        logger.warning("  ✗ 配置同步失败（可能是默认配置）")
    
    # 3. 测试数据上报
    logger.info("\n[3] 测试数据上报...")
    reporter = DataReporter(client)
    
    # 模拟净值数据
    reporter.update_equity(
        jlp_amount=1000,
        jlp_price=4.5,
        jlp_value_usd=4500,
        total_equity_usd=5000,
        unrealized_pnl=100,
        margin_ratio=0.5,
        hedge_ratio=0.67,
    )
    
    if await reporter.report_equity_now():
        logger.info("  ✓ 净值数据上报成功")
    else:
        logger.warning("  ✗ 净值数据上报失败")
    
    # 模拟订单数据
    reporter.add_order(
        order_id="test_order_001",
        symbol="SOLUSDT",
        side="sell",
        order_type="market",
        amount=1.5,
        status="filled",
        filled_amount=1.5,
        avg_price=140.5,
    )
    
    if await reporter.report_orders_now():
        logger.info("  ✓ 订单数据上报成功")
    else:
        logger.warning("  ✗ 订单数据上报失败")
    
    await client.close()
    
    logger.info("\n" + "=" * 60)
    logger.info("  云端连接测试完成")
    logger.info("=" * 60)


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="JLP Delta-Neutral 对冲机器人 (SaaS 版本)")
    parser.add_argument(
        "--once",
        action="store_true",
        help="只执行一次调仓检查",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="查看当前状态",
    )
    parser.add_argument(
        "--test-cloud",
        action="store_true",
        help="测试云端连接",
    )
    args = parser.parse_args()

    # 测试云端连接
    if args.test_cloud:
        await test_cloud_connection()
        return

    bot = HedgeBot()

    if not await bot.initialize():
        return

    if args.status:
        import json
        status = await bot.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    elif args.once:
        await bot.run_once()
    else:
        await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
