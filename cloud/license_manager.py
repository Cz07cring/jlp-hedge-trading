"""
License 验证管理器

负责 License 验证和状态维护
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from cloud.client import CloudClient

logger = logging.getLogger(__name__)


class LicenseManager:
    """License 管理器"""
    
    # 计划类型账户限制
    PLAN_ACCOUNT_LIMITS = {
        "lifetime": 100,  # 终身版：支持多账户
        "pro": 1,         # 专业版（月付/年付）：单账户
        "free": 0,        # 免费版：不支持
    }
    
    def __init__(self, cloud_client: CloudClient):
        self.client = cloud_client
        self.is_valid = False
        self.user_id: Optional[str] = None
        self.plan_type: str = "unknown"
        self.max_accounts: int = 1  # 默认单账户
        self.expires_at: Optional[datetime] = None
        self.cloud_config: Dict[str, Any] = {}
        self._last_check: Optional[datetime] = None
        self._check_interval = timedelta(hours=1)  # 1小时检查一次
        self._background_task: Optional[asyncio.Task] = None
    
    async def verify(self) -> bool:
        """
        验证 License
        
        Returns:
            是否验证成功
        """
        try:
            result = await self.client.verify_license()
            
            if result.get("valid"):
                self.is_valid = True
                self.user_id = result.get("user_id")
                self.plan_type = result.get("plan_type", "unknown")
                self.max_accounts = result.get("max_accounts", self.PLAN_ACCOUNT_LIMITS.get(self.plan_type, 1))
                self.cloud_config = result.get("config", {})
                
                # 解析过期时间
                expires_at_str = result.get("expires_at")
                if expires_at_str:
                    self.expires_at = datetime.fromisoformat(
                        expires_at_str.replace("Z", "+00:00")
                    )
                
                self._last_check = datetime.now()
                
                logger.info(f"License 验证成功: {self.plan_type} 计划")
                if self.expires_at:
                    logger.info(f"有效期至: {self.expires_at}")
                
                return True
            else:
                self.is_valid = False
                error = result.get("error", "Unknown error")
                logger.error(f"License 验证失败: {error}")
                return False
                
        except Exception as e:
            logger.error(f"License 验证异常: {e}")
            self.is_valid = False
            return False
    
    def needs_refresh(self) -> bool:
        """检查是否需要刷新验证"""
        if not self._last_check:
            return True
        return datetime.now() - self._last_check > self._check_interval
    
    def is_expiring_soon(self, days: int = 7) -> bool:
        """检查 License 是否即将过期"""
        if not self.expires_at:
            return False
        return self.expires_at - datetime.now(self.expires_at.tzinfo) < timedelta(days=days)
    
    def get_remaining_days(self) -> Optional[int]:
        """获取剩余天数"""
        if not self.expires_at:
            return None
        delta = self.expires_at - datetime.now(self.expires_at.tzinfo)
        return max(0, delta.days)
    
    async def start_background_check(self):
        """启动后台验证任务"""
        self._background_task = asyncio.create_task(self._background_check_loop())
        logger.info("License 后台检查任务已启动")
    
    async def stop_background_check(self):
        """停止后台验证任务"""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
            logger.info("License 后台检查任务已停止")
    
    async def _background_check_loop(self):
        """后台验证循环"""
        while True:
            try:
                await asyncio.sleep(self._check_interval.total_seconds())
                
                if self.needs_refresh():
                    logger.debug("执行定期 License 验证...")
                    await self.verify()
                    
                    # 检查是否即将过期
                    if self.is_valid and self.is_expiring_soon(7):
                        remaining = self.get_remaining_days()
                        logger.warning(f"License 即将过期，剩余 {remaining} 天")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"License 后台检查异常: {e}")
                await asyncio.sleep(60)  # 出错后等待 1 分钟再试
    
    def get_status(self) -> Dict[str, Any]:
        """获取 License 状态"""
        return {
            "is_valid": self.is_valid,
            "user_id": self.user_id,
            "plan_type": self.plan_type,
            "max_accounts": self.max_accounts,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "remaining_days": self.get_remaining_days(),
            "last_check": self._last_check.isoformat() if self._last_check else None,
        }
    
    def can_use_accounts(self, account_count: int) -> bool:
        """检查是否可以使用指定数量的账户"""
        return self.is_valid and account_count <= self.max_accounts
    
    def get_max_accounts(self) -> int:
        """获取最大允许账户数"""
        return self.max_accounts
