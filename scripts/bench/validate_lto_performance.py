#!/usr/bin/env python3
"""
LTO Performance Validation Script
验证 LTO 性能是否达到目标

目标：
1. LTO 构建时间增加 < 30%
2. 运行时性能提升 +5%~+10%
3. 无性能退化 > 1%
"""

import argparse
import json
import statistics
from pathlib import Path
from typing import Dict, List, Tuple


def load_results(json_file: Path) -> Dict:
    """Load benchmark results from JSON file."""
    with open(json_file) as f:
        return json.load(f)


def calculate_geometric_mean(values: List[float]) -> float:
    """Calculate geometric mean of a list of values."""
    if not values or any(v <= 0 for v in values):
        raise ValueError("All values must be positive for geometric mean")

    product = 1.0
    for v in values:
        product *= v

    return product ** (1.0 / len(values))


def compare_benchmarks(
    baseline: Dict, lto: Dict, threshold_pct: float = 1.0
) -> Dict:
    """
    Compare LTO vs baseline benchmark results.

    Args:
        baseline: Baseline (non-LTO) results
        lto: LTO results
        threshold_pct: Regression threshold percentage

    Returns:
        Comparison report dictionary
    """
    # Extract benchmark results
    baseline_benches = {b["name"]: b["median"] for b in baseline.get("benchmarks", [])}
    lto_benches = {b["name"]: b["median"] for b in lto.get("benchmarks", [])}

    # Compare each benchmark
    comparisons = []
    regressions = []
    improvements = []

    all_benchmarks = set(baseline_benches.keys()) | set(lto_benches.keys())

    for bench_name in sorted(all_benchmarks):
        baseline_time = baseline_benches.get(bench_name)
        lto_time = lto_benches.get(bench_name)

        if baseline_time is None or lto_time is None:
            comparisons.append(
                {
                    "name": bench_name,
                    "baseline": baseline_time,
                    "lto": lto_time,
                    "delta_pct": None,
                    "status": "missing",
                }
            )
            continue

        # Calculate delta (negative = improvement)
        delta_pct = ((lto_time / baseline_time) - 1.0) * 100.0

        # Determine status
        if abs(delta_pct) <= threshold_pct:
            status = "ok"  # Within noise threshold
        elif delta_pct < 0:
            status = "improvement"
            improvements.append((bench_name, delta_pct))
        else:
            status = "regression"
            regressions.append((bench_name, delta_pct))

        comparisons.append(
            {
                "name": bench_name,
                "baseline": baseline_time,
                "lto": lto_time,
                "delta_pct": delta_pct,
                "status": status,
            }
        )

    # Calculate geometric mean
    baseline_times = [c["baseline"] for c in comparisons if c["delta_pct"] is not None]
    lto_times = [c["lto"] for c in comparisons if c["delta_pct"] is not None]

    if baseline_times and lto_times:
        baseline_geom_mean = calculate_geometric_mean(baseline_times)
        lto_geom_mean = calculate_geometric_mean(lto_times)
        overall_delta = ((lto_geom_mean / baseline_geom_mean) - 1.0) * 100.0
    else:
        baseline_geom_mean = lto_geom_mean = overall_delta = None

    # Build report
    report = {
        "summary": {
            "baseline_geom_mean": baseline_geom_mean,
            "lto_geom_mean": lto_geom_mean,
            "overall_delta_pct": overall_delta,
            "threshold_pct": threshold_pct,
            "total_benchmarks": len(comparisons),
            "regressions": len(regressions),
            "improvements": len(improvements),
            "status": "pass" if not regressions else "fail",
        },
        "comparisons": comparisons,
        "regressions": [
            {"name": name, "delta_pct": delta} for name, delta in regressions
        ],
        "improvements": [
            {"name": name, "delta_pct": delta} for name, delta in improvements
        ],
    }

    return report


