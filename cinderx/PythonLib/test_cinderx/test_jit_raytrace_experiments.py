import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

import cinderx.jit


@unittest.skipUnless(cinderx.jit.is_enabled(), "Tests functionality on cinderjit")
class RaytraceExperimentTests(unittest.TestCase):
    def test_polymorphic_self_no_instance_value_relaxes_colourat_field_lowering(
        self,
    ) -> None:
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
                "bm_raytrace",
                "/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_raytrace/run_benchmark.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            mod.bench_raytrace(1, 100, 100, None)
            mod.bench_raytrace(1, 100, 100, None)

            if not jit.is_jit_compiled(mod.SimpleSurface.colourAt):
                assert jit.force_compile(mod.SimpleSurface.colourAt)
            counts = cinderjit.get_function_hir_opcode_counts(mod.SimpleSurface.colourAt)
            print(
                counts.get("LoadField", 0),
                counts.get("CheckField", 0),
                counts.get("LoadAttrCached", 0),
                counts.get("LoadAttr", 0),
            )
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/raytrace_colourat_shape.py"
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
            env_relaxed["PYTHONJIT_ARM_POLYMORPHIC_SELF_NO_INSTANCE_VALUE"] = "1"
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
            self.assertEqual(len(baseline), 4, proc_baseline.stdout)
            self.assertEqual(len(relaxed), 4, proc_relaxed.stdout)

            b_load_field, b_check_field, b_load_attr_cached, b_load_attr = baseline
            r_load_field, r_check_field, r_load_attr_cached, r_load_attr = relaxed

            self.assertGreater(b_load_field, 0, proc_baseline.stdout)
            self.assertGreater(b_check_field, 0, proc_baseline.stdout)
            self.assertLess(r_load_field, b_load_field, (proc_baseline.stdout, proc_relaxed.stdout))
            self.assertLess(r_check_field, b_check_field, (proc_baseline.stdout, proc_relaxed.stdout))
            self.assertGreaterEqual(
                r_load_attr_cached + r_load_attr,
                b_load_attr_cached + b_load_attr,
                (proc_baseline.stdout, proc_relaxed.stdout),
            )

    def test_addcolours_tuple_float_helper_rewrites_colourat_calls(self) -> None:
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
                "bm_raytrace",
                "/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_raytrace/run_benchmark.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            mod.bench_raytrace(1, 100, 100, None)
            mod.bench_raytrace(1, 100, 100, None)

            if not jit.is_jit_compiled(mod.SimpleSurface.colourAt):
                assert jit.force_compile(mod.SimpleSurface.colourAt)
            counts = cinderjit.get_function_hir_opcode_counts(mod.SimpleSurface.colourAt)
            print(
                counts.get("CallMethod", 0),
                counts.get("CallStatic", 0),
            )
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/raytrace_addcolours_tuple_float_helper.py"
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

            env_helper = dict(os.environ)
            env_helper["PYTHONJIT_ARM_RAYTRACE_ADD_COLOURS_TUPLE_FLOAT_HELPER"] = "1"
            proc_helper = subprocess.run(
                [sys.executable, script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env_helper,
            )
            self.assertEqual(
                proc_helper.returncode,
                0,
                f"stdout:\n{proc_helper.stdout}\nstderr:\n{proc_helper.stderr}",
            )

            baseline = [int(part) for part in proc_baseline.stdout.split()]
            helper = [int(part) for part in proc_helper.stdout.split()]
            self.assertEqual(len(baseline), 2, proc_baseline.stdout)
            self.assertEqual(len(helper), 2, proc_helper.stdout)

            b_call_method, b_call_static = baseline
            h_call_method, h_call_static = helper

            self.assertGreater(b_call_method, 0, proc_baseline.stdout)
            self.assertEqual(b_call_static, 0, proc_baseline.stdout)
            self.assertGreaterEqual(
                h_call_static,
                3,
                (proc_baseline.stdout, proc_helper.stdout),
            )
