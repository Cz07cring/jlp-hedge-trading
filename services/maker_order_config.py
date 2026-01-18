"""
Maker 订单配置
"""

from dataclasses import dataclass


@dataclass
class MakerOrderConfig:
    """Maker 订单执行器配置"""

    # 单次挂单超时时间 (秒)
    order_timeout: float = 5.0

    # 订单状态检查间隔 (毫秒)
    check_interval_ms: int = 200

    # 盘口变化容忍度 (超过此比例立即撤单重挂)
    price_tolerance: float = 0.0002  # 0.02%

    # 最大循环次数 (防止无限挂单)
    max_iterations: int = 120  # 5秒 × 120 = 10分钟

    # 总超时时间 (秒)，超时后本次调仓结束，等待下个周期
    total_timeout: float = 600  # 10分钟

    # 部分成交阈值，达到此比例视为成功
    partial_fill_threshold: float = 0.95  # 95%

    # 最小剩余比例，小于此值放弃继续挂单
    min_remaining_ratio: float = 0.05  # 5%

    # 拆单配置
    split_order_enabled: bool = True           # 是否启用拆单
    split_order_threshold: float = 500.0       # 拆单阈值 (USD)，超过此金额拆单
    split_order_min_value: float = 100.0       # 单笔最小金额 (USD)
    split_order_max_value: float = 300.0       # 单笔最大金额 (USD)
    split_order_random: bool = True            # 是否随机拆分金额

    # 价格精度 (小数位数)
    price_precision: dict = None

    def __post_init__(self):
        if self.price_precision is None:
            self.price_precision = {
                "SOLUSDT": 2,   # SOL: $0.01
                "ETHUSDT": 2,   # ETH: $0.01
                "BTCUSDT": 1,   # BTC: $0.1
            }
