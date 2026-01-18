"""
配置同步模块

从云端同步配置到本地
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
from cloud.client import CloudClient

logger = logging.getLogger(__name__)


class ConfigSync:
    """配置同步器"""
    
    def __init__(self, cloud_client: CloudClient, sync_interval: int = 300):
        self.client = cloud_client
        self.sync_interval = sync_interval  # 同步间隔（秒）
        self._running = False
        self._background_task: Optional[asyncio.Task] = None
        self._last_sync: Optional[datetime] = None
        
        # 当前配置
        self.strategy_config: Dict[str, Any] = {}
        self.notification_config: Dict[str, Any] = {}
        self.preferences: Dict[str, Any] = {}
        
        # 配置变更回调
        self._on_config_change: Optional[Callable[[Dict[str, Any]], None]] = None
    
    def set_on_config_change(self, callback: Callable[[Dict[str, Any]], None]):
        """设置配置变更回调函数"""
        self._on_config_change = callback
    
    async def sync(self) -> bool:
        """
        从云端同步配置
        
        Returns:
            是否同步成功
        """
        try:
            config = await self.client.get_config()
            
            if not config:
                logger.warning("云端配置为空")
                return False
            
            # 检查配置是否有变化
            old_config = {
                "strategy": self.strategy_config,
                "notification": self.notification_config,
                "preferences": self.preferences,
            }
            
            # 更新配置
            self.strategy_config = config.get("strategy", {})
            self.notification_config = config.get("notification", {})
            self.preferences = config.get("preferences", {})
            
            self._last_sync = datetime.now()
            
            # 检查是否有变化
            new_config = {
                "strategy": self.strategy_config,
                "notification": self.notification_config,
                "preferences": self.preferences,
            }
            
            if old_config != new_config and self._on_config_change:
                logger.info("检测到配置变更，触发回调")
                self._on_config_change(new_config)
            
            logger.debug("配置同步成功")
            return True
            
        except Exception as e:
            logger.error(f"配置同步异常: {e}")
            return False
    
    async def start_background_sync(self):
        """启动后台同步任务"""
        self._running = True
        
        # 先执行一次同步
        await self.sync()
        
        # 启动后台任务
        self._background_task = asyncio.create_task(self._background_sync_loop())
        logger.info(f"配置同步任务已启动 (间隔: {self.sync_interval}s)")
    
    async def stop_background_sync(self):
        """停止后台同步任务"""
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
        logger.info("配置同步任务已停止")
    
    async def _background_sync_loop(self):
        """后台同步循环"""
        while self._running:
            try:
                await asyncio.sleep(self.sync_interval)
                await self.sync()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"配置同步异常: {e}")
                await asyncio.sleep(60)
    
    # ========== 配置获取接口 ==========
    
    def get_rebalance_threshold(self) -> float:
        """获取调仓阈值"""
        return float(self.strategy_config.get("rebalanceThreshold", "0.02"))
    
    def get_rebalance_interval(self) -> int:
        """获取调仓间隔（秒）"""
        return int(self.strategy_config.get("rebalanceInterval", 300))
    
    def get_leverage(self) -> int:
        """获取杠杆倍数"""
        return int(self.strategy_config.get("leverage", 1))
    
    def is_maker_order_enabled(self) -> bool:
        """是否启用 Maker 订单"""
        return self.strategy_config.get("useMakerOrder", True)
    
    def get_order_timeout(self) -> int:
        """获取订单超时时间（秒）"""
        return int(self.strategy_config.get("orderTimeout", 60))
    
    def is_split_order_enabled(self) -> bool:
        """是否启用拆单"""
        return self.strategy_config.get("splitOrderEnabled", True)
    
    def get_split_order_threshold(self) -> float:
        """获取拆单阈值（USD）"""
        return float(self.strategy_config.get("splitOrderThreshold", "1500"))
    
    def is_telegram_enabled(self) -> bool:
        """是否启用 Telegram 通知"""
        return self.notification_config.get("telegramEnabled", False)
    
    def get_telegram_config(self) -> Dict[str, str]:
        """获取 Telegram 配置"""
        return {
            "bot_token": self.notification_config.get("telegramBotToken", ""),
            "chat_id": self.notification_config.get("telegramChatId", ""),
        }
    
    def is_wecom_enabled(self) -> bool:
        """是否启用企业微信通知"""
        return self.notification_config.get("wecomEnabled", False)
    
    def get_wecom_webhook(self) -> str:
        """获取企业微信 Webhook"""
        return self.notification_config.get("wecomWebhook", "")
    
    def should_notify_on_profit(self) -> bool:
        """盈利时是否通知"""
        return self.preferences.get("notifyOnProfit", True)
    
    def should_notify_on_loss(self) -> bool:
        """亏损时是否通知"""
        return self.preferences.get("notifyOnLoss", True)
    
    def should_notify_on_rebalance(self) -> bool:
        """调仓时是否通知"""
        return self.preferences.get("notifyOnRebalance", False)
    
    def should_notify_on_alert(self) -> bool:
        """告警时是否通知"""
        return self.preferences.get("notifyOnAlert", True)
    
    def is_daily_report_enabled(self) -> bool:
        """是否启用每日报告"""
        return self.preferences.get("dailyReport", True)
    
    def get_daily_report_time(self) -> str:
        """获取每日报告时间"""
        return self.preferences.get("dailyReportTime", "20:00")
    
    def get_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        return {
            "running": self._running,
            "sync_interval": self.sync_interval,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "strategy_config": self.strategy_config,
            "notification_config": {
                "telegram_enabled": self.is_telegram_enabled(),
                "wecom_enabled": self.is_wecom_enabled(),
            },
            "preferences": self.preferences,
        }
