"""
Economic News Calendar & Market Sentiment Analysis Feed.
Parses economic releases, calculates sentiment polarity, evaluates currency exposure impact,
and broadcasts volatility risk warnings before high-impact events.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import logging
import re
import time
from typing import Any, Dict, List, Optional

from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.core.config_manager import get_config

logger = logging.getLogger("autotrade.data_layer.news_feed")

BULLISH_KEYWORDS = {
    "surge", "surges", "soar", "soars", "gain", "gains", "jump", "jumps", "rally", "rallies",
    "hawkish", "hike", "rate hike", "beat", "beats", "strong", "growth", "expansion", "optimism",
    "record high", "rebound", "boost", "bullish", "cooling inflation", "robust"
}

BEARISH_KEYWORDS = {
    "plunge", "plunges", "drop", "drops", "fall", "falls", "slump", "slumps", "tumble", "tumbles",
    "dovish", "cut", "rate cut", "miss", "misses", "weak", "recession", "contraction", "pessimism",
    "record low", "collapse", "crisis", "bearish", "stagflation", "default", "slowdown"
}


@dataclass
class EconomicEvent:
    """Standardized institutional economic news event schema."""
    title: str
    country: str
    date_str: str
    time_str: str
    impact: str
    forecast: str = ""
    previous: str = ""
    sentiment_score: float = 0.0
    minutes_remaining: int = 9999
    is_alerted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "country": self.country,
            "date": self.date_str,
            "time": self.time_str,
            "impact": self.impact,
            "forecast": self.forecast,
            "previous": self.previous,
            "sentiment_score": self.sentiment_score,
            "minutes_remaining": self.minutes_remaining
        }


class NewsFeedService:
    """
    Service managing economic calendar synchronization, NLP keyword sentiment extraction,
    and automated trade volatility safeguards.
    """
    def __init__(self):
        self.config = get_config()
        self._cached_events: List[EconomicEvent] = []
        self._last_fetch_time: float = 0.0
        self._cache_ttl_sec: float = 1800.0  # 30 minutes

    def analyze_sentiment(self, text: str) -> float:
        """
        Calculates sentiment polarity score (-1.0 to +1.0) using institutional financial lexicon.
        """
        clean_text = re.sub(r"[^\w\s]", " ", text.lower())
        words = set(clean_text.split())
        
        bull_count = sum(1 for kw in BULLISH_KEYWORDS if kw in clean_text)
        bear_count = sum(1 for kw in BEARISH_KEYWORDS if kw in clean_text)
        
        total = bull_count + bear_count
        if total == 0:
            return 0.0
        return round((bull_count - bear_count) / float(total), 3)

    def load_events(self) -> List[EconomicEvent]:
        """
        Loads economic events from the news_service module, scoring sentiment and parsing timing.
        """
        now = time.time()
        if self._cached_events and (now - self._last_fetch_time) < self._cache_ttl_sec:
            return self._cached_events

        try:
            # Delegate to existing news_service for data fetching
            from news_service import news_service
            raw_events = news_service.fetch_events()
            parsed: List[EconomicEvent] = []

            for ev in raw_events:
                title = ev.get("title", "")
                country = ev.get("country", "")
                impact = ev.get("impact", "Low")
                sentiment = self.analyze_sentiment(f"{title} {country}")

                event_obj = EconomicEvent(
                    title=title,
                    country=country,
                    date_str=ev.get("date", ""),
                    time_str=ev.get("time", ""),
                    impact=impact,
                    forecast=ev.get("forecast", ""),
                    previous=ev.get("previous", ""),
                    sentiment_score=sentiment,
                    minutes_remaining=ev.get("minutes_remaining", 9999)
                )
                parsed.append(event_obj)

            self._cached_events = parsed
            self._last_fetch_time = now
            logger.info(f"NewsFeedService refreshed {len(parsed)} economic calendar events.")
            return parsed
        except Exception as ex:
            logger.error(f"Failed to load economic events: {ex}")
            return self._cached_events

    async def check_due_alerts(self) -> List[EconomicEvent]:
        """
        Checks for upcoming high-impact economic news within the reminder lead window
        and broadcasts risk alerts.
        """
        events = self.load_events()
        due: List[EconomicEvent] = []
        lead_min = self.config.news.reminder_lead_minutes

        for ev in events:
            if ev.impact in ("High", "Medium") and 0 <= ev.minutes_remaining <= lead_min:
                if not ev.is_alerted:
                    ev.is_alerted = True
                    due.append(ev)
                    
                    event_bus.publish(
                        EventType.NEWS_ALERT,
                        payload=ev.to_dict(),
                        priority=EventPriority.HIGH,
                        source="NewsFeedService"
                    )
        return due

    def is_currency_impacted_soon(self, currency: str, window_minutes: int = 30) -> bool:
        """
        Checks if a given currency (e.g. USD, GBP, EUR) has high-impact news in the next `window_minutes`.
        Used by the RiskManager to reduce lot size or halt entries.
        """
        events = self.load_events()
        curr_upper = currency.upper()
        for ev in events:
            if ev.impact == "High" and ev.country.upper() == curr_upper:
                if 0 <= ev.minutes_remaining <= window_minutes:
                    return True
        return False
