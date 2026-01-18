"""
CSV 存储模块

存储和读取净值历史数据
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd

from scripts.equity_reporter.collector import EquitySnapshot

logger = logging.getLogger(__name__)

# 数据目录
DATA_DIR = Path(__file__).parent.parent.parent / "data"
HISTORY_FILE = DATA_DIR / "equity_history.csv"
DAILY_FILE = DATA_DIR / "daily_summary.csv"


class EquityStorage:
    """CSV 存储管理"""

    # CSV 列定义
    HISTORY_COLUMNS = [
        "timestamp", "account", "equity", "jlp_amount", "jlp_price", "jlp_value",
        "available_balance", "used_margin", "unrealized_pnl", "margin_ratio",
        "hedge_ratio", "sol_pos", "eth_pos", "btc_pos",
        "sol_funding", "eth_funding", "btc_funding"
    ]

    DAILY_COLUMNS = [
        "date", "account", "open_equity", "close_equity", "high_equity",
        "low_equity", "daily_pnl", "daily_pnl_pct", "jlp_amount", "avg_margin_ratio"
    ]

    def __init__(self, data_dir: Optional[Path] = None):
        """
        初始化存储

        Args:
            data_dir: 数据目录，默认为 project/data
        """
        self.data_dir = data_dir or DATA_DIR
        self.history_file = self.data_dir / "equity_history.csv"
        self.daily_file = self.data_dir / "daily_summary.csv"

        # 确保目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "charts").mkdir(exist_ok=True)

        # 初始化 CSV 文件
        self._init_csv_files()

    def _init_csv_files(self):
        """初始化 CSV 文件（如果不存在）"""
        if not self.history_file.exists():
            df = pd.DataFrame(columns=self.HISTORY_COLUMNS)
            df.to_csv(self.history_file, index=False)
            logger.info(f"创建历史数据文件: {self.history_file}")

        if not self.daily_file.exists():
            df = pd.DataFrame(columns=self.DAILY_COLUMNS)
            df.to_csv(self.daily_file, index=False)
            logger.info(f"创建每日汇总文件: {self.daily_file}")

    def append_snapshot(self, snapshot: EquitySnapshot):
        """
        追加一条快照记录

        Args:
            snapshot: 净值快照
        """
        row = {
            "timestamp": snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "account": snapshot.account,
            "equity": float(snapshot.equity),
            "jlp_amount": float(snapshot.jlp_amount),
            "jlp_price": float(snapshot.jlp_price),
            "jlp_value": float(snapshot.jlp_value),
            "available_balance": float(snapshot.available_balance),
            "used_margin": float(snapshot.used_margin),
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

        df = pd.DataFrame([row])
        df.to_csv(self.history_file, mode='a', header=False, index=False)
        logger.debug(f"记录已保存: {snapshot.account} equity=${snapshot.equity:.2f}")

    def get_history(
        self,
        days: int = 7,
        account: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取历史数据

        Args:
            days: 天数
            account: 账户名称（可选）

        Returns:
            pd.DataFrame: 历史数据
        """
        if not self.history_file.exists():
            return pd.DataFrame(columns=self.HISTORY_COLUMNS)

        df = pd.read_csv(self.history_file)

        if df.empty:
            return df

        # 转换时间戳
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # 过滤时间范围
        cutoff = datetime.now() - timedelta(days=days)
        df = df[df['timestamp'] >= cutoff]

        # 过滤账户
        if account:
            df = df[df['account'] == account]

        # 按时间排序
        df = df.sort_values('timestamp')

        return df

    def get_daily_summary(
        self,
        days: int = 30,
        account: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取每日汇总数据

        Args:
            days: 天数
            account: 账户名称（可选）

        Returns:
            pd.DataFrame: 每日汇总
        """
        if not self.daily_file.exists():
            return pd.DataFrame(columns=self.DAILY_COLUMNS)

        df = pd.read_csv(self.daily_file)

        if df.empty:
            return df

        # 转换日期
        df['date'] = pd.to_datetime(df['date'])

        # 过滤时间范围
        cutoff = datetime.now() - timedelta(days=days)
        df = df[df['date'] >= cutoff]

        # 过滤账户
        if account:
            df = df[df['account'] == account]

        # 按日期排序
        df = df.sort_values('date')

        return df

    def update_daily_summary(self, account: Optional[str] = None):
        """
        更新每日汇总数据

        从历史数据中计算每日汇总
        """
        # 读取所有历史数据
        if not self.history_file.exists():
            return

        df = pd.read_csv(self.history_file)
        if df.empty:
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['date'] = df['timestamp'].dt.date

        # 过滤账户
        if account:
            df = df[df['account'] == account]

        # 按账户和日期分组
        daily_data = []
        for (acc, date), group in df.groupby(['account', 'date']):
            daily_data.append({
                'date': date,
                'account': acc,
                'open_equity': group.iloc[0]['equity'],
                'close_equity': group.iloc[-1]['equity'],
                'high_equity': group['equity'].max(),
                'low_equity': group['equity'].min(),
                'daily_pnl': group.iloc[-1]['equity'] - group.iloc[0]['equity'],
                'daily_pnl_pct': (group.iloc[-1]['equity'] - group.iloc[0]['equity']) / group.iloc[0]['equity'] if group.iloc[0]['equity'] > 0 else 0,
                'jlp_amount': group.iloc[-1]['jlp_amount'],
                'avg_margin_ratio': group['margin_ratio'].mean(),
            })

        if daily_data:
            daily_df = pd.DataFrame(daily_data)
            daily_df.to_csv(self.daily_file, index=False)
            logger.info(f"每日汇总已更新: {len(daily_data)} 条记录")

    def get_latest_snapshot(self, account: str) -> Optional[dict]:
        """
        获取最新的快照

        Args:
            account: 账户名称

        Returns:
            dict: 最新快照数据，如果没有则返回 None
        """
        df = self.get_history(days=1, account=account)

        if df.empty:
            return None

        return df.iloc[-1].to_dict()

    def get_today_open_equity(self, account: str) -> Optional[float]:
        """
        获取今日开盘权益

        Args:
            account: 账户名称

        Returns:
            float: 今日开盘权益
        """
        df = self.get_history(days=1, account=account)

        if df.empty:
            return None

        # 筛选今天的数据
        today = datetime.now().date()
        df = df[df['timestamp'].dt.date == today]

        if df.empty:
            return None

        return float(df.iloc[0]['equity'])
