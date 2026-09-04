"""
Security & Authentication Layer.
Provides AES-256 cryptographic encryption for credentials, IP whitelisting,
token-bucket rate limiting, brute-force shields, and TOTP Two-Factor Authentication (2FA).
"""

from autotrade.security.crypto_manager import CryptoManager, crypto_manager
from autotrade.security.auth import SecurityGuardian, AuthResult
from autotrade.security.two_factor import TwoFactorAuth, TOTPChallenge

__all__ = [
    "CryptoManager",
    "crypto_manager",
    "SecurityGuardian",
    "AuthResult",
    "TwoFactorAuth",
    "TOTPChallenge",
]
