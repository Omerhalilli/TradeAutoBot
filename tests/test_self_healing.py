"""
Unit tests for Self-Healing Engine & Source Compiler.
"""

import os
import shutil
import tempfile
import unittest
from autotrade.self_healing.compiler import SourceCompiler
from autotrade.self_healing.healing_engine import HealingEngine, RepairCandidate


class TestSelfHealing(unittest.TestCase):
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

    def test_missing_colon_healing(self):
        faulty_file = os.path.join(self.temp_dir, "faulty_colon.py")
        with open(faulty_file, "w", encoding="utf-8") as f:
            f.write("def calculate_pnl(entry, exit_price)\n    return exit_price - entry\n")

        # Verify compiler catches syntax error
        compile_res = self.compiler.compile_all_sync()
        self.assertFalse(compile_res.success)
        self.assertGreater(len(compile_res.error_details), 0)

        # Invoke self-healing
        err_dicts = [
            {
                "file_path": e.file_path,
                "line_number": e.line_number,
                "message": e.message,
                "error_type": e.error_type
            }
            for e in compile_res.error_details
        ]
        heal_res = self.healer.heal_compilation_errors_sync(err_dicts)
        self.assertTrue(heal_res.resolved)
        self.assertEqual(heal_res.succeeded, 1)

        # Confirm repaired file compiles cleanly
        post_compile = self.compiler.compile_all_sync()
        self.assertTrue(post_compile.success)

    def test_unclosed_parenthesis_healing(self):
        faulty_file = os.path.join(self.temp_dir, "faulty_paren.py")
        with open(faulty_file, "w", encoding="utf-8") as f:
            f.write("def run():\n    val = int(abs(-5)\n    return val\n")

        compile_res = self.compiler.compile_all_sync()
        self.assertFalse(compile_res.success)

        err_dicts = [
            {
                "file_path": e.file_path,
                "line_number": e.line_number,
                "message": e.message,
                "error_type": e.error_type
            }
            for e in compile_res.error_details
        ]
        heal_res = self.healer.heal_compilation_errors_sync(err_dicts)
        self.assertTrue(heal_res.resolved)

    def test_unrecoverable_error_reporting(self):
        faulty_file = os.path.join(self.temp_dir, "unrecoverable.py")
        with open(faulty_file, "w", encoding="utf-8") as f:
            f.write("!@#$%^&*()_+ INVALID GARBAGE NOT REPAIRABLE\n")

        compile_res = self.compiler.compile_all_sync()
        err_dicts = [
            {
                "file_path": e.file_path,
                "line_number": e.line_number,
                "message": e.message,
                "error_type": e.error_type
            }
            for e in compile_res.error_details
        ]
        heal_res = self.healer.heal_compilation_errors_sync(err_dicts)
        self.assertFalse(heal_res.resolved)
        self.assertIn("AUTOTRADE COMPILER FAULT", heal_res.telegram_report)


if __name__ == "__main__":
    unittest.main()
