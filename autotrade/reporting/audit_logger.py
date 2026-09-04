"""
Structured Trade & System Audit Logger.
Maintains forensic chronological logs of all order events, risk validations,
strategy signal emissions, compiler repairs, and parameter adjustments.
"""

from __future__ import annotations
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from autotrade.core.event_bus import event_bus, EventType, Event
from autotrade.data_layer.database import DatabaseEngine, db_engine

logger = logging.getLogger("autotrade.reporting.audit_logger")


class AuditLogger:
    """
    Forensic audit logger writing structured telemetry to SQLite and files.
    """
    def __init__(self, database: Optional[DatabaseEngine] = None, audit_file_path: Optional[str] = None):
        self.db = database or db_engine
        self.audit_file_path = audit_file_path or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "logs", "audit.jsonl")
        )
        os.makedirs(os.path.dirname(self.audit_file_path), exist_ok=True)

        # Wire up audit listeners on EventBus
        event_bus.subscribe("order.*", self._on_order_event)
        event_bus.subscribe("risk.*", self._on_risk_event)
        event_bus.subscribe("compiler.*", self._on_compiler_event)

    def log(self, category: str, level: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Records an audit log entry to SQLite and append-only JSON Lines file."""
        now = time.time()
        det = details or {}
        
        # 1. Write to database
        self.db.record_audit(category, level, message, det)

        # 2. Append to JSONL audit file
        entry = {
            "timestamp": now,
            "category": category,
            "level": level,
            "message": message,
            "details": det
        }
        try:
            with open(self.audit_file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as ex:
            logger.debug(f"Failed to append to audit log file: {ex}")

    def _on_order_event(self, event: Event) -> None:
        """Audit listener for all order-related events."""
        self.log(
            category="ORDER",
            level="INFO",
            message=f"Order Event: {event.event_type}",
            details=event.payload
        )

    def _on_risk_event(self, event: Event) -> None:
        """Audit listener for risk checks and breaches."""
        level = "CRITICAL" if "breached" in str(event.event_type) or "halt" in str(event.event_type) else "INFO"
        self.log(
            category="RISK",
            level=level,
            message=f"Risk Event: {event.event_type}",
            details=event.payload
        )

    def _on_compiler_event(self, event: Event) -> None:
        """Audit listener for compilation and self-healing operations."""
        self.log(
            category="SELF_HEALING",
            level="INFO",
            message=f"Compiler Event: {event.event_type}",
            details=event.payload
        )
