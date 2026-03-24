#!/usr/bin/env python3
"""
Fixed version of run_pyperf_subset.py
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Default benchmarks that are JIT-intensive
DEFAULT_BENCHMARKS = [
    "richards",
    "nbody",
    "deltablue",
    "regex_compile",
    "nqueens",
]

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark run."""

    benchmarks: List[str]
    iterations: int = 5
    warmup: int = 1
    output_file: Optional[Path] = None
    fast_mode: bool = False
    verbose: bool = False


def parse_pyperf_json(data: dict) -> Dict[str, float]:
    """
    Parse pyperformance JSON output to extract benchmark results.

    Args:
        data: JSON data from pyperformance

    Returns:
        Dictionary mapping benchmark name to median value in seconds
    """
    import statistics

    results = {}

    # Get benchmark name from top-level metadata
    metadata = data.get("metadata", {})
    benchmark_name = metadata.get("name")

    if not benchmark_name:
        raise ValueError("No benchmark name found in metadata")

    # Extract all values from all runs
    benchmarks = data.get("benchmarks", [])
    if not benchmarks:
        raise ValueError("No benchmarks found in pyperformance output")

    all_values = []
    for benchmark in benchmarks:
        runs = benchmark.get("runs", [])
        for run in runs:
            values = run.get("values", [])
            if values:
                all_values.extend(values)

    if not all_values:
        raise ValueError(f"No benchmark values found for {benchmark_name}")

    # Calculate median
    median_value = statistics.median(all_values)
    results[benchmark_name] = median_value

    logger.debug(f"Parsed {benchmark_name}: median={median_value:.6f}s from {len(all_values)} values")

    return results


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
    # Use a unique filename for output (don't create it yet, pyperformance doesn't like existing files)
    import uuid
    temp_dir = tempfile.gettempdir()
    temp_output = os.path.join(temp_dir, f"pyperf_{uuid.uuid4().hex}.json")

    try:
        cmd = [
            sys.executable,
            "-m",
            "pyperformance",
            "run",
            "-b",
            benchmark,
            "--output",
            temp_output,
        ]

        if fast_mode:
            cmd.append("--fast")

        logger.info(f"Running benchmark: {benchmark}")
        logger.debug(f"Command: {' '.join(cmd)}")

        # Ensure JIT can allocate memory on macOS
        env = dict(os.environ)
        env.setdefault("PYTHONJITHUGEPAGES", "0")

        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout per benchmark
        )

        if result.returncode != 0:
            logger.error(f"Benchmark {benchmark} failed: {result.stderr}")
            return {"name": benchmark, "error": result.stderr, "status": "failed"}

        # Read JSON output from temp file
        with open(temp_output, 'r') as f:
            data = json.load(f)

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
    finally:
        # Clean up temp file
        try:
            if temp_output and os.path.exists(temp_output):
                os.unlink(temp_output)
        except:
            pass


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
        "summary": {"total": 0, "passed": 0, "failed": 0},
    }

    for benchmark in config.benchmarks:
        result = run_single_benchmark(
            benchmark,
            iterations=config.iterations,
            warmup=config.warmup,
            fast_mode=config.fast_mode,
        )
        results["benchmarks"].append(result)
        results["summary"]["total"] += 1

        if result.get("status") == "ok":
            results["summary"]["passed"] += 1
        else:
            results["summary"]["failed"] += 1

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run JIT-focused benchmark subset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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
        "--warmup",
        type=int,
        default=1,
        help="Number of warmup iterations (default: 1)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output file path for JSON results",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Use --fast mode for quicker results (less accurate)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = BenchmarkConfig(
        benchmarks=args.benchmarks,
        iterations=args.iterations,
        warmup=args.warmup,
        output_file=args.output,
        fast_mode=args.fast,
        verbose=args.verbose,
    )

    results = run_benchmark_subset(config)

    # Output results
    output_json = json.dumps(results, indent=2)
    if config.output_file:
        config.output_file.write_text(output_json)
        logger.info(f"Results written to {config.output_file}")
    else:
        print(output_json)

    # Return exit code based on results
    if results["summary"]["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
