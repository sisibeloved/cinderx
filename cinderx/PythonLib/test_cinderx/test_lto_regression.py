# Copyright (c) Meta Platforms, Inc. and affiliates.

"""LTO/PGO regression tests for CinderX.

These tests verify that LTO builds:
1. Complete successfully
2. Export JITRT_* symbols correctly (not inlined)
3. Have no performance regressions
"""

import subprocess
import sys
import unittest
from pathlib import Path

import cinderx


class TestLTOSymbolIntegrity(unittest.TestCase):
    """Verify JITRT functions are not inlined by LTO."""

    def _get_cinderx_so_path(self):
        """Find the _cinderx.so library path."""
        import _cinderx
        return Path(_cinderx.__file__)

    def test_jitrt_symbols_exist(self):
        """JITRT_* symbols should exist in the shared library."""
        so_path = self._get_cinderx_so_path()
        result = subprocess.run(
            ['nm', '-C', str(so_path)],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0, "nm command failed")
        
        # Check that key JITRT functions exist
        key_functions = [
            'JITRT_ReCompileCached',
            'JITRT_Call',
            'JITRT_CallMethod',
            'JITRT_Decref',
            'JITRT_AllocateAndLinkFrame',
        ]
        
        for func in key_functions:
            with self.subTest(function=func):
                self.assertIn(func, result.stdout, 
                    f"{func} not found in symbol table")

    def test_jitrt_symbols_not_inlined(self):
        """JITRT_* symbols should not have .isra or .part suffixes (inlining indicators)."""
        so_path = self._get_cinderx_so_path()
        result = subprocess.run(
            ['nm', '-C', str(so_path)],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        
        # Check for .isra or .part suffixes which indicate partial inlining
        jitrt_lines = [l for l in result.stdout.split('\n') if 'JITRT_' in l]
        inlined = [l for l in jitrt_lines if '.isra' in l or '.part' in l]
        
        if inlined:
            self.fail(f"Found potentially inlined JITRT functions: {inlined}")

    def test_jitrt_symbols_are_global(self):
        """JITRT_* symbols should be global (T) not local (t)."""
        so_path = self._get_cinderx_so_path()
        result = subprocess.run(
            ['nm', str(so_path)],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        
        # Look for JITRT_ lines that are local text symbols (lowercase t)
        for line in result.stdout.split('\n'):
            if 'JITRT_' in line:
                parts = line.split()
                if len(parts) >= 2:
                    sym_type = parts[-2] if parts[-2] in ['t', 'T', 'W'] else parts[-1]
                    if sym_type == 't':  # local text symbol
                        func_name = parts[-1]
                        self.fail(f"JITRT function {func_name} is local (t) not global (T)")


class TestLTOBasicFunctionality(unittest.TestCase):
    """Verify basic CinderX functionality with LTO builds."""

    def test_module_imports(self):
        """cinderx module should import without errors."""
        import cinderx
        self.assertTrue(hasattr(cinderx, '__version__'))

    def test_jit_can_be_enabled(self):
        """JIT should be enableable."""
        import cinderx.jit
        # Don't actually enable, just verify the module loads
        self.assertTrue(hasattr(cinderx.jit, 'auto'))
        self.assertTrue(hasattr(cinderx.jit, 'force_compile'))

    def test_jit_compiles_simple_function(self):
        """JIT should compile a simple function."""
        import cinderx.jit
        
        @cinderx.jit.force_compile
        def add(a, b):
            return a + b
        
        result = add(1, 2)
        self.assertEqual(result, 3)


class TestLTOPerformanceBaseline(unittest.TestCase):
    """Basic performance tests to detect major regressions."""

    def test_jit_compile_time_reasonable(self):
        """JIT compilation should complete in reasonable time."""
        import time
        import cinderx.jit

        def fib(n):
            if n < 2:
                return n
            return fib(n - 1) + fib(n - 2)

        # Time compilation
        start = time.perf_counter()
        compiled_fib = cinderx.jit.force_compile(fib)
        # Warmup
        compiled_fib(10)
        elapsed = time.perf_counter() - start

        # Should complete in under 5 seconds
        self.assertLess(elapsed, 5.0, 
            f"JIT compilation took {elapsed:.2f}s, expected < 5s")


if __name__ == '__main__':
    unittest.main()
