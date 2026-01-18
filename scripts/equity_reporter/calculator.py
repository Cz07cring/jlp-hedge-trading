"""
指标计算模块

计算收益率、盈亏等指标

本金定义：JLP 数量 × JLP 价格 = JLP 价值
收益 = 账户净值 - 本金（JLP 价值）
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PnLMetrics:
    """盈亏指标"""
    pnl: float              # 绝对盈亏
    pnl_pct: float          # 盈亏百分比
    start_equity: float     # 起始权益
    end_equity: float       # 结束权益
    high_equity: float      # 最高权益
    low_equity: float       # 最低权益


@dataclass
class ReportMetrics:
    """报告指标汇总"""
    # 当前状态
    current_equity: float       # 账户净值
    jlp_amount: float           # JLP 数量
    jlp_price: float            # JLP 单价
    jlp_value: float            # JLP 价值 = 本金
    available_balance: float
    unrealized_pnl: float
    margin_ratio: float
    hedge_ratio: float

    # 持仓
    sol_pos: float
    eth_pos: float
    btc_pos: float

    # 资金费率
    sol_funding: float
    eth_funding: float
    btc_funding: float

    # 收益指标
    today_pnl: PnLMetrics
    week_pnl: PnLMetrics
    month_pnl: PnLMetrics
    total_pnl: PnLMetrics       # 累计盈亏 = 账户净值 - JLP价值

    # 年化收益率
    annualized_return: float

    # 运行天数（从首条历史数据开始）
    running_days: int


class EquityCalculator:
    """指标计算器"""

    def __init__(self):
        """初始化计算器"""
        pass

    def calc_pnl(
        self,
        df: pd.DataFrame,
        start_equity: Optional[float] = None,
    ) -> PnLMetrics:
        """
        计算盈亏指标

        Args:
            df: 历史数据 DataFrame
            start_equity: 起始权益（可选，默认使用第一条数据）

        Returns:
            PnLMetrics: 盈亏指标
        """
        if df.empty:
            return PnLMetrics(
                pnl=0, pnl_pct=0,
                start_equity=start_equity or 0,
                end_equity=start_equity or 0,
                high_equity=start_equity or 0,
                low_equity=start_equity or 0,
            )

        start = start_equity if start_equity is not None else float(df.iloc[0]['equity'])
        end = float(df.iloc[-1]['equity'])
        high = float(df['equity'].max())
        low = float(df['equity'].min())

        pnl = end - start
        pnl_pct = pnl / start if start > 0 else 0

        return PnLMetrics(
            pnl=pnl,
            pnl_pct=pnl_pct,
            start_equity=start,
            end_equity=end,
            high_equity=high,
            low_equity=low,
        )

    def calc_today_pnl(self, df: pd.DataFrame) -> PnLMetrics:
        """计算今日盈亏"""
        today = datetime.now().date()
        today_df = df[df['timestamp'].dt.date == today]
        return self.calc_pnl(today_df)

    def calc_week_pnl(self, df: pd.DataFrame) -> PnLMetrics:
        """计算本周盈亏（从周一开始）"""
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)

        week_df = df[df['timestamp'] >= monday]
        return self.calc_pnl(week_df)

    def calc_month_pnl(self, df: pd.DataFrame) -> PnLMetrics:
        """计算本月盈亏"""
        today = datetime.now()
        month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        month_df = df[df['timestamp'] >= month_start]
        return self.calc_pnl(month_df)

    def calc_total_pnl(self, current_equity: float, jlp_value: float) -> PnLMetrics:
        """
        计算累计盈亏

        本金 = JLP 价值
        收益 = 账户净值 - JLP 价值
        """
        pnl = current_equity - jlp_value
        pnl_pct = pnl / jlp_value if jlp_value > 0 else 0

        return PnLMetrics(
            pnl=pnl,
            pnl_pct=pnl_pct,
            start_equity=jlp_value,      # 本金 = JLP 价值
            end_equity=current_equity,
            high_equity=current_equity,
            low_equity=current_equity,
        )

    def calc_running_days(self, df: pd.DataFrame) -> int:
        """
        计算运行天数（从首条历史数据开始）
        """
        if df.empty:
            return 0

        first_timestamp = df.iloc[0]['timestamp']
        if isinstance(first_timestamp, str):
            first_timestamp = pd.to_datetime(first_timestamp)

        return (datetime.now() - first_timestamp).days

    def calc_annualized_return(self, cumulative_pct: float, running_days: int) -> float:
        """
        计算年化收益率

        Args:
            cumulative_pct: 累计收益率
            running_days: 运行天数

        Returns:
            float: 年化收益率
        """
        if running_days <= 0:
            return 0

        # 年化 = 累计收益率 / 运行天数 × 365
        return cumulative_pct / running_days * 365

    def calc_report_metrics(
        self,
        df: pd.DataFrame,
        current_snapshot: dict,
    ) -> ReportMetrics:
        """
        计算完整的报告指标

        Args:
            df: 历史数据
            current_snapshot: 当前快照

        Returns:
            ReportMetrics: 报告指标
        """
        current_equity = float(current_snapshot.get('equity', 0))
        jlp_value = float(current_snapshot.get('jlp_value', 0))
        jlp_price = float(current_snapshot.get('jlp_price', 0))

        # 计算各周期盈亏
        today_pnl = self.calc_today_pnl(df)
        week_pnl = self.calc_week_pnl(df)
        month_pnl = self.calc_month_pnl(df)

        # 累计盈亏 = 账户净值 - JLP价值（本金）
        total_pnl = self.calc_total_pnl(current_equity, jlp_value)

        # 运行天数
        running_days = self.calc_running_days(df)

        # 年化收益率
        annualized = self.calc_annualized_return(total_pnl.pnl_pct, running_days)

        return ReportMetrics(
            current_equity=current_equity,
            jlp_amount=float(current_snapshot.get('jlp_amount', 0)),
            jlp_price=jlp_price,
            jlp_value=jlp_value,
            available_balance=float(current_snapshot.get('available_balance', 0)),
            unrealized_pnl=float(current_snapshot.get('unrealized_pnl', 0)),
            margin_ratio=float(current_snapshot.get('margin_ratio', 0)),
            hedge_ratio=float(current_snapshot.get('hedge_ratio', 0)),
            sol_pos=float(current_snapshot.get('sol_pos', 0)),
            eth_pos=float(current_snapshot.get('eth_pos', 0)),
            btc_pos=float(current_snapshot.get('btc_pos', 0)),
            sol_funding=float(current_snapshot.get('sol_funding', 0)),
            eth_funding=float(current_snapshot.get('eth_funding', 0)),
            btc_funding=float(current_snapshot.get('btc_funding', 0)),
            today_pnl=today_pnl,
            week_pnl=week_pnl,
            month_pnl=month_pnl,
            total_pnl=total_pnl,
            annualized_return=annualized,
            running_days=running_days,
        )
