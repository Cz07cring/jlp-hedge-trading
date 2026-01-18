"""
云端 API 客户端

与 SaaS 后端通信，提供 License 验证、数据上报等功能
"""

import os
import hashlib
import platform
import uuid
import logging
import httpx
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CloudConfig:
    """云端配置"""
    enabled: bool = True
    api_url: str = "https://jlp.finance"  # SaaS 平台 URL
    license_key: str = ""
    report_interval: int = 300  # 上报间隔（秒）
    timeout: float = 30.0
    
    @classmethod
    def from_env(cls) -> "CloudConfig":
        """从环境变量加载配置"""
        return cls(
            enabled=os.getenv("CLOUD_ENABLED", "true").lower() == "true",
            api_url=os.getenv("CLOUD_API_URL", "https://jlp.finance"),
            license_key=os.getenv("LICENSE_KEY", ""),
            report_interval=int(os.getenv("REPORT_INTERVAL", "300")),
            timeout=float(os.getenv("CLOUD_TIMEOUT", "30.0")),
        )


class CloudClient:
    """云端 API 客户端"""
    
    def __init__(self, config: CloudConfig, account_name: str = "default"):
        self.config = config
        self.account_name = account_name  # 账户名（用于服务端限制）
        self.device_id = self._get_device_id()
        self.device_name = platform.node()
        self._http_client: Optional[httpx.AsyncClient] = None
    
    def set_account_name(self, name: str):
        """设置当前账户名"""
        self.account_name = name
    
    def _get_device_id(self) -> str:
        """生成设备唯一标识"""
        machine_info = f"{platform.node()}-{platform.machine()}-{uuid.getnode()}"
        return hashlib.sha256(machine_info.encode()).hexdigest()[:32]
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=self.config.timeout,
                proxy=None,  # 禁用代理
                headers={
                    "Content-Type": "application/json",
                    "X-License-Key": self.config.license_key,
                    "User-Agent": "JLP-Hedge-Trading/1.0",
                }
            )
        return self._http_client
    
    async def close(self):
        """关闭客户端"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None
    
    # ========== License 相关 API ==========
    
    async def verify_license(self) -> Dict[str, Any]:
        """
        验证 License
        
        Returns:
            验证结果: {
                "valid": bool,
                "user_id": str,
                "plan_type": str,
                "expires_at": str | None,
                "config": dict,  # 策略配置
            }
        """
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self.config.api_url}/api/hedge/verify",
                json={
                    "license_key": self.config.license_key,
                    "device_id": self.device_id,
                    "device_name": self.device_name,
                }
            )
            
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"License 验证失败: HTTP {resp.status_code}")
                return {"valid": False, "error": f"HTTP {resp.status_code}"}
                
        except Exception as e:
            logger.error(f"License 验证异常: {e}")
            return {"valid": False, "error": str(e)}
    
    # ========== 数据上报 API ==========
    
    async def report_equity(self, data: Dict[str, Any]) -> bool:
        """
        上报净值数据
        
        Args:
            data: {
                "jlp_amount": float,
                "jlp_price": float,
                "jlp_value_usd": float,
                "total_equity_usd": float,
                "unrealized_pnl": float,
                "margin_ratio": float,
                "hedge_ratio": float,
                "positions": dict,
            }
        """
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self.config.api_url}/api/hedge/report",
                json={
                    "type": "equity",
                    "data": data,
                    "account_name": self.account_name,  # 服务端账户限制
                }
            )
            
            if resp.status_code == 200:
                logger.debug("净值数据上报成功")
                return True
            elif resp.status_code == 403:
                # 账户数量限制
                result = resp.json()
                if result.get("error_code") == "ACCOUNT_LIMIT_EXCEEDED":
                    logger.error(f"账户数量超限: {result.get('error')}")
                    logger.error("请升级到终身版以支持多账户")
                return False
            else:
                logger.warning(f"净值数据上报失败: HTTP {resp.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"净值数据上报异常: {e}")
            return False
    
    async def report_rebalance(self, data: Dict[str, Any]) -> bool:
        """
        上报调仓记录
        
        Args:
            data: {
                "symbol": str,
                "side": str,
                "amount": float,
                "price": float,
                "status": str,
                "before_position": float,
                "after_position": float,
                "reason": str,
            }
        """
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self.config.api_url}/api/hedge/report",
                json={
                    "type": "rebalance",
                    "data": data,
                    "account_name": self.account_name,
                }
            )
            
            if resp.status_code == 200:
                logger.debug(f"调仓记录上报成功: {data.get('symbol')}")
                return True
            elif resp.status_code == 403:
                logger.error("账户数量超限，调仓记录上报被拒绝")
                return False
            else:
                logger.warning(f"调仓记录上报失败: HTTP {resp.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"调仓记录上报异常: {e}")
            return False
    
    async def report_alert(self, data: Dict[str, Any]) -> bool:
        """
        上报告警信息
        
        Args:
            data: {
                "alert_type": str,  # margin_low, funding_high, execution_failed
                "level": str,       # info, warning, critical
                "title": str,
                "message": str,
            }
        """
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self.config.api_url}/api/hedge/report",
                json={
                    "type": "alert",
                    "data": data,
                    "account_name": self.account_name,
                }
            )
            
            if resp.status_code == 200:
                logger.debug(f"告警上报成功: {data.get('title')}")
                return True
            elif resp.status_code == 403:
                logger.error("账户数量超限，告警上报被拒绝")
                return False
            else:
                logger.warning(f"告警上报失败: HTTP {resp.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"告警上报异常: {e}")
            return False
    
    async def report_orders(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量上报订单信息
        
        Args:
            orders: 订单列表，每个订单包含:
                {
                    "order_id": str,
                    "client_order_id": str,
                    "symbol": str,
                    "side": str,
                    "order_type": str,
                    "amount": float,
                    "price": float,
                    "filled_amount": float,
                    "avg_price": float,
                    "fee": float,
                    "fee_asset": str,
                    "status": str,
                    "error_message": str,
                    "rebalance_id": str,
                    "order_time": str,
                    "update_time": str,
                }
        
        Returns:
            {"success": bool, "data": {"received": int, "saved": int}}
        """
        try:
            client = await self._get_client()
            resp = await client.post(
                f"{self.config.api_url}/api/executor/report-order",
                json={"orders": orders}
            )
            
            if resp.status_code == 200:
                result = resp.json()
                logger.debug(f"订单上报成功: {result.get('data', {}).get('saved', 0)} 条")
                return result
            else:
                logger.warning(f"订单上报失败: HTTP {resp.status_code}")
                return {"success": False, "error": f"HTTP {resp.status_code}"}
                
        except Exception as e:
            logger.error(f"订单上报异常: {e}")
            return {"success": False, "error": str(e)}
    
    # ========== 配置同步 API ==========
    
    async def get_config(self) -> Dict[str, Any]:
        """
        获取云端配置
        
        Returns:
            配置信息: {
                "strategy": {...},
                "notification": {...},
                "preferences": {...},
            }
        """
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.config.api_url}/api/executor/get-config"
            )
            
            if resp.status_code == 200:
                result = resp.json()
                if result.get("success"):
                    logger.info("云端配置获取成功")
                    return result.get("data", {})
                else:
                    logger.warning(f"云端配置获取失败: {result.get('message')}")
                    return {}
            else:
                logger.warning(f"云端配置获取失败: HTTP {resp.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"云端配置获取异常: {e}")
            return {}
    
    # ========== 对冲计算 API ==========
    
    async def get_hedge_positions(self, jlp_amount: float) -> Dict[str, Any]:
        """
        调用 Hedge API 计算对冲仓位
        
        Args:
            jlp_amount: JLP 持有数量
            
        Returns:
            对冲仓位计算结果
        """
        # Hedge API 默认使用 api.jlp.finance
        hedge_api_url = os.getenv("HEDGE_API_URL", "https://api.jlp.finance")
        
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{hedge_api_url}/api/v1/hedge-positions",
                params={"jlp_amount": jlp_amount},
                headers={"X-License-Key": self.config.license_key},
            )
            
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 401:
                logger.error("Hedge API 调用失败: License Key 无效或未提供")
                return {"success": False, "error": "Invalid or missing License Key"}
            elif resp.status_code == 403:
                logger.error("Hedge API 调用失败: License 已过期或无权限")
                return {"success": False, "error": "License expired or no permission"}
            else:
                logger.error(f"对冲仓位计算失败: HTTP {resp.status_code}")
                return {"success": False, "error": f"HTTP {resp.status_code}"}
                
        except Exception as e:
            logger.error(f"对冲仓位计算异常: {e}")
            return {"success": False, "error": str(e)}
