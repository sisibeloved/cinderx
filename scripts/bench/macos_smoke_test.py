#!/usr/bin/env python3
"""
macOS-local quick validation for LTO changes.

This script provides fast iteration testing on macOS (under 10 minutes)
to validate that changes don't break the build or cause performance regressions.

Note: macOS does not support LTO, so this tests the graceful degradation path
and validates that the non-LTO build still works correctly.

Usage:
    python scripts/bench/macos_smoke_test.py
    python scripts/bench/macos_smoke_test.py --quick
    python scripts/bench/macos_smoke_test.py --output results.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any

# Import from sibling module
sys.path.insert(0, str(Path(__file__).parent))
from run_pyperf_subset import BenchmarkConfig, run_benchmark_subset

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DEFAULT_MAX_BUILD_TIME_INCREASE_PCT = 30.0
DEFAULT_ITERATIONS = 3
DEFAULT_TIMEOUT_SECONDS = 600  # 10 minutes


@dataclass
class SmokeTestConfig:
    """Configuration for smoke test execution."""

    baseline_build_dir: Optional[Path] = None
    lto_build_dir: Optional[Path] = None
    max_build_time_increase_pct: float = DEFAULT_MAX_BUILD_TIME_INCREASE_PCT
    iterations: int = DEFAULT_ITERATIONS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    quick_mode: bool = False
    output_path: Optional[Path] = None

    def __post_init__(self):
        if self.max_build_time_increase_pct <= 0:
            raise ValueError(
                f"max_build_time_increase_pct must be positive, "
                f"got {self.max_build_time_increase_pct}"
            )
        if self.iterations < 1:
            raise ValueError(f"iterations must be >= 1, got {self.iterations}")


def measure_build_time(
    build_func: Callable[[], int], timeout: float = 300.0
) -> Tuple[float, bool]:
    """
    Measure the execution time of a build function.

    Args:
        build_func: Function that performs the build and returns exit code
        timeout: Maximum time to wait in seconds

    Returns:
        Tuple of (duration_seconds, success_boolean)
    """
    start_time = time.perf_counter()

    try:
        exit_code = build_func()
        duration = time.perf_counter() - start_time
        success = exit_code == 0
        return duration, success
    except Exception as e:
        logger.error(f"Build failed with exception: {e}")
        duration = time.perf_counter() - start_time
        return duration, False


def calculate_build_time_increase(baseline_time: float, current_time: float) -> float:
    """
    Calculate percentage increase in build time.

    Args:
        baseline_time: Baseline build time in seconds
        current_time: Current build time in seconds

    Returns:
        Percentage increase (0.0 = no increase, 30.0 = 30% increase)

    Raises:
        ValueError: If baseline_time is zero or negative
    """
    if baseline_time <= 0:
        raise ValueError(f"Baseline time must be positive, got {baseline_time}")

    increase = ((current_time / baseline_time) - 1.0) * 100.0
    return increase


def run_cinderx_build(enable_lto: bool = False) -> int:
    """
    Run CinderX build with specified LTO configuration.

    Args:
        enable_lto: Whether to enable LTO (note: macOS will gracefully degrade)

    Returns:
        Exit code from build process
    """
    env = dict(os.environ)
    env["CINDERX_ENABLE_LTO"] = "1" if enable_lto else "0"
    env["CINDERX_ENABLE_PGO"] = "0"  # Never enable PGO for smoke tests

    cmd = [sys.executable, "setup.py", "build_ext", "--inplace"]

    logger.info(f"Running build with LTO={'enabled' if enable_lto else 'disabled'}")
    logger.debug(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout for build
        )

        if result.returncode != 0:
            logger.error(f"Build failed:\n{result.stderr}")
        else:
            logger.info("Build completed successfully")

        return result.returncode

    except subprocess.TimeoutExpired:
        logger.error("Build timed out after 300 seconds")
        return 1
    except Exception as e:
        logger.error(f"Build failed with exception: {e}")
        return 1


def validate_smoke_test_results(
    results: Dict[str, Any], config: SmokeTestConfig
) -> Tuple[bool, List[str]]:
    """
    Validate smoke test results against thresholds.

    Args:
        results: Results dictionary from run_smoke_test
        config: SmokeTestConfig with validation thresholds

    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []

    # Check build time increase
    build_time_increase = results.get("build_time_increase_pct", 0.0)
    if build_time_increase > config.max_build_time_increase_pct:
        issues.append(
            f"Build time increase ({build_time_increase:.1f}%) exceeds "
            f"threshold ({config.max_build_time_increase_pct:.1f}%)"
        )

    # Check benchmark results
    benchmarks_failed = results.get("benchmarks_failed", 0)
    if benchmarks_failed > 0:
        issues.append(f"{benchmarks_failed} benchmark(s) failed")

    benchmarks_passed = results.get("benchmarks_passed", 0)
    if benchmarks_passed == 0:
        issues.append("No benchmarks passed")

    # Check for critical errors
    if results.get("baseline_build_failed", False):
        issues.append("Baseline build failed")

    if results.get("lto_build_failed", False):
        issues.append("LTO build failed")

    return len(issues) == 0, issues


