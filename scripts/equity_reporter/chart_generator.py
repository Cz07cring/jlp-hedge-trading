"""
Chart Generator Module

Generate equity charts with dual Y-axis and drawdown
"""

import io
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Use default font (no Chinese)
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial']
plt.rcParams['axes.unicode_minus'] = False

logger = logging.getLogger(__name__)

# Charts directory
CHARTS_DIR = Path(__file__).parent.parent.parent / "data" / "charts"


class ChartGenerator:
    """Chart Generator"""

    # Color scheme
    COLORS = {
        'equity_line': '#2196F3',      # Blue - equity curve
        'return_line': '#4CAF50',      # Green - return %
        'drawdown_fill': '#F44336',    # Red - drawdown area
        'grid': '#E0E0E0',             # Light gray - grid
        'text': '#212121',             # Dark gray - text
        'background': '#FFFFFF',       # White - background
        'title': '#1976D2',            # Dark blue - title
        'zero_line': '#9E9E9E',        # Gray - zero line
    }

    def __init__(self, charts_dir: Optional[Path] = None):
        """
        Initialize chart generator

        Args:
            charts_dir: Directory to save charts
        """
        self.charts_dir = charts_dir or CHARTS_DIR
        self.charts_dir.mkdir(parents=True, exist_ok=True)

        # Try to use seaborn for styling
        try:
            import seaborn as sns
            sns.set_style("whitegrid")
            self.use_seaborn = True
        except ImportError:
            self.use_seaborn = False
            logger.warning("seaborn not installed, using default style")

    def _calculate_returns(self, df: pd.DataFrame) -> pd.Series:
        """Calculate cumulative returns from first value"""
        first_equity = df['equity'].iloc[0]
        returns = (df['equity'] - first_equity) / first_equity * 100
        return returns

    def _calculate_drawdown(self, df: pd.DataFrame) -> Tuple[pd.Series, float, int]:
        """
        Calculate drawdown series

        Returns:
            Tuple[drawdown_series, max_drawdown, max_dd_idx]
        """
        equity = df['equity']
        rolling_max = equity.expanding().max()
        drawdown = (equity - rolling_max) / rolling_max * 100

        max_dd = drawdown.min()
        max_dd_idx = drawdown.idxmin()

        return drawdown, max_dd, max_dd_idx

    def generate_equity_chart(
        self,
        df: pd.DataFrame,
        period_name: str,
        account: str,
    ) -> bytes:
        """
        Generate equity chart with 3 separate subplots

        Args:
            df: Historical data DataFrame
            period_name: Period name (7D/30D/365D)
            account: Account name

        Returns:
            bytes: PNG image data
        """
        if df.empty or len(df) < 2:
            return self._generate_empty_chart(period_name, account)

        # Create figure with 3 subplots
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 10), height_ratios=[1.2, 1, 1])
        fig.patch.set_facecolor(self.COLORS['background'])

        # Ensure timestamp is datetime type
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Calculate metrics
        returns = self._calculate_returns(df)
        drawdown, max_dd, max_dd_idx = self._calculate_drawdown(df)

        # Title
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        fig.suptitle(
            f'JLP Neutral Arbitrage - {period_name}\n{account} | {now}',
            fontsize=14,
            fontweight='bold',
            color=self.COLORS['title'],
            y=0.98,
        )

        # ========== Subplot 1: Equity Curve ==========
        ax1.set_facecolor(self.COLORS['background'])

        ax1.plot(
            df['timestamp'],
            df['equity'],
            color=self.COLORS['equity_line'],
            linewidth=2,
            label='Equity',
            marker='o' if len(df) <= 14 else None,
            markersize=4,
        )
        ax1.fill_between(
            df['timestamp'],
            df['equity'],
            alpha=0.15,
            color=self.COLORS['equity_line'],
        )

        ax1.set_ylabel('Equity ($)', fontsize=11, color=self.COLORS['equity_line'])
        ax1.tick_params(axis='y', labelcolor=self.COLORS['equity_line'])
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))

        # Add high/low annotations
        max_idx = df['equity'].idxmax()
        min_idx = df['equity'].idxmin()

        ax1.annotate(
            f'High: ${df.loc[max_idx, "equity"]:,.0f}',
            xy=(df.loc[max_idx, 'timestamp'], df.loc[max_idx, 'equity']),
            xytext=(10, 5),
            textcoords='offset points',
            fontsize=9,
            color=self.COLORS['return_line'],
            fontweight='bold',
        )

        ax1.annotate(
            f'Low: ${df.loc[min_idx, "equity"]:,.0f}',
            xy=(df.loc[min_idx, 'timestamp'], df.loc[min_idx, 'equity']),
            xytext=(10, -12),
            textcoords='offset points',
            fontsize=9,
            color=self.COLORS['drawdown_fill'],
            fontweight='bold',
        )

        ax1.set_title('Equity Curve', fontsize=12, pad=10)
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper left', fontsize=9)

        # ========== Subplot 2: Return % ==========
        ax2.set_facecolor(self.COLORS['background'])

        ax2.plot(
            df['timestamp'],
            returns,
            color=self.COLORS['return_line'],
            linewidth=2,
            label='Return %',
        )
        ax2.fill_between(
            df['timestamp'],
            returns,
            0,
            where=(returns >= 0),
            alpha=0.2,
            color=self.COLORS['return_line'],
            interpolate=True,
        )
        ax2.fill_between(
            df['timestamp'],
            returns,
            0,
            where=(returns < 0),
            alpha=0.2,
            color=self.COLORS['drawdown_fill'],
            interpolate=True,
        )

        ax2.axhline(y=0, color=self.COLORS['zero_line'], linestyle='-', linewidth=1, alpha=0.7)
        ax2.set_ylabel('Return (%)', fontsize=11, color=self.COLORS['return_line'])
        ax2.tick_params(axis='y', labelcolor=self.COLORS['return_line'])
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:+.2f}%'))

        # Annotate current return
        current_return = returns.iloc[-1]
        ax2.annotate(
            f'Current: {current_return:+.2f}%',
            xy=(df['timestamp'].iloc[-1], current_return),
            xytext=(-60, 10 if current_return >= 0 else -15),
            textcoords='offset points',
            fontsize=9,
            color=self.COLORS['return_line'] if current_return >= 0 else self.COLORS['drawdown_fill'],
            fontweight='bold',
        )

        ax2.set_title('Cumulative Return', fontsize=12, pad=10)
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='upper left', fontsize=9)

        # ========== Subplot 3: Drawdown ==========
        ax3.set_facecolor(self.COLORS['background'])

        ax3.fill_between(
            df['timestamp'],
            drawdown,
            0,
            color=self.COLORS['drawdown_fill'],
            alpha=0.4,
            label='Drawdown',
        )
        ax3.plot(
            df['timestamp'],
            drawdown,
            color=self.COLORS['drawdown_fill'],
            linewidth=1.5,
        )

        ax3.axhline(y=0, color=self.COLORS['zero_line'], linestyle='-', linewidth=1)
        ax3.set_ylabel('Drawdown (%)', fontsize=11, color=self.COLORS['drawdown_fill'])
        ax3.tick_params(axis='y', labelcolor=self.COLORS['drawdown_fill'])
        ax3.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:.2f}%'))

        # Annotate max drawdown
        if max_dd < 0:
            max_dd_time = df.loc[max_dd_idx, 'timestamp']
            ax3.annotate(
                f'Max DD: {max_dd:.2f}%',
                xy=(max_dd_time, max_dd),
                xytext=(10, -10),
                textcoords='offset points',
                fontsize=10,
                color=self.COLORS['drawdown_fill'],
                fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=self.COLORS['drawdown_fill'], alpha=0.8),
            )

        ax3.set_title('Drawdown', fontsize=12, pad=10)
        ax3.grid(True, alpha=0.3)
        ax3.legend(loc='lower left', fontsize=9)

        # Remove top spines
        for ax in [ax1, ax2, ax3]:
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)

        # ========== Bottom Summary ==========
        start_equity = float(df.iloc[0]['equity'])
        end_equity = float(df.iloc[-1]['equity'])
        period_pnl = end_equity - start_equity
        period_pnl_pct = period_pnl / start_equity * 100 if start_equity > 0 else 0

        summary_text = (
            f"Return: ${period_pnl:+,.0f} ({period_pnl_pct:+.2f}%)  |  "
            f"High: ${df['equity'].max():,.0f}  |  "
            f"Low: ${df['equity'].min():,.0f}  |  "
            f"Max DD: {max_dd:.2f}%"
        )

        fig.text(
            0.5, 0.01,
            summary_text,
            ha='center',
            fontsize=11,
            color=self.COLORS['text'],
            bbox=dict(boxstyle='round', facecolor='#F5F5F5', edgecolor='#E0E0E0'),
        )

        # Adjust layout
        plt.tight_layout()
        plt.subplots_adjust(top=0.92, bottom=0.06, hspace=0.30)

        # Save to bytes
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return buf.getvalue()

    def _generate_empty_chart(self, period_name: str, account: str) -> bytes:
        """Generate empty data chart"""
        fig, ax = plt.subplots(figsize=(10, 6))

        ax.text(
            0.5, 0.5,
            f'No data for {period_name}\n\nWaiting for data collection',
            ha='center',
            va='center',
            fontsize=14,
            color=self.COLORS['text'],
        )

        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        fig.suptitle(
            f'JLP Neutral Arbitrage - {period_name}\n{account} | {now}',
            fontsize=14,
            fontweight='bold',
            color=self.COLORS['title'],
        )

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)

        return buf.getvalue()

    def generate_7d_chart(
        self,
        df: pd.DataFrame,
        account: str,
    ) -> bytes:
        """Generate 7-day chart"""
        cutoff = datetime.now() - timedelta(days=7)
        df_7d = df[df['timestamp'] >= cutoff].copy()

        return self.generate_equity_chart(df_7d, "Last 7 Days", account)

    def generate_30d_chart(
        self,
        df: pd.DataFrame,
        account: str,
    ) -> bytes:
        """Generate 30-day chart"""
        cutoff = datetime.now() - timedelta(days=30)
        df_30d = df[df['timestamp'] >= cutoff].copy()

        # Aggregate by day (reduce data points)
        if not df_30d.empty:
            df_30d['date'] = df_30d['timestamp'].dt.date
            df_daily = df_30d.groupby('date').last().reset_index()
            df_daily['timestamp'] = pd.to_datetime(df_daily['date'])

            return self.generate_equity_chart(df_daily, "Last 30 Days", account)

        return self.generate_equity_chart(df_30d, "Last 30 Days", account)

    def generate_365d_chart(
        self,
        df: pd.DataFrame,
        account: str,
    ) -> bytes:
        """Generate 365-day chart"""
        cutoff = datetime.now() - timedelta(days=365)
        df_365d = df[df['timestamp'] >= cutoff].copy()

        # Aggregate by day
        if not df_365d.empty:
            df_365d['date'] = df_365d['timestamp'].dt.date
            df_daily = df_365d.groupby('date').last().reset_index()
            df_daily['timestamp'] = pd.to_datetime(df_daily['date'])

            return self.generate_equity_chart(df_daily, "Last 365 Days", account)

        return self.generate_equity_chart(df_365d, "Last 365 Days", account)

    def save_charts(
        self,
        df: pd.DataFrame,
        account: str,
    ) -> list:
        """
        Generate and save all period charts

        Args:
            df: Full historical data
            account: Account name

        Returns:
            list: Saved file paths
        """
        today = datetime.now().strftime("%Y-%m-%d")
        saved_files = []

        # Generate 3 charts
        charts = [
            ("7d", self.generate_7d_chart),
            ("30d", self.generate_30d_chart),
            ("365d", self.generate_365d_chart),
        ]

        for period, generator in charts:
            try:
                chart_data = generator(df, account)
                file_path = self.charts_dir / f"equity_{period}_{today}.png"

                with open(file_path, 'wb') as f:
                    f.write(chart_data)

                saved_files.append(file_path)
                logger.info(f"Chart saved: {file_path}")

            except Exception as e:
                logger.error(f"Failed to generate {period} chart: {e}")

        return saved_files
