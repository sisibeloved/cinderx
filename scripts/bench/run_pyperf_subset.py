#!/usr/bin/env python3
"""
Run a subset of pyperformance benchmarks optimized for JIT validation.

This script runs 5 JIT-intensive benchmarks from the pyperformance suite:
- richards: Classic OS kernel simulation
- nbody: N-body physics simulation
- deltablue: Constraint solver
- regex_compile: Regular expression compilation
- nqueens: N-Queens puzzle solver

Usage:
    python scripts/bench/run_pyperf_subset.py --output results.json
    python scripts/bench/run_pyperf_subset.py --iterations 5 --warmup 1
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Default 5-benchmark JIT subset
DEFAULT_BENCHMARKS = ["richards", "nbody", "deltablue", "regex_compile", "nqueens"]


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark execution."""

    benchmarks: List[str]
    iterations: int = 5
    warmup: int = 1
    output_path: Optional[Path] = None
    fast_mode: bool = False

    def __post_init__(self):
        if self.iterations < 1:
            raise ValueError(f"iterations must be >= 1, got {self.iterations}")
        if self.warmup < 0:
            raise ValueError(f"warmup must be >= 0, got {self.warmup}")
        if not self.benchmarks:
            raise ValueError("benchmarks list cannot be empty")


def parse_pyperf_json(data: dict) -> Dict[str, float]:
    """
    Parse pyperformance JSON output into benchmark name -> median time mapping.

    Args:
        data: Parsed JSON from pyperformance output

    Returns:
        Dictionary mapping benchmark name to median execution time

    Raises:
        ValueError: If benchmarks list is empty or malformed
    """
    benchmarks = data.get("benchmarks", [])
    if not benchmarks:
        raise ValueError("No benchmarks found in pyperformance output")

    result = {}
    for bench in benchmarks:
        name = bench.get("name")
        median = bench.get("median")
        if name is None or median is None:
            logger.warning(f"Skipping malformed benchmark entry: {bench}")
            continue
        result[name] = float(median)

    if not result:
        raise ValueError("No valid benchmark results found")

    return result


def run_single_benchmark(
    benchmark: str, iterations: int = 5, warmup: int = 1, fast_mode: bool = False
) -> Dict[str, any]:
    """
    Run a single benchmark using pyperformance.

    Args:
        benchmark: Name of the benchmark to run
        iterations: Number of iterations to run
        warmup: Number of warmup iterations
        fast_mode: If True, use --fast flag for quicker results

    Returns:
        Dictionary with benchmark results including median, mean, stddev
    """
    cmd = [
        sys.executable,
        "-m",
        "pyperformance",
        "run",
        "-b",
        benchmark,
        "--output",
        "-",  # Output to stdout
    ]

    if fast_mode:
        cmd.append("--fast")

    logger.info(f"Running benchmark: {benchmark}")
    logger.debug(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout per benchmark
        )

        if result.returncode != 0:
            logger.error(f"Benchmark {benchmark} failed: {result.stderr}")
            return {"name": benchmark, "error": result.stderr, "status": "failed"}

        # Parse JSON output
        data = json.loads(result.stdout)
        parsed = parse_pyperf_json(data)

        if benchmark not in parsed:
            return {
                "name": benchmark,
                "error": f"Benchmark {benchmark} not found in output",
                "status": "missing",
            }

        return {"name": benchmark, "median": parsed[benchmark], "status": "ok"}

    except subprocess.TimeoutExpired:
        logger.error(f"Benchmark {benchmark} timed out")
        return {
            "name": benchmark,
            "error": "Timeout after 300 seconds",
            "status": "timeout",
        }
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse benchmark output: {e}")
        return {
            "name": benchmark,
            "error": f"JSON parse error: {e}",
            "status": "parse_error",
        }
    except Exception as e:
        logger.error(f"Unexpected error running {benchmark}: {e}")
        return {"name": benchmark, "error": str(e), "status": "error"}


def run_benchmark_subset(config: BenchmarkConfig) -> Dict[str, any]:
    """
    Run the configured benchmark subset.

    Args:
        config: BenchmarkConfig with benchmarks, iterations, etc.

    Returns:
        Dictionary with complete results for all benchmarks
    """
    logger.info(f"Running {len(config.benchmarks)} benchmarks")
    logger.info(
        f"Configuration: iterations={config.iterations}, warmup={config.warmup}"
    )

    results = {
        "config": {
            "benchmarks": config.benchmarks,
            "iterations": config.iterations,
            "warmup": config.warmup,
            "fast_mode": config.fast_mode,
        },
        "benchmarks": [],
        "summary": {"total": len(config.benchmarks), "passed": 0, "failed": 0},
    }

    for benchmark in config.benchmarks:
        bench_result = run_single_benchmark(
            benchmark,
            iterations=config.iterations,
            warmup=config.warmup,
            fast_mode=config.fast_mode,
        )
        results["benchmarks"].append(bench_result)

        if bench_result.get("status") == "ok":
            results["summary"]["passed"] += 1
        else:
            results["summary"]["failed"] += 1

    # Calculate geometric mean of successful benchmarks
    successful_times = [
        b["median"]
        for b in results["benchmarks"]
        if b.get("status") == "ok" and "median" in b
    ]

    if successful_times:
        results["summary"]["geometric_mean"] = calculate_geometric_mean(
            successful_times
        )

    return results


def calculate_geometric_mean(values: List[float]) -> float:
    """Calculate geometric mean of a list of values."""
    import math

    if not values:
        raise ValueError("Cannot calculate geometric mean of empty list")
    product = 1.0
    for v in values:
        product *= v
    return product ** (1.0 / len(values))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run JIT-focused benchmark subset")
    parser.add_argument(
        "--benchmarks",
        nargs="+",
        default=DEFAULT_BENCHMARKS,
        help=f"Benchmarks to run (default: {' '.join(DEFAULT_BENCHMARKS)})",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Number of iterations per benchmark (default: 5)",
    )
    parser.add_argument(
        "--warmup", type=int, default=1, help="Number of warmup iterations (default: 1)"
    )
    parser.add_argument(
        "--output", "-o", type=Path, help="Output file path for JSON results"
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use --fast mode for quicker results (less accurate)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        config = BenchmarkConfig(
            benchmarks=args.benchmarks,
            iterations=args.iterations,
            warmup=args.warmup,
            output_path=args.output,
            fast_mode=args.fast,
        )
    except ValueError as e:
        logger.error(f"Invalid configuration: {e}")
        return 1

    results = run_benchmark_subset(config)

    # Output results
    json_output = json.dumps(results, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_output)
        logger.info(f"Results written to {args.output}")
    else:
        print(json_output)

    # Return non-zero if any benchmarks failed
    return 0 if results["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
