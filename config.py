"""
Configuration module for MT4 Telegram Bot & ZeroMQ Bridge.
Supports loading from .env, environment variables, and config.ini.
Configures file and console logging with automatic rotation.
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
import configparser
from typing import List

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Native .env parser (avoids mandatory python-dotenv external dependency)
def load_env_file(filepath: str) -> None:
    if not os.path.exists(filepath):
        return
    with open(filepath, "r", encoding="utf-8") as f:
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

load_env_file(ENV_FILE)

# Read config.ini as fallback
config = configparser.ConfigParser()
if os.path.exists(CONFIG_FILE):
    config.read(CONFIG_FILE, encoding="utf-8-sig")

# Telegram Bot Settings
TELEGRAM_BOT_TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN",
    config.get("TELEGRAM", "bot_token", fallback="")
)

_raw_chat_ids = os.environ.get(
    "ALLOWED_CHAT_IDS",
    os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS",
        config.get("TELEGRAM", "allowed_chat_ids", fallback=""))
)
ALLOWED_CHAT_IDS: List[int] = [
    int(cid.strip()) for cid in _raw_chat_ids.split(",") if cid.strip().lstrip("-").isdigit()
]

# ZeroMQ Settings
ZMQ_SERVER_URL = os.environ.get(
    "ZMQ_SERVER_URL",
    config.get("ZEROMQ", "server_url", fallback="tcp://127.0.0.1:5555")
)
ZMQ_TIMEOUT_MS = int(os.environ.get(
    "ZMQ_TIMEOUT_MS",
    config.get("ZEROMQ", "timeout_ms", fallback="3000")
))
ZMQ_RETRY_INTERVAL_SEC = int(os.environ.get(
    "ZMQ_RETRY_INTERVAL_SEC",
    config.get("ZEROMQ", "retry_interval_sec", fallback="5")
))

# Economic Calendar / News Settings
NEWS_REMINDER_LEAD_MINUTES = int(os.environ.get(
    "NEWS_REMINDER_LEAD_MINUTES",
    config.get("NEWS", "reminder_lead_minutes", fallback="15")
))
NEWS_IMPACT_FILTER = [
    imp.strip() for imp in os.environ.get(
        "NEWS_IMPACT_FILTER",
        config.get("NEWS", "impact_filter", fallback="High,Medium")
    ).split(",") if imp.strip()
]
USER_TIMEZONE = os.environ.get(
    "USER_TIMEZONE",
    config.get("NEWS", "user_timezone", fallback="Asia/Baku")
)
BROKER_GMT_OFFSET = int(os.environ.get(
    "BROKER_GMT_OFFSET",
    config.get("NEWS", "broker_gmt_offset", fallback="3")
))

# Flag file for external EAs to check auto-trading state
AUTOTRADE_FLAG_FILE = os.path.join(BASE_DIR, "autotrade_state.flag")

# MT4 Directories
def _resolve_mt4_files_dir() -> str:
    explicit = os.environ.get("MT4_FILES_DIR", config.get("MT4", "files_dir", fallback=""))
    if explicit and os.path.exists(explicit):
        return explicit
    default_target = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\80152BA938C72BA373B1EA4889AEE06F\MQL4\Files")
    if os.path.exists(default_target):
        return default_target
    term_root = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal")
    if os.path.exists(term_root):
        for entry in os.listdir(term_root):
            cand = os.path.join(term_root, entry, "MQL4", "Files")
            if os.path.exists(cand):
                return cand
    return default_target

MT4_FILES_DIR = _resolve_mt4_files_dir()
MT4_TERMINAL_DIR = os.path.dirname(os.path.dirname(MT4_FILES_DIR))

# Logging Configuration
LOG_FILE = os.path.join(LOGS_DIR, "bot.log")

def setup_logging(log_level_name: str = "INFO"):
    level = getattr(logging, log_level_name.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not root_logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s - [%(levelname)s] - %(name)s: %(message)s"
        )

        # 1. Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        # 2. Rotating File Handler (5 MB max, 5 backup files)
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger

# Initialize logging
logger = setup_logging(os.environ.get("LOG_LEVEL", "INFO"))

