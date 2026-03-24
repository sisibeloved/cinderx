---
phase: 03-validation
subphase: 3A-quick
plan: 02
type: tdd
wave: 1
depends_on: [03A-01]
files_modified:
  - scripts/bench/macos_smoke_test.py
  - scripts/bench/quick_validation.sh
autonomous: true
requirements:
  - PR-001
  - PR-003
must_haves:
  truths:
    - macOS smoke test can be run with single command
    - Quick validation completes in under 10 minutes
    - Build time increase is measured and validated < 30%
    - Test results indicate pass/fail status clearly
  artifacts:
    - path: scripts/bench/macos_smoke_test.py
      provides: macOS-local quick validation with build time measurement
      min_lines: 250
      exports: ["run_smoke_test", "measure_build_time"]
    - path: scripts/bench/quick_validation.sh
      provides: One-command validation wrapper script
      min_lines: 100
      exports: []
  key_links:
    - from: scripts/bench/macos_smoke_test.py
      to: scripts/bench/run_pyperf_subset.py
      via: import and execute benchmark subset
      pattern: "from.*run_pyperf_subset import"
    - from: scripts/bench/quick_validation.sh
      to: scripts/bench/macos_smoke_test.py
      via: subprocess execution
      pattern: "python.*macos_smoke_test.py"
---

<objective>
Implement macOS-local quick validation for LTO changes with build time measurement and smoke test capabilities.

Purpose: Provide developers with a fast feedback loop (under 10 minutes) to validate LTO changes locally on macOS before pushing to CI, measuring build time increase to ensure it stays under 30%.

Output:
- scripts/bench/macos_smoke_test.py: Python script for macOS validation
- scripts/bench/quick_validation.sh: Shell wrapper for one-command execution
</objective>

<execution_context>
@$HOME/.config/opencode/get-shit-done/workflows/execute-plan.md
@$HOME/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@scripts/bench/run_pyperf_subset.py (from 03A-01)

<interfaces>
<!-- Interface from run_pyperf_subset.py -->
```python
from scripts.bench.run_pyperf_subset import (
    BenchmarkConfig,
    run_benchmark_subset
)

# Usage:
config = BenchmarkConfig(
    benchmarks=["richards", "nbody", "deltablue", "regex_compile", "nqueens"],
    iterations=3,
    warmup=1
)
results = run_benchmark_subset(config)
```

