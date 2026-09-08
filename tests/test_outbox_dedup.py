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


    def test_empty_chat_id_falls_back_to_allowed_chat_ids(self):
        """When outbox file has empty chat_id, message should fall back to ALLOWED_CHAT_IDS."""
        f1 = os.path.join(self.test_dir, "tg_out_fallback.json")
        with open(f1, "w", encoding="utf-8") as f:
            json.dump({"chat_id": "", "text": "🚀 <b>SmartAutoTradeEA Pro Online</b>", "parse_mode": "HTML"}, f)

        mock_context = MagicMock()
        mock_context.bot.send_message = AsyncMock()

        with patch("bot.MT4_FILES_DIR", self.test_dir), patch("bot.ALLOWED_CHAT_IDS", [123456789]):
            asyncio.run(outbox_alert_job(mock_context))

        self.assertEqual(mock_context.bot.send_message.call_count, 1)
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=123456789,
            text="🚀 <b>SmartAutoTradeEA Pro Online</b>",
            parse_mode=unittest.mock.ANY,
            reply_markup=None,
            disable_web_page_preview=True
        )

    def test_debounce_cache_pruning_in_place(self):
        """Debounce cache pruning must evict expired entries (>60s) while preserving dict object identity."""
        initial_dict_id = id(_recent_outbox_dispatches)
        old_time = time.time() - 100.0
        # Populate over 200 entries to trigger pruning
        for i in range(205):
            _recent_outbox_dispatches[(f"chat_{i}", f"sig_{i}")] = old_time
        # Add 1 fresh entry
        _recent_outbox_dispatches[("fresh_chat", "fresh_sig")] = time.time()

        # Run outbox_alert_job with empty dir to trigger post-loop pruning
        mock_context = MagicMock()
        with patch("bot.MT4_FILES_DIR", self.test_dir):
            asyncio.run(outbox_alert_job(mock_context))

        self.assertEqual(id(_recent_outbox_dispatches), initial_dict_id, "Cache dictionary object identity must be preserved")
        self.assertIn(("fresh_chat", "fresh_sig"), _recent_outbox_dispatches)
        self.assertEqual(len(_recent_outbox_dispatches), 1)

    def test_timeframe_specific_messages_not_suppressed(self):
        """Messages for different timeframes on same symbol should both be dispatched."""
        f1 = os.path.join(self.test_dir, "tg_out_h1.json")
        f2 = os.path.join(self.test_dir, "tg_out_m15.json")
        with open(f1, "w", encoding="utf-8") as f:
            json.dump({"chat_id": "111", "text": "Online EURUSD (H1)", "parse_mode": "HTML"}, f)
        with open(f2, "w", encoding="utf-8") as f:
            json.dump({"chat_id": "111", "text": "Online EURUSD (M15)", "parse_mode": "HTML"}, f)

        mock_context = MagicMock()
        mock_context.bot.send_message = AsyncMock()

        with patch("bot.MT4_FILES_DIR", self.test_dir):
            asyncio.run(outbox_alert_job(mock_context))

        self.assertEqual(mock_context.bot.send_message.call_count, 2)
        self.assertEqual(len(os.listdir(self.test_dir)), 0)

    def test_outbox_photo_dispatched_and_cleaned_up(self):
        """Outbox payload with a photo should dispatch via send_photo and clean up image file."""
        photo_filename = "Entry_12345.png"
        photo_path = os.path.join(self.test_dir, photo_filename)
        with open(photo_path, "wb") as pf:
            pf.write(b"PNG_FAKE_IMAGE_DATA_PADDING_BYTE_ARRAY" * 10)  # > 100 bytes

        payload = {
            "chat_id": "999888",
            "photo": photo_filename,
            "text": "<b>SELL EURUSD</b> opened",
            "parse_mode": "HTML"
        }
        json_path = os.path.join(self.test_dir, "tg_out_photo.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        mock_context = MagicMock()
        mock_context.bot.send_photo = AsyncMock()
        mock_context.bot.send_message = AsyncMock()

        with patch("bot.MT4_FILES_DIR", self.test_dir):
            asyncio.run(outbox_alert_job(mock_context))

        self.assertEqual(mock_context.bot.send_photo.call_count, 1)
        self.assertEqual(mock_context.bot.send_message.call_count, 0)
        # Ensure image file and json file were both cleaned up
        self.assertFalse(os.path.exists(photo_path))
        self.assertFalse(os.path.exists(json_path))

    def test_outbox_photo_missing_file_falls_back_to_send_message(self):
        """If referenced photo file does not exist, outbox poller falls back to send_message cleanly."""
        payload = {
            "chat_id": "999888",
            "photo": "non_existent.png",
            "text": "<b>SELL EURUSD</b> opened",
            "parse_mode": "HTML"
        }
        json_path = os.path.join(self.test_dir, "tg_out_missing_photo.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        mock_context = MagicMock()
        mock_context.bot.send_photo = AsyncMock()
        mock_context.bot.send_message = AsyncMock()

        with patch("bot.MT4_FILES_DIR", self.test_dir):
            asyncio.run(outbox_alert_job(mock_context))

        self.assertEqual(mock_context.bot.send_photo.call_count, 0)
        self.assertEqual(mock_context.bot.send_message.call_count, 1)
        self.assertFalse(os.path.exists(json_path))


if __name__ == "__main__":
    unittest.main()

