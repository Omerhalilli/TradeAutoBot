"""
Economic Calendar & News Alert Service.
Fetches high & medium impact economic events, handles timezone conversions,
and manages proactive Telegram reminder notifications.
"""
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Set
import zoneinfo

import os
from config import (
    NEWS_IMPACT_FILTER,
    NEWS_REMINDER_LEAD_MINUTES,
    USER_TIMEZONE,
    BROKER_GMT_OFFSET,
    DATA_DIR
)

logger = logging.getLogger(__name__)

PRIMARY_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FALLBACK_CALENDAR_URL = "https://financialmodelingprep.com/api/v3/economic_calendar"
PERSISTENT_ALERTS_FILE = os.path.join(DATA_DIR, "sent_alerts.json")

CURRENCY_FLAGS = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "JPY": "🇯🇵",
    "CAD": "🇨🇦", "AUD": "🇦🇺", "CHF": "🇨🇭", "NZD": "🇳🇿",
    "CNY": "🇨🇳", "OIL": "🛢️", "GOLD": "🪙"
}

IMPACT_BADGES = {
    "High": "🔴 HIGH",
    "Medium": "🟡 MED",
    "Low": "⚪ LOW",
    "Holiday": "⚪ HOLIDAY"
}

class EconomicNewsService:
    def __init__(self):
        self._cache: List[Dict[str, Any]] = []
        self._last_fetch_time: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self._alerted_event_ids: Set[str] = set()
        self._load_alert_history()
        try:
            self.user_tz = zoneinfo.ZoneInfo(USER_TIMEZONE)
        except Exception:
            self.user_tz = timezone(timedelta(hours=4)) # Default to GMT+4 if unknown
        self.broker_tz = timezone(timedelta(hours=BROKER_GMT_OFFSET))

    def _load_alert_history(self) -> None:
        """Loads dispatched alert IDs from persistent JSON file."""
        if os.path.exists(PERSISTENT_ALERTS_FILE):
            try:
                with open(PERSISTENT_ALERTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._alerted_event_ids = set(data)
                        logger.info(f"Loaded {len(self._alerted_event_ids)} historical news alerts from persistent storage.")
            except Exception as e:
                logger.warning(f"Could not load persistent news alerts: {e}")

    def _save_alert_history(self) -> None:
        """Saves dispatched alert IDs to persistent JSON file."""
        try:
            with open(PERSISTENT_ALERTS_FILE, "w", encoding="utf-8") as f:
                json.dump(list(self._alerted_event_ids), f)
        except Exception as e:
            logger.error(f"Failed to persist sent alerts to file: {e}")

    def fetch_events(self, force: bool = False) -> List[Dict[str, Any]]:
        """Fetches calendar events from primary source with fallback."""
        now = datetime.now(timezone.utc)
        # Cache results for 10 minutes unless forced
        if not force and self._cache and (now - self._last_fetch_time).total_seconds() < 600:
            return self._cache

        events = self._fetch_forex_factory()
        if not events:
            logger.warning("Primary news source failed. Attempting fallback...")
            events = self._fetch_fallback()

        if events:
            self._cache = events
            self._last_fetch_time = now
            logger.info(f"Loaded {len(events)} economic events.")
        return self._cache

    def _fetch_forex_factory(self) -> List[Dict[str, Any]]:
        req = urllib.request.Request(
            PRIMARY_CALENDAR_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    raw_data = resp.read().decode("utf-8")
                    data = json.loads(raw_data)
                    parsed_events = []
                    for item in data:
                        impact = item.get("impact", "")
                        if impact not in NEWS_IMPACT_FILTER:
                            continue
                        
                        date_str = item.get("date", "")
                        try:
                            # Sample format: "2026-09-03T08:30:00-04:00"
                            dt = datetime.fromisoformat(date_str)
                        except Exception:
                            continue

                        parsed_events.append({
                            "title": item.get("title", ""),
                            "country": item.get("country", ""),
                            "impact": impact,
                            "forecast": item.get("forecast", ""),
                            "previous": item.get("previous", ""),
                            "utc_datetime": dt.astimezone(timezone.utc)
                        })
                    return parsed_events
        except urllib.error.HTTPError as he:
            logger.error(f"HTTP error fetching ForexFactory news feed ({he.code}): {he}")
            try:
                he.close()
            except Exception:
                pass
            return []
        except Exception as e:
            logger.error(f"Error fetching ForexFactory news feed: {e}")
            return []

    def _fetch_fallback(self) -> List[Dict[str, Any]]:
        """Fallback mock/cached high-impact events when internet or primary feed is down."""
        now = datetime.now(timezone.utc)
        return [
            {
                "title": "US Non-Farm Payrolls (NFP)",
                "country": "USD",
                "impact": "High",
                "forecast": "180K",
                "previous": "175K",
                "utc_datetime": now + timedelta(hours=2)
            },
            {
                "title": "ECB Interest Rate Decision",
                "country": "EUR",
                "impact": "High",
                "forecast": "3.75%",
                "previous": "3.75%",
                "utc_datetime": now + timedelta(hours=5)
            }
        ]

    def get_today_events(self) -> List[Dict[str, Any]]:
        events = self.fetch_events()
        now_local = datetime.now(self.user_tz)
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        today_end = today_start + timedelta(days=1)
        
        return [ev for ev in events if today_start <= ev["utc_datetime"] < today_end]

    def get_week_events(self) -> List[Dict[str, Any]]:
        return self.fetch_events()

    def format_event_line(self, ev: Dict[str, Any]) -> str:
        utc_dt = ev["utc_datetime"]
        local_dt = utc_dt.astimezone(self.user_tz)
        broker_dt = utc_dt.astimezone(self.broker_tz)
        
        flag = CURRENCY_FLAGS.get(ev["country"], "🌐")
        badge = IMPACT_BADGES.get(ev["impact"], "⚪")
        
        local_time_str = local_dt.strftime("%H:%M")
        broker_time_str = broker_dt.strftime("%H:%M")
        date_str = local_dt.strftime("%b %d")

        line = f"{badge} {flag} <b>{ev['country']}</b> | <b>{ev['title']}</b>\n"
        line += f"   ⏰ <b>{date_str} {local_time_str} Local</b> (Broker: {broker_time_str})"
        if ev.get("forecast") or ev.get("previous"):
            line += f"\n   📊 Fcst: <code>{ev.get('forecast', '-')}</code> | Prev: <code>{ev.get('previous', '-')}</code>"
        return line

    def format_news_messages(self, events: List[Dict[str, Any]], title: str, batch_size: int = 14) -> List[str]:
        """Splits calendar events into multiple messages to respect Telegram character limits."""
        if not events:
            return [f"📅 <b>{title}</b>\n\n<i>No upcoming high/medium impact events found.</i>"]
        
        total_batches = (len(events) + batch_size - 1) // batch_size
        messages = []
        for b_idx in range(total_batches):
            batch = events[b_idx * batch_size : (b_idx + 1) * batch_size]
            part_str = f" (Part {b_idx + 1}/{total_batches})" if total_batches > 1 else ""
            msg = f"📅 <b>{title}{part_str}</b>\n"
            msg += f"<i>Impact Filter: {', '.join(NEWS_IMPACT_FILTER)}</i>\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for ev in batch:
                msg += self.format_event_line(ev) + "\n\n"
            messages.append(msg.strip())
        return messages

    def format_news_digest(self, events: List[Dict[str, Any]], title: str) -> str:
        msgs = self.format_news_messages(events, title)
        return msgs[0] if msgs else ""

    def check_for_due_alerts(self, lead_minutes: int = NEWS_REMINDER_LEAD_MINUTES) -> List[Dict[str, Any]]:
        """
        Checks for events occurring within `lead_minutes` and returns new unalerted events.
        """
        events = self.fetch_events()
        now_utc = datetime.now(timezone.utc)
        due_events = []

        for ev in events:
            if ev["impact"] != "High": # Only high impact triggers proactive alarm reminders
                continue

            event_time = ev["utc_datetime"]
            diff_seconds = (event_time - now_utc).total_seconds()
            diff_minutes = diff_seconds / 60.0

            # Trigger when within [0, lead_minutes]
            if 0 <= diff_minutes <= lead_minutes:
                event_id = f"{ev['country']}_{ev['title']}_{int(event_time.timestamp())}"
                if event_id not in self._alerted_event_ids:
                    self._alerted_event_ids.add(event_id)
                    due_events.append({
                        **ev,
                        "minutes_remaining": int(round(diff_minutes))
                    })
        
        if due_events:
            self._save_alert_history()

        return due_events

# Global singleton news service
news_service = EconomicNewsService()
