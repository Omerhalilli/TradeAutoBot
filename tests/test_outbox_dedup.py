"""
Unit tests for Telegram outbox alert deduplication, debounce caching, and atomic file processing.
"""
import asyncio
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bot import outbox_alert_job, _recent_outbox_dispatches


class TestOutboxDeduplication(unittest.TestCase):
    def setUp(self):
        _recent_outbox_dispatches.clear()
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        _recent_outbox_dispatches.clear()

    def test_duplicate_outbox_messages_debounced(self):
        """Two identical outbox files written in rapid succession should only produce 1 dispatch."""
        msg_payload = {
            "chat_id": "987654321",
            "text": "🚀 <b>SmartAutoTradeEA Pro Online</b>\nSymbol: EURGBP (H4)",
            "parse_mode": "HTML"
        }
        f1 = os.path.join(self.test_dir, "tg_out_10_1.json")
        f2 = os.path.join(self.test_dir, "tg_out_10_2.json")
        with open(f1, "w", encoding="utf-8") as f:
            json.dump(msg_payload, f)
        with open(f2, "w", encoding="utf-8") as f:
            json.dump(msg_payload, f)

        mock_context = MagicMock()
        mock_context.bot.send_message = AsyncMock()

        with patch("bot.MT4_FILES_DIR", self.test_dir):
            asyncio.run(outbox_alert_job(mock_context))

        self.assertEqual(mock_context.bot.send_message.call_count, 1)
        self.assertEqual(len(os.listdir(self.test_dir)), 0)

    def test_distinct_outbox_messages_both_dispatched(self):
        """Distinct outbox messages should both be dispatched without suppression."""
        f1 = os.path.join(self.test_dir, "tg_out_1.json")
        f2 = os.path.join(self.test_dir, "tg_out_2.json")
        with open(f1, "w", encoding="utf-8") as f:
            json.dump({"chat_id": "111", "text": "Trade 1 Opened", "parse_mode": "HTML"}, f)
        with open(f2, "w", encoding="utf-8") as f:
            json.dump({"chat_id": "111", "text": "Trade 2 Opened", "parse_mode": "HTML"}, f)

        mock_context = MagicMock()
        mock_context.bot.send_message = AsyncMock()

        with patch("bot.MT4_FILES_DIR", self.test_dir):
            asyncio.run(outbox_alert_job(mock_context))

        self.assertEqual(mock_context.bot.send_message.call_count, 2)
        self.assertEqual(len(os.listdir(self.test_dir)), 0)

    def test_empty_or_malformed_outbox_files_cleaned_up(self):
        """Empty or invalid json files should not crash the poller and should be cleaned up."""
        empty_f = os.path.join(self.test_dir, "tg_out_empty.json")
        bad_f = os.path.join(self.test_dir, "tg_out_bad.json")
        with open(empty_f, "w", encoding="utf-8") as f:
            f.write("")
        with open(bad_f, "w", encoding="utf-8") as f:
            f.write("NOT_JSON")

        mock_context = MagicMock()
        mock_context.bot.send_message = AsyncMock()

        with patch("bot.MT4_FILES_DIR", self.test_dir):
            asyncio.run(outbox_alert_job(mock_context))

        self.assertEqual(mock_context.bot.send_message.call_count, 0)
        self.assertEqual(len(os.listdir(self.test_dir)), 0)


if __name__ == "__main__":
    unittest.main()
