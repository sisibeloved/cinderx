#!/usr/bin/env python3
"""Run a small pyperformance experiment matrix on local macOS Arm."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


BENCHMARK_SPECS: dict[str, dict[str, str]] = {
    "coroutines": {
        "module_relpath": "pyperformance/data-files/benchmarks/bm_coroutines/run_benchmark.py",
        "bench_func": "bench_coroutines",
        "bench_args_json": "[1]",
    },
    "comprehensions": {
        "module_relpath": "pyperformance/data-files/benchmarks/bm_comprehensions/run_benchmark.py",
        "bench_func": "bench_comprehensions",
        "bench_args_json": "[1]",
    },
    "richards": {
        "module_relpath": "pyperformance/data-files/benchmarks/bm_richards/run_benchmark.py",
        "bench_func": "Richards().run",
        "bench_args_json": "[1]",
    },
    "richards_super": {
        "module_relpath": "pyperformance/data-files/benchmarks/bm_richards_super/run_benchmark.py",
        "bench_func": "Richards().run",
        "bench_args_json": "[1]",
    },
    "go": {
        "module_relpath": "pyperformance/data-files/benchmarks/bm_go/run_benchmark.py",
        "bench_func": "bench_go",
        "bench_args_json": "[1]",
    },
    "deltablue": {
        "module_relpath": "pyperformance/data-files/benchmarks/bm_deltablue/run_benchmark.py",
        "bench_func": "delta_blue",
        "bench_args_json": "[10]",
    },
    "raytrace": {
        "module_relpath": "pyperformance/data-files/benchmarks/bm_raytrace/run_benchmark.py",
        "bench_func": "bench_raytrace",
        "bench_args_json": "[1, 100, 100, null]",
    },
    "nqueens": {
        "module_relpath": "pyperformance/data-files/benchmarks/bm_nqueens/run_benchmark.py",
        "bench_func": "bench_n_queens",
        "bench_args_json": "[8]",
    },
    "float": {
        "module_relpath": "pyperformance/data-files/benchmarks/bm_float/run_benchmark.py",
        "bench_func": "benchmark",
        "bench_args_json": "[1000]",
    },
    "generators": {
        "module_relpath": "pyperformance/data-files/benchmarks/bm_generators/run_benchmark.py",
        "bench_func": "bench_generators",
        "bench_args_json": "[1]",
    },
}


def build_mode_env(mode: str) -> dict[str, str]:
    env = {
        "ENABLE_STATIC_PYTHON": "0",
        "ENABLE_ADAPTIVE_STATIC_PYTHON": "0",
        "ENABLE_LIGHTWEIGHT_FRAMES": "0",
    }
    if mode == "baseline":
        return env
    if mode == "arm_coro_fast":
        env["PYTHONJITARMCOROFAST"] = "1"
        return env
    if mode == "arm_instance_fast":
        env["PYTHONJITARMINSTANCEFAST"] = "1"
        return env
    if mode == "arm_instance_skip_valid":
        env["PYTHONJITARMINSTANCEFAST"] = "1"
        env["PYTHONJITARMINSTANCEFASTSKIPVALID"] = "1"
        env["PYTHONCINDERXINSTANCEVALUESKIPVALID"] = "1"
        return env
    if mode == "arm_numeric_leaf":
        env["PYTHONJITARMNUMERICLEAF"] = "1"
        return env
    if mode == "arm_all_experiments":
        env["PYTHONJITARMCOROFAST"] = "1"
        env["PYTHONJITARMINSTANCEFAST"] = "1"
        env["PYTHONJITARMINSTANCEFASTSKIPVALID"] = "1"
        env["PYTHONCINDERXINSTANCEVALUESKIPVALID"] = "1"
        env["PYTHONJITARMNUMERICLEAF"] = "1"
        env["PYTHONJITARMGENFAST"] = "1"
        return env
    raise KeyError(f"unsupported mode: {mode}")


def resolve_benchmark_spec(
    pyperformance_root: Path,
    benchmark: str,
) -> dict[str, object]:
    if benchmark not in BENCHMARK_SPECS:
        raise KeyError(f"unsupported benchmark: {benchmark}")
    spec = dict(BENCHMARK_SPECS[benchmark])
    spec["module_path"] = pyperformance_root / str(spec["module_relpath"])
    return spec


def build_command(
    repo_root: Path,
    pyperformance_root: Path,
    benchmark: str,
    mode: str,
    python_exe: str,
    samples: int,
    prewarm_runs: int,
    specialized_opcodes: bool,
) -> tuple[list[str], dict[str, str]]:
    spec = resolve_benchmark_spec(pyperformance_root, benchmark)
    cmd = [
        python_exe,
        str(repo_root / "scripts" / "arm" / "bench_pyperf_direct.py"),
        "--module-path",
        str(spec["module_path"]),
        "--bench-func",
        str(spec["bench_func"]),
        "--bench-args-json",
        str(spec["bench_args_json"]),
        "--samples",
        str(samples),
        "--prewarm-runs",
        str(prewarm_runs),
        "--compile-strategy",
        "all",
    ]
    if specialized_opcodes:
        cmd.append("--specialized-opcodes")
    env = os.environ.copy()
    env.update(build_mode_env(mode))
    return cmd, env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyperformance-root", required=True)
    parser.add_argument("--benchmark", required=True, choices=sorted(BENCHMARK_SPECS))
    parser.add_argument(
        "--mode",
        default="baseline",
        choices=[
            "baseline",
            "arm_coro_fast",
            "arm_instance_fast",
            "arm_instance_skip_valid",
            "arm_numeric_leaf",
            "arm_all_experiments",
        ],
    )
    parser.add_argument("--python", dest="python_exe", default=sys.executable)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--prewarm-runs", type=int, default=1)
    parser.add_argument("--no-specialized-opcodes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    cmd, env = build_command(
        repo_root=repo_root,
        pyperformance_root=Path(args.pyperformance_root),
        benchmark=args.benchmark,
        mode=args.mode,
        python_exe=args.python_exe,
        samples=args.samples,
        prewarm_runs=args.prewarm_runs,
        specialized_opcodes=not args.no_specialized_opcodes,
    )

    print("mode=", args.mode)
    print("benchmark=", args.benchmark)
    print("command=", " ".join(cmd))
    interesting_env = build_mode_env(args.mode)
    if interesting_env:
        print("env=", interesting_env)

    if args.dry_run:
        return 0

    proc = subprocess.run(cmd, env=env, check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
