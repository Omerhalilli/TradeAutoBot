"""
Dynamic Configuration Manager with Real-Time Hot-Reloading and Schema Validation.
Parses settings from .env, config.ini, and JSON configuration stores.
Emits configuration change events onto the event bus to allow zero-downtime parameter adaptation.
"""

from __future__ import annotations
import configparser
from dataclasses import dataclass, field, asdict
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from autotrade.core.event_bus import event_bus, EventType, EventPriority

logger = logging.getLogger("autotrade.core.config_manager")

BASE_DIR = str(Path(__file__).resolve().parent.parent.parent)
ENV_FILE = os.path.join(BASE_DIR, ".env")
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")


@dataclass
class TelegramConfig:
    """Telegram interface credentials, authorized users, and delivery parameters."""
    bot_token: str = ""
    allowed_chat_ids: List[int] = field(default_factory=list)
    admin_chat_id: Optional[int] = None
    enable_2fa: bool = False
    rate_limit_per_minute: int = 60
    batch_notifications_sec: float = 1.0


@dataclass
class ZmqConfig:
    """ZeroMQ high-frequency bridge transport parameters."""
    server_url: str = "tcp://127.0.0.1:5555"
    timeout_ms: int = 3000
    retry_interval_sec: int = 5
    max_retries: int = 3
    heartbeat_interval_sec: float = 5.0


@dataclass
class RiskLimitsConfig:
    """Institutional Prop-Firm & Account Safeguard Parameters."""
    max_account_risk_pct: float = 2.0         # Max risk % per single trade
    max_daily_loss_pct: float = 4.0           # Halt threshold if daily drawdown >= 4%
    max_total_drawdown_pct: float = 8.0       # Global kill-switch drawdown
    max_open_positions: int = 10              # Maximum concurrent open orders
    max_lots_per_symbol: float = 5.0          # Max cumulative volume per currency pair
    max_total_lots: float = 15.0              # Max portfolio volume exposure
    max_margin_usage_pct: float = 50.0        # Max margin utilization %
    max_correlated_positions: int = 2         # Max orders on pairs with correlation > 0.70
    daily_trade_limit: int = 50               # Maximum total orders executed per 24h
    news_volatility_reduction_pct: float = 50.0 # Reduce lot size by 50% around red news
    enable_trailing_stop: bool = True
    default_trailing_pips: int = 20
    enable_breakeven: bool = True
    breakeven_trigger_pips: int = 15
    breakeven_lock_pips: int = 1


@dataclass
class StrategyConfig:
    """Algorithmic strategy execution settings."""
    active_strategies: List[str] = field(default_factory=lambda: [
        "TrendFollowingStrategy",
        "MeanReversionStrategy",
        "BreakoutStrategy",
        "MLPredictorStrategy"
    ])
    primary_symbols: List[str] = field(default_factory=lambda: [
        "GBPUSD", "EURUSD", "XAUUSD", "USOIL", "USDJPY"
    ])
    timeframes: List[str] = field(default_factory=lambda: ["M5", "M15", "H1", "H4"])
    default_sizing_method: str = "volatility_atr" # fixed_lot, pct_risk, kelly, volatility_atr, auto
    default_fixed_lot: float = 0.05
    kelly_fraction: float = 0.5                  # Half-Kelly for conservative capital preservation
    min_risk_reward_ratio: float = 1.5           # Minimum TP / SL ratio


@dataclass
class NewsConfig:
    """Economic calendar & sentiment filter settings."""
    reminder_lead_minutes: int = 15
    impact_filter: List[str] = field(default_factory=lambda: ["High", "Medium"])
    user_timezone: str = "Asia/Baku"
    broker_gmt_offset: int = 3
    halt_trading_during_red_news: bool = False   # If True, no new orders 15m before & after
    auto_hedge_red_news: bool = False


@dataclass
class SelfHealingConfig:
    """Automated source compilation, error analysis, and self-repair settings."""
    enable_startup_compilation: bool = True
    enable_auto_heal_ast: bool = True
    max_healing_attempts: int = 5
    backup_before_patch: bool = True
    watchdog_interval_sec: float = 10.0
    restart_crashed_modules: bool = True


