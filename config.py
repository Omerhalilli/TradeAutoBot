"""
Configuration module for MT4 Telegram Bot & ZeroMQ Bridge.
Loads settings from .env (via python-dotenv or native fallback), environment variables, and config.ini.
Enforces cross-platform portability, relative paths, and automatic log scrubbing for sensitive credentials.
"""
import configparser
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# Base Directories - 100% relative and portable
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
CONFIG_FILE = BASE_DIR / "config.ini"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

os.makedirs(str(LOGS_DIR), exist_ok=True)
os.makedirs(str(DATA_DIR), exist_ok=True)

# ------------------------------------------------------------------------------
# Environment Loading (python-dotenv with native fallback)
# ------------------------------------------------------------------------------
def _load_environment() -> None:
    # 1. Try python-dotenv
    try:
        from dotenv import load_dotenv
        if ENV_FILE.exists():
            load_dotenv(dotenv_path=str(ENV_FILE), override=False)
            return
    except ImportError:
        pass

    # 2. Native fallback parser
    if not ENV_FILE.exists():
        return

    try:
        with open(str(ENV_FILE), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception:
        pass

_load_environment()

# Read config.ini as secondary fallback
config = configparser.ConfigParser()
if CONFIG_FILE.exists():
    try:
        config.read(str(CONFIG_FILE), encoding="utf-8-sig")
    except Exception:
        pass

# ------------------------------------------------------------------------------
# Telegram Bot Configuration
# ------------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN: str = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    config.get("TELEGRAM", "bot_token", fallback="")
).strip()

_raw_chat_ids: str = os.environ.get(
    "ALLOWED_CHAT_IDS",
    os.environ.get(
        "TELEGRAM_ALLOWED_CHAT_IDS",
        config.get("TELEGRAM", "allowed_chat_ids", fallback="")
    )
).strip()

ALLOWED_CHAT_IDS: List[int] = [
    int(cid.strip())
    for cid in _raw_chat_ids.split(",")
    if cid.strip().lstrip("-").isdigit()
]

TELEGRAM_ENABLE_2FA: bool = os.environ.get(
    "TELEGRAM_ENABLE_2FA",
    config.get("TELEGRAM", "enable_2fa", fallback="false")
).lower() in ("true", "1", "yes")

# ------------------------------------------------------------------------------
# ZeroMQ Settings
# ------------------------------------------------------------------------------
ZMQ_SERVER_URL: str = os.environ.get(
    "ZMQ_SERVER_URL",
    config.get("ZEROMQ", "server_url", fallback="tcp://127.0.0.1:5555")
).strip()

ZMQ_TIMEOUT_MS: int = int(os.environ.get(
    "ZMQ_TIMEOUT_MS",
    config.get("ZEROMQ", "timeout_ms", fallback="3000")
))

ZMQ_RETRY_INTERVAL_SEC: int = int(os.environ.get(
    "ZMQ_RETRY_INTERVAL_SEC",
    config.get("ZEROMQ", "retry_interval_sec", fallback="5")
))

# ------------------------------------------------------------------------------
# Economic Calendar / News Settings
# ------------------------------------------------------------------------------
NEWS_REMINDER_LEAD_MINUTES: int = int(os.environ.get(
    "NEWS_REMINDER_LEAD_MINUTES",
    config.get("NEWS", "reminder_lead_minutes", fallback="15")
))

NEWS_IMPACT_FILTER: List[str] = [
    imp.strip()
    for imp in os.environ.get(
        "NEWS_IMPACT_FILTER",
        config.get("NEWS", "impact_filter", fallback="High,Medium")
    ).split(",")
    if imp.strip()
]

USER_TIMEZONE: str = os.environ.get(
    "USER_TIMEZONE",
    config.get("NEWS", "user_timezone", fallback="Asia/Baku")
).strip()

BROKER_GMT_OFFSET: int = int(os.environ.get(
    "BROKER_GMT_OFFSET",
    config.get("NEWS", "broker_gmt_offset", fallback="3")
))

# Flag file for external EAs to check auto-trading state
AUTOTRADE_FLAG_FILE: str = str(BASE_DIR / "autotrade_state.flag")

