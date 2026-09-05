"""
Institutional Source Code Compiler & Static AST Analysis Engine.
Performs automatic self-compilation of Python source trees on startup,
deep AST integrity checks, and optional MetaEditor MQL4 compilation.
"""

from __future__ import annotations
import ast
import compileall
from dataclasses import dataclass, field
import logging
import os
import py_compile
import subprocess
import time
from typing import Any, Dict, List, Optional

from autotrade.core.event_bus import event_bus, EventType, EventPriority

logger = logging.getLogger("autotrade.self_healing.compiler")


@dataclass
class CompilationErrorDetail:
    """Detailed metadata representing a single source compilation error."""
    file_path: str
    line_number: int
    offset: int
    error_type: str
    message: str
    code_snippet: str = ""
    suggested_fix: str = ""


@dataclass
class CompilationResult:
    """Consolidated outcome of the source tree compilation process."""
    success: bool
    total_files_checked: int = 0
    total_files_compiled: int = 0
    duration_ms: float = 0.0
    errors: List[str] = field(default_factory=list)
    error_details: List[CompilationErrorDetail] = field(default_factory=list)
    mql4_compiled: bool = False
    mql4_details: Dict[str, Any] = field(default_factory=dict)


class SourceCompiler:
    """
    Automated self-compilation engine.
    Scans the repository, compiles byte-code, analyzes AST syntax, and detects anomalies.
    """
    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = root_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self._ignored_dirs = {".git", "__pycache__", "venv", ".pytest_cache", ".idea", ".vscode"}

    def compile_all_sync(self, include_mql4: bool = False) -> CompilationResult:
        """
        Synchronously compiles all Python files in the repository using py_compile and ast.parse.
        Captures any SyntaxError, IndentationError, or TokenError.
        """
        t0 = time.perf_counter()
        event_bus.publish(
            EventType.COMPILATION_STARTED,
            payload={"root_dir": self.root_dir},
            priority=EventPriority.NORMAL,
            source="SourceCompiler"
        )
        
        total_checked = 0
        total_compiled = 0
        error_details: List[CompilationErrorDetail] = []
        error_messages: List[str] = []

        for root, dirs, files in os.walk(self.root_dir):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in self._ignored_dirs]
            
            for file in files:
                if not file.endswith(".py"):
                    continue
                file_path = os.path.join(root, file)
                total_checked += 1
                
                # Step 1: Deep AST parsing check
                ast_err = self._check_ast_syntax(file_path)
                if ast_err:
                    error_details.append(ast_err)
                    error_messages.append(f"{file_path}:{ast_err.line_number}: {ast_err.message}")
                    continue

                # Step 2: py_compile bytecode emission
                try:
                    py_compile.compile(file_path, doraise=True)
                    total_compiled += 1
                except py_compile.PyCompileError as pce:
                    err_detail = CompilationErrorDetail(
                        file_path=file_path,
                        line_number=getattr(pce.exc_value, "lineno", 1) or 1,
                        offset=getattr(pce.exc_value, "offset", 0) or 0,
                        error_type=pce.exc_value.__class__.__name__,
                        message=str(pce.exc_value),
                        code_snippet=self._extract_snippet(file_path, getattr(pce.exc_value, "lineno", 1) or 1)
                    )
                    error_details.append(err_detail)
                    error_messages.append(f"{file_path}:{err_detail.line_number}: {err_detail.message}")

        duration_ms = (time.perf_counter() - t0) * 1000.0
        success = len(error_details) == 0

        # Check MQL4 if MetaEditor is requested
        mql4_res = self.compile_mql4_all() if include_mql4 else {"attempted": False, "success": True}

        result = CompilationResult(
            success=success and mql4_res.get("success", True),
            total_files_checked=total_checked,
            total_files_compiled=total_compiled,
            duration_ms=round(duration_ms, 2),
            errors=error_messages,
            error_details=error_details,
            mql4_compiled=mql4_res.get("attempted", False),
            mql4_details=mql4_res
        )

        event_bus.publish(
            EventType.COMPILATION_SUCCESS if result.success else EventType.COMPILATION_ERROR,
            payload={
                "success": result.success,
                "duration_ms": result.duration_ms,
                "error_count": len(error_details),
                "errors": error_messages[:5]
            },
            priority=EventPriority.NORMAL if result.success else EventPriority.HIGH,
            source="SourceCompiler"
        )
        return result

    async def compile_all_async(self, include_mql4: bool = False) -> Dict[str, Any]:
        """Runs the compilation asynchronously without blocking the event loop."""
        import asyncio
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: self.compile_all_sync(include_mql4=include_mql4))
        return {
            "success": res.success,
            "total_files_checked": res.total_files_checked,
            "total_files_compiled": res.total_files_compiled,
            "duration_ms": res.duration_ms,
            "errors": res.errors,
            "error_details": [
                {
                    "file_path": e.file_path,
                    "line_number": e.line_number,
                    "offset": e.offset,
                    "error_type": e.error_type,
                    "message": e.message,
                    "code_snippet": e.code_snippet,
                }
                for e in res.error_details
            ],
            "mql4_details": res.mql4_details
        }

    def _check_ast_syntax(self, file_path: str) -> Optional[CompilationErrorDetail]:
        """Reads and parses Python file into Abstract Syntax Tree to identify errors early."""
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                source = f.read()
            ast.parse(source, filename=file_path)
            return None
        except SyntaxError as se:
            lineno = se.lineno or 1
            offset = se.offset or 0
            snippet = self._extract_snippet(file_path, lineno)
            return CompilationErrorDetail(
                file_path=file_path,
                line_number=lineno,
                offset=offset,
                error_type=se.__class__.__name__,
                message=str(se.msg) if hasattr(se, "msg") else str(se),
                code_snippet=snippet
            )
        except Exception as ex:
            return CompilationErrorDetail(
                file_path=file_path,
                line_number=1,
                offset=0,
                error_type=ex.__class__.__name__,
                message=str(ex),
                code_snippet=""
            )

    def _extract_snippet(self, file_path: str, line_number: int, context_lines: int = 2) -> str:
        """Extracts code snippet around the faulty line with context lines."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            start = max(0, line_number - 1 - context_lines)
            end = min(len(lines), line_number + context_lines)
            snippet = "".join(f"{i+1:4d}: {lines[i]}" for i in range(start, end))
            return snippet
        except Exception:
            return ""

    def compile_mql4_all(self) -> Dict[str, Any]:
        """
        Attempts to compile MQL4 expert advisors using Wine and MetaEditor if available.
        """
        metaeditor_cand = os.path.expanduser(
            "~/.wine/drive_c/Program Files (x86)/MetaTrader 4/metaeditor.exe"
        )
        if not os.path.exists(metaeditor_cand):
            return {"attempted": False, "reason": "MetaEditor not installed at default path"}

        mq4_files = [
            os.path.join(self.root_dir, "SmartAutoTradeEA_Pro.mq4"),
            os.path.join(self.root_dir, "MT4_ZeroMQ_Bridge.mq4")
        ]
        
        results = {}
        for mq4 in mq4_files:
            if not os.path.exists(mq4):
                continue
            log_path = mq4.replace(".mq4", "_compile.log")
            try:
                win_mq4 = subprocess.check_output(["winepath", "-w", mq4], text=True).strip()
                win_log = subprocess.check_output(["winepath", "-w", log_path], text=True).strip()
            except Exception:
                win_mq4 = mq4
                win_log = log_path
            cmd = f'DISPLAY=:1 wine "{metaeditor_cand}" /compile:"{win_mq4}" /log:"{win_log}"'
            try:
                proc = subprocess.run(
                    cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15
                )
                compiled = False
                if os.path.exists(log_path):
                    try:
                        with open(log_path, "rb") as lf:
                            log_text = lf.read().decode("utf-16le", errors="replace")
                            if "0 errors" in log_text:
                                compiled = True
                    except Exception:
                        pass
                if not compiled:
                    compiled = (proc.returncode == 0)

                results[os.path.basename(mq4)] = {
                    "exit_code": proc.returncode,
                    "compiled": compiled
                }
            except Exception as ex:
                results[os.path.basename(mq4)] = {"error": str(ex), "compiled": False}

        all_ok = all(r.get("compiled", False) for r in results.values()) if results else True
        return {"attempted": True, "success": all_ok, "results": results}
