"""
企业微信通知模块
"""

import logging
import httpx
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class WeChatNotifier:
    """企业微信机器人通知器"""

    def __init__(self, webhook_url: str, enabled: bool = True):
        """
        初始化通知器

        Args:
            webhook_url: 企业微信 Webhook URL
            enabled: 是否启用通知
        """
        self.webhook_url = webhook_url
        self.enabled = enabled

    async def send(
        self,
        title: str,
        content: str,
        msg_type: MessageType = MessageType.INFO,
        mentioned_list: Optional[list] = None,
    ) -> bool:
        """
        发送 Markdown 消息

        Args:
            title: 消息标题
            content: 消息内容
            msg_type: 消息类型
            mentioned_list: @用户列表

        Returns:
            bool: 是否发送成功
        """
        if not self.enabled:
            logger.debug(f"通知已禁用，跳过发送: {title}")
            return True

        # 根据类型添加图标
        icon_map = {
            MessageType.INFO: "ℹ️",
            MessageType.WARNING: "⚠️",
            MessageType.ERROR: "❌",
            MessageType.SUCCESS: "✅",
        }
        icon = icon_map.get(msg_type, "")

        # 构造 Markdown 消息
        markdown_content = f"### {icon} {title}\n\n{content}"

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": markdown_content,
            }
        }

        if mentioned_list:
            payload["markdown"]["mentioned_list"] = mentioned_list

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json=payload)

                if response.status_code == 200:
                    result = response.json()
                    if result.get("errcode") == 0:
                        logger.debug(f"通知发送成功: {title}")
                        return True
                    else:
                        logger.error(f"通知发送失败: {result}")
                        return False
                else:
                    logger.error(f"通知发送失败: HTTP {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"通知发送异常: {e}")
            return False

    async def send_text(self, content: str) -> bool:
        """
        发送纯文本消息

        Args:
            content: 消息内容

        Returns:
            bool: 是否发送成功
        """
        if not self.enabled:
            return True

        payload = {
            "msgtype": "text",
            "text": {
                "content": content,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                return response.status_code == 200
        except Exception as e:
            logger.error(f"通知发送异常: {e}")
            return False

    # ==================== 便捷方法 ====================

    async def notify_startup(self, account_name: str, jlp_amount: float):
        """启动通知"""
        content = f"""
**账户**: {account_name}
**JLP 数量**: {jlp_amount:.4f}
**状态**: 策略启动成功

对冲机器人已开始运行，将每10分钟自动调仓。
        """
        await self.send("JLP 对冲策略启动", content, MessageType.SUCCESS)

    async def notify_rebalance(
        self,
        account_name: str,
        adjustments: dict,
        total_value: float,
    ):
        """调仓通知"""
        adj_str = ""
        for symbol, delta in adjustments.items():
            direction = "加仓" if delta > 0 else "减仓"
            adj_str += f"- **{symbol}**: {direction} {abs(delta):.6f}\n"

        content = f"""
**账户**: {account_name}
**调整仓位**:
{adj_str}
**对冲总价值**: ${total_value:,.2f}
        """
        await self.send("仓位调整", content, MessageType.INFO)

    async def notify_error(self, account_name: str, error: str):
        """错误通知"""
        content = f"""
**账户**: {account_name}
**错误信息**: {error}

请检查系统状态！
        """
        await self.send("系统错误", content, MessageType.ERROR, mentioned_list=["@all"])

    async def notify_risk_alert(
        self,
        account_name: str,
        alert_type: str,
        details: str,
    ):
        """风险告警"""
        content = f"""
**账户**: {account_name}
**告警类型**: {alert_type}
**详情**: {details}

请及时处理！
        """
        await self.send("风险告警", content, MessageType.WARNING, mentioned_list=["@all"])

    async def notify_daily_summary(
        self,
        account_name: str,
        jlp_amount: float,
        jlp_value: float,
        hedge_value: float,
        pnl: float,
        funding_earned: float,
    ):
        """每日汇总"""
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        content = f"""
**账户**: {account_name}

**持仓情况**:
- JLP 数量: {jlp_amount:.4f}
- JLP 价值: ${jlp_value:,.2f}
- 对冲价值: ${hedge_value:,.2f}

**收益情况** {pnl_emoji}:
- 今日盈亏: ${pnl:,.2f}
- 资金费收入: ${funding_earned:,.2f}
        """
        await self.send("每日汇总", content, MessageType.INFO)
