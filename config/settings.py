"""
配置文件

支持多用户 JSON 配置 + 环境变量覆盖（Docker 友好）
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def get_env(key: str, default: Any = None, cast_type: type = str) -> Any:
    """从环境变量获取配置，支持类型转换"""
    value = os.environ.get(key)
    if value is None:
        return default
    if cast_type == bool:
        return value.lower() in ('true', '1', 'yes', 'on')
    if cast_type == int:
        return int(value)
    if cast_type == float:
        return float(value)
    return value

# 配置文件路径
CONFIG_DIR = Path(__file__).parent
ACCOUNTS_FILE = CONFIG_DIR / "accounts.json"


@dataclass
class MakerOrderSettings:
    """Maker 订单配置"""
    enabled: bool = True                  # 是否启用 Maker 模式
    order_timeout: float = 5.0            # 单次挂单超时 (秒)
    total_timeout: float = 600            # 总超时 (秒)
    check_interval_ms: int = 200          # 订单状态检查间隔 (毫秒)
    price_tolerance: float = 0.0002       # 盘口变化容忍度 (0.02%)
    max_iterations: int = 120             # 最大重挂次数
    # 拆单配置
    split_order_enabled: bool = True      # 是否启用拆单
    split_order_threshold: float = 500.0  # 拆单阈值 (USD)
    split_order_min_value: float = 100.0  # 单笔最小金额 (USD)
    split_order_max_value: float = 300.0  # 单笔最大金额 (USD)


@dataclass
class TradingConfig:
    """交易配置"""
    leverage: int = 1
    slippage: float = 0.001
    min_order_size: Dict[str, float] = field(default_factory=lambda: {
        "SOL": 0.01,
        "ETH": 0.001,
        "BTC": 0.0001
    })
    maker_order: MakerOrderSettings = field(default_factory=MakerOrderSettings)


@dataclass
class AsterDexConfig:
    """AsterDex 账户配置 - 支持 EVM 和 Solana 两种模式"""
    user_address: str
    # EVM 模式
    signer_address: Optional[str] = None
    private_key: Optional[str] = None
    # Solana/HMAC 模式
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    # 链类型
    chain: str = "evm"

    def is_hmac_mode(self) -> bool:
        """是否使用 HMAC 签名模式"""
        return self.chain.lower() == "solana" or (self.api_key and self.api_secret)


@dataclass
class AccountConfig:
    """单个账户配置"""
    name: str
    enabled: bool
    asterdex: AsterDexConfig
    trading: TradingConfig

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccountConfig":
        trading_data = data.get("trading", {})
        maker_order_data = trading_data.pop("maker_order", {}) if "maker_order" in trading_data else {}

        # 解析 maker_order 配置
        maker_order = MakerOrderSettings(**maker_order_data) if maker_order_data else MakerOrderSettings()

        # 构建 TradingConfig
        trading = TradingConfig(
            leverage=trading_data.get("leverage", 1),
            slippage=trading_data.get("slippage", 0.001),
            min_order_size=trading_data.get("min_order_size", {"SOL": 0.01, "ETH": 0.001, "BTC": 0.0001}),
            maker_order=maker_order,
        )

        return cls(
            name=data.get("name", "未命名"),
            enabled=data.get("enabled", True),
            asterdex=AsterDexConfig(**data.get("asterdex", {})),
            trading=trading,
        )


@dataclass
class GlobalConfig:
    """全局配置"""
    hedge_api_url: str = "http://localhost:3000"
    asterdex_base_url: str = "https://fapi.asterdex.com"
    asterdex_ws_url: str = "wss://fstream.asterdex.com"
    rebalance_interval: int = 600
    rebalance_threshold: float = 0.02
    max_funding_rate: float = 0.001
    min_margin_ratio: float = 0.1
    max_daily_loss: float = 0.02
    log_level: str = "INFO"


@dataclass
class NotificationConfig:
    """通知配置"""
    enabled: bool = True
    wechat_webhook: str = ""


@dataclass
class CloudConfig:
    """云端配置"""
    enabled: bool = False  # 是否启用云端功能
    api_url: str = "https://your-saas-domain.com"  # SaaS 平台 URL
    license_key: str = ""  # License Key
    report_interval: int = 300  # 数据上报间隔（秒）
    sync_interval: int = 300  # 配置同步间隔（秒）
    timeout: float = 30.0  # API 超时时间


@dataclass
class AppConfig:
    """应用总配置"""
    accounts: List[AccountConfig]
    global_config: GlobalConfig
    notification: NotificationConfig
    cloud: CloudConfig = field(default_factory=CloudConfig)

    def get_enabled_accounts(self) -> List[AccountConfig]:
        """获取启用的账户列表"""
        return [acc for acc in self.accounts if acc.enabled]

    def get_account_by_name(self, name: str) -> Optional[AccountConfig]:
        """根据名称获取账户"""
        for acc in self.accounts:
            if acc.name == name:
                return acc
        return None


def load_config(config_file: Path = ACCOUNTS_FILE) -> AppConfig:
    """
    加载配置文件

    Args:
        config_file: 配置文件路径

    Returns:
        AppConfig: 应用配置
    """
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_file}")

    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    accounts = [
        AccountConfig.from_dict(acc_data)
        for acc_data in data.get("accounts", [])
    ]

    global_config = GlobalConfig(**data.get("global", {}))
    notification = NotificationConfig(**data.get("notification", {}))
    
    # 加载云端配置（支持环境变量覆盖，Docker 友好）
    cloud_data = data.get("cloud", {})
    cloud = CloudConfig(
        enabled=get_env("CLOUD_ENABLED", cloud_data.get("enabled", False), bool),
        api_url=get_env("CLOUD_API_URL", cloud_data.get("api_url", "https://jlp.finance")),
        license_key=get_env("LICENSE_KEY", cloud_data.get("license_key", "")),
        report_interval=get_env("REPORT_INTERVAL", cloud_data.get("report_interval", 300), int),
        sync_interval=get_env("SYNC_INTERVAL", cloud_data.get("sync_interval", 300), int),
        timeout=get_env("CLOUD_TIMEOUT", cloud_data.get("timeout", 30.0), float),
    )
    
    # 如果有 LICENSE_KEY 环境变量，自动启用云端
    if os.environ.get("LICENSE_KEY") and not cloud.enabled:
        cloud.enabled = True
        logger.info("检测到 LICENSE_KEY 环境变量，自动启用云端功能")

    logger.info(f"加载配置: {len(accounts)} 个账户")
    if cloud.enabled:
        logger.info(f"云端功能已启用: {cloud.api_url}")
        # 安全日志：只显示 License Key 前几位
        if cloud.license_key:
            masked_key = cloud.license_key[:8] + "..." if len(cloud.license_key) > 8 else "***"
            logger.info(f"License Key: {masked_key}")

    return AppConfig(
        accounts=accounts,
        global_config=global_config,
        notification=notification,
        cloud=cloud,
    )


def save_config(config: AppConfig, config_file: Path = ACCOUNTS_FILE):
    """保存配置到文件"""
    data = {
        "accounts": [
            {
                "name": acc.name,
                "enabled": acc.enabled,
                "asterdex": {
                    "user_address": acc.asterdex.user_address,
                    "signer_address": acc.asterdex.signer_address,
                    "private_key": acc.asterdex.private_key,
                },
                "trading": {
                    "leverage": acc.trading.leverage,
                    "slippage": acc.trading.slippage,
                    "min_order_size": acc.trading.min_order_size,
                },
            }
            for acc in config.accounts
        ],
        "global": {
            "hedge_api_url": config.global_config.hedge_api_url,
            "rebalance_interval": config.global_config.rebalance_interval,
            "rebalance_threshold": config.global_config.rebalance_threshold,
            "max_funding_rate": config.global_config.max_funding_rate,
            "min_margin_ratio": config.global_config.min_margin_ratio,
            "max_daily_loss": config.global_config.max_daily_loss,
        },
        "notification": {
            "enabled": config.notification.enabled,
            "wechat_webhook": config.notification.wechat_webhook,
        },
    }

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# 全局配置实例 (延迟加载)
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = load_config()
    return _config