# ------------------------------------------------------------------------------
# Cross-Platform MT4 Files Directory Resolution
# ------------------------------------------------------------------------------
def _resolve_mt4_files_dir() -> str:
    explicit = os.environ.get("MT4_FILES_DIR", config.get("MT4", "files_dir", fallback="")).strip()
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

    # 3. Fallback to workspace data directory
    fallback_dir = os.path.join(str(DATA_DIR), "mql4_files")
    os.makedirs(fallback_dir, exist_ok=True)
    return fallback_dir

MT4_FILES_DIR: str = _resolve_mt4_files_dir()
MT4_TERMINAL_DIR: str = os.path.dirname(os.path.dirname(MT4_FILES_DIR))

# ------------------------------------------------------------------------------
# Log Scrubbing & Privacy Protection
# ------------------------------------------------------------------------------
_SENSITIVE_PATTERNS = [
    # Telegram Bot Tokens (e.g. 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz)
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),
    # Telegram Bot API URLs with token embedded
    re.compile(r"(https?://api\.telegram\.org/bot)\d+:[A-Za-z0-9_-]+"),
    # Key / Secret / Password parameter assignments
    re.compile(r"(?i)(password|secret|api[_-]?key|token)\s*[:=]\s*['\"]?[^\s,'\"]+['\"]?"),
]

def scrub_sensitive_text(text: str) -> str:
    """Scrubs passwords, secret tokens, and API credentials from logged strings."""
    if not isinstance(text, str):
        return text

    scrubbed = text
    # Mask active bot token if defined
    if TELEGRAM_BOT_TOKEN and len(TELEGRAM_BOT_TOKEN) > 8:
        scrubbed = scrubbed.replace(TELEGRAM_BOT_TOKEN, "[REDACTED_BOT_TOKEN]")

    for pat in _SENSITIVE_PATTERNS:
        if "bot" in pat.pattern:
            scrubbed = pat.sub(r"\1[REDACTED_BOT_TOKEN]" if r"\1" in pat.pattern else "[REDACTED_BOT_TOKEN]", scrubbed)
        elif "password" in pat.pattern:
            scrubbed = pat.sub(r"\1=[REDACTED]", scrubbed)
        else:
            scrubbed = pat.sub("[REDACTED_SECRET]", scrubbed)

    return scrubbed

class SensitiveDataFilter(logging.Filter):
    """Logging filter that redacts API tokens, secrets, and credentials from log records."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_sensitive_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: scrub_sensitive_text(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    scrub_sensitive_text(v) if isinstance(v, str) else v
                    for v in record.args
                )
        return True

class SensitiveFormatter(logging.Formatter):
    """Logging formatter that ensures the final rendered log string is scrubbed."""
    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return scrub_sensitive_text(formatted)

# ------------------------------------------------------------------------------
# Logging Initialization
# ------------------------------------------------------------------------------
LOG_FILE = os.path.join(str(LOGS_DIR), "bot.log")

def setup_logging(log_level_name: str = "INFO") -> logging.Logger:
    """Initializes console and rotating file loggers with privacy scrubbers."""
    level = getattr(logging, log_level_name.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Attach privacy scrubber filter to root logger
    root_filter = SensitiveDataFilter()
    root_logger.addFilter(root_filter)

    # Configure handlers if not already present
    if not root_logger.handlers:
        formatter = SensitiveFormatter(
            "%(asctime)s - [%(levelname)s] - %(name)s: %(message)s"
        )

        # 1. Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(console_handler)

        # 2. Rotating File Handler (5 MB max, 5 backup files)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(file_handler)

    # Silence third-party noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext.ExtBot").setLevel(logging.INFO)

    return root_logger

# Initialize logging
logger = setup_logging(os.environ.get("LOG_LEVEL", "INFO"))

# ------------------------------------------------------------------------------
# Configuration Validation Helper
# ------------------------------------------------------------------------------
def validate_config() -> Tuple[bool, List[str]]:
    """Checks for required configuration settings and returns status and any error messages."""
    errors: List[str] = []
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("your_"):
        errors.append("TELEGRAM_BOT_TOKEN is missing or has a placeholder value.")
    if not ALLOWED_CHAT_IDS:
        errors.append("ALLOWED_CHAT_IDS is missing or does not contain numeric chat IDs.")
    if not ZMQ_SERVER_URL.startswith("tcp://"):
        errors.append(f"ZMQ_SERVER_URL '{ZMQ_SERVER_URL}' is invalid (must start with tcp://).")
    return (len(errors) == 0, errors)
