---
phase: 03-validation
subphase: 3A-quick
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - scripts/bench/run_pyperf_subset.py
  - scripts/bench/compare_lto_impact.py
autonomous: true
requirements:
  - PR-001
  - PR-003
must_haves:
  truths:
    - 5-benchmark JIT subset can be run automatically with single command
    - LTO vs non-LTO comparison produces statistical results
    - Performance regression detection flags degradation > 1%
    - macOS local validation provides quick feedback loop
  artifacts:
    - path: scripts/bench/run_pyperf_subset.py
      provides: Automated 5-benchmark runner with configurable iterations
      min_lines: 200
      exports: ["run_benchmark_subset", "BenchmarkConfig"]
    - path: scripts/bench/compare_lto_impact.py
      provides: LTO vs non-LTO statistical comparison with regression detection
      min_lines: 300
      exports: ["compare_builds", "detect_regression", "generate_report"]
  key_links:
    - from: scripts/bench/run_pyperf_subset.py
      to: pyperformance CLI
      via: subprocess execution with JSON output parsing
      pattern: "pyperformance run.*--output"
    - from: scripts/bench/compare_lto_impact.py
      to: scripts/bench/run_pyperf_subset.py
      via: import and function call for benchmark execution
      pattern: "from.*run_pyperf_subset"
---

<objective>
Create fast-iteration benchmark automation for 5-benchmark JIT subset (richards, nbody, deltablue, regex_compile, nqueens) with LTO vs non-LTO comparison and < 1% regression detection.

Purpose: Enable rapid validation of LTO changes with quick feedback loop on macOS local environment before comprehensive ARM testing.

Output: 
- scripts/bench/run_pyperf_subset.py: Automated 5-benchmark runner
- scripts/bench/compare_lto_impact.py: Statistical comparison and regression detection
</objective>

<execution_context>
@$HOME/.config/opencode/get-shit-done/workflows/execute-plan.md
@$HOME/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/LTO_PGO_PERFORMANCE_ANALYSIS.md
@scripts/arm/compare_pyperf_subset.py
@scripts/bench/richards_metrics.py

<interfaces>
<!-- Existing benchmark comparison patterns from compare_pyperf_subset.py -->
```python
def load_summary(path: Path) -> dict[str, float]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        row["name"]: float(row["median"])
        for row in data.get("benchmarks", [])
    }
```

<!-- Existing metrics patterns from richards_metrics.py -->
```python
def summarize_samples(samples):
    vals = [float(x) for x in samples]
    return {
        "count": len(vals),
        "mean": statistics.mean(vals),
        "median": statistics.median(vals),
        "min": min(vals),
        "max": max(vals),
    }

def bootstrap_mean_ci(samples, iterations=5000, seed=42, alpha=0.05):
    # Returns (lower_bound, upper_bound) confidence interval
```