@dataclass
class SystemConfig:
    """Master application configuration schema."""
    environment: str = "production"
    log_level: str = "INFO"
    data_dir: str = DATA_DIR
    logs_dir: str = LOGS_DIR
    mt4_files_dir: str = ""
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    zmq: ZmqConfig = field(default_factory=ZmqConfig)
    risk: RiskLimitsConfig = field(default_factory=RiskLimitsConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    healing: SelfHealingConfig = field(default_factory=SelfHealingConfig)


class ConfigManager:
    """
    Centralized, thread-safe configuration repository with automatic environment loading,
    hot-reloading, and schema persistence.
    """
    def __init__(self, env_path: str = ENV_FILE, config_ini_path: str = CONFIG_FILE):
        self.env_path = env_path
        self.config_ini_path = config_ini_path
        self.settings_ini_path = os.path.join(BASE_DIR, "settings.ini")
        self.config_json_path = os.path.join(BASE_DIR, "config.json")
        self._lock = threading.RLock()
        self._last_loaded_mtime: float = 0.0
        self.config = SystemConfig()
        
        # Load initial configuration
        self.reload()

    def _parse_env_file(self) -> Dict[str, str]:
        """Parses KEY=VALUE lines from .env file directly into dictionary without external deps."""
        env_vars: Dict[str, str] = {}
        if not os.path.exists(self.env_path):
            return env_vars
            
        with open(self.env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k:
                        env_vars[k] = v
                        # Keep process os.environ updated
                        os.environ[k] = v
        return env_vars

    def _read_ini_file(self) -> configparser.ConfigParser:
        """Parses fallback config.ini or settings.ini if available."""
        parser = configparser.ConfigParser()
        for cand in (self.config_ini_path, self.settings_ini_path):
            if os.path.exists(cand):
                try:
                    parser.read(cand, encoding="utf-8-sig")
                    break
                except Exception as ex:
                    logger.warning(f"Failed to read {cand}: {ex}")
        return parser

    def _read_json_file(self) -> Dict[str, Any]:
        """Parses tertiary fallback config.json if available."""
        if os.path.exists(self.config_json_path):
            try:
                with open(self.config_json_path, "r", encoding="utf-8-sig") as jf:
                    return json.load(jf)
            except Exception as ex:
                logger.warning(f"Failed to read {self.config_json_path}: {ex}")
        return {}

    def reload(self) -> None:
        """Loads configuration from environment variables, .env, config.ini, settings.ini, and config.json."""
        with self._lock:
            env_vars = self._parse_env_file()
            ini = self._read_ini_file()
            json_cfg = self._read_json_file()
            
            # Helper to retrieve value with fallback cascade: OS ENV -> .env -> config.ini -> config.json -> default
            def get_val(key: str, section: str, ini_key: str, default: Any) -> Any:
                if key in os.environ and os.environ[key] != "":
                    return os.environ[key]
                if key in env_vars and env_vars[key] != "":
                    return env_vars[key]
                if ini.has_option(section, ini_key):
                    return ini.get(section, ini_key)
                if json_cfg and isinstance(json_cfg.get(section.lower()), dict):
                    val = json_cfg[section.lower()].get(ini_key)
                    if val is not None:
                        return val
                return default

            # Telegram Config
            token = str(get_val("TELEGRAM_BOT_TOKEN", "TELEGRAM", "bot_token", ""))
            raw_chats = str(get_val("ALLOWED_CHAT_IDS", "TELEGRAM", "allowed_chat_ids", os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")))
            allowed_ids = [
                int(c.strip()) for c in raw_chats.split(",") if c.strip().lstrip("-").isdigit()
            ]
            
            self.config.telegram.bot_token = token
            self.config.telegram.allowed_chat_ids = allowed_ids
            if allowed_ids:
                self.config.telegram.admin_chat_id = allowed_ids[0]
            self.config.telegram.enable_2fa = str(get_val("TELEGRAM_ENABLE_2FA", "TELEGRAM", "enable_2fa", "False")).lower() in ("true", "1", "yes")

            # ZMQ Config
            self.config.zmq.server_url = str(get_val("ZMQ_SERVER_URL", "ZEROMQ", "server_url", "tcp://127.0.0.1:5555"))
            self.config.zmq.timeout_ms = int(get_val("ZMQ_TIMEOUT_MS", "ZEROMQ", "timeout_ms", 3000))
            self.config.zmq.retry_interval_sec = int(get_val("ZMQ_RETRY_INTERVAL_SEC", "ZEROMQ", "retry_interval_sec", 5))

            # News Config
            self.config.news.reminder_lead_minutes = int(get_val("NEWS_REMINDER_LEAD_MINUTES", "NEWS", "reminder_lead_minutes", 15))
            raw_impact = str(get_val("NEWS_IMPACT_FILTER", "NEWS", "impact_filter", "High,Medium"))
            self.config.news.impact_filter = [i.strip() for i in raw_impact.split(",") if i.strip()]
            self.config.news.user_timezone = str(get_val("USER_TIMEZONE", "NEWS", "user_timezone", "Asia/Baku"))
            self.config.news.broker_gmt_offset = int(get_val("BROKER_GMT_OFFSET", "NEWS", "broker_gmt_offset", 3))

            # MT4 Files Dir Resolution
            explicit_files = str(get_val("MT4_FILES_DIR", "MT4", "files_dir", ""))
            self.config.mt4_files_dir = self._resolve_mt4_files(explicit_files)

            # Risk Limits
            self.config.risk.max_account_risk_pct = float(get_val("MAX_ACCOUNT_RISK_PCT", "RISK", "max_account_risk_pct", 2.0))
            self.config.risk.max_daily_loss_pct = float(get_val("MAX_DAILY_LOSS_PCT", "RISK", "max_daily_loss_pct", 4.0))
            self.config.risk.max_total_drawdown_pct = float(get_val("MAX_TOTAL_DRAWDOWN_PCT", "RISK", "max_total_drawdown_pct", 8.0))
            self.config.risk.max_open_positions = int(get_val("MAX_OPEN_POSITIONS", "RISK", "max_open_positions", 10))
            self.config.risk.max_lots_per_symbol = float(get_val("MAX_LOTS_PER_SYMBOL", "RISK", "max_lots_per_symbol", 5.0))
            self.config.risk.max_total_lots = float(get_val("MAX_TOTAL_LOTS", "RISK", "max_total_lots", 15.0))
            self.config.risk.enable_trailing_stop = str(get_val("ENABLE_TRAILING_STOP", "RISK", "enable_trailing_stop", "true")).lower() in ("true", "1", "yes")
            self.config.risk.default_trailing_pips = int(get_val("DEFAULT_TRAILING_PIPS", "RISK", "default_trailing_pips", 20))
            self.config.risk.enable_breakeven = str(get_val("ENABLE_BREAKEVEN", "RISK", "enable_breakeven", "true")).lower() in ("true", "1", "yes")
            self.config.risk.breakeven_trigger_pips = int(get_val("BREAKEVEN_TRIGGER_PIPS", "RISK", "breakeven_trigger_pips", 15))
            self.config.risk.breakeven_lock_pips = int(get_val("BREAKEVEN_LOCK_PIPS", "RISK", "breakeven_lock_pips", 1))

            # Strategy Settings
            raw_syms = str(get_val("TRADING_SYMBOLS", "STRATEGY", "trading_symbols", "GBPUSD,EURUSD,XAUUSD,USOIL,USDJPY"))
            self.config.strategy.primary_symbols = [s.strip() for s in raw_syms.split(",") if s.strip()]
            raw_tfs = str(get_val("TRADING_TIMEFRAMES", "STRATEGY", "trading_timeframes", "M5,M15,H1,H4"))
            self.config.strategy.timeframes = [tf.strip() for tf in raw_tfs.split(",") if tf.strip()]
            self.config.strategy.default_sizing_method = str(get_val("DEFAULT_SIZING_METHOD", "STRATEGY", "default_sizing_method", "volatility_atr")).strip()
            self.config.strategy.default_fixed_lot = float(get_val("DEFAULT_FIXED_LOT", "STRATEGY", "default_fixed_lot", 0.05))

            # System & Logging
            self.config.log_level = get_val("LOG_LEVEL", "SYSTEM", "log_level", "INFO").upper()

            self._last_loaded_mtime = time.time()
            logger.info("Configuration loaded and verified successfully.")

    def _resolve_mt4_files(self, explicit: str) -> str:
        """Determines the active MT4 Files directory across Wine and Windows paths."""
        if explicit and os.path.exists(explicit):
            return explicit

        # 1. Linux Wine environment discovery
        wine_prefix = os.path.expanduser("~/.wine/drive_c")
        if os.path.exists(wine_prefix):
            users_dir = os.path.join(wine_prefix, "users")
            candidates: List[str] = []
            cur_user = os.environ.get("USER") or os.environ.get("USERNAME")
            if cur_user:
                candidates.append(cur_user)
            if os.path.exists(users_dir):
                try:
                    for u in os.listdir(users_dir):
                        if u not in candidates and not u.startswith("."):
                            candidates.append(u)
                except Exception:
                    pass
            for u in candidates:
                appdata = os.path.join(users_dir, u, "AppData", "Roaming", "MetaQuotes", "Terminal")
                if os.path.exists(appdata):
                    try:
                        for sub in os.listdir(appdata):
                            cand = os.path.join(appdata, sub, "MQL4", "Files")
                            if os.path.exists(cand):
                                return cand
                    except Exception:
                        pass

        # 2. Native Windows environment discovery
        appdata_win = os.environ.get("APPDATA")
        if appdata_win:
            term_root = os.path.join(appdata_win, "MetaQuotes", "Terminal")
            if os.path.exists(term_root):
                try:
                    for sub in os.listdir(term_root):
                        cand = os.path.join(term_root, sub, "MQL4", "Files")
                        if os.path.exists(cand):
                            return cand
                except Exception:
                    pass

        # 3. Fallback to data/mql4_files directory within workspace
        fallback_dir = os.path.join(DATA_DIR, "mql4_files")
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback_dir

    def update_risk_limits(self, **kwargs) -> None:
        """
        Dynamically updates risk limit parameters at runtime and broadcasts an event to the RiskManager.
        """
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self.config.risk, k):
                    setattr(self.config.risk, k, v)
                    logger.info(f"Updated risk parameter: {k} = {v}")
            
            event_bus.publish(
                EventType.RISK_LIMITS_UPDATED,
                payload=asdict(self.config.risk),
                priority=EventPriority.HIGH,
                source="ConfigManager"
            )

    def update_strategy_param(self, symbol: str, param: str, value: Any) -> None:
        """Updates strategy configuration and publishes event for live adaptation."""
        with self._lock:
            event_bus.publish(
                EventType.STRATEGY_PARAM_UPDATED,
                payload={"symbol": symbol, "param": param, "value": value},
                priority=EventPriority.NORMAL,
                source="ConfigManager"
            )

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Validates the current configuration.
        Returns a tuple of (is_valid, list_of_error_messages).
        """
        with self._lock:
            errors: List[str] = []
            tok = self.config.telegram.bot_token
            if not tok or tok.startswith("your_") or ":" not in tok:
                errors.append("TELEGRAM_BOT_TOKEN is missing, invalid, or set to placeholder value.")
            if not self.config.telegram.allowed_chat_ids:
                errors.append("ALLOWED_CHAT_IDS must specify at least one authorized numeric Telegram chat ID.")
            if not self.config.zmq.server_url.startswith("tcp://"):
                errors.append(f"ZMQ_SERVER_URL '{self.config.zmq.server_url}' is invalid (must start with tcp://).")
            return (len(errors) == 0, errors)

    def export_dict(self) -> Dict[str, Any]:
        """Exports sanitized configuration dictionary (hiding sensitive token secrets)."""
        with self._lock:
            d = asdict(self.config)
            if d.get("telegram", {}).get("bot_token"):
                tok = d["telegram"]["bot_token"]
                d["telegram"]["bot_token"] = tok[:6] + "..." + tok[-4:] if len(tok) > 10 else "***"
            return d


# Global singleton instance
_config_manager = ConfigManager()

def get_config() -> SystemConfig:
    """Returns the active SystemConfig schema instance."""
    return _config_manager.config

def get_config_manager() -> ConfigManager:
    """Returns the singleton ConfigManager controller."""
    return _config_manager
