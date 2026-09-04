"""
Unit tests for Cryptography, Security Guardian, and Two-Factor Authentication.
"""

import unittest
from autotrade.security.crypto_manager import CryptoManager
from autotrade.security.auth import SecurityGuardian
from autotrade.security.two_factor import TwoFactorAuth


class TestSecurity(unittest.TestCase):
    def setUp(self):
        self.crypto = CryptoManager()
        self.sec = SecurityGuardian()
        self.two_fa = TwoFactorAuth()

    def test_aes256_encryption_decryption(self):
        secret = "Institutional_API_Secret_Key_987654"
        cipher = self.crypto.encrypt(secret)
        self.assertNotEqual(secret, cipher)
        decrypted = self.crypto.decrypt(cipher)
        self.assertEqual(secret, decrypted)

    def test_security_auth_whitelist_and_rate_limit(self):
        # Configure allowed IDs
        self.sec.config.telegram.allowed_chat_ids = [123456789]
        self.sec.config.telegram.rate_limit_per_minute = 5

        # 1. Allowed user
        res_ok = self.sec.is_user_authorized(123456789)
        self.assertTrue(res_ok.is_authorized)

        # 2. Unauthorized user
        res_fail = self.sec.is_user_authorized(999999999)
        self.assertFalse(res_fail.is_authorized)

        # 3. Rate limiting check
        for _ in range(5):
            self.sec.is_user_authorized(123456789)
        res_limited = self.sec.is_user_authorized(123456789)
        self.assertTrue(res_limited.is_rate_limited)

    def test_two_factor_auth_challenge(self):
        challenge = self.two_fa.generate_challenge(
            user_id=123456789,
            action_name="panic",
            payload={"ticket": 0}
        )
        self.assertEqual(len(challenge.code), 6)

        # Incorrect PIN
        self.assertFalse(self.two_fa.verify_challenge(challenge.challenge_id, 123456789, "000000"))

        # Valid PIN
        self.assertTrue(self.two_fa.verify_challenge(challenge.challenge_id, 123456789, challenge.code))


if __name__ == "__main__":
    unittest.main()
