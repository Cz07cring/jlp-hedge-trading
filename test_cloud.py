#!/usr/bin/env python3
"""
云端模块联调测试脚本

测试内容:
1. License 验证 API
2. 配置获取 API
3. 数据上报 API（净值、订单、告警、调仓）
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from cloud.client import CloudClient, CloudConfig
from cloud.license_manager import LicenseManager
from cloud.data_reporter import DataReporter
from cloud.config_sync import ConfigSync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_all():
    """运行所有测试"""
    logger.info("=" * 60)
    logger.info("  云端模块联调测试")
    logger.info("=" * 60)
    
    # 配置（指向本地 mksaas-template）
    cloud_config = CloudConfig(
        enabled=True,
        api_url="http://localhost:3001",
        license_key="JLP-OSCG-9LUY-QRMW-THOJ",  # 真实测试 License Key
        timeout=10.0,
    )
    
    client = CloudClient(cloud_config)
    
    # ========== 测试 1: License 验证 ==========
    logger.info("\n[1] 测试 License 验证 API...")
    license_mgr = LicenseManager(client)
    result = await license_mgr.verify()
    
    if result:
        logger.info(f"  ✓ License 验证成功")
        logger.info(f"    - 计划类型: {license_mgr.plan_type}")
        logger.info(f"    - 过期时间: {license_mgr.expires_at}")
    else:
        logger.warning("  ✗ License 验证失败（预期行为，因为使用测试 Key）")
        logger.info("    继续测试其他 API...")
    
    # ========== 测试 2: 获取配置 ==========
    logger.info("\n[2] 测试获取配置 API...")
    config_sync = ConfigSync(client)
    
    # 直接调用 API
    config = await client.get_config()
    if config:
        logger.info("  ✓ 配置获取成功（可能是默认配置）")
        logger.info(f"    - 策略配置: {config.get('strategy', {})}")
    else:
        logger.warning("  ✗ 配置获取失败（需要有效 License）")
    
    # ========== 测试 3: 数据上报 ==========
    logger.info("\n[3] 测试数据上报 API...")
    reporter = DataReporter(client)
    
    # 3.1 测试净值上报
    logger.info("  3.1 测试净值数据上报...")
    reporter.update_equity(
        jlp_amount=1000,
        jlp_price=4.5,
        jlp_value_usd=4500,
        total_equity_usd=5000,
        unrealized_pnl=100,
        margin_ratio=0.5,
        hedge_ratio=0.67,
        positions={
            "SOL": {"target": 15.0, "current": 14.8, "delta": -0.2},
            "ETH": {"target": 0.12, "current": 0.12, "delta": 0},
            "BTC": {"target": 0.008, "current": 0.008, "delta": 0},
        }
    )
    
    result = await reporter.report_equity_now()
    if result:
        logger.info("    ✓ 净值数据上报成功")
    else:
        logger.warning("    ✗ 净值数据上报失败（需要有效 License）")
    
    # 3.2 测试订单上报
    logger.info("  3.2 测试订单数据上报...")
    reporter.add_order(
        order_id="test_order_001",
        symbol="SOLUSDT",
        side="sell",
        order_type="maker",
        amount=1.5,
        status="filled",
        filled_amount=1.5,
        avg_price=140.5,
        fee=0.0015,
        fee_asset="USDT",
    )
    reporter.add_order(
        order_id="test_order_002",
        symbol="ETHUSDT",
        side="sell",
        order_type="market",
        amount=0.05,
        status="filled",
        filled_amount=0.05,
        avg_price=3250.0,
    )
    
    result = await reporter.report_orders_now()
    if result:
        logger.info("    ✓ 订单数据上报成功")
    else:
        logger.warning("    ✗ 订单数据上报失败（需要有效 License）")
    
    # 3.3 测试告警上报
    logger.info("  3.3 测试告警上报...")
    reporter.add_alert(
        alert_type="margin_low",
        level="warning",
        title="保证金率较低",
        message="当前保证金率 45%，建议关注",
    )
    
    result = await reporter.report_alerts_now()
    if result:
        logger.info("    ✓ 告警上报成功")
    else:
        logger.warning("    ✗ 告警上报失败（需要有效 License）")
    
    # 3.4 测试调仓记录上报
    logger.info("  3.4 测试调仓记录上报...")
    reporter.add_rebalance(
        symbol="SOLUSDT",
        side="sell",
        amount=0.5,
        status="success",
        price=140.5,
        before_position=15.0,
        after_position=14.5,
        reason="定期调仓",
    )
    
    result = await reporter.report_rebalances_now()
    if result:
        logger.info("    ✓ 调仓记录上报成功")
    else:
        logger.warning("    ✗ 调仓记录上报失败（需要有效 License）")
    
    # ========== 测试 4: 直接调用 API 端点 ==========
    logger.info("\n[4] 直接测试 API 端点...")
    
    # 4.1 测试 verify-license 端点
    import httpx
    # 禁用代理
    async with httpx.AsyncClient(timeout=10.0, proxy=None) as http:
        # 测试 /api/executor/verify-license
        logger.info("  4.1 测试 /api/executor/verify-license...")
        try:
            resp = await http.post(
                "http://localhost:3001/api/executor/verify-license",
                json={
                    "licenseKey": "JLP-TEST-1234-5678-ABCD",
                    "deviceId": "test_device_001",
                    "deviceName": "Test Machine",
                }
            )
            logger.info(f"    状态码: {resp.status_code}")
            logger.info(f"    响应: {resp.json()}")
        except Exception as e:
            logger.error(f"    请求失败: {e}")
        
        # 测试 /api/hedge/verify
        logger.info("  4.2 测试 /api/hedge/verify...")
        try:
            resp = await http.post(
                "http://localhost:3001/api/hedge/verify",
                json={
                    "license_key": "JLP-TEST-1234-5678-ABCD",
                    "device_id": "test_device_001",
                    "device_name": "Test Machine",
                }
            )
            logger.info(f"    状态码: {resp.status_code}")
            logger.info(f"    响应: {resp.json()}")
        except Exception as e:
            logger.error(f"    请求失败: {e}")
        
        # 测试 /api/executor/get-config（带 License Header）
        logger.info("  4.3 测试 /api/executor/get-config...")
        try:
            resp = await http.get(
                "http://localhost:3001/api/executor/get-config",
                headers={"X-License-Key": "JLP-TEST-1234-5678-ABCD"}
            )
            logger.info(f"    状态码: {resp.status_code}")
            data = resp.json()
            logger.info(f"    响应: success={data.get('success')}, message={data.get('message')}")
        except Exception as e:
            logger.error(f"    请求失败: {e}")
    
    await client.close()
    
    logger.info("\n" + "=" * 60)
    logger.info("  联调测试完成")
    logger.info("=" * 60)
    logger.info("\n注意: 部分测试失败是预期的，因为使用了无效的测试 License Key")
    logger.info("在实际使用时，需要在 SaaS 平台创建有效的 License")


if __name__ == "__main__":
    asyncio.run(test_all())
