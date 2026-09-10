"""
Production Error Boundary & Circuit Breaker System.
Enforces production source code immutability. Replaces hazardous on-the-fly source code modification
with formal stateful circuit breakers, isolated error boundaries, and fail-safe execution containment.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import functools
import logging
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("autotrade.self_healing.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"       # Normal operation
    OPEN = "OPEN"           # Tripped: Execution halted / protected
    HALF_OPEN = "HALF_OPEN" # Probing recovery


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    recovery_timeout_sec: float = 60.0
    half_open_success_threshold: int = 2


class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while the circuit breaker is in OPEN state."""
    pass


class CircuitBreaker:
    """
    Production-grade Circuit Breaker.
    Maintains system integrity by arresting catastrophic cascades when consecutive faults occur.
    """
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change = time.time()
        self.last_failure_time = 0.0
        self.trip_history: List[Dict[str, Any]] = []

    def record_success(self) -> None:
        """Registers successful operation."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.half_open_success_threshold:
                self._transition_to(CircuitState.CLOSED, "Recovery threshold satisfied in HALF_OPEN state.")
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self, error: Optional[Exception] = None) -> None:
        """Registers failed operation and trips breaker if threshold is breached."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        logger.warning(
            f"CircuitBreaker [{self.name}]: Failure recorded ({self.failure_count}/{self.config.failure_threshold}). "
            f"Error: {error}"
        )
        if self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN) and self.failure_count >= self.config.failure_threshold:
            self._transition_to(CircuitState.OPEN, f"Failure threshold reached ({self.failure_count}). Error: {error}")

    def can_execute(self) -> bool:
        """Determines whether operations are permitted through the circuit breaker."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self.last_state_change
            if elapsed >= self.config.recovery_timeout_sec:
                self._transition_to(CircuitState.HALF_OPEN, f"Recovery timeout ({self.config.recovery_timeout_sec}s) elapsed.")
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            return True
        return False

    def reset(self) -> None:
        """Manually resets circuit breaker to CLOSED state."""
        self._transition_to(CircuitState.CLOSED, "Manual operator reset.")
        self.failure_count = 0
        self.success_count = 0

    def _transition_to(self, new_state: CircuitState, reason: str) -> None:
        old_state = self.state
        self.state = new_state
        self.last_state_change = time.time()
        if new_state == CircuitState.CLOSED:
            self.failure_count = 0
            self.success_count = 0
        logger.info(f"CircuitBreaker [{self.name}]: Transition {old_state.value} -> {new_state.value}. Reason: {reason}")
        self.trip_history.append({
            "timestamp": self.last_state_change,
            "from": old_state.value,
            "to": new_state.value,
            "reason": reason
        })

    def __call__(self, fn: Callable) -> Callable:
        """Decorator wrapping target function with circuit breaker protection."""
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not self.can_execute():
                raise CircuitBreakerOpenException(f"CircuitBreaker [{self.name}] is OPEN. Execution blocked.")
            try:
                res = fn(*args, **kwargs)
                self.record_success()
                return res
            except Exception as ex:
                self.record_failure(ex)
                raise
        return wrapper
