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
    SmokeTestConfig,
)


class TestSmokeTestConfig(unittest.TestCase):
    def test_valid_config(self):
        config = SmokeTestConfig(
            baseline_build_dir="/tmp/baseline",
            lto_build_dir="/tmp/lto",
            max_build_time_increase_pct=30.0,
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
            "benchmarks_failed": 0,
        }
        config = SmokeTestConfig(max_build_time_increase_pct=30.0)
        is_valid, issues = validate_smoke_test_results(results, config)
        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)

    def test_build_time_exceeded(self):
        results = {
            "build_time_increase_pct": 35.0,
            "benchmarks_passed": 5,
            "benchmarks_failed": 0,
        }
        config = SmokeTestConfig(max_build_time_increase_pct=30.0)
        is_valid, issues = validate_smoke_test_results(results, config)
        self.assertFalse(is_valid)
        self.assertIn("build_time", str(issues))

    def test_benchmarks_failed(self):
        results = {
            "build_time_increase_pct": 15.0,
            "benchmarks_passed": 3,
            "benchmarks_failed": 2,
        }
        config = SmokeTestConfig(max_build_time_increase_pct=30.0)
        is_valid, issues = validate_smoke_test_results(results, config)
        self.assertFalse(is_valid)
        self.assertIn("benchmark", str(issues))


if __name__ == "__main__":
    unittest.main()
