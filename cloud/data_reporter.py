"""
数据上报模块

定期上报净值、订单、告警等数据到云端
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import deque
from cloud.client import CloudClient

logger = logging.getLogger(__name__)


class DataReporter:
    """数据上报器"""
    
    def __init__(self, cloud_client: CloudClient, report_interval: int = 300):
        self.client = cloud_client
        self.report_interval = report_interval  # 上报间隔（秒）
        self._running = False
        self._background_task: Optional[asyncio.Task] = None
        
        # 数据缓存队列
        self._equity_data: Optional[Dict[str, Any]] = None
        self._order_queue: deque = deque(maxlen=100)  # 最多缓存 100 条订单
        self._alert_queue: deque = deque(maxlen=50)   # 最多缓存 50 条告警
        self._rebalance_queue: deque = deque(maxlen=50)  # 最多缓存 50 条调仓
    
    # ========== 数据收集接口 ==========
    
    def update_equity(
        self,
        jlp_amount: float,
        jlp_price: float,
        jlp_value_usd: float,
        total_equity_usd: float,
        unrealized_pnl: float = 0,
        margin_ratio: float = 0,
        hedge_ratio: float = 0,
        positions: Optional[Dict[str, Any]] = None,
    ):
        """更新净值数据（待上报）"""
        self._equity_data = {
            "jlp_amount": jlp_amount,
            "jlp_price": jlp_price,
            "jlp_value_usd": jlp_value_usd,
            "total_equity_usd": total_equity_usd,
            "unrealized_pnl": unrealized_pnl,
            "margin_ratio": margin_ratio,
            "hedge_ratio": hedge_ratio,
            "positions": positions or {},
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    
    def add_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        status: str,
        client_order_id: Optional[str] = None,
        price: Optional[float] = None,
        filled_amount: Optional[float] = None,
        avg_price: Optional[float] = None,
        fee: Optional[float] = None,
        fee_asset: Optional[str] = None,
        error_message: Optional[str] = None,
        rebalance_id: Optional[str] = None,
        order_time: Optional[datetime] = None,
        update_time: Optional[datetime] = None,
    ):
        """添加订单记录（待上报）"""
        self._order_queue.append({
            "order_id": order_id,
            "client_order_id": client_order_id,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "amount": amount,
            "price": price,
            "filled_amount": filled_amount,
            "avg_price": avg_price,
            "fee": fee,
            "fee_asset": fee_asset,
            "status": status,
            "error_message": error_message,
            "rebalance_id": rebalance_id,
            "order_time": order_time.isoformat() if order_time else None,
            "update_time": update_time.isoformat() if update_time else None,
        })
    
    def add_alert(
        self,
        alert_type: str,
        level: str,
        title: str,
        message: str,
    ):
        """添加告警记录（待上报）"""
        self._alert_queue.append({
            "alert_type": alert_type,
            "level": level,
            "title": title,
            "message": message,
        })
    
    def add_rebalance(
        self,
        symbol: str,
        side: str,
        amount: float,
        status: str,
        price: Optional[float] = None,
        before_position: Optional[float] = None,
        after_position: Optional[float] = None,
        reason: Optional[str] = None,
    ):
        """添加调仓记录（待上报）"""
        self._rebalance_queue.append({
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "status": status,
            "before_position": before_position,
            "after_position": after_position,
            "reason": reason,
        })
    
    # ========== 立即上报接口 ==========
    
    async def report_equity_now(self) -> bool:
        """立即上报净值数据"""
        if not self._equity_data:
            return True
        
        success = await self.client.report_equity(self._equity_data)
        if success:
            self._equity_data = None
        return success
    
    async def report_orders_now(self) -> bool:
        """立即上报所有待上报订单"""
        if not self._order_queue:
            return True
        
        orders = list(self._order_queue)
        result = await self.client.report_orders(orders)
        
        if result.get("success"):
            self._order_queue.clear()
            return True
        return False
    
    async def report_alerts_now(self) -> bool:
        """立即上报所有待上报告警"""
        if not self._alert_queue:
            return True
        
        success = True
        while self._alert_queue:
            alert = self._alert_queue.popleft()
            if not await self.client.report_alert(alert):
                # 上报失败，放回队列
                self._alert_queue.appendleft(alert)
                success = False
                break
        
        return success
    
    async def report_rebalances_now(self) -> bool:
        """立即上报所有待上报调仓"""
        if not self._rebalance_queue:
            return True
        
        success = True
        while self._rebalance_queue:
            rebalance = self._rebalance_queue.popleft()
            if not await self.client.report_rebalance(rebalance):
                # 上报失败，放回队列
                self._rebalance_queue.appendleft(rebalance)
                success = False
                break
        
        return success
    
    async def report_all_now(self) -> bool:
        """立即上报所有数据"""
        results = await asyncio.gather(
            self.report_equity_now(),
            self.report_orders_now(),
            self.report_alerts_now(),
            self.report_rebalances_now(),
            return_exceptions=True,
        )
        
        return all(r is True for r in results if not isinstance(r, Exception))
    
    # ========== 后台上报任务 ==========
    
    async def start_background_report(self):
        """启动后台上报任务"""
        self._running = True
        self._background_task = asyncio.create_task(self._background_report_loop())
        logger.info(f"数据上报任务已启动 (间隔: {self.report_interval}s)")
    
    async def stop_background_report(self):
        """停止后台上报任务"""
        self._running = False
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
        
        # 停止前上报所有数据
        await self.report_all_now()
        logger.info("数据上报任务已停止")
    
    async def _background_report_loop(self):
        """后台上报循环"""
        while self._running:
            try:
                await asyncio.sleep(self.report_interval)
                
                logger.debug("执行定期数据上报...")
                await self.report_all_now()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"数据上报异常: {e}")
                await asyncio.sleep(60)  # 出错后等待 1 分钟再试
    
    def get_status(self) -> Dict[str, Any]:
        """获取上报状态"""
        return {
            "running": self._running,
            "report_interval": self.report_interval,
            "pending_equity": self._equity_data is not None,
            "pending_orders": len(self._order_queue),
            "pending_alerts": len(self._alert_queue),
            "pending_rebalances": len(self._rebalance_queue),
        }
