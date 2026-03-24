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
    compare_builds,
)


class TestBenchmarkConfig(unittest.TestCase):
    def test_valid_config(self):
        config = BenchmarkConfig(
            benchmarks=["richards", "nbody"], iterations=5, warmup=1
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
                {"name": "nbody", "median": 0.10},
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
