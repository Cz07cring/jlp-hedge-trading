"""
数据采集模块

从 AsterDex 采集账户数据
"""

from __future__ import annotations

import json
import asyncio
import logging
from typing import Optional
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from clients.asterdex_client import AsterDexClient

logger = logging.getLogger(__name__)

# JLP 价格缓存文件
CACHE_DIR = Path(__file__).parent.parent.parent / "data"
JLP_PRICE_CACHE_FILE = CACHE_DIR / "jlp_price_cache.json"


@dataclass
class EquitySnapshot:
    """净值快照"""
    timestamp: datetime
    account: str
    equity: Decimal                 # 账户总权益 (totalWalletBalance)
    jlp_amount: Decimal             # JLP 数量
    jlp_price: Decimal              # JLP 单价
    jlp_value: Decimal              # JLP 价值 (USD) = 本金
    available_balance: Decimal      # 可用余额
    used_margin: Decimal            # 已用保证金
    unrealized_pnl: Decimal         # 未实现盈亏
    margin_ratio: float             # 保证金率
    hedge_ratio: float              # 对冲比例
    sol_pos: Decimal                # SOL 持仓
    eth_pos: Decimal                # ETH 持仓
    btc_pos: Decimal                # BTC 持仓
    sol_funding: float              # SOL 资金费率
    eth_funding: float              # ETH 资金费率
    btc_funding: float              # BTC 资金费率


