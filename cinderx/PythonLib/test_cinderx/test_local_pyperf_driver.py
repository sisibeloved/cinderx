# Copyright (c) Meta Platforms, Inc. and affiliates.

import importlib.util
import pathlib
import tempfile
import textwrap
import unittest


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[3]


def _load_driver():
    path = _repo_root() / "scripts" / "arm" / "run_local_pyperf_matrix.py"
    spec = importlib.util.spec_from_file_location("run_local_pyperf_matrix", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_direct_runner():
    path = _repo_root() / "scripts" / "arm" / "bench_pyperf_direct.py"
    spec = importlib.util.spec_from_file_location("bench_pyperf_direct", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_probe():
    path = _repo_root() / "scripts" / "arm" / "probe_jit_apis.py"
    spec = importlib.util.spec_from_file_location("probe_jit_apis", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LocalPyperfDriverTests(unittest.TestCase):
    def test_build_mode_env_baseline_and_arm_coro_fast(self) -> None:
        driver = _load_driver()
        self.assertEqual(
            driver.build_mode_env("baseline"),
            {
                "ENABLE_STATIC_PYTHON": "0",
                "ENABLE_ADAPTIVE_STATIC_PYTHON": "0",
                "ENABLE_LIGHTWEIGHT_FRAMES": "0",
            },
        )
        self.assertEqual(
            driver.build_mode_env("arm_coro_fast"),
            {
                "ENABLE_STATIC_PYTHON": "0",
                "ENABLE_ADAPTIVE_STATIC_PYTHON": "0",
                "ENABLE_LIGHTWEIGHT_FRAMES": "0",
                "PYTHONJIT_ARM_CORO_FAST": "1",
            },
        )

    def test_resolve_coroutines_benchmark(self) -> None:
        driver = _load_driver()
        spec = driver.resolve_benchmark_spec(
            pathlib.Path("/Users/luchen/Repo/pyperformance"),
            "coroutines",
        )
        self.assertEqual(spec["bench_func"], "bench_coroutines")
        self.assertEqual(spec["bench_args_json"], "[1]")
        self.assertTrue(str(spec["module_path"]).endswith("bm_coroutines/run_benchmark.py"))

    def test_resolve_richards_benchmark_uses_dotted_bench_func(self) -> None:
        driver = _load_driver()
        spec = driver.resolve_benchmark_spec(
            pathlib.Path("/Users/luchen/Repo/pyperformance"),
            "richards",
        )
        self.assertEqual(spec["bench_func"], "Richards().run")

    def test_resolve_mdp_benchmark(self) -> None:
        driver = _load_driver()
        spec = driver.resolve_benchmark_spec(
            pathlib.Path("/Users/luchen/Repo/pyperformance"),
            "mdp",
        )
        self.assertEqual(spec["bench_func"], "bench_mdp")
        self.assertEqual(spec["bench_args_json"], "[1]")
        self.assertTrue(str(spec["module_path"]).endswith("bm_mdp/run_benchmark.py"))

    def test_direct_runner_resolve_attr_path(self) -> None:
        direct_runner = _load_direct_runner()

        class Inner:
            def bench(self):
                return "ok"

        class Factory:
            @staticmethod
            def make():
                return Inner()

        class Outer:
            inner = Inner()

        self.assertEqual(direct_runner.resolve_attr_path(Outer, "inner.bench")(), "ok")
        setattr(Outer, "Factory", Factory)
        self.assertEqual(direct_runner.resolve_attr_path(Outer, "Factory.make().bench")(), "ok")

    def test_direct_runner_can_import_module_without_real_pyperf(self) -> None:
        direct_runner = _load_direct_runner()
        code = textwrap.dedent(
            """
            import pyperf

            def bench_demo(loops):
                return pyperf.perf_counter()
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            module_path = pathlib.Path(tmp) / "bench_demo.py"
            module_path.write_text(code, encoding="utf-8")
            module = direct_runner.load_module(module_path, "bench_demo")
            self.assertTrue(hasattr(module, "bench_demo"))

    def test_direct_runner_collects_hir_opcode_counts(self) -> None:
        direct_runner = _load_direct_runner()

        def alpha():
            return 1

        def beta():
            return 2

        class FakeJit:
            def get_function_hir_opcode_counts(self, fn):
                if fn is alpha:
                    return {"LoadConst": 1}
                if fn is beta:
                    return {"BinaryOp": 2}
                return None

        self.assertEqual(
            direct_runner.collect_hir_opcode_counts(FakeJit(), [alpha, beta]),
            {
                alpha.__qualname__: {"LoadConst": 1},
                beta.__qualname__: {"BinaryOp": 2},
            },
        )

    def test_probe_reports_hir_related_api_support(self) -> None:
        probe = _load_probe()

        class FakeJit:
            enable = object()
            print_hir = object()
            get_function_hir_opcode_counts = object()
            get_and_clear_runtime_stats = object()

        self.assertEqual(
            probe.probe_api_support(
                FakeJit(),
                (
                    "enable",
                    "print_hir",
                    "get_function_hir_opcode_counts",
                    "get_and_clear_runtime_stats",
                ),
            ),
            {
                "enable": True,
                "print_hir": True,
                "get_function_hir_opcode_counts": True,
                "get_and_clear_runtime_stats": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
