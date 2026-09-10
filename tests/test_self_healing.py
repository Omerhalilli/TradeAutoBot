"""
Unit tests for Code Integrity, Immutability & Circuit Breaker System.
"""

import os
import shutil
import tempfile
import unittest
from autotrade.self_healing.compiler import SourceCompiler
from autotrade.self_healing.healing_engine import HealingEngine
from autotrade.self_healing.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState, CircuitBreakerOpenException


class TestSelfHealingAndCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.compiler = SourceCompiler(root_dir=self.temp_dir)
        self.healer = HealingEngine(compiler=self.compiler)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_clean_compilation(self):
        clean_file = os.path.join(self.temp_dir, "clean_mod.py")
        with open(clean_file, "w", encoding="utf-8") as f:
            f.write("def sample_func(x, y):\n    return x + y\n")

        res = self.compiler.compile_all_sync()
        self.assertTrue(res.success)
        self.assertEqual(len(res.error_details), 0)

        heal_res = self.healer.heal_compilation_errors_sync([])
        self.assertTrue(heal_res.resolved)
        self.assertEqual(self.healer.circuit_breaker.state, CircuitState.CLOSED)

    def test_code_immutability_on_fault(self):
        """Confirms that syntax errors NEVER trigger dangerous disk file self-modification."""
        faulty_file = os.path.join(self.temp_dir, "faulty_colon.py")
        original_content = "def calculate_pnl(entry, exit_price)\n    return exit_price - entry\n"
        with open(faulty_file, "w", encoding="utf-8") as f:
            f.write(original_content)

        compile_res = self.compiler.compile_all_sync()
        self.assertFalse(compile_res.success)
        self.assertGreater(len(compile_res.error_details), 0)

        heal_res = self.healer.heal_compilation_errors_sync(compile_res.error_details)
        # Immutability preserved: file is NOT modified, circuit breaker trips to OPEN
        self.assertFalse(heal_res.resolved)
        self.assertEqual(self.healer.circuit_breaker.state, CircuitState.OPEN)

        with open(faulty_file, "r", encoding="utf-8") as f:
            current_content = f.read()
        self.assertEqual(current_content, original_content, "Source file was mutated on disk! Immutability violated.")

    def test_circuit_breaker_transitions(self):
        cb = CircuitBreaker("TestBreaker", CircuitBreakerConfig(failure_threshold=2, recovery_timeout_sec=0.1))
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.can_execute())

        # 1st failure
        cb.record_failure(ValueError("Err1"))
        self.assertEqual(cb.state, CircuitState.CLOSED)

        # 2nd failure -> trips to OPEN
        cb.record_failure(ValueError("Err2"))
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.can_execute())

        # Decorator raises CircuitBreakerOpenException
        @cb
        def guarded():
            return 42

        with self.assertRaises(CircuitBreakerOpenException):
            guarded()

        # Reset
        cb.reset()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertEqual(guarded(), 42)

    def test_unrecoverable_error_reporting(self):
        faulty_file = os.path.join(self.temp_dir, "unrecoverable.py")
        with open(faulty_file, "w", encoding="utf-8") as f:
            f.write("!@#$%^&*()_+ INVALID GARBAGE NOT REPAIRABLE\n")

        compile_res = self.compiler.compile_all_sync()
        heal_res = self.healer.heal_compilation_errors_sync(compile_res.error_details)
        self.assertFalse(heal_res.resolved)
        self.assertIn("AUTOTRADE COMPILER FAULT", heal_res.telegram_report)
        self.assertIn("Production Immutability Enforced", heal_res.telegram_report)


if __name__ == "__main__":
    unittest.main()
