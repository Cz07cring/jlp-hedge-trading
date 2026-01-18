#!/usr/bin/env python3
"""
AsterDex 净值统计报告 - 独立启动脚本

用法:
    python scripts/run_reporter.py                    # 运行一次
    python scripts/run_reporter.py --daemon          # 后台运行（定时采集+推送）
    python scripts/run_reporter.py --report-now      # 立即发送报告
    python scripts/run_reporter.py --collect-only    # 仅采集数据不推送
"""

import os
import sys
import json
import asyncio
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from clients.asterdex_client import AsterDexClient
from scripts.equity_reporter.collector import EquityCollector
from scripts.equity_reporter.storage import EquityStorage
from scripts.equity_reporter.calculator import EquityCalculator
from scripts.equity_reporter.chart_generator import ChartGenerator
from scripts.equity_reporter.notifier import WeChatNotifier, WeChatConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("equity_reporter")


class EquityReporter:
    """净值报告服务 - 支持多用户"""

    def __init__(self, config_path: Path):
        """
        初始化报告服务

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = self._load_config()

        # 初始化组件
        self.storage = EquityStorage()
        self.chart_generator = ChartGenerator()

        # 报告配置
        report_config = self.config.get("report", {})
        self.collect_interval = report_config.get("collect_interval_minutes", 5)
        self.report_interval = report_config.get("report_interval_minutes", 30)

        # 企业微信配置
        wechat_config = report_config.get("wechat", {})
        self.notifier = WeChatNotifier(WeChatConfig(
            webhook_url=wechat_config.get("webhook_url", ""),
            enabled=wechat_config.get("enabled", False),
            timeout=wechat_config.get("timeout", 30.0),
        ))

        # 指标计算器
        self.calculator = EquityCalculator()

        # 多账户支持
        self.collectors = {}  # {account_name: (client, collector)}
        self.account_configs = []  # 启用的账户配置列表

    def _load_config(self) -> dict:
        """加载配置文件"""
        if not self.config_path.exists():
            logger.error(f"配置文件不存在: {self.config_path}")
            sys.exit(1)

        with open(self.config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def _init_clients(self):
        """初始化所有启用账户的 AsterDex 客户端"""
        accounts = self.config.get("accounts", [])
        hedge_api_url = self.config.get("global", {}).get("hedge_api_url", "http://localhost:3000")

        for acc in accounts:
            if not acc.get("enabled", True):
                continue

            account_name = acc.get("name", "未命名")
            asterdex_config = acc.get("asterdex", {})

            try:
                client = AsterDexClient(
                    user_address=asterdex_config.get("user_address", ""),
                    api_key=asterdex_config.get("api_key", ""),
                    api_secret=asterdex_config.get("api_secret", ""),
                    chain=asterdex_config.get("chain", "solana"),
                    base_url=asterdex_config.get("base_url", "https://fapi.asterdex.com"),
                )

                collector = EquityCollector(
                    asterdex_client=client,
                    account_name=account_name,
                    hedge_api_url=hedge_api_url,
                )

                self.collectors[account_name] = (client, collector)
                self.account_configs.append(acc)
                logger.info(f"初始化账户: {account_name}")

            except Exception as e:
                logger.error(f"初始化账户 {account_name} 失败: {e}")

        if not self.collectors:
            raise ValueError("没有成功初始化任何账户")

        logger.info(f"共初始化 {len(self.collectors)} 个账户")

    async def collect_once(self) -> bool:
        """
        采集所有账户数据

        Returns:
            bool: 是否全部成功
        """
        try:
            if not self.collectors:
                await self._init_clients()

            success_count = 0
            for account_name, (client, collector) in self.collectors.items():
                try:
                    snapshot = await collector.collect()
                    self.storage.append_snapshot(snapshot)
                    logger.info(f"[{account_name}] 数据采集成功: equity=${snapshot.equity:.2f}")
                    success_count += 1
                except Exception as e:
                    logger.error(f"[{account_name}] 数据采集失败: {e}")

            return success_count > 0

        except Exception as e:
            logger.error(f"数据采集失败: {e}")
            return False

    async def send_report(self, with_charts: bool = True) -> bool:
        """
        发送所有账户报告

        Args:
            with_charts: 是否包含图表

        Returns:
            bool: 是否成功
        """
        try:
            if not self.collectors:
                await self._init_clients()

            all_snapshots = []
            all_metrics = []

            # 1. 采集所有账户数据
            for account_name, (client, collector) in self.collectors.items():
                try:
                    snapshot = await collector.collect()
                    self.storage.append_snapshot(snapshot)
                    all_snapshots.append(snapshot)

                    # 获取该账户的历史数据
                    df = self.storage.get_history(days=365, account=account_name)

                    # 计算该账户的指标
                    current_snapshot = {
                        "equity": float(snapshot.equity),
                        "jlp_amount": float(snapshot.jlp_amount),
                        "jlp_price": float(snapshot.jlp_price),
                        "jlp_value": float(snapshot.jlp_value),
                        "available_balance": float(snapshot.available_balance),
                        "unrealized_pnl": float(snapshot.unrealized_pnl),
                        "margin_ratio": snapshot.margin_ratio,
                        "hedge_ratio": snapshot.hedge_ratio,
                        "sol_pos": float(snapshot.sol_pos),
                        "eth_pos": float(snapshot.eth_pos),
                        "btc_pos": float(snapshot.btc_pos),
                        "sol_funding": snapshot.sol_funding,
                        "eth_funding": snapshot.eth_funding,
                        "btc_funding": snapshot.btc_funding,
                    }

                    metrics = self.calculator.calc_report_metrics(df, current_snapshot)
                    all_metrics.append((account_name, metrics, df))

                except Exception as e:
                    logger.error(f"[{account_name}] 采集失败: {e}")

            if not all_metrics:
                logger.error("没有成功采集任何账户数据")
                return False

            # 2. 发送每个账户的报告
            for account_name, metrics, df in all_metrics:
                try:
                    # 生成图表
                    chart_images = []
                    if with_charts and not df.empty:
                        try:
                            chart_images = [
                                self.chart_generator.generate_7d_chart(df, account_name),
                                self.chart_generator.generate_30d_chart(df, account_name),
                                self.chart_generator.generate_365d_chart(df, account_name),
                            ]
                            logger.info(f"[{account_name}] 生成了 {len(chart_images)} 张图表")
                        except Exception as e:
                            logger.error(f"[{account_name}] 生成图表失败: {e}")

                    # 发送报告（包含账户名）
                    success = await self.notifier.send_report(metrics, chart_images, account_name)

                    if success:
                        logger.info(f"[{account_name}] 报告发送成功")
                    else:
                        logger.error(f"[{account_name}] 报告发送失败")

                except Exception as e:
                    logger.error(f"[{account_name}] 发送报告失败: {e}")

            # 3. 如果有多个账户，发送汇总报告
            if len(all_metrics) > 1:
                await self._send_summary_report(all_metrics)

            return True

        except Exception as e:
            logger.error(f"发送报告失败: {e}")
            return False

    async def _send_summary_report(self, all_metrics: list) -> bool:
        """
        发送多账户汇总报告

        Args:
            all_metrics: [(account_name, metrics, df), ...]
        """
        try:
            # 计算汇总数据
            total_equity = sum(m.current_equity for _, m, _ in all_metrics)
            total_jlp_value = sum(m.jlp_value for _, m, _ in all_metrics)
            total_unrealized = sum(m.unrealized_pnl for _, m, _ in all_metrics)
            total_today_pnl = sum(m.today_pnl.pnl for _, m, _ in all_metrics)
            total_week_pnl = sum(m.week_pnl.pnl for _, m, _ in all_metrics)
            total_month_pnl = sum(m.month_pnl.pnl for _, m, _ in all_metrics)

            # 计算百分比
            today_pct = total_today_pnl / total_equity * 100 if total_equity > 0 else 0
            week_pct = total_week_pnl / total_equity * 100 if total_equity > 0 else 0
            month_pct = total_month_pnl / total_equity * 100 if total_equity > 0 else 0

            # 构建汇总报告
            summary = f"""📊 **JLP 中性套利 - 多账户汇总**

