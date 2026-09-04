"""
Automated AI-Assisted Source Code Error Correction & Self-Healing Engine.
Analyzes syntax, compilation, import, and AST anomalies, generates candidate patches,
validates them via isolated recompilation, and safely rewrites code with rollback protection.
Dispatches detailed Telegram reports when human intervention is required.
"""

from __future__ import annotations
import ast
from dataclasses import dataclass, field
import difflib
import logging
import os
import py_compile
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

from autotrade.core.event_bus import event_bus, EventType, EventPriority
from autotrade.self_healing.compiler import SourceCompiler, CompilationErrorDetail

logger = logging.getLogger("autotrade.self_healing.healing_engine")


@dataclass
class RepairCandidate:
    """A proposed code patch for a detected syntax or runtime anomaly."""
    file_path: str
    line_number: int
    original_line: str
    proposed_line: str
    repair_strategy: str
    confidence: float = 1.0


@dataclass
class RepairReport:
    """Report detailing the self-healing attempts and resolution status."""
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    resolved: bool = False
    details: List[Dict[str, Any]] = field(default_factory=list)
    telegram_report: str = ""


class HealingEngine:
    """
    Self-healing engine capable of parsing, diagnosing, and repairing source code defects.
    Features:
    - Multi-stage diagnostic pattern matching
    - AST-guided structural synthesis
    - Re-compilation validation loop
    - Automated rollback on candidate failure
    - Detailed emergency dispatch generation
    """
    def __init__(self, compiler: Optional[SourceCompiler] = None, max_attempts: int = 5):
        self.compiler = compiler or SourceCompiler()
        self.max_attempts = max_attempts
        self._backup_suffix = ".pre_heal.bak"

    async def heal_compilation_errors(self, error_details: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Asynchronously runs the iterative self-healing cycle across all detected compilation errors.
        """
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
        Synchronous healing loop. Attempts candidate patches and re-tests compilation.
        Iterates repeatedly until no errors remain or max_attempts is reached.
        """
        report = RepairReport()
        logger.info(f"Self-Healing Engine initiated for compilation anomalies (max {self.max_attempts} passes)...")

        for iteration in range(self.max_attempts):
            # Check current compilation status
            check = self.compiler.compile_all_sync()
            if check.success:
                report.resolved = True
                logger.info(f"✅ Self-Healing completed successfully at iteration {iteration + 1}. All code compiled cleanly.")
                break

            current_errors = [
                {
                    "file_path": e.file_path,
                    "line_number": e.line_number,
                    "message": e.message,
                    "error_type": e.error_type
                }
                for e in check.error_details
            ] if iteration > 0 else (error_details or [
                {
                    "file_path": e.file_path,
                    "line_number": e.line_number,
                    "message": e.message,
                    "error_type": e.error_type
                }
                for e in check.error_details
            ])

            if not current_errors:
                report.resolved = True
                break

            any_healed_this_pass = False

            for err in current_errors:
                file_path = err.get("file_path", "")
                lineno = err.get("line_number", 1)
                msg = err.get("message", "")
                err_type = err.get("error_type", "SyntaxError")

                if not os.path.exists(file_path):
                    continue

                report.attempted += 1
                success = self._attempt_file_heal(file_path, lineno, msg, err_type)

                if success:
                    any_healed_this_pass = True
                    report.succeeded += 1
                    report.details.append({
                        "file": file_path,
                        "line": lineno,
                        "status": "HEALED",
                        "error": msg,
                        "pass": iteration + 1
                    })
                    logger.info(f"✅ Successfully healed {file_path}:{lineno} (pass {iteration + 1})")
                    event_bus.publish(
                        EventType.SELF_HEAL_RESOLVED,
                        payload={"file": file_path, "line": lineno},
                        priority=EventPriority.HIGH,
                        source="HealingEngine"
                    )
                else:
                    report.failed += 1
                    report.details.append({
                        "file": file_path,
                        "line": lineno,
                        "status": "FAILED",
                        "error": msg,
                        "pass": iteration + 1
                    })
                    logger.error(f"❌ Failed to heal {file_path}:{lineno}")

            if not any_healed_this_pass:
                # No progress could be made in this pass
                break

        # Final verification
        final_check = self.compiler.compile_all_sync()
        report.resolved = final_check.success

        if not report.resolved:
            report.telegram_report = self._format_telegram_failure_report(final_check.error_details)
            event_bus.publish(
                EventType.TELEGRAM_NOTIFICATION,
                payload={"message": report.telegram_report, "priority": "CRITICAL"},
                priority=EventPriority.CRITICAL,
                source="HealingEngine"
            )

        return report

    def _attempt_file_heal(self, file_path: str, lineno: int, error_msg: str, error_type: str) -> bool:
        """Generates candidate repairs for a file and evaluates their compilation in isolation."""
        backup_path = file_path + self._backup_suffix
        try:
            shutil.copy2(file_path, backup_path)
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            if lineno > len(lines) or lineno < 1:
                return False

            # Candidate pool: primary line candidates + preceding line candidates
            # (as Python syntax errors are frequently reported on the token following the defect)
            candidates: List[RepairCandidate] = []

            faulty_line = lines[lineno - 1]
            candidates.extend(self._generate_candidates(faulty_line, lines, lineno, error_msg, error_type))

            if lineno > 1:
                prev_line = lines[lineno - 2]
                candidates.extend(self._generate_candidates(prev_line, lines, lineno - 1, error_msg, error_type))

            for cand in candidates:
                target_idx = cand.line_number - 1
                if target_idx < 0 or target_idx >= len(lines):
                    continue

                test_lines = list(lines)
                test_lines[target_idx] = cand.proposed_line

                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(test_lines)

                # Recompile test
                if self._verify_isolated_compile(file_path):
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    return True
                else:
                    shutil.copy2(backup_path, file_path)

            shutil.copy2(backup_path, file_path)
            if os.path.exists(backup_path):
                os.remove(backup_path)
            return False
        except Exception as ex:
            logger.error(f"Exception during file healing of {file_path}: {ex}")
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, file_path)
                os.remove(backup_path)
            return False

    def _generate_candidates(
        self,
        faulty_line: str,
        all_lines: List[str],
        lineno: int,
        error_msg: str,
        error_type: str
    ) -> List[RepairCandidate]:
        """
        Generates prioritized repair candidates based on heuristic and algorithmic syntax rules.
        """
        candidates: List[RepairCandidate] = []
        stripped = faulty_line.strip()

        # Strategy 1: Missing colon after block statement
        block_keywords = ("def ", "class ", "if ", "elif ", "else:", "while ", "for ", "try:", "except", "finally:", "with ", "async def ", "async for ", "async with ")
        if any(stripped.startswith(kw) for kw in block_keywords) and not stripped.endswith(":"):
            # Check if there is an inline comment
            if "#" in faulty_line:
                code_part, comment = faulty_line.split("#", 1)
                fixed = code_part.rstrip() + ": #" + comment
            else:
                fixed = faulty_line.rstrip() + ":\n"
            candidates.append(RepairCandidate(
                file_path="", line_number=lineno,
                original_line=faulty_line, proposed_line=fixed,
                repair_strategy="Append missing colon to block header", confidence=0.95
            ))

        # Strategy 2: Unbalanced parenthesis or brackets
        open_parens = faulty_line.count("(") - faulty_line.count(")")
        open_brackets = faulty_line.count("[") - faulty_line.count("]")
        open_braces = faulty_line.count("{") - faulty_line.count("}")
        
        if open_parens > 0 or open_brackets > 0 or open_braces > 0:
            closing_chars = (")" * open_parens) + ("]" * open_brackets) + ("}" * open_braces)
            fixed = faulty_line.rstrip() + closing_chars + "\n"
            candidates.append(RepairCandidate(
                file_path="", line_number=lineno,
                original_line=faulty_line, proposed_line=fixed,
                repair_strategy="Close unclosed brackets/parentheses", confidence=0.90
            ))

        # Strategy 3: Tab vs Space Indentation Mismatch
        if "IndentationError" in error_type or "tab" in error_msg.lower():
            # Replace all tabs with 4 spaces
            fixed = faulty_line.replace("\t", "    ")
            candidates.append(RepairCandidate(
                file_path="", line_number=lineno,
                original_line=faulty_line, proposed_line=fixed,
                repair_strategy="Normalize tab indentation to 4 spaces", confidence=0.92
            ))
            # Align indent with previous non-empty line
            prev_indent = ""
            for i in range(lineno - 2, -1, -1):
                if all_lines[i].strip():
                    prev_indent = re.match(r"^\s*", all_lines[i]).group(0)
                    break
            fixed_aligned = prev_indent + stripped + "\n"
            candidates.append(RepairCandidate(
                file_path="", line_number=lineno,
                original_line=faulty_line, proposed_line=fixed_aligned,
                repair_strategy="Align indent with preceding code line", confidence=0.85
            ))

        # Strategy 4: Unclosed single/double quote string
        if "'" in faulty_line and faulty_line.count("'") % 2 != 0:
            fixed = faulty_line.rstrip() + "'\n"
            candidates.append(RepairCandidate(
                file_path="", line_number=lineno,
                original_line=faulty_line, proposed_line=fixed,
                repair_strategy="Close dangling single quote", confidence=0.80
            ))
        if '"' in faulty_line and faulty_line.count('"') % 2 != 0:
            fixed = faulty_line.rstrip() + '"\n'
            candidates.append(RepairCandidate(
                file_path="", line_number=lineno,
                original_line=faulty_line, proposed_line=fixed,
                repair_strategy="Close dangling double quote", confidence=0.80
            ))

        # Strategy 5: Missing comma in dictionary/list/tuple
        if stripped.endswith("}") or stripped.endswith("]") or stripped.endswith(")"):
            # If followed by another item, might need a trailing comma
            fixed = faulty_line.rstrip() + ",\n"
            candidates.append(RepairCandidate(
                file_path="", line_number=lineno,
                original_line=faulty_line, proposed_line=fixed,
                repair_strategy="Append missing trailing comma", confidence=0.75
            ))

        return candidates

    def _verify_isolated_compile(self, file_path: str) -> bool:
        """Tests if a single file compiles cleanly via py_compile and ast.parse."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                ast.parse(f.read(), filename=file_path)
            py_compile.compile(file_path, doraise=True)
            return True
        except Exception:
            return False

    def _format_telegram_failure_report(self, errors: List[CompilationErrorDetail]) -> str:
        """Formats an institutional emergency diagnostic dispatch for Telegram delivery."""
        lines = [
            "🚨 <b>AUTOTRADE COMPILER FAULT: HUMAN ASSISTANCE REQUIRED</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "⚠️ <i>The self-healing engine encountered unresolvable compilation anomalies:</i>\n"
        ]
        
        for err in errors[:3]:
            rel_path = os.path.basename(err.file_path)
            lines.append(f"📁 <b>File:</b> <code>{rel_path}</code> (Line {err.line_number})")
            lines.append(f"🔍 <b>Error:</b> <code>{err.error_type}</code> - {err.message}")
            if err.code_snippet:
                lines.append(f"<pre>{err.code_snippet}</pre>")
            lines.append("💡 <b>Proposed Solution:</b> Check syntax structure, matching brackets, or missing module import.\n")

        lines.append("🛡️ <i>Trading engine is locked in SAFEGUARD MODE to protect capital.</i>")
        return "\n".join(lines)
