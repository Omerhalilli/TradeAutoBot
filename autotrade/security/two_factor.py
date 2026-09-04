"""
Two-Factor Authentication (2FA) & High-Privilege Action Gatekeeper.
Implements RFC 6238 Time-based One-Time Password (TOTP) verification
and dynamic cryptographic PIN challenge tokens for critical operator commands.
"""

from __future__ import annotations
from dataclasses import dataclass
import hashlib
import hmac
import logging
import secrets
import struct
import time
from typing import Dict, Optional

from autotrade.core.config_manager import get_config

logger = logging.getLogger("autotrade.security.two_factor")


@dataclass
class TOTPChallenge:
    """Represents an active 2FA authorization challenge."""
    challenge_id: str
    user_id: int
    action_name: str
    action_payload: dict
    code: str
    created_at: float
    expires_at: float


class TwoFactorAuth:
    """
    Two-Factor Authentication Guardian.
    Protects high-privilege operations (/panic, /reset_risk, limit modifications).
    """
    def __init__(self, challenge_ttl_sec: float = 60.0):
        self.config = get_config()
        self.challenge_ttl_sec = challenge_ttl_sec
        self._active_challenges: Dict[str, TOTPChallenge] = {} # {challenge_id: TOTPChallenge}
        self._user_secrets: Dict[int, str] = {}

    def is_2fa_required(self, command_name: str) -> bool:
        """Determines if the given command requires 2FA confirmation."""
        if not self.config.telegram.enable_2fa:
            return False
        critical_cmds = {"panic", "closeall", "reset_risk", "reset_prop", "emergency_halt", "set_risk"}
        return command_name.lower().lstrip("/") in critical_cmds

    def generate_challenge(self, user_id: int, action_name: str, payload: dict) -> TOTPChallenge:
        """
        Creates a time-sensitive 6-digit challenge code for the user.
        """
        now = time.time()
        challenge_id = secrets.token_hex(4)
        # Generate random 6-digit PIN
        code = f"{secrets.randbelow(900000) + 100000}"

        challenge = TOTPChallenge(
            challenge_id=challenge_id,
            user_id=user_id,
            action_name=action_name,
            action_payload=payload,
            code=code,
            created_at=now,
            expires_at=now + self.challenge_ttl_sec
        )
        self._active_challenges[challenge_id] = challenge
        logger.info(f"Generated 2FA challenge for user {user_id} on action '{action_name}'")
        return challenge

    def verify_challenge(self, challenge_id: str, user_id: int, submitted_code: str) -> bool:
        """
        Validates user submission against active challenge.
        """
        now = time.time()
        challenge = self._active_challenges.get(challenge_id)
        if not challenge:
            return False

        if challenge.user_id != user_id:
            logger.warning(f"2FA user mismatch: expected {challenge.user_id}, got {user_id}")
            return False

        if now > challenge.expires_at:
            self._active_challenges.pop(challenge_id, None)
            logger.warning(f"2FA challenge {challenge_id} expired.")
            return False

        if hmac.compare_digest(challenge.code.strip(), submitted_code.strip()):
            self._active_challenges.pop(challenge_id, None)
            logger.info(f"✅ 2FA challenge {challenge_id} successfully verified for user {user_id}")
            return True

        return False

    def generate_totp(self, secret: str, time_step: int = 30) -> str:
        """Computes standard RFC 6238 6-digit TOTP token."""
        counter = int(time.time() // time_step)
        msg = struct.pack(">Q", counter)
        key = secret.encode("utf-8")
        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset = h[-1] & 0x0F
        code_int = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
        return f"{code_int % 1000000:06d}"
