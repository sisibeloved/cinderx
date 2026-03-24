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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
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
    threshold_pct: float = DEFAULT_REGRESSION_THRESHOLD_PCT,
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
                status="missing_baseline",
            )
        elif lto_time is None:
            comparison = BenchmarkComparison(
                name=name,
                baseline_time=baseline_time,
                current_time=0.0,
                delta_pct=0.0,
                is_regression=True,
                status="missing_current",
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
                status="ok",
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
        threshold_pct=threshold_pct,
    )


def detect_regression(
    baseline_times: Dict[str, float],
    current_times: Dict[str, float],
    threshold_pct: float = DEFAULT_REGRESSION_THRESHOLD_PCT,
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
            regressions.append(
                {
                    "benchmark": name,
                    "status": "missing",
                    "error": "Missing from baseline results",
                }
            )
        elif current is None:
            regressions.append(
                {
                    "benchmark": name,
                    "status": "missing",
                    "error": "Missing from current results",
                }
            )
        else:
            degradation_pct = ((current / baseline) - 1.0) * 100.0
            if degradation_pct >= threshold_pct:
                regressions.append(
                    {
                        "benchmark": name,
                        "baseline_time": baseline,
                        "current_time": current,
                        "degradation_pct": degradation_pct,
                        "status": "regression",
                    }
                )

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
            status = "REGRESSION" if comp.is_regression else "OK"
            lines.append(
                f"| {comp.name} | {comp.baseline_time:.6f}s | "
                f"{comp.current_time:.6f}s | {delta_str} | {status} |"
            )
        elif comp.status == "missing_baseline":
            lines.append(
                f"| {comp.name} | N/A | {comp.current_time:.6f}s | N/A | Missing Baseline |"
            )
        elif comp.status == "missing_current":
            lines.append(
                f"| {comp.name} | {comp.baseline_time:.6f}s | N/A | N/A | Missing LTO |"
            )

    if report.regressions:
        lines.extend(
            [
                "",
                "## Regressions",
                "",
                "The following benchmarks exceeded the regression threshold:",
                "",
            ]
        )
        for comp in report.regressions:
            lines.append(
                f"- **{comp.name}**: {comp.delta_pct:+.2f}% degradation "
                f"({comp.baseline_time:.6f}s -> {comp.current_time:.6f}s)"
            )
    else:
        lines.extend(
            [
                "",
                "## Regressions",
                "",
                "No regressions detected. All benchmarks within threshold.",
            ]
        )

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
        help="Path to baseline (no LTO) results JSON",
    )
    parser.add_argument(
        "--lto", "-l", type=Path, required=True, help="Path to LTO results JSON"
    )
    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        default=DEFAULT_REGRESSION_THRESHOLD_PCT,
        help=f"Regression threshold percentage (default: {DEFAULT_REGRESSION_THRESHOLD_PCT}%)",
    )
    parser.add_argument(
        "--output", "-o", type=Path, help="Output file for markdown report"
    )
    parser.add_argument("--json", type=Path, help="Output file for JSON report")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
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
                    "current": r.current_time,
                }
                for r in report.regressions
            ],
            "benchmarks": [
                {"name": b.name, "delta_pct": b.delta_pct, "status": b.status}
                for b in report.benchmarks
            ],
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
