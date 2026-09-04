"""
Self-Healing & Compiler Layer.
Provides automated startup source compilation, static AST analysis,
algorithmic error correction, and runtime module watchdog supervisors.
"""

from autotrade.self_healing.compiler import SourceCompiler, CompilationResult
from autotrade.self_healing.healing_engine import HealingEngine, RepairReport
from autotrade.self_healing.watchdog import ModuleWatchdog, SupervisedModule

__all__ = [
    "SourceCompiler",
    "CompilationResult",
    "HealingEngine",
    "RepairReport",
    "ModuleWatchdog",
    "SupervisedModule",
]
