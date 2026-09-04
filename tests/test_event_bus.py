"""
Unit tests for High-Throughput Asynchronous Priority EventBus.
"""

import asyncio
import unittest
import time
from autotrade.core.event_bus import EventBus, Event, EventType, EventPriority


class TestEventBus(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus(queue_capacity=1000)

    def tearDown(self):
        self.bus.clear()

    def test_priority_ordering(self):
        ev_low = Event(priority=EventPriority.LOW, event_type=EventType.SYSTEM_HEARTBEAT)
        ev_crit = Event(priority=EventPriority.CRITICAL, event_type=EventType.EMERGENCY_HALT)
        ev_norm = Event(priority=EventPriority.NORMAL, event_type=EventType.TICK)

        events = [ev_low, ev_crit, ev_norm]
        events.sort()

        self.assertEqual(events[0].priority, EventPriority.CRITICAL)
        self.assertEqual(events[1].priority, EventPriority.NORMAL)
        self.assertEqual(events[2].priority, EventPriority.LOW)

    def test_wildcard_subscription(self):
        received = []
        def handler(event):
            received.append(event.event_type)

        self.bus.subscribe("market.*", handler)
        matched = self.bus._get_matching_handlers(EventType.TICK)
        self.assertIn(handler, matched)

        matched_bar = self.bus._get_matching_handlers(EventType.BAR_COMPLETED)
        self.assertIn(handler, matched_bar)

        matched_unrelated = self.bus._get_matching_handlers(EventType.ORDER_FILLED)
        self.assertNotIn(handler, matched_unrelated)

    def test_async_dispatch_cycle(self):
        async def run_test():
            received = []
            async def test_handler(event: Event):
                received.append(event.payload.get("val"))

            self.bus.subscribe(EventType.TICK, test_handler)
            await self.bus.start()

            self.bus.publish(EventType.TICK, payload={"val": 42}, priority=EventPriority.NORMAL)
            await asyncio.sleep(0.05)
            await self.bus.stop()

            self.assertIn(42, received)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