def run_smoke_test(config: SmokeTestConfig) -> Dict[str, Any]:
    """
    Execute the complete smoke test.

    Args:
        config: SmokeTestConfig with test parameters

    Returns:
        Dictionary with complete test results
    """
    results = {
        "config": {
            "max_build_time_increase_pct": config.max_build_time_increase_pct,
            "iterations": config.iterations,
            "quick_mode": config.quick_mode,
        },
        "baseline_build_time": None,
        "baseline_build_failed": False,
        "lto_build_time": None,
        "lto_build_failed": False,
        "build_time_increase_pct": None,
        "benchmarks": [],
        "benchmarks_passed": 0,
        "benchmarks_failed": 0,
        "issues": [],
        "passed": False,
    }

    # Step 1: Measure baseline build time (no LTO)
    logger.info("=" * 60)
    logger.info("STEP 1: Baseline Build (No LTO)")
    logger.info("=" * 60)

    baseline_duration, baseline_success = measure_build_time(
        lambda: run_cinderx_build(enable_lto=False)
    )
    results["baseline_build_time"] = baseline_duration
    results["baseline_build_failed"] = not baseline_success

    if not baseline_success:
        results["issues"].append("Baseline build failed")
        return results

    logger.info(f"Baseline build time: {baseline_duration:.2f}s")

    # Step 2: Measure LTO build time (macOS will gracefully degrade)
    logger.info("=" * 60)
    logger.info("STEP 2: LTO Build (macOS: graceful degradation)")
    logger.info("=" * 60)

    lto_duration, lto_success = measure_build_time(
        lambda: run_cinderx_build(enable_lto=True)
    )
    results["lto_build_time"] = lto_duration
    results["lto_build_failed"] = not lto_success

    if not lto_success:
        results["issues"].append("LTO build failed")
        return results

    logger.info(f"LTO build time: {lto_duration:.2f}s")

    # Step 3: Calculate build time increase
    try:
        increase = calculate_build_time_increase(baseline_duration, lto_duration)
        results["build_time_increase_pct"] = increase
        logger.info(f"Build time increase: {increase:.1f}%")

        if increase > config.max_build_time_increase_pct:
            results["issues"].append(
                f"Build time increase ({increase:.1f}%) exceeds threshold "
                f"({config.max_build_time_increase_pct:.1f}%)"
            )
    except ValueError as e:
        logger.error(f"Failed to calculate build time increase: {e}")
        results["issues"].append(f"Build time calculation error: {e}")

    # Step 4: Run benchmark subset
    logger.info("=" * 60)
    logger.info("STEP 3: Running Benchmark Subset")
    logger.info("=" * 60)

    iterations = 1 if config.quick_mode else config.iterations

    bench_config = BenchmarkConfig(
        benchmarks=["richards", "nbody", "deltablue", "regex_compile", "nqueens"],
        iterations=iterations,
        warmup=1,
        fast_mode=config.quick_mode,
    )

    try:
        bench_results = run_benchmark_subset(bench_config)
        results["benchmarks"] = bench_results.get("benchmarks", [])
        results["benchmarks_passed"] = bench_results["summary"]["passed"]
        results["benchmarks_failed"] = bench_results["summary"]["failed"]

        if results["benchmarks_failed"] > 0:
            results["issues"].append(
                f"{results['benchmarks_failed']} benchmark(s) failed"
            )

    except Exception as e:
        logger.error(f"Benchmark execution failed: {e}")
        results["issues"].append(f"Benchmark error: {e}")

    # Step 5: Validate results
    is_valid, validation_issues = validate_smoke_test_results(results, config)
    results["issues"].extend(validation_issues)
    results["passed"] = is_valid and len(results["issues"]) == 0

    return results


