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

    def test_router_2fa_and_callback_handling(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from autotrade.telegram_interface.command_router import command_router

        async def run_checks():
            command_router.config.telegram.allowed_chat_ids = [123456789]
            command_router.config.telegram.enable_2fa = True

            # Test confirm_close_all triggers 2FA prompt
            update = MagicMock()
            update.effective_user.id = 123456789
            update.message = None
            update.callback_query.data = "confirm_close_all"
            update.callback_query.answer = AsyncMock()
            update.callback_query.edit_message_text = AsyncMock()
            context = MagicMock()

            await command_router.handle_callback_query(update, context)
            update.callback_query.edit_message_text.assert_called()
            call_args = update.callback_query.edit_message_text.call_args[0][0]
            self.assertIn("TWO-FACTOR AUTHENTICATION", call_args)

            # Verify active challenge exists
            self.assertGreater(len(command_router.two_factor._active_challenges), 0)
            ch_id = list(command_router.two_factor._active_challenges.keys())[-1]
            ch_code = command_router.two_factor._active_challenges[ch_id].code

            # Test cmd_verify with valid code
            update_verify = MagicMock()
            update_verify.effective_user.id = 123456789
            update_verify.message.reply_text = AsyncMock()
            context_verify = MagicMock()
            context_verify.args = [ch_id, ch_code]

            await command_router.cmd_verify(update_verify, context_verify)
            update_verify.message.reply_text.assert_called()
            resp = update_verify.message.reply_text.call_args[0][0]
            self.assertIn("EMERGENCY HALT COMPLETED", resp)

            # Test strat_toggle callback
            update_strat = MagicMock()
            update_strat.effective_user.id = 123456789
            update_strat.message = None
            update_strat.callback_query.data = "strat_toggle:TrendFollowingStrategy:disable"
            update_strat.callback_query.answer = AsyncMock()
            update_strat.callback_query.edit_message_text = AsyncMock()
            await command_router.handle_callback_query(update_strat, context)
            self.assertNotIn("TrendFollowingStrategy", command_router.config.strategy.active_strategies)

            # Restore
            command_router.config.telegram.enable_2fa = False

        asyncio.run(run_checks())


if __name__ == "__main__":
    unittest.main()
