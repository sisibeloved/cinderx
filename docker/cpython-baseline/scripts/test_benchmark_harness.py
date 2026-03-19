import importlib.util
import pathlib
import sys
import tempfile
import textwrap
import unittest


def _load_harness():
    root = pathlib.Path(__file__).resolve().parent
    path = root / "benchmark_harness.py"
    spec = importlib.util.spec_from_file_location("benchmark_harness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BenchmarkHarnessTests(unittest.TestCase):
    def test_resolve_mdp_benchmark(self) -> None:
        harness = _load_harness()
        spec = harness.resolve_benchmark("mdp")
        self.assertEqual(spec.module_dir, "bm_mdp")
        self.assertEqual(spec.bench_func, "bench_mdp")
        self.assertEqual(spec.bench_args, (1,))

    def test_load_benchmark_module_and_entrypoint(self) -> None:
        harness = _load_harness()
        code = textwrap.dedent(
            """
            def bench_mdp(loops):
                return loops
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bench_dir = root / "bm_mdp"
            bench_dir.mkdir()
            module_path = bench_dir / "run_benchmark.py"
            module_path.write_text(code, encoding="utf-8")
            module, bench = harness.load_benchmark(root, "mdp")
            self.assertEqual(module.__name__, "bm_mdp")
            self.assertEqual(bench(3), 3)

    def test_load_benchmark_accepts_string_root(self) -> None:
        harness = _load_harness()
        code = textwrap.dedent(
            """
            def bench_mdp(loops):
                return loops + 1
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bench_dir = root / "bm_mdp"
            bench_dir.mkdir()
            module_path = bench_dir / "run_benchmark.py"
            module_path.write_text(code, encoding="utf-8")
            module, bench = harness.load_benchmark(str(root), "mdp")
            self.assertEqual(module.__name__, "bm_mdp")
            self.assertEqual(bench(3), 4)

    def test_load_benchmark_allows_local_pyperf_shim_import(self) -> None:
        harness = _load_harness()
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bench_dir = root / "bm_mdp"
            bench_dir.mkdir()
            (bench_dir / "pyperf.py").write_text(
                "value = 7\n",
                encoding="utf-8",
            )
            (bench_dir / "run_benchmark.py").write_text(
                textwrap.dedent(
                    """
                    import pyperf

                    def bench_mdp(loops):
                        return loops + pyperf.value
                    """
                ),
                encoding="utf-8",
            )
            sys.modules.pop("pyperf", None)
            module, bench = harness.load_benchmark(root, "mdp")
            self.assertEqual(module.__name__, "bm_mdp")
            self.assertEqual(bench(3), 10)

    def test_stock_cpython_python_defaults_to_jit_prefix(self) -> None:
        harness = _load_harness()
        self.assertEqual(
            harness.stock_cpython_python(),
            pathlib.Path("/opt/cpython-jit/bin/python3"),
        )

    def test_stock_cpython_configure_args_enable_yes_off(self) -> None:
        harness = _load_harness()
        self.assertEqual(
            harness.stock_cpython_configure_args(),
            (
                "./configure",
                "--prefix=/opt/cpython-jit",
                "--enable-experimental-jit=yes-off",
            ),
        )

    def test_stock_cpython_runtime_env_enables_jit(self) -> None:
        harness = _load_harness()
        self.assertEqual(harness.stock_cpython_runtime_env(), {"PYTHON_JIT": "1"})

    def test_cinderx_wheel_glob_defaults_to_dist_directory(self) -> None:
        harness = _load_harness()
        self.assertEqual(
            harness.cinderx_wheel_glob(),
            pathlib.Path("/dist/cinderx-*-linux_aarch64.whl"),
        )

    def test_cinderx_runtime_env_uses_generator_flag_for_generators(self) -> None:
        harness = _load_harness()
        self.assertEqual(
            harness.cinderx_runtime_env("generators", enable_optimization=True),
            {"PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY": "1"},
        )

    def test_cinderx_runtime_env_uses_mdp_flags_for_mdp(self) -> None:
        harness = _load_harness()
        self.assertEqual(
            harness.cinderx_runtime_env("mdp", enable_optimization=True),
            {
                "PYTHONJIT_ARM_MDP_INT_CLAMP_MIN_MAX": "1",
                "PYTHONJIT_ARM_MDP_FRACTION_MIN_COMPARE": "1",
                "PYTHONJIT_ARM_MDP_PRIORITY_COMPARE_ADD": "1",
            },
        )

    def test_cinderx_runtime_env_is_empty_when_optimization_disabled(self) -> None:
        harness = _load_harness()
        self.assertEqual(harness.cinderx_runtime_env("mdp", enable_optimization=False), {})


if __name__ == "__main__":
    unittest.main()
