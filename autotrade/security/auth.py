"""
Authentication, Authorization & Perimeter Defense Guardian.
Enforces Telegram user ID verification, token-bucket rate limiting,
IP whitelisting, and automated brute-force lockout defenses.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
import time
from typing import Dict, List, Optional, Set

from autotrade.core.config_manager import get_config

logger = logging.getLogger("autotrade.security.auth")


@dataclass
class AuthResult:
    """Outcome of security clearance check."""
    is_authorized: bool
    user_id: int
    reason: str = "Authorized"
    is_rate_limited: bool = False


class SecurityGuardian:
    """
    Perimeter authentication and anti-abuse defense system.
    """
    def __init__(self):
        self.config = get_config()
        self._user_request_timestamps: Dict[int, List[float]] = {}
        self._failed_attempts: Dict[int, int] = {}
        self._lockout_until: Dict[int, float] = {}
        self._whitelisted_ips: Set[str] = {"127.0.0.1", "::1"}

    def is_user_authorized(self, user_id: int) -> AuthResult:
        """
        Validates user identity against authorized chat IDs, lockout state, and rate limits.
        """
        now = time.time()

        # 1. Lockout Check
        if user_id in self._lockout_until:
            if now < self._lockout_until[user_id]:
                remaining = int(self._lockout_until[user_id] - now)
                return AuthResult(
                    is_authorized=False,
                    user_id=user_id,
                    reason=f"Account locked out due to suspicious activity. Try again in {remaining}s."
                )
            else:
                del self._lockout_until[user_id]
                self._failed_attempts.pop(user_id, None)

        # 2. Whitelist Check
        allowed_ids = self.config.telegram.allowed_chat_ids
        if not allowed_ids or user_id not in allowed_ids:
            self._failed_attempts[user_id] = self._failed_attempts.get(user_id, 0) + 1
            if self._failed_attempts[user_id] >= 5:
                self._lockout_until[user_id] = now + 900.0  # 15 minute lockout
                logger.warning(f"🚨 Security alert: User {user_id} locked out after 5 unauthorized attempts.")
            return AuthResult(is_authorized=False, user_id=user_id, reason="Unauthorized user ID.")

        # 3. Token-Bucket Rate Limiter Check (default 60 requests/minute)
        max_rate = self.config.telegram.rate_limit_per_minute
        if user_id not in self._user_request_timestamps:
            self._user_request_timestamps[user_id] = []

        window = self._user_request_timestamps[user_id]
        # Keep only timestamps within last 60 seconds
        self._user_request_timestamps[user_id] = [t for t in window if now - t < 60.0]

        if len(self._user_request_timestamps[user_id]) >= max_rate:
            return AuthResult(
                is_authorized=False,
                user_id=user_id,
                reason="Rate limit exceeded. Please wait a few seconds before sending another command.",
                is_rate_limited=True
            )

        self._user_request_timestamps[user_id].append(now)
        # Reset failed attempts upon successful authorized access
        self._failed_attempts.pop(user_id, None)

        return AuthResult(is_authorized=True, user_id=user_id)

    def is_ip_allowed(self, ip_address: str) -> bool:
        """Verifies if incoming IP is on institutional whitelist."""
        return ip_address in self._whitelisted_ips

    def add_ip_to_whitelist(self, ip_address: str) -> None:
        """Adds an IP to the allowed list."""
        self._whitelisted_ips.add(ip_address)
        logger.info(f"Added {ip_address} to security IP whitelist.")