def print_summary(results: Dict[str, Any]) -> None:
    """Print formatted summary of smoke test results."""
    print("\n" + "=" * 60)
    print("SMOKE TEST SUMMARY")
    print("=" * 60)

    # Build times
    baseline_time = results.get("baseline_build_time")
    lto_time = results.get("lto_build_time")
    increase = results.get("build_time_increase_pct")

    print(f"\nBuild Times:")
    if baseline_time is not None:
        print(f"  Baseline (no LTO): {baseline_time:.2f}s")
    if lto_time is not None:
        print(f"  LTO:               {lto_time:.2f}s")
    if increase is not None:
        status = "✅" if increase <= 30.0 else "❌"
        print(f"  Increase:          {increase:.1f}% {status}")

    # Benchmarks
    passed = results.get("benchmarks_passed", 0)
    failed = results.get("benchmarks_failed", 0)
    print(f"\nBenchmarks:")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")

    # Issues
    issues = results.get("issues", [])
    if issues:
        print(f"\nIssues ({len(issues)}):")
        for issue in issues:
            print(f"  ❌ {issue}")
    else:
        print(f"\nIssues: None")

    # Final status
    print("\n" + "=" * 60)
    if results.get("passed", False):
        print("✅ SMOKE TEST PASSED")
    else:
        print("❌ SMOKE TEST FAILED")
    print("=" * 60 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="macOS smoke test for LTO validation")
    parser.add_argument(
        "--max-build-increase",
        type=float,
        default=DEFAULT_MAX_BUILD_TIME_INCREASE_PCT,
        help=f"Max build time increase percentage (default: {DEFAULT_MAX_BUILD_TIME_INCREASE_PCT}%%)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help=f"Benchmark iterations (default: {DEFAULT_ITERATIONS})",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: single iteration, faster feedback",
    )
    parser.add_argument(
        "--output", "-o", type=Path, help="Output file path for JSON results"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("=" * 60)
    print("CinderX LTO Smoke Test (macOS)")
    print("=" * 60)
    print("\nNote: macOS does not support LTO.")
    print("This test validates graceful degradation and basic functionality.\n")

    try:
        config = SmokeTestConfig(
            max_build_time_increase_pct=args.max_build_increase,
            iterations=args.iterations,
            quick_mode=args.quick,
            output_path=args.output,
        )
    except ValueError as e:
        logger.error(f"Invalid configuration: {e}")
        return 2

    # Run smoke test
    start_time = time.perf_counter()
    results = run_smoke_test(config)
    total_time = time.perf_counter() - start_time

    results["total_duration_seconds"] = total_time

    # Print summary
    print_summary(results)

    # Write output if requested
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results written to {args.output}")

    # Return appropriate exit code
    if results.get("passed", False):
        logger.info(f"Smoke test completed in {total_time:.1f}s")
        return 0
    else:
        logger.error(f"Smoke test failed after {total_time:.1f}s")
        return 1


if __name__ == "__main__":
    sys.exit(main())
