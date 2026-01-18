"""
企业微信推送模块

发送报告消息和图表到企业微信群
"""

import logging
import httpx
from typing import Optional
from dataclasses import dataclass

from scripts.equity_reporter.calculator import ReportMetrics

logger = logging.getLogger(__name__)


@dataclass
class WeChatConfig:
    """企业微信配置"""
    webhook_url: str
    enabled: bool = True
    timeout: float = 30.0


class WeChatNotifier:
    """企业微信推送器"""

    def __init__(self, config: WeChatConfig):
        """
        初始化推送器

        Args:
            config: 企业微信配置
        """
        self.config = config

    async def send_text(self, content: str) -> bool:
        """
        发送文本消息

        Args:
            content: 消息内容

        Returns:
            bool: 是否成功
        """
        if not self.config.enabled:
            logger.warning("企业微信推送已禁用")
            return False

        payload = {
            "msgtype": "text",
            "text": {
                "content": content
            }
        }

        return await self._send(payload)

    async def send_markdown(self, content: str) -> bool:
        """
        发送 Markdown 消息

        Args:
            content: Markdown 内容

        Returns:
            bool: 是否成功
        """
        if not self.config.enabled:
            logger.warning("企业微信推送已禁用")
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }

        return await self._send(payload)

    async def send_image(self, image_base64: str, md5: str) -> bool:
        """
        发送图片消息

        Args:
            image_base64: 图片 base64 编码
            md5: 图片 MD5

        Returns:
            bool: 是否成功
        """
        if not self.config.enabled:
            logger.warning("企业微信推送已禁用")
            return False

        payload = {
            "msgtype": "image",
            "image": {
                "base64": image_base64,
                "md5": md5
            }
        }

        return await self._send(payload)

    async def _send(self, payload: dict) -> bool:
        """
        发送消息到企业微信

        Args:
            payload: 消息体

        Returns:
            bool: 是否成功
        """
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                resp = await client.post(
                    self.config.webhook_url,
                    json=payload,
                )

                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("errcode") == 0:
                        logger.info("消息发送成功")
                        return True
                    else:
                        logger.error(f"发送失败: {result}")
                        return False
                else:
                    logger.error(f"HTTP 错误: {resp.status_code}")
                    return False

        except Exception as e:
            logger.error(f"发送消息异常: {e}")
            return False

    def format_report(self, metrics: ReportMetrics, account_name: str = "") -> str:
        """
        格式化报告为 Markdown

        Args:
            metrics: 报告指标
            account_name: 账户名称

        Returns:
            str: Markdown 格式的报告
        """
        # 盈亏颜色标记
        def pnl_color(pnl: float) -> str:
            if pnl > 0:
                return f"<font color=\"info\">+${pnl:,.2f}</font>"
            elif pnl < 0:
                return f"<font color=\"warning\">${pnl:,.2f}</font>"
            else:
                return f"${pnl:,.2f}"

        def pct_color(pct: float) -> str:
            if pct > 0:
                return f"<font color=\"info\">+{pct:.2%}</font>"
            elif pct < 0:
                return f"<font color=\"warning\">{pct:.2%}</font>"
            else:
                return f"{pct:.2%}"

        # 未实现盈亏颜色
        def unrealized_color(pnl: float) -> str:
            if pnl > 0:
                return f"<font color=\"info\">+${pnl:,.2f}</font>"
            elif pnl < 0:
                return f"<font color=\"warning\">${pnl:,.2f}</font>"
            else:
                return f"${pnl:,.2f}"

        # 构建报告 (企业微信手机端兼容格式)
        title = f"📊 **JLP 中性套利报告 - {account_name}**" if account_name else "📊 **JLP 中性套利报告**"
        report = f"""{title}

💰 **账户净值**: <font color="info">${metrics.current_equity:,.2f}</font>

📈 **收益统计**
今日: {pnl_color(metrics.today_pnl.pnl)} ({pct_color(metrics.today_pnl.pnl_pct)})
本周: {pnl_color(metrics.week_pnl.pnl)} ({pct_color(metrics.week_pnl.pnl_pct)})
本月: {pnl_color(metrics.month_pnl.pnl)} ({pct_color(metrics.month_pnl.pnl_pct)})

📊 **持仓信息**
SOL: {metrics.sol_pos:,.4f} | 费率 {metrics.sol_funding:.4%}
ETH: {metrics.eth_pos:,.4f} | 费率 {metrics.eth_funding:.4%}
BTC: {metrics.btc_pos:,.6f} | 费率 {metrics.btc_funding:.4%}

📋 **账户详情**
JLP: {metrics.jlp_amount:,.2f} × ${metrics.jlp_price:.4f} = ${metrics.jlp_value:,.2f}
可用余额: ${metrics.available_balance:,.2f}
未实现盈亏: {unrealized_color(metrics.unrealized_pnl)}
保证金率: {metrics.margin_ratio:.2%}
对冲比例: {metrics.hedge_ratio:.2%}
"""
        return report

    async def send_report(
        self,
        metrics: ReportMetrics,
        chart_images: Optional[list] = None,
        account_name: str = "",
    ) -> bool:
        """
        发送完整报告（文字 + 图表）

        Args:
            metrics: 报告指标
            chart_images: 图表图片列表 [(base64, md5), ...]
            account_name: 账户名称

        Returns:
            bool: 是否成功
        """
        import hashlib
        import base64

        # 1. 发送 Markdown 报告
        report_md = self.format_report(metrics, account_name)
        success = await self.send_markdown(report_md)

        if not success:
            logger.error("发送报告文本失败")
            return False

        # 2. 发送图表
        if chart_images:
            for i, image_bytes in enumerate(chart_images):
                try:
                    # 计算 MD5 和 Base64
                    md5_hash = hashlib.md5(image_bytes).hexdigest()
                    b64_data = base64.b64encode(image_bytes).decode('utf-8')

                    img_success = await self.send_image(b64_data, md5_hash)
                    if not img_success:
                        logger.error(f"发送图表 {i+1} 失败")
                except Exception as e:
                    logger.error(f"处理图表 {i+1} 异常: {e}")

        return True
