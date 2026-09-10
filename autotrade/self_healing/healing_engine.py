"""
Structured Error Boundary & System Integrity Engine.
Replaces legacy runtime source code mutation with strict immutability,
comprehensive diagnostic audits, circuit breaker containment, and Telegram escalation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional

from autotrade.self_healing.compiler import SourceCompiler, CompilationErrorDetail
from autotrade.self_healing.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

logger = logging.getLogger("autotrade.self_healing.healing_engine")


@dataclass
class RepairCandidate:
    """Represents a diagnostic issue identified by AST or syntax inspection."""
    file_path: str
    line_number: int
    original_line: str
    proposed_line: str
    repair_strategy: str
    confidence: float = 1.0


@dataclass
class RepairReport:
    """Consolidated system integrity and diagnostic report."""
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    resolved: bool = False
    details: List[Dict[str, Any]] = field(default_factory=list)
    telegram_report: str = ""


class HealingEngine:
    """
    System Integrity Guardian.
    Enforces production code immutability: NEVER modifies or rewrites source files on disk.
    Diagnoses syntax/AST anomalies, trips circuit breakers, and generates forensic reports.
    """
    def __init__(self, compiler: Optional[SourceCompiler] = None, max_attempts: int = 1):
        self.compiler = compiler or SourceCompiler()
        self.max_attempts = max_attempts
        self.circuit_breaker = CircuitBreaker("CodeIntegrityBreaker", CircuitBreakerConfig(failure_threshold=1, recovery_timeout_sec=300.0))

    async def heal_compilation_errors(self, error_details: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Asynchronously evaluates compilation errors without modifying source files on disk."""
        import asyncio
        loop = asyncio.get_running_loop()
        report: RepairReport = await loop.run_in_executor(None, self.heal_compilation_errors_sync, error_details)
        return {
            "attempted": report.attempted,
            "succeeded": report.succeeded,
            "failed": report.failed,
            "resolved": report.resolved,
            "details": report.details,
            "telegram_report": report.telegram_report
        }

    def heal_compilation_errors_sync(self, error_details: List[Dict[str, Any]]) -> RepairReport:
        """
        Evaluates source integrity synchronously.
        Enforces code immutability: logs diagnostics and trips circuit breakers rather than modifying disk files.
        """
        report = RepairReport()
        check = self.compiler.compile_all_sync()
        if check.success:
            report.resolved = True
            self.circuit_breaker.record_success()
            logger.info("✅ Code Integrity check PASSED. All source modules compiled cleanly.")
            return report

        # Compilation errors present
        report.attempted = len(check.error_details)
        report.failed = len(check.error_details)
        report.resolved = False
        self.circuit_breaker.record_failure(RuntimeError(f"{len(check.error_details)} syntax/compilation faults detected"))

        lines = [
            "🚨 <b>AUTOTRADE COMPILER FAULT DETECTED</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"⚠️ <b>Total Anomalies:</b> {len(check.error_details)}",
            "🛡️ <b>Production Immutability Enforced:</b> Self-modifying source rewrite blocked.",
            "🔒 <b>Safeguard Mode Activated:</b> Auto-trading halted for capital protection.",
            ""
        ]

        for err in check.error_details[:5]:
            report.details.append({
                "file": err.file_path,
                "line": err.line_number,
                "message": err.message,
                "type": err.error_type
            })
            lines.append(f"• <code>{err.file_path}:{err.line_number}</code> - {err.message}")

        report.telegram_report = "\n".join(lines)
        logger.error(f"Code integrity check failed with {len(check.error_details)} errors. Immutability preserved.")
        return report