<!-- macOS specific notes from PROJECT.md -->
```
macOS: 优雅降级（禁用 LTO，文档说明限制）
- LTO is disabled on macOS automatically
- Build should complete successfully without LTO
- Smoke test validates basic functionality
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write tests for macOS smoke test</name>
  <files>scripts/bench/test_macos_smoke.py</files>
  <behavior>
    - Test build time measurement accuracy
    - Test build time increase calculation
    - Test smoke test result validation
    - Test 30% threshold enforcement
    - Test timeout handling
  </behavior>
  <action>
    Create scripts/bench/test_macos_smoke.py:

    ```python
    #!/usr/bin/env python3
    """Unit tests for macOS smoke test functionality."""
    import unittest
    import tempfile
    import time
    from pathlib import Path
    from unittest.mock import Mock, patch
    from scripts.bench.macos_smoke_test import (
        measure_build_time,
        calculate_build_time_increase,
        validate_smoke_test_results,
        SmokeTestConfig
    )

    class TestSmokeTestConfig(unittest.TestCase):
        def test_valid_config(self):
            config = SmokeTestConfig(
                baseline_build_dir="/tmp/baseline",
                lto_build_dir="/tmp/lto",
                max_build_time_increase_pct=30.0
            )
            self.assertEqual(config.max_build_time_increase_pct, 30.0)

        def test_invalid_build_time_threshold(self):
            with self.assertRaises(ValueError):
                SmokeTestConfig(max_build_time_increase_pct=-1.0)

    class TestMeasureBuildTime(unittest.TestCase):
        def test_returns_time_and_success(self):
            def mock_build():
                time.sleep(0.01)
                return 0  # Success
            
            duration, success = measure_build_time(mock_build)
            self.assertTrue(success)
            self.assertGreater(duration, 0)

        def test_returns_time_and_failure(self):
            def mock_build():
                return 1  # Failure
            
            duration, success = measure_build_time(mock_build)
            self.assertFalse(success)

        def test_timeout_handling(self):
            def slow_build():
                time.sleep(10)
                return 0
            
            duration, success = measure_build_time(slow_build, timeout=0.01)
            self.assertFalse(success)

    class TestCalculateBuildTimeIncrease(unittest.TestCase):
        def test_no_increase(self):
            result = calculate_build_time_increase(100.0, 100.0)
            self.assertEqual(result, 0.0)

        def test_30_percent_increase(self):
            result = calculate_build_time_increase(100.0, 130.0)
            self.assertEqual(result, 30.0)

        def test_50_percent_increase(self):
            result = calculate_build_time_increase(100.0, 150.0)
            self.assertEqual(result, 50.0)

        def test_invalid_baseline(self):
            with self.assertRaises(ValueError):
                calculate_build_time_increase(0.0, 100.0)

    class TestValidateSmokeTestResults(unittest.TestCase):
        def test_all_pass(self):
            results = {
                "build_time_increase_pct": 15.0,
                "benchmarks_passed": 5,
                "benchmarks_failed": 0
            }
            config = SmokeTestConfig(max_build_time_increase_pct=30.0)
            is_valid, issues = validate_smoke_test_results(results, config)
            self.assertTrue(is_valid)
            self.assertEqual(len(issues), 0)

        def test_build_time_exceeded(self):
            results = {
                "build_time_increase_pct": 35.0,
                "benchmarks_passed": 5,
                "benchmarks_failed": 0
            }
            config = SmokeTestConfig(max_build_time_increase_pct=30.0)
            is_valid, issues = validate_smoke_test_results(results, config)
            self.assertFalse(is_valid)
            self.assertIn("build_time", str(issues))

        def test_benchmarks_failed(self):
            results = {
                "build_time_increase_pct": 15.0,
                "benchmarks_passed": 3,
                "benchmarks_failed": 2
            }
            config = SmokeTestConfig(max_build_time_increase_pct=30.0)
            is_valid, issues = validate_smoke_test_results(results, config)
            self.assertFalse(is_valid)
            self.assertIn("benchmark", str(issues))

    if __name__ == "__main__":
        unittest.main()
    ```

    Save to scripts/bench/test_macos_smoke.py
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && python -m pytest scripts/bench/test_macos_smoke.py -v 2>&1 | grep -E "(PASSED|FAILED)" | head -15</automated>
  </verify>
  <done>Unit tests created and initially failing (RED phase)</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement macOS smoke test (macos_smoke_test.py)</name>
  <files>scripts/bench/macos_smoke_test.py</files>
  <behavior>
    - Dataclass SmokeTestConfig with paths and thresholds
    - Function measure_build_time(build_func, timeout) -> (duration, success)
    - Function calculate_build_time_increase(baseline, lto) -> percentage
    - Function run_smoke_test(config) -> results dict
    - Function validate_smoke_test_results(results, config) -> (bool, issues)
    - CLI interface with --baseline-dir, --lto-dir, --iterations
    - macOS-specific handling (no LTO, expect graceful degradation)
  </behavior>
  <action>
    Create scripts/bench/macos_smoke_test.py:

    ```python
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
    import subprocess
    import sys
    import time
    from dataclasses import dataclass, field
    from pathlib import Path
    from typing import Callable, Dict, List, Optional, Tuple

    # Import from sibling module
    sys.path.insert(0, str(Path(__file__).parent))
    from run_pyperf_subset import BenchmarkConfig, run_benchmark_subset

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
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
        build_func: Callable[[], int],
        timeout: float = 300.0
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
            success = (exit_code == 0)
            return duration, success
        except Exception as e:
            logger.error(f"Build failed with exception: {e}")
            duration = time.perf_counter() - start_time
            return duration, False


    def calculate_build_time_increase(
        baseline_time: float,
        current_time: float
    ) -> float:
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
                timeout=300  # 5 minute timeout for build
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
        results: Dict[str, any],
        config: SmokeTestConfig
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


    def run_smoke_test(config: SmokeTestConfig) -> Dict[str, any]:
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
                "quick_mode": config.quick_mode
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
            "passed": False
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
            fast_mode=config.quick_mode
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


    def print_summary(results: Dict[str, any]) -> None:
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
        parser = argparse.ArgumentParser(
            description="macOS smoke test for LTO validation"
        )
        parser.add_argument(
            "--max-build-increase",
            type=float,
            default=DEFAULT_MAX_BUILD_TIME_INCREASE_PCT,
            help=f"Max build time increase percentage (default: {DEFAULT_MAX_BUILD_TIME_INCREASE_PCT}%)"
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=DEFAULT_ITERATIONS,
            help=f"Benchmark iterations (default: {DEFAULT_ITERATIONS})"
        )
        parser.add_argument(
            "--quick",
            action="store_true",
            help="Quick mode: single iteration, faster feedback"
        )
        parser.add_argument(
            "--output",
            "-o",
            type=Path,
            help="Output file path for JSON results"
        )
        parser.add_argument(
            "--verbose",
            "-v",
            action="store_true",
            help="Enable verbose logging"
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
                output_path=args.output
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
        import os
        sys.exit(main())
    ```

    Make the script executable: chmod +x scripts/bench/macos_smoke_test.py
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && python -m pytest scripts/bench/test_macos_smoke.py::TestMeasureBuildTime -v 2>&1 | grep -E "(PASSED|FAILED)"</automated>
  </verify>
  <done>macos_smoke_test.py implemented, build time tests passing (GREEN phase)</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Implement quick validation shell script</name>
  <files>scripts/bench/quick_validation.sh</files>
  <behavior>
    - Shell wrapper for one-command execution
    - Detects platform (macOS vs Linux)
    - Runs appropriate validation (smoke test on macOS)
    - Provides clear pass/fail output
    - Handles errors gracefully
  </behavior>
  <action>
    Create scripts/bench/quick_validation.sh:

    ```bash
    #!/bin/bash
    #
    # Quick validation script for CinderX LTO changes
    #
    # This script provides a single-command validation that:
    # - Runs on macOS (smoke test with graceful degradation)
    # - Runs on Linux (full validation where available)
    # - Completes in under 10 minutes
    # - Provides clear pass/fail output
    #
    # Usage:
    #   ./scripts/bench/quick_validation.sh
    #   ./scripts/bench/quick_validation.sh --quick
    #   ./scripts/bench/quick_validation.sh --verbose
    #

    set -euo pipefail

    # Script directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

    # Default options
    QUICK_MODE=""
    VERBOSE=""
    OUTPUT_DIR="${PROJECT_ROOT}/.benchmark_results"

    # Colors for output
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m' # No Color

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --quick)
                QUICK_MODE="--quick"
                shift
                ;;
            --verbose|-v)
                VERBOSE="--verbose"
                shift
                ;;
            --output-dir)
                OUTPUT_DIR="$2"
                shift 2
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --quick         Quick mode: single iteration, faster feedback"
                echo "  --verbose, -v   Enable verbose output"
                echo "  --output-dir    Directory for results (default: .benchmark_results)"
                echo "  --help, -h      Show this help message"
                echo ""
                echo "Examples:"
                echo "  $0                      # Standard validation"
                echo "  $0 --quick              # Quick validation (~5 min)"
                echo "  $0 --verbose            # Verbose output"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done

    # Create output directory
    mkdir -p "${OUTPUT_DIR}"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)

    # Detect platform
    PLATFORM=$(uname -s)
    ARCH=$(uname -m)

    echo "=============================================="
    echo "CinderX LTO Quick Validation"
    echo "=============================================="
    echo "Platform: ${PLATFORM} (${ARCH})"
    echo "Timestamp: ${TIMESTAMP}"
    echo "Output: ${OUTPUT_DIR}"
    echo ""

    # Change to project root
    cd "${PROJECT_ROOT}"

    # Platform-specific validation
    case "${PLATFORM}" in
        Darwin)
            echo -e "${YELLOW}Running macOS Smoke Test${NC}"
            echo "Note: LTO is not supported on macOS."
            echo "Testing graceful degradation and basic functionality."
            echo ""
            
            PYTHON_CMD=$(command -v python3 || command -v python)
            if [[ -z "${PYTHON_CMD}" ]]; then
                echo -e "${RED}Error: Python not found${NC}"
                exit 1
            fi
            
            OUTPUT_FILE="${OUTPUT_DIR}/macos_smoke_${TIMESTAMP}.json"
            
            if "${PYTHON_CMD}" "${SCRIPT_DIR}/macos_smoke_test.py" \
                ${QUICK_MODE} \
                ${VERBOSE} \
                --output "${OUTPUT_FILE}"; then
                echo ""
                echo -e "${GREEN}✅ macOS Smoke Test PASSED${NC}"
                echo "Results saved to: ${OUTPUT_FILE}"
                exit 0
            else
                echo ""
                echo -e "${RED}❌ macOS Smoke Test FAILED${NC}"
                echo "Results saved to: ${OUTPUT_FILE}"
                exit 1
            fi
            ;;
            
        Linux)
            echo -e "${YELLOW}Running Linux Quick Validation${NC}"
            echo "Note: Full LTO validation requires Docker ARM environment."
            echo "Running subset validation only."
            echo ""
            
            PYTHON_CMD=$(command -v python3 || command -v python)
            if [[ -z "${PYTHON_CMD}" ]]; then
                echo -e "${RED}Error: Python not found${NC}"
                exit 1
            fi
            
            # For Linux, we can run a simplified version
            # that doesn't require full Docker setup
            OUTPUT_FILE="${OUTPUT_DIR}/linux_quick_${TIMESTAMP}.json"
            
            echo "Step 1: Running 5-benchmark subset..."
            if "${PYTHON_CMD}" "${SCRIPT_DIR}/run_pyperf_subset.py" \
                --iterations 3 \
                --output "${OUTPUT_FILE}"; then
                echo ""
                echo -e "${GREEN}✅ Linux Quick Validation PASSED${NC}"
                echo "Results saved to: ${OUTPUT_FILE}"
                echo ""
                echo "Note: For full LTO validation including build time comparison,"
                echo "      use the Docker ARM environment (Phase 3B)."
                exit 0
            else
                echo ""
                echo -e "${RED}❌ Linux Quick Validation FAILED${NC}"
                exit 1
            fi
            ;;
            
        *)
            echo -e "${RED}Error: Unsupported platform: ${PLATFORM}${NC}"
            echo "Supported platforms: Darwin (macOS), Linux"
            exit 1
            ;;
    esac
    ```

    Make the script executable: chmod +x scripts/bench/quick_validation.sh
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && bash -n scripts/bench/quick_validation.sh && echo "Shell script syntax OK"</automated>
  </verify>
  <done>quick_validation.sh shell wrapper created with proper error handling</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Run all tests and verify complete implementation</name>
  <files>scripts/bench/test_macos_smoke.py</files>
  <behavior>
    - Run all macOS smoke test unit tests
    - Verify test coverage is complete
    - Ensure no regressions in existing tests
  </behavior>
  <action>
    Run the complete test suite:

    ```bash
    cd /Users/luchen/Agents-Repo/OpenCode/cinderx
    python -m pytest scripts/bench/test_macos_smoke.py -v --tb=short
    ```

    Then verify shell script:
    ```bash
    bash -n scripts/bench/quick_validation.sh
    ```
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && python -m pytest scripts/bench/test_macos_smoke.py -v 2>&1 | tail -15</automated>
  </verify>
  <done>All tests passing, macOS smoke test and quick validation ready (REFACTOR phase complete)</done>
</task>

</tasks>

<verification>
- [ ] scripts/bench/test_macos_smoke.py exists with comprehensive unit tests
- [ ] scripts/bench/macos_smoke_test.py implements macOS validation with build time measurement
- [ ] scripts/bench/quick_validation.sh provides one-command execution
- [ ] All unit tests passing
- [ ] Build time measurement working correctly
- [ ] 30% threshold validation working
- [ ] Shell script syntax validated
</verification>

<success_criteria>
- macOS smoke test can be run with single command: ./scripts/bench/quick_validation.sh
- Build time measurement accurate within 1 second tolerance
- Build time increase validation enforces < 30% threshold
- Quick validation completes in under 10 minutes
- All unit tests passing
- Scripts provide clear pass/fail output
</success_criteria>

<output>
After completion, create `.planning/phases/03-validation/03A-02-SUMMARY.md`
</output>

<atomic_commits>
Commit 1: `test(03A-02): add unit tests for macOS smoke test`
- Add scripts/bench/test_macos_smoke.py
- Tests for SmokeTestConfig, measure_build_time, build time calculations
- Tests initially failing (RED phase)

Commit 2: `feat(03A-02): implement macOS smoke test with build time measurement`
- Add scripts/bench/macos_smoke_test.py
- Build time measurement with subprocess
- 30% threshold validation
- Benchmark subset integration
- CLI interface with argparse

Commit 3: `feat(03A-02): add quick validation shell wrapper`
- Add scripts/bench/quick_validation.sh
- Platform detection (macOS/Linux)
- One-command execution
- All tests passing (GREEN phase)
</atomic_commits>
