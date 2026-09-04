"""
Account & Profile Manager for MT4 Telegram Bot.
Handles registry of multiple trading accounts/profiles, active account selection,
and persistent storage.
"""
import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from config import DATA_DIR, ZMQ_SERVER_URL

logger = logging.getLogger(__name__)

ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
ACTIVE_ACCOUNT_FILE = os.path.join(DATA_DIR, "active_account.json")

@dataclass
class AccountProfile:
    id: str
    account_number: str
    name: str
    profile_name: str
    server: str
    zmq_url: str

DEFAULT_ACCOUNTS: List[Dict[str, str]] = [
    {
        "id": "1",
        "account_number": "Demo Account",
        "name": "Invest-AZ Demo",
        "profile_name": "Demo Profile",
        "server": "InvestAZ-Demo",
        "zmq_url": "tcp://127.0.0.1:5555"
    },
    {
        "id": "2",
        "account_number": "Real Live",
        "name": "Invest-AZ Real",
        "profile_name": "Real Profile",
        "server": "InvestAZ-Real",
        "zmq_url": "tcp://127.0.0.1:5555"
    }
]

class AccountManager:
    def __init__(self):
        self.accounts: List[AccountProfile] = []
        self.active_id: str = "1"
        self._load()

    def _load(self) -> None:
        """Loads accounts and active selection from persistent disk storage."""
        if os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, "r", encoding="utf-8-sig") as f:
                    raw_data = json.load(f)
                    self.accounts = [AccountProfile(**item) for item in raw_data]
            except Exception as e:
                logger.error(f"Error loading {ACCOUNTS_FILE}: {e}")
                self.accounts = [AccountProfile(**item) for item in DEFAULT_ACCOUNTS]
        else:
            self.accounts = [AccountProfile(**item) for item in DEFAULT_ACCOUNTS]
            self._save_accounts()

        if os.path.exists(ACTIVE_ACCOUNT_FILE):
            try:
                with open(ACTIVE_ACCOUNT_FILE, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    self.active_id = str(data.get("active_id", "1"))
            except Exception as e:
                logger.debug(f"Could not load active account file: {e}")
                self.active_id = "1"
        else:
            self.active_id = "1"
            self._save_active()

        # Ensure active_id exists in accounts
        if not any(acc.id == self.active_id for acc in self.accounts) and self.accounts:
            self.active_id = self.accounts[0].id
            self._save_active()

    def _save_accounts(self) -> None:
        try:
            with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
                json.dump([asdict(acc) for acc in self.accounts], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save {ACCOUNTS_FILE}: {e}")

    def _save_active(self) -> None:
        try:
            with open(ACTIVE_ACCOUNT_FILE, "w", encoding="utf-8") as f:
                json.dump({"active_id": self.active_id}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save {ACTIVE_ACCOUNT_FILE}: {e}")

    def get_all_accounts(self) -> List[AccountProfile]:
        return list(self.accounts)

    def get_account_by_id(self, account_id: str) -> Optional[AccountProfile]:
        for acc in self.accounts:
            if str(acc.id) == str(account_id):
                return acc
        return None

    def get_active_account(self) -> AccountProfile:
        acc = self.get_account_by_id(self.active_id)
        if acc is not None:
            return acc
        return self.accounts[0] if self.accounts else AccountProfile("1", "000000", "Default", "default", "Server", ZMQ_SERVER_URL)

    def set_active_account(self, account_id: str) -> Optional[AccountProfile]:
        acc = self.get_account_by_id(account_id)
        if acc:
            self.active_id = str(acc.id)
            self._save_active()
            try:
                from zmq_client import zmq_client
                zmq_client.switch_endpoint(acc.zmq_url)
            except Exception as e:
                logger.debug(f"Could not switch zmq_client endpoint: {e}")
            logger.info(f"Switched active account to ID {acc.id} ({acc.account_number} - {acc.name})")
            return acc
        return None

    def sync_with_live_terminal(self, acc_data: Dict[str, Any]) -> AccountProfile:
        """
        Dynamically synchronizes the active account profile with live MT4 terminal state.
        Detects whether MT4 is running DEMO or REAL, updates live account number,
        broker server name, and automatically selects the matching profile.
        """
        if not acc_data or acc_data.get("status") != "ok":
            return self.get_active_account()

        live_num = str(acc_data.get("account_number", "")).strip()
        trade_mode = str(acc_data.get("trade_mode", "")).upper()
        server = str(acc_data.get("server", "")).strip()

        is_real = (trade_mode == "REAL" or "REAL" in server.upper())
        target_id = "2" if is_real else "1"

        # Update account profile details
        for idx, acc in enumerate(self.accounts):
            if acc.id == target_id:
                updated = False
                if live_num and live_num not in ["0", "Demo Account", "Real Live"] and acc.account_number != live_num:
                    acc.account_number = live_num
                    updated = True
                if server and acc.server != server:
                    acc.server = server
                    updated = True
                if updated:
                    self._save_accounts()
                break

        # Automatically switch active account if it differs
        if self.active_id != target_id:
            self.set_active_account(target_id)

        return self.get_active_account()

    def add_or_update_account(self, id_str: str, number: str, name: str, profile: str, server: str, zmq_url: str) -> AccountProfile:
        for idx, acc in enumerate(self.accounts):
            if acc.id == id_str:
                updated = AccountProfile(id_str, number, name, profile, server, zmq_url)
                self.accounts[idx] = updated
                self._save_accounts()
                return updated
        new_acc = AccountProfile(id_str, number, name, profile, server, zmq_url)
        self.accounts.append(new_acc)
        self._save_accounts()
        return new_acc

# Global singleton
account_manager = AccountManager()