class EquityCollector:
    """数据采集器"""

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # 秒

    def __init__(
        self,
        asterdex_client: AsterDexClient,
        account_name: str,
        hedge_api_url: str = "https://api.jlp.finance",
    ):
        """
        初始化采集器

        Args:
            asterdex_client: AsterDex 客户端
            account_name: 账户名称
            hedge_api_url: 对冲 API 地址
        """
        self.client = asterdex_client
        self.account_name = account_name
        self.hedge_api_url = hedge_api_url

    def _load_cached_jlp_price(self) -> tuple[Decimal, Optional[str]]:
        """
        加载缓存的 JLP 价格

        Returns:
            (price, updated_at): 价格和更新时间
        """
        try:
            if JLP_PRICE_CACHE_FILE.exists():
                with open(JLP_PRICE_CACHE_FILE, "r") as f:
                    data = json.load(f)
                    price = Decimal(str(data.get("price", "0")))
                    updated_at = data.get("updated_at")
                    return price, updated_at
        except Exception as e:
            logger.warning(f"加载价格缓存失败: {e}")
        return Decimal("0"), None

    def _save_jlp_price_cache(self, price: Decimal):
        """保存 JLP 价格到缓存"""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(JLP_PRICE_CACHE_FILE, "w") as f:
                json.dump({
                    "price": str(price),
                    "updated_at": datetime.now().isoformat()
                }, f)
            logger.debug(f"JLP 价格已缓存: ${price}")
        except Exception as e:
            logger.warning(f"保存价格缓存失败: {e}")

    async def _fetch_hedge_data_with_retry(self, jlp_amount: Decimal) -> tuple[Decimal, Decimal, bool]:
        """
        获取 JLP 价格和目标对冲价值（带重试和缓存）

        Args:
            jlp_amount: JLP 数量

        Returns:
            (price, target_hedge_value, from_cache): 价格、目标对冲价值、是否来自缓存
        """
        import httpx

        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"{self.hedge_api_url}/api/v1/hedge-positions",
                        params={"jlp_amount": float(jlp_amount)}
                    )

                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("success"):
                            hedge_data = data.get("data", {})
                            jlp_stats = hedge_data.get("jlp_stats", {})
                            price = Decimal(str(jlp_stats.get("virtual_price", "0")))

                            # 计算目标对冲总价值
                            hedge_positions = hedge_data.get("hedge_positions", {})
                            target_hedge_value = Decimal("0")
                            for pos in hedge_positions.values():
                                target_hedge_value += Decimal(str(pos.get("value_usd", "0")))

                            if price > 0:
                                self._save_jlp_price_cache(price)
                                return price, target_hedge_value, False
                    else:
                        last_error = f"HTTP {resp.status_code}"

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"获取对冲数据失败 (尝试 {attempt + 1}/{self.MAX_RETRIES}): {e}"
                )

            # 重试前等待
            if attempt < self.MAX_RETRIES - 1:
                await asyncio.sleep(self.RETRY_DELAY)

        # 所有重试失败，使用缓存
        cached_price, updated_at = self._load_cached_jlp_price()
        if cached_price > 0:
            logger.warning(f"使用缓存的 JLP 价格: ${cached_price} (缓存时间: {updated_at})")
            return cached_price, Decimal("0"), True

        logger.error(f"无法获取对冲数据: {last_error}，缓存也不可用")
        return Decimal("0"), Decimal("0"), False

    async def collect(self) -> EquitySnapshot:
        """
        采集当前账户数据

        Returns:
            EquitySnapshot: 净值快照
        """
        logger.info(f"[{self.account_name}] 开始采集数据...")

        # 1. 获取账户信息
        account = await self.client.get_account()

        total_initial_margin = Decimal(str(account.get("totalInitialMargin", "0")))
        available_balance = Decimal(str(account.get("availableBalance", "0")))
        total_maint_margin = Decimal(str(account.get("totalMaintMargin", "0")))
        total_unrealized_pnl = Decimal(str(account.get("totalUnrealizedProfit", "0")))

        # 2. 获取余额 (JLP)
        balances = await self.client.get_balance()
        jlp_amount = Decimal("0")
        jlp_price = Decimal("0")
        jlp_value = Decimal("0")
        target_hedge_value = Decimal("0")
        price_from_cache = False

        for balance in balances:
            if balance.asset.upper() == "JLP":
                jlp_amount = balance.balance
                break

        # 获取 JLP 价格和目标对冲价值（带重试和缓存）
        jlp_price, target_hedge_value, price_from_cache = await self._fetch_hedge_data_with_retry(jlp_amount)
        jlp_value = jlp_amount * jlp_price

        if price_from_cache:
            logger.info(f"JLP 价格(缓存): ${jlp_price:.4f}, JLP 价值: ${jlp_value:.2f}")
        else:
            logger.info(f"JLP 价格: ${jlp_price:.4f}, JLP 价值: ${jlp_value:.2f}, 目标对冲: ${target_hedge_value:.2f}")

        # 账户净值 = JLP价值 + USDT钱包余额 + 未实现盈亏
        # 反映账户真实净值
        usdt_wallet_balance = Decimal("0")
        assets = account.get("assets", [])
        for asset in assets:
            if asset.get("asset") == "USDT":
                usdt_wallet_balance = Decimal(str(asset.get("walletBalance", "0")))
                break

        # 账户净值 = JLP价值(USD) + USDT钱包余额 + 未实现盈亏
        equity = jlp_value + usdt_wallet_balance + total_unrealized_pnl
        logger.info(f"账户净值: JLP ${jlp_value:.2f} + USDT ${usdt_wallet_balance:.2f} + 未实现 ${total_unrealized_pnl:.2f} = ${equity:.2f}")

        # 保证金率 = 维持保证金 / 权益
        margin_ratio = float(total_maint_margin / equity) if equity > 0 else 0

        # 3. 获取持仓
        positions = await self.client.get_positions()

        sol_pos = Decimal("0")
        eth_pos = Decimal("0")
        btc_pos = Decimal("0")

        for pos in positions:
            if pos.symbol == "SOLUSDT":
                sol_pos = pos.quantity
            elif pos.symbol == "ETHUSDT":
                eth_pos = pos.quantity
            elif pos.symbol == "BTCUSDT":
                btc_pos = pos.quantity

        # 4. 获取资金费率
        sol_funding = 0.0
        eth_funding = 0.0
        btc_funding = 0.0

        try:
            for symbol, attr in [("SOLUSDT", "sol_funding"), ("ETHUSDT", "eth_funding"), ("BTCUSDT", "btc_funding")]:
                funding = await self.client.get_funding_rate(symbol)
                if attr == "sol_funding":
                    sol_funding = float(funding.funding_rate)
                elif attr == "eth_funding":
                    eth_funding = float(funding.funding_rate)
                elif attr == "btc_funding":
                    btc_funding = float(funding.funding_rate)
        except Exception as e:
            logger.warning(f"获取资金费率失败: {e}")

        # 5. 计算对冲覆盖率 = 实际持仓价值 / 目标对冲价值
        hedge_ratio = 0.0
        total_position_value = Decimal("0")
        for pos in positions:
            total_position_value += abs(pos.quantity) * pos.mark_price

        if target_hedge_value > 0:
            # 对冲覆盖率 = 实际对冲 / 目标对冲
            hedge_ratio = float(total_position_value / target_hedge_value)
            logger.info(f"对冲覆盖率: 实际 ${total_position_value:.2f} / 目标 ${target_hedge_value:.2f} = {hedge_ratio:.2%}")
        elif jlp_value > 0:
            # 降级：如果没有目标值，用 JLP 价值计算
            hedge_ratio = float(total_position_value / jlp_value)
            logger.info(f"对冲比例(降级): ${total_position_value:.2f} / ${jlp_value:.2f} = {hedge_ratio:.2%}")

        snapshot = EquitySnapshot(
            timestamp=datetime.now(),
            account=self.account_name,
            equity=equity,
            jlp_amount=jlp_amount,
            jlp_price=jlp_price,
            jlp_value=jlp_value,
            available_balance=available_balance,
            used_margin=total_initial_margin,
            unrealized_pnl=total_unrealized_pnl,
            margin_ratio=margin_ratio,
            hedge_ratio=hedge_ratio,
            sol_pos=sol_pos,
            eth_pos=eth_pos,
            btc_pos=btc_pos,
            sol_funding=sol_funding,
            eth_funding=eth_funding,
            btc_funding=btc_funding,
        )

        logger.info(
            f"[{self.account_name}] 采集完成: "
            f"权益=${equity:.2f}, JLP={jlp_amount:.2f}, 保证金率={margin_ratio:.2%}"
        )

        return snapshot
