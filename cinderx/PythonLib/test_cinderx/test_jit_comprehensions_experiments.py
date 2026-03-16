import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

import cinderx.jit


@unittest.skipUnless(cinderx.jit.is_enabled(), "Tests functionality on cinderjit")
class ComprehensionsExperimentTests(unittest.TestCase):
    def test_attr_int_compare_no_guards_reduces_add_widgets_int_compare_shape(
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
                "bm_comprehensions",
                "/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_comprehensions/run_benchmark.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            widgets = mod.make_some_widgets()
            for _ in range(200):
                mod.WidgetTray(1, widgets)

            fn = mod.WidgetTray._add_widgets
            if not jit.is_jit_compiled(fn):
                assert jit.force_compile(fn)
            counts = cinderjit.get_function_hir_opcode_counts(fn)
            print(
                counts.get("GuardType", 0),
                counts.get("LongCompare", 0),
                counts.get("Compare", 0),
            )
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/comprehensions_compare_shape.py"
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
            env_relaxed["PYTHONJIT_ARM_ATTR_INT_COMPARE_NO_GUARDS"] = "1"
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

            b_guard_type, b_long_compare, b_compare = baseline
            r_guard_type, r_long_compare, r_compare = relaxed

            self.assertGreater(b_guard_type, 0, proc_baseline.stdout)
            self.assertGreater(b_long_compare, 0, proc_baseline.stdout)
            self.assertLess(r_guard_type, b_guard_type, (proc_baseline.stdout, proc_relaxed.stdout))
            self.assertEqual(r_long_compare, 0, (proc_baseline.stdout, proc_relaxed.stdout))
            self.assertGreater(r_compare, b_compare, (proc_baseline.stdout, proc_relaxed.stdout))

    def test_tiny_helpers_rewrite_add_widgets_calls(self) -> None:
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
                "bm_comprehensions",
                "/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_comprehensions/run_benchmark.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            widgets = mod.make_some_widgets()
            for _ in range(200):
                mod.WidgetTray(1, widgets)

            fn = mod.WidgetTray._add_widgets
            if not jit.is_jit_compiled(fn):
                assert jit.force_compile(fn)
            counts = cinderjit.get_function_hir_opcode_counts(fn)
            print(
                counts.get("CallMethod", 0),
                counts.get("CallStatic", 0),
            )
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/comprehensions_tiny_helpers.py"
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
            env_helper["PYTHONJIT_ARM_COMPREHENSIONS_TINY_HELPERS"] = "1"
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
            self.assertLess(h_call_method, b_call_method, (proc_baseline.stdout, proc_helper.stdout))
            self.assertGreaterEqual(h_call_static, 2, (proc_baseline.stdout, proc_helper.stdout))

    def test_dict_get_helper_rewrites_add_widgets_call(self) -> None:
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
                "bm_comprehensions",
                "/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_comprehensions/run_benchmark.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            widgets = mod.make_some_widgets()
            for _ in range(200):
                mod.WidgetTray(1, widgets)

            fn = mod.WidgetTray._add_widgets
            if not jit.is_jit_compiled(fn):
                assert jit.force_compile(fn)
            counts = cinderjit.get_function_hir_opcode_counts(fn)
            print(
                counts.get("CallMethod", 0),
                counts.get("CallStatic", 0),
            )
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/comprehensions_dict_get_helper.py"
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
            env_helper["PYTHONJIT_ARM_COMPREHENSIONS_DICT_GET_HELPER"] = "1"
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
            self.assertLess(h_call_method, b_call_method, (proc_baseline.stdout, proc_helper.stdout))
            self.assertGreaterEqual(h_call_static, 1, (proc_baseline.stdout, proc_helper.stdout))

    def test_list_sort_helper_rewrites_add_widgets_call(self) -> None:
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
                "bm_comprehensions",
                "/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_comprehensions/run_benchmark.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            jit.enable()
            jit.enable_specialized_opcodes()
            jit.compile_after_n_calls(1000000)

            widgets = mod.make_some_widgets()
            for _ in range(200):
                mod.WidgetTray(1, widgets)

            fn = mod.WidgetTray._add_widgets
            if not jit.is_jit_compiled(fn):
                assert jit.force_compile(fn)
            counts = cinderjit.get_function_hir_opcode_counts(fn)
            print(
                counts.get("CallMethod", 0),
                counts.get("CallStatic", 0),
            )
            """
        )

        with tempfile.TemporaryDirectory() as tmp:
            script = f"{tmp}/comprehensions_list_sort_helper.py"
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
            env_helper["PYTHONJIT_ARM_COMPREHENSIONS_LIST_SORT_HELPER"] = "1"
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
            self.assertLess(h_call_method, b_call_method, (proc_baseline.stdout, proc_helper.stdout))
            self.assertGreaterEqual(h_call_static, 1, (proc_baseline.stdout, proc_helper.stdout))
