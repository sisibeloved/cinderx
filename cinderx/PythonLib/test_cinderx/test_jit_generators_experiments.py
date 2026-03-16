import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

import cinderx.jit


@unittest.skipUnless(cinderx.jit.is_enabled(), "Tests functionality on cinderjit")
class GeneratorsExperimentTests(unittest.TestCase):
    def test_generator_none_truthiness_reduces_istruthy_shape(self) -> None:
        code = textwrap.dedent(
            """
            import cinderx.jit as jit
            import cinderjit
            import importlib.util
            import sys
            import time
            import types

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            pyperf = types.SimpleNamespace(perf_counter=time.perf_counter)
            sys.modules["pyperf"] = pyperf

            spec = importlib.util.spec_from_file_location(
                "bm_generators",
                "/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_generators/run_benchmark.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            root = mod.tree(range(10))
            for _ in range(2000):
                for _ in root:
                    pass

            fn = mod.Tree.__iter__
            if not jit.is_jit_compiled(fn):
                assert jit.force_compile(fn)
            counts = cinderjit.get_function_hir_opcode_counts(fn)
            print(
                counts.get("IsTruthy", 0),
                counts.get("PrimitiveCompare", 0),
                counts.get("Decref", 0),
            )
            print(list(root))
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/generators_none_truthiness.py"
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
            env_relaxed["PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY"] = "1"
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

            baseline_lines = [line.strip() for line in proc_baseline.stdout.splitlines() if line.strip()]
            relaxed_lines = [line.strip() for line in proc_relaxed.stdout.splitlines() if line.strip()]
            self.assertGreaterEqual(len(baseline_lines), 2, proc_baseline.stdout)
            self.assertGreaterEqual(len(relaxed_lines), 2, proc_relaxed.stdout)

            baseline = [int(part) for part in baseline_lines[-2].split()]
            relaxed = [int(part) for part in relaxed_lines[-2].split()]
            self.assertEqual(len(baseline), 3, proc_baseline.stdout)
            self.assertEqual(len(relaxed), 3, proc_relaxed.stdout)

            b_istruthy, b_primitive_compare, b_decref = baseline
            r_istruthy, r_primitive_compare, r_decref = relaxed

            self.assertGreaterEqual(b_istruthy, 2, proc_baseline.stdout)
            self.assertEqual(r_istruthy, 0, (proc_baseline.stdout, proc_relaxed.stdout))
            self.assertGreater(r_primitive_compare, b_primitive_compare, (proc_baseline.stdout, proc_relaxed.stdout))
            self.assertLess(r_decref, b_decref, (proc_baseline.stdout, proc_relaxed.stdout))
            self.assertEqual(relaxed_lines[-1], str(list(range(10))), proc_relaxed.stdout)