<!-- pyperformance JSON output format -->
```json
{
  "benchmarks": [
    {
      "name": "richards",
      "median": 0.0516,
      "mean": 0.0521,
      "stddev": 0.0012
    }
  ]
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write tests for benchmark automation framework</name>
  <files>scripts/bench/test_lto_benchmarks.py</files>
  <behavior>
    - Test BenchmarkConfig dataclass validation
    - Test pyperformance JSON parsing
    - Test geometric mean calculation
    - Test regression detection (< 1% threshold)
    - Test statistical significance (p-value < 0.05)
  </behavior>
  <action>
    Create scripts/bench/test_lto_benchmarks.py with comprehensive unit tests:

    ```python
    #!/usr/bin/env python3
    """Unit tests for LTO benchmark automation."""
    import unittest
    import json
    import tempfile
    from pathlib import Path
    from scripts.bench.run_pyperf_subset import BenchmarkConfig, parse_pyperf_json
    from scripts.bench.compare_lto_impact import (
        calculate_geometric_mean,
        detect_regression,
        compare_builds
    )

    class TestBenchmarkConfig(unittest.TestCase):
        def test_valid_config(self):
            config = BenchmarkConfig(
                benchmarks=["richards", "nbody"],
                iterations=5,
                warmup=1
            )
            self.assertEqual(len(config.benchmarks), 2)

        def test_invalid_iterations(self):
            with self.assertRaises(ValueError):
                BenchmarkConfig(iterations=0)

    class TestParsePyperfJson(unittest.TestCase):
        def test_valid_json(self):
            data = {
                "benchmarks": [
                    {"name": "richards", "median": 0.05},
                    {"name": "nbody", "median": 0.10}
                ]
            }
            result = parse_pyperf_json(data)
            self.assertEqual(result["richards"], 0.05)

        def test_empty_benchmarks(self):
            with self.assertRaises(ValueError):
                parse_pyperf_json({"benchmarks": []})

    class TestGeometricMean(unittest.TestCase):
        def test_basic_calculation(self):
            values = [1.0, 2.0, 4.0]
            result = calculate_geometric_mean(values)
            self.assertAlmostEqual(result, 2.0, places=5)

        def test_single_value(self):
            self.assertEqual(calculate_geometric_mean([5.0]), 5.0)

    class TestRegressionDetection(unittest.TestCase):
        def test_no_regression(self):
            # 0.5% improvement - within tolerance
            baseline = {"richards": 0.10}
            current = {"richards": 0.0995}
            regressions = detect_regression(baseline, current, threshold_pct=1.0)
            self.assertEqual(len(regressions), 0)

        def test_regression_detected(self):
            # 2% degradation - above threshold
            baseline = {"richards": 0.10}
            current = {"richards": 0.102}
            regressions = detect_regression(baseline, current, threshold_pct=1.0)
            self.assertEqual(len(regressions), 1)
            self.assertEqual(regressions[0]["benchmark"], "richards")
            self.assertAlmostEqual(regressions[0]["degradation_pct"], 2.0)

        def test_regression_at_threshold(self):
            # Exactly 1% degradation - should be flagged
            baseline = {"richards": 0.10}
            current = {"richards": 0.101}
            regressions = detect_regression(baseline, current, threshold_pct=1.0)
            self.assertEqual(len(regressions), 1)

        def test_missing_benchmark(self):
            baseline = {"richards": 0.10}
            current = {}  # Missing benchmark
            regressions = detect_regression(baseline, current, threshold_pct=1.0)
            self.assertEqual(len(regressions), 1)
            self.assertEqual(regressions[0]["benchmark"], "richards")
            self.assertEqual(regressions[0]["status"], "missing")

    if __name__ == "__main__":
        unittest.main()
    ```

    Save to scripts/bench/test_lto_benchmarks.py
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && python -m pytest scripts/bench/test_lto_benchmarks.py -v 2>&1 | grep -E "(PASSED|FAILED|ERROR)" | head -20</automated>
  </verify>
  <done>Unit tests created and initially failing (RED phase)</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement 5-benchmark subset runner (run_pyperf_subset.py)</name>
  <files>scripts/bench/run_pyperf_subset.py</files>
  <read_first>
    - scripts/arm/compare_pyperf_subset.py (JSON parsing pattern)
    - scripts/bench/richards_metrics.py (statistics patterns)
  </read_first>
  <behavior>
    - Dataclass BenchmarkConfig with benchmarks, iterations, warmup
    - Function run_benchmark_subset(config) -> JSON results
    - Function parse_pyperf_json(raw_data) -> dict[name, median_time]
    - Support for 5 JIT benchmarks: richards, nbody, deltablue, regex_compile, nqueens
    - CLI interface with argparse for --output, --iterations, --warmup
    - Proper error handling for pyperformance not found
  </behavior>
  <action>
    Create scripts/bench/run_pyperf_subset.py:

    ```python
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
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    # Default 5-benchmark JIT subset
    DEFAULT_BENCHMARKS = [
        "richards",
        "nbody", 
        "deltablue",
        "regex_compile",
        "nqueens"
    ]


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
        benchmark: str,
        iterations: int = 5,
        warmup: int = 1,
        fast_mode: bool = False
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
            sys.executable, "-m", "pyperformance", "run",
            "-b", benchmark,
            "--output", "-"  # Output to stdout
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
                timeout=300  # 5 minute timeout per benchmark
            )
            
            if result.returncode != 0:
                logger.error(f"Benchmark {benchmark} failed: {result.stderr}")
                return {
                    "name": benchmark,
                    "error": result.stderr,
                    "status": "failed"
                }
            
            # Parse JSON output
            data = json.loads(result.stdout)
            parsed = parse_pyperf_json(data)
            
            if benchmark not in parsed:
                return {
                    "name": benchmark,
                    "error": f"Benchmark {benchmark} not found in output",
                    "status": "missing"
                }
            
            return {
                "name": benchmark,
                "median": parsed[benchmark],
                "status": "ok"
            }
            
        except subprocess.TimeoutExpired:
            logger.error(f"Benchmark {benchmark} timed out")
            return {
                "name": benchmark,
                "error": "Timeout after 300 seconds",
                "status": "timeout"
            }
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse benchmark output: {e}")
            return {
                "name": benchmark,
                "error": f"JSON parse error: {e}",
                "status": "parse_error"
            }
        except Exception as e:
            logger.error(f"Unexpected error running {benchmark}: {e}")
            return {
                "name": benchmark,
                "error": str(e),
                "status": "error"
            }


    def run_benchmark_subset(config: BenchmarkConfig) -> Dict[str, any]:
        """
        Run the configured benchmark subset.
        
        Args:
            config: BenchmarkConfig with benchmarks, iterations, etc.
            
        Returns:
            Dictionary with complete results for all benchmarks
        """
        logger.info(f"Running {len(config.benchmarks)} benchmarks")
        logger.info(f"Configuration: iterations={config.iterations}, warmup={config.warmup}")
        
        results = {
            "config": {
                "benchmarks": config.benchmarks,
                "iterations": config.iterations,
                "warmup": config.warmup,
                "fast_mode": config.fast_mode
            },
            "benchmarks": [],
            "summary": {
                "total": len(config.benchmarks),
                "passed": 0,
                "failed": 0
            }
        }
        
        for benchmark in config.benchmarks:
            bench_result = run_single_benchmark(
                benchmark,
                iterations=config.iterations,
                warmup=config.warmup,
                fast_mode=config.fast_mode
            )
            results["benchmarks"].append(bench_result)
            
            if bench_result.get("status") == "ok":
                results["summary"]["passed"] += 1
            else:
                results["summary"]["failed"] += 1
        
        # Calculate geometric mean of successful benchmarks
        successful_times = [
            b["median"] for b in results["benchmarks"]
            if b.get("status") == "ok" and "median" in b
        ]
        
        if successful_times:
            results["summary"]["geometric_mean"] = calculate_geometric_mean(successful_times)
        
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
        parser = argparse.ArgumentParser(
            description="Run JIT-focused benchmark subset"
        )
        parser.add_argument(
            "--benchmarks",
            nargs="+",
            default=DEFAULT_BENCHMARKS,
            help=f"Benchmarks to run (default: {' '.join(DEFAULT_BENCHMARKS)})"
        )
        parser.add_argument(
            "--iterations",
            type=int,
            default=5,
            help="Number of iterations per benchmark (default: 5)"
        )
        parser.add_argument(
            "--warmup",
            type=int,
            default=1,
            help="Number of warmup iterations (default: 1)"
        )
        parser.add_argument(
            "--output",
            "-o",
            type=Path,
            help="Output file path for JSON results"
        )
        parser.add_argument(
            "--fast",
            action="store_true",
            help="Use --fast mode for quicker results (less accurate)"
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
        
        try:
            config = BenchmarkConfig(
                benchmarks=args.benchmarks,
                iterations=args.iterations,
                warmup=args.warmup,
                output_path=args.output,
                fast_mode=args.fast
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
    ```

    Make the script executable: chmod +x scripts/bench/run_pyperf_subset.py
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && python -m pytest scripts/bench/test_lto_benchmarks.py::TestBenchmarkConfig -v 2>&1 | grep -E "(PASSED|FAILED)" | head -5</automated>
  </verify>
  <done>run_pyperf_subset.py implemented, tests passing (GREEN phase)</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Implement LTO comparison and regression detection (compare_lto_impact.py)</name>
  <files>scripts/bench/compare_lto_impact.py</files>
  <read_first>
    - scripts/bench/richards_metrics.py (bootstrap CI patterns)
    - scripts/arm/compare_pyperf_subset.py (comparison patterns)
  </read_first>
  <behavior>
    - Function compare_builds(baseline_results, lto_results) -> comparison dict
    - Function detect_regression(baseline, current, threshold_pct=1.0) -> regressions list
    - Function calculate_geometric_mean(values) -> float
    - Function generate_report(comparison, output_path) -> markdown report
    - CLI interface for --baseline, --lto, --threshold, --output
    - Exit code 1 if regressions detected (for CI integration)
  </behavior>
  <action>
    Create scripts/bench/compare_lto_impact.py:

    ```python
    #!/usr/bin/env python3
    """
    Compare LTO vs non-LTO build performance and detect regressions.
    
    This script compares benchmark results between two builds and detects
    performance regressions above a configurable threshold.
    
    Usage:
        python scripts/bench/compare_lto_impact.py \\
            --baseline baseline_results.json \\
            --lto lto_results.json \\
            --threshold 1.0 \\
            --output report.md
    
    Exit codes:
        0: No regressions detected
        1: Regressions detected (or errors)
        2: Usage error
    """
    from __future__ import annotations

    import argparse
    import json
    import logging
    import math
    import statistics
    import sys
    from dataclasses import dataclass
    from pathlib import Path
    from typing import Dict, List, Optional, Tuple

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    # Default threshold for regression detection (1%)
    DEFAULT_REGRESSION_THRESHOLD_PCT = 1.0


    @dataclass
    class BenchmarkComparison:
        """Comparison result for a single benchmark."""
        name: str
        baseline_time: float
        current_time: float
        delta_pct: float
        is_regression: bool
        status: str  # "ok", "missing_baseline", "missing_current", "error"


    @dataclass
    class ComparisonReport:
        """Complete comparison report."""
        benchmarks: List[BenchmarkComparison]
        baseline_geom_mean: float
        current_geom_mean: float
        overall_delta_pct: float
        regressions: List[BenchmarkComparison]
        threshold_pct: float


    def calculate_geometric_mean(values: List[float]) -> float:
        """
        Calculate geometric mean of a list of positive values.
        
        Args:
            values: List of positive float values
            
        Returns:
            Geometric mean
            
        Raises:
            ValueError: If values is empty or contains non-positive values
        """
        if not values:
            raise ValueError("Cannot calculate geometric mean of empty list")
        
        for v in values:
            if v <= 0:
                raise ValueError(f"Geometric mean requires positive values, got {v}")
        
        # Use logarithms to avoid overflow for large products
        log_sum = sum(math.log(v) for v in values)
        return math.exp(log_sum / len(values))


    def load_results(path: Path) -> Dict[str, any]:
        """Load benchmark results from JSON file."""
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Results file not found: {path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {path}: {e}")


    def extract_benchmark_times(results: Dict[str, any]) -> Dict[str, float]:
        """
        Extract benchmark name -> median time mapping from results.
        
        Args:
            results: Results dictionary from run_pyperf_subset.py
            
        Returns:
            Dictionary mapping benchmark name to median time
        """
        times = {}
        for bench in results.get("benchmarks", []):
            name = bench.get("name")
            if bench.get("status") == "ok" and "median" in bench:
                times[name] = float(bench["median"])
            else:
                logger.warning(f"Benchmark {name} did not complete successfully")
        return times


    def compare_builds(
        baseline_results: Dict[str, any],
        lto_results: Dict[str, any],
        threshold_pct: float = DEFAULT_REGRESSION_THRESHOLD_PCT
    ) -> ComparisonReport:
        """
        Compare baseline vs LTO build performance.
        
        Args:
            baseline_results: Results from baseline (no LTO) build
            lto_results: Results from LTO build
            threshold_pct: Regression threshold percentage
            
        Returns:
            ComparisonReport with detailed comparison
        """
        baseline_times = extract_benchmark_times(baseline_results)
        lto_times = extract_benchmark_times(lto_results)
        
        all_benchmarks = set(baseline_times.keys()) | set(lto_times.keys())
        
        comparisons = []
        regressions = []
        
        for name in sorted(all_benchmarks):
            baseline_time = baseline_times.get(name)
            lto_time = lto_times.get(name)
            
            if baseline_time is None:
                comparison = BenchmarkComparison(
                    name=name,
                    baseline_time=0.0,
                    current_time=lto_time or 0.0,
                    delta_pct=0.0,
                    is_regression=True,
                    status="missing_baseline"
                )
            elif lto_time is None:
                comparison = BenchmarkComparison(
                    name=name,
                    baseline_time=baseline_time,
                    current_time=0.0,
                    delta_pct=0.0,
                    is_regression=True,
                    status="missing_current"
                )
            else:
                # Calculate percentage change
                # Positive delta means slower (regression)
                # Negative delta means faster (improvement)
                delta_pct = ((lto_time / baseline_time) - 1.0) * 100.0
                is_regression = delta_pct >= threshold_pct
                
                comparison = BenchmarkComparison(
                    name=name,
                    baseline_time=baseline_time,
                    current_time=lto_time,
                    delta_pct=delta_pct,
                    is_regression=is_regression,
                    status="ok"
                )
                
                if is_regression:
                    regressions.append(comparison)
            
            comparisons.append(comparison)
        
        # Calculate geometric means for successful benchmarks only
        baseline_geom = calculate_geometric_mean(list(baseline_times.values()))
        lto_geom = calculate_geometric_mean(list(lto_times.values()))
        overall_delta = ((lto_geom / baseline_geom) - 1.0) * 100.0
        
        return ComparisonReport(
            benchmarks=comparisons,
            baseline_geom_mean=baseline_geom,
            current_geom_mean=lto_geom,
            overall_delta_pct=overall_delta,
            regressions=regressions,
            threshold_pct=threshold_pct
        )


    def detect_regression(
        baseline_times: Dict[str, float],
        current_times: Dict[str, float],
        threshold_pct: float = DEFAULT_REGRESSION_THRESHOLD_PCT
    ) -> List[Dict[str, any]]:
        """
        Detect performance regressions between two builds.
        
        Args:
            baseline_times: Dictionary of benchmark name -> time for baseline
            current_times: Dictionary of benchmark name -> time for current build
            threshold_pct: Regression threshold in percentage
            
        Returns:
            List of regression records with benchmark name, times, and degradation
        """
        regressions = []
        all_benchmarks = set(baseline_times.keys()) | set(current_times.keys())
        
        for name in all_benchmarks:
            baseline = baseline_times.get(name)
            current = current_times.get(name)
            
            if baseline is None:
                regressions.append({
                    "benchmark": name,
                    "status": "missing",
                    "error": "Missing from baseline results"
                })
            elif current is None:
                regressions.append({
                    "benchmark": name,
                    "status": "missing",
                    "error": "Missing from current results"
                })
            else:
                degradation_pct = ((current / baseline) - 1.0) * 100.0
                if degradation_pct >= threshold_pct:
                    regressions.append({
                        "benchmark": name,
                        "baseline_time": baseline,
                        "current_time": current,
                        "degradation_pct": degradation_pct,
                        "status": "regression"
                    })
        
        return regressions


    def generate_markdown_report(report: ComparisonReport) -> str:
        """Generate a markdown report from comparison results."""
        lines = [
            "# LTO Performance Comparison Report",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Baseline Geometric Mean | {report.baseline_geom_mean:.6f}s |",
            f"| LTO Geometric Mean | {report.current_geom_mean:.6f}s |",
            f"| Overall Delta | {report.overall_delta_pct:+.2f}% |",
            f"| Regression Threshold | {report.threshold_pct:.1f}% |",
            f"| Regressions Detected | {len(report.regressions)} |",
            "",
            "## Benchmark Details",
            "",
            "| Benchmark | Baseline | LTO | Delta | Status |",
            "|-----------|----------|-----|-------|--------|",
        ]
        
        for comp in report.benchmarks:
            if comp.status == "ok":
                delta_str = f"{comp.delta_pct:+.2f}%"
                status = "❌ REGRESSION" if comp.is_regression else "✅ OK"
                lines.append(
                    f"| {comp.name} | {comp.baseline_time:.6f}s | "
                    f"{comp.current_time:.6f}s | {delta_str} | {status} |"
                )
            elif comp.status == "missing_baseline":
                lines.append(
                    f"| {comp.name} | N/A | {comp.current_time:.6f}s | N/A | ⚠️ Missing Baseline |"
                )
            elif comp.status == "missing_current":
                lines.append(
                    f"| {comp.name} | {comp.baseline_time:.6f}s | N/A | N/A | ⚠️ Missing LTO |"
                )
        
        if report.regressions:
            lines.extend([
                "",
                "## Regressions",
                "",
                "The following benchmarks exceeded the regression threshold:",
                "",
            ])
            for comp in report.regressions:
                lines.append(
                    f"- **{comp.name}**: {comp.delta_pct:+.2f}% degradation "
                    f"({comp.baseline_time:.6f}s → {comp.current_time:.6f}s)"
                )
        else:
            lines.extend([
                "",
                "## Regressions",
                "",
                "✅ No regressions detected. All benchmarks within threshold.",
            ])
        
        lines.append("")
        return "\n".join(lines)


    def main() -> int:
        parser = argparse.ArgumentParser(
            description="Compare LTO vs non-LTO build performance"
        )
        parser.add_argument(
            "--baseline",
            "-b",
            type=Path,
            required=True,
            help="Path to baseline (no LTO) results JSON"
        )
        parser.add_argument(
            "--lto",
            "-l",
            type=Path,
            required=True,
            help="Path to LTO results JSON"
        )
        parser.add_argument(
            "--threshold",
            "-t",
            type=float,
            default=DEFAULT_REGRESSION_THRESHOLD_PCT,
            help=f"Regression threshold percentage (default: {DEFAULT_REGRESSION_THRESHOLD_PCT}%)"
        )
        parser.add_argument(
            "--output",
            "-o",
            type=Path,
            help="Output file for markdown report"
        )
        parser.add_argument(
            "--json",
            type=Path,
            help="Output file for JSON report"
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
        
        # Load results
        try:
            baseline_results = load_results(args.baseline)
            lto_results = load_results(args.lto)
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Failed to load results: {e}")
            return 1
        
        # Perform comparison
        report = compare_builds(baseline_results, lto_results, args.threshold)
        
        # Generate and output markdown report
        markdown = generate_markdown_report(report)
        print(markdown)
        
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(markdown)
            logger.info(f"Markdown report written to {args.output}")
        
        # Output JSON if requested
        if args.json:
            json_report = {
                "baseline_geom_mean": report.baseline_geom_mean,
                "current_geom_mean": report.current_geom_mean,
                "overall_delta_pct": report.overall_delta_pct,
                "threshold_pct": report.threshold_pct,
                "regressions": [
                    {
                        "name": r.name,
                        "delta_pct": r.delta_pct,
                        "baseline": r.baseline_time,
                        "current": r.current_time
                    }
                    for r in report.regressions
                ],
                "benchmarks": [
                    {
                        "name": b.name,
                        "delta_pct": b.delta_pct,
                        "status": b.status
                    }
                    for b in report.benchmarks
                ]
            }
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(json_report, indent=2))
            logger.info(f"JSON report written to {args.json}")
        
        # Return non-zero if regressions detected
        if report.regressions:
            logger.error(f"Detected {len(report.regressions)} regression(s)")
            return 1
        
        logger.info("No regressions detected")
        return 0


    if __name__ == "__main__":
        sys.exit(main())
    ```

    Make the script executable: chmod +x scripts/bench/compare_lto_impact.py
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && python -m pytest scripts/bench/test_lto_benchmarks.py -v 2>&1 | grep -E "(test_.*PASSED|test_.*FAILED)" | head -15</automated>
  </verify>
  <done>compare_lto_impact.py implemented, all tests passing (GREEN phase)</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Run tests and verify implementations</name>
  <files>scripts/bench/test_lto_benchmarks.py</files>
  <behavior>
    - Run all unit tests
    - Verify test coverage
    - Ensure no test failures
  </behavior>
  <action>
    Run the complete test suite for the benchmark automation:

    ```bash
    cd /Users/luchen/Agents-Repo/OpenCode/cinderx
    python -m pytest scripts/bench/test_lto_benchmarks.py -v --tb=short
    ```

    Expected output: All tests passing (8-10 tests)
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && python -m pytest scripts/bench/test_lto_benchmarks.py -v 2>&1 | tail -20</automated>
  </verify>
  <done>All unit tests passing, benchmark framework ready (REFACTOR phase complete)</done>
</task>

</tasks>

<verification>
- [ ] scripts/bench/test_lto_benchmarks.py exists with comprehensive unit tests
- [ ] scripts/bench/run_pyperf_subset.py implements 5-benchmark runner
- [ ] scripts/bench/compare_lto_impact.py implements LTO comparison and regression detection
- [ ] All unit tests passing
- [ ] Geometric mean calculation working correctly
- [ ] Regression detection with < 1% threshold working
- [ ] CLI interfaces functional for both scripts
</verification>

<success_criteria>
- 5-benchmark subset (richards, nbody, deltablue, regex_compile, nqueens) can be run with single command
- LTO vs non-LTO comparison produces statistical results with geometric mean
- Regression detection correctly flags degradation > 1%
- All unit tests passing
- Scripts have proper CLI interfaces with --help documentation
</success_criteria>

<output>
After completion, create `.planning/phases/03-validation/03A-01-SUMMARY.md`
</output>

<atomic_commits>
Commit 1: `test(03A-01): add unit tests for benchmark automation framework`
- Add scripts/bench/test_lto_benchmarks.py
- Tests for BenchmarkConfig, parse_pyperf_json, geometric mean, regression detection
- Tests initially failing (RED phase)

Commit 2: `feat(03A-01): implement 5-benchmark subset runner`
- Add scripts/bench/run_pyperf_subset.py
- BenchmarkConfig dataclass with validation
- 5-benchmark JIT subset support
- CLI interface with argparse

Commit 3: `feat(03A-01): implement LTO comparison and regression detection`
- Add scripts/bench/compare_lto_impact.py
- Statistical comparison with geometric mean
- Regression detection with configurable threshold
- Markdown and JSON report generation
- All tests now passing (GREEN phase)
</atomic_commits>