def generate_markdown_report(report: Dict) -> str:
    """Generate markdown report from comparison results."""
    lines = []

    # Header
    lines.append("# LTO Performance Comparison Report")
    lines.append("")
    lines.append(f"**Status**: {'✅ PASS' if report['summary']['status'] == 'pass' else '❌ FAIL'}")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")

    summary = report["summary"]
    if summary["baseline_geom_mean"] is not None:
        lines.append(f"| Baseline Geometric Mean | {summary['baseline_geom_mean']:.6f}s |")
        lines.append(f"| LTO Geometric Mean | {summary['lto_geom_mean']:.6f}s |")
        lines.append(f"| Overall Delta | {summary['overall_delta_pct']:+.2f}% |")

    lines.append(f"| Regression Threshold | {summary['threshold_pct']:.1f}% |")
    lines.append(f"| Total Benchmarks | {summary['total_benchmarks']} |")
    lines.append(f"| Regressions | {summary['regressions']} |")
    lines.append(f"| Improvements | {summary['improvements']} |")
    lines.append(f"| Status | {'✅ PASS' if summary['status'] == 'pass' else '❌ FAIL'} |")
    lines.append("")

    # Detailed comparison table
    lines.append("## Benchmark Details")
    lines.append("")
    lines.append("| Benchmark | Baseline | LTO | Delta | Status |")
    lines.append("|-----------|----------|-----|-------|--------|")

    for comp in report["comparisons"]:
        if comp["delta_pct"] is None:
            lines.append(
                f"| {comp['name']} | {comp['baseline'] or 'N/A'} | {comp['lto'] or 'N/A'} | N/A | ⚠️ {comp['status']} |"
            )
        else:
            status_icon = {
                "ok": "✅",
                "improvement": "🚀",
                "regression": "❌",
            }.get(comp["status"], "❓")

            lines.append(
                f"| {comp['name']} | {comp['baseline']:.6f}s | {comp['lto']:.6f}s | {comp['delta_pct']:+.2f}% | {status_icon} {comp['status']} |"
            )

    lines.append("")

    # Regressions section
    if report["regressions"]:
        lines.append("## ⚠️ Regressions")
        lines.append("")
        lines.append("| Benchmark | Delta |")
        lines.append("|-----------|-------|")
        for reg in report["regressions"]:
            lines.append(f"| {reg['name']} | {reg['delta_pct']:+.2f}% |")
        lines.append("")

    # Improvements section
    if report["improvements"]:
        lines.append("## 🚀 Improvements")
        lines.append("")
        lines.append("| Benchmark | Delta |")
        lines.append("|-----------|-------|")
        for imp in report["improvements"]:
            lines.append(f"| {imp['name']} | {imp['delta_pct']:+.2f}% |")
        lines.append("")

    # Performance targets
    lines.append("## Performance Targets")
    lines.append("")
    lines.append("| Target | Goal | Actual | Status |")
    lines.append("|--------|------|--------|--------|")

    overall_delta = summary["overall_delta_pct"]
    if overall_delta is not None:
        # Target 1: No regression > 1%
        no_regression = overall_delta >= -1.0
        lines.append(
            f"| No Regression | ≥ -1.0% | {overall_delta:+.2f}% | {'✅' if no_regression else '❌'} |"
        )

        # Target 2: Improvement +5%~+10%
        improvement_target = -10.0 <= overall_delta <= -5.0
        lines.append(
            f"| Performance Improvement | -10% ~ -5% | {overall_delta:+.2f}% | {'✅' if improvement_target else '⚠️'} |"
        )

    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Validate LTO performance")
    parser.add_argument(
        "--baseline", required=True, type=Path, help="Baseline results JSON"
    )
    parser.add_argument("--lto", required=True, type=Path, help="LTO results JSON")
    parser.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="Regression threshold percentage (default: 1.0)",
    )
    parser.add_argument(
        "--output", type=Path, help="Output markdown report file (optional)"
    )
    parser.add_argument(
        "--json-output", type=Path, help="Output JSON report file (optional)"
    )

    args = parser.parse_args()

    # Load results
    print(f"Loading baseline results: {args.baseline}")
    baseline = load_results(args.baseline)

    print(f"Loading LTO results: {args.lto}")
    lto = load_results(args.lto)

    # Compare
    print(f"Comparing with threshold: {args.threshold}%")
    report = compare_benchmarks(baseline, lto, args.threshold)

    # Generate markdown report
    markdown = generate_markdown_report(report)

    # Output
    if args.output:
        args.output.write_text(markdown)
        print(f"\nMarkdown report saved to: {args.output}")

    if args.json_output:
        with open(args.json_output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"JSON report saved to: {args.json_output}")

    # Print to stdout
    print("\n" + markdown)

    # Return exit code
    return 0 if report["summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    exit(main())