💰 **总净值**: <font color="info">${total_equity:,.2f}</font>

📈 **汇总收益**
今日: {"+" if total_today_pnl >= 0 else ""}${total_today_pnl:,.2f} ({today_pct:+.2f}%)
本周: {"+" if total_week_pnl >= 0 else ""}${total_week_pnl:,.2f} ({week_pct:+.2f}%)
本月: {"+" if total_month_pnl >= 0 else ""}${total_month_pnl:,.2f} ({month_pct:+.2f}%)

📋 **账户明细**"""

            for account_name, metrics, _ in all_metrics:
                pnl_icon = "🟢" if metrics.today_pnl.pnl >= 0 else "🔴"
                summary += f"""
{pnl_icon} **{account_name}**: ${metrics.current_equity:,.2f} (今日 {metrics.today_pnl.pnl:+.2f})"""

            summary += f"""

📊 **汇总详情**
JLP 总价值: ${total_jlp_value:,.2f}
未实现盈亏: ${total_unrealized:,.2f}
账户数量: {len(all_metrics)}
"""

            await self.notifier.send_markdown(summary)
            logger.info("多账户汇总报告发送成功")
            return True

        except Exception as e:
            logger.error(f"发送汇总报告失败: {e}")
            return False

    async def run_daemon(self):
        """
        后台运行模式

        - 每 N 分钟采集一次数据
        - 每 M 分钟发送一次报告
        """
        logger.info("=== 启动净值报告服务 (后台模式 - 多账户) ===")
        logger.info(f"采集间隔: {self.collect_interval} 分钟")
        logger.info(f"报告间隔: {self.report_interval} 分钟")

        await self._init_clients()
        logger.info(f"监控账户: {list(self.collectors.keys())}")

        last_report_time = None  # 上次发送报告的时间
        collect_count = 0  # 采集计数

        while True:
            try:
                now = datetime.now()

                # 1. 采集所有账户数据
                await self.collect_once()
                collect_count += 1

                # 2. 检查是否到报告时间（每 report_interval 分钟发送一次）
                should_report = False
                if last_report_time is None:
                    # 首次运行，立即发送一次报告
                    should_report = True
                else:
                    elapsed = (now - last_report_time).total_seconds() / 60
                    if elapsed >= self.report_interval:
                        should_report = True

                if should_report:
                    logger.info(f"发送定时报告 (已采集 {collect_count} 次, {len(self.collectors)} 个账户)")
                    await self.send_report(with_charts=True)
                    last_report_time = now

                # 3. 更新每日汇总（每天 0 点）
                if now.hour == 0 and now.minute < self.collect_interval:
                    self.storage.update_daily_summary()

                # 等待下次采集
                await asyncio.sleep(self.collect_interval * 60)

            except Exception as e:
                logger.error(f"运行异常: {e}")
                await asyncio.sleep(60)  # 出错后等待 1 分钟重试


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="AsterDex 净值统计报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        type=str,
        default=str(PROJECT_ROOT / "config" / "accounts.json"),
        help="配置文件路径 (默认: config/accounts.json)",
    )

    parser.add_argument(
        "--daemon",
        action="store_true",
        help="后台运行模式（定时采集+推送）",
    )

    parser.add_argument(
        "--report-now",
        action="store_true",
        help="立即发送报告",
    )

    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="仅采集数据不推送",
    )

    parser.add_argument(
        "--no-charts",
        action="store_true",
        help="发送报告时不包含图表",
    )

    args = parser.parse_args()

    config_path = Path(args.config)
    reporter = EquityReporter(config_path)

    if args.daemon:
        # 后台模式
        asyncio.run(reporter.run_daemon())

    elif args.report_now:
        # 立即发送报告
        asyncio.run(reporter.send_report(with_charts=not args.no_charts))

    elif args.collect_only:
        # 仅采集
        asyncio.run(reporter.collect_once())

    else:
        # 默认：采集一次 + 发送报告
        asyncio.run(reporter.send_report(with_charts=not args.no_charts))


if __name__ == "__main__":
    main()
