import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

import cinderx.jit


@unittest.skipUnless(cinderx.jit.is_enabled(), "Tests functionality on cinderjit")
class NQueensConcatExperimentTests(unittest.TestCase):
    def test_list_slice_concat_fast_path_reduces_generic_binary_add(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit
            import importlib.util
            import sys
            import time
            import types

            pyperf = types.SimpleNamespace(perf_counter=time.perf_counter)
            sys.modules["pyperf"] = pyperf

            spec = importlib.util.spec_from_file_location(
                "bm_nqueens",
                "/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_nqueens/run_benchmark.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            mod.bench_n_queens(8)
            mod.bench_n_queens(8)

            if not jit.is_jit_compiled(mod.permutations):
                assert jit.force_compile(mod.permutations)
            counts = cinderjit.get_function_hir_opcode_counts(mod.permutations)
            print(
                counts.get("BinaryOp", 0),
                counts.get("CallStatic", 0),
                counts.get("ListSlice", 0),
            )
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/nqueens_slice_concat_shape.py"
            with open(script, "w", encoding="utf-8") as fp:
                fp.write(code)

            proc_baseline = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=dict(os.environ),
            )
            self.assertEqual(
                proc_baseline.returncode,
                0,
                f"stdout:\n{proc_baseline.stdout}\nstderr:\n{proc_baseline.stderr}",
            )

            env_relaxed = dict(os.environ)
            env_relaxed["PYTHONJIT_ARM_LIST_SLICE_CONCAT"] = "1"
            proc_relaxed = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env_relaxed,
            )
            self.assertEqual(
                proc_relaxed.returncode,
                0,
                f"stdout:\n{proc_relaxed.stdout}\nstderr:\n{proc_relaxed.stderr}",
            )

            baseline = [int(part) for part in proc_baseline.stdout.split()]
            relaxed = [int(part) for part in proc_relaxed.stdout.split()]
            self.assertEqual(len(baseline), 3, proc_baseline.stdout)
            self.assertEqual(len(relaxed), 3, proc_relaxed.stdout)

            b_binary, b_call_static, b_list_slice = baseline
            r_binary, r_call_static, r_list_slice = relaxed

            self.assertGreaterEqual(b_list_slice, 2, proc_baseline.stdout)
            self.assertGreater(b_binary, 0, proc_baseline.stdout)
            self.assertLess(r_binary, b_binary, (proc_baseline.stdout, proc_relaxed.stdout))
            self.assertGreater(r_call_static, b_call_static, (proc_baseline.stdout, proc_relaxed.stdout))

