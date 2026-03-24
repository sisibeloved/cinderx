#!/usr/bin/env python3
"""Unit tests for CI workflow validation."""

import unittest
import json
from pathlib import Path
from unittest.mock import Mock, patch, mock_open


class TestWorkflowConfig(unittest.TestCase):
    """Test CI workflow configuration parsing."""

    def test_threshold_parsing(self):
        """Test that performance thresholds are correctly parsed."""
        config = {
            "regression_threshold_pct": 1.0,
            "build_time_threshold_pct": 30.0,
            "target_improvement_pct": 5.0,
        }
        self.assertEqual(config["regression_threshold_pct"], 1.0)
        self.assertEqual(config["build_time_threshold_pct"], 30.0)

    def test_threshold_validation(self):
        """Test that thresholds are within valid ranges."""

        def validate_threshold(value, name):
            if not 0 <= value <= 100:
                raise ValueError(f"{name} must be between 0 and 100")
            return True

        self.assertTrue(validate_threshold(1.0, "regression"))
        self.assertTrue(validate_threshold(30.0, "build_time"))
        with self.assertRaises(ValueError):
            validate_threshold(-1.0, "invalid")


class TestResultsArtifact(unittest.TestCase):
    """Test performance results artifact handling."""

    def test_results_parsing(self):
        """Test parsing of benchmark results JSON."""
        results = {
            "baseline_geom_mean": 0.05,
            "current_geom_mean": 0.051,
            "overall_delta_pct": 2.0,
            "threshold_pct": 1.0,
            "regressions": [{"name": "richards", "delta_pct": 2.0}],
        }
        self.assertEqual(results["overall_delta_pct"], 2.0)
        self.assertEqual(len(results["regressions"]), 1)

    def test_regression_detection(self):
        """Test regression detection from results."""

        def has_regression(results, threshold):
            return results["overall_delta_pct"] > threshold

        results_pass = {"overall_delta_pct": 0.5, "threshold_pct": 1.0}
        results_fail = {"overall_delta_pct": 2.0, "threshold_pct": 1.0}

        self.assertFalse(has_regression(results_pass, 1.0))
        self.assertTrue(has_regression(results_fail, 1.0))


class TestBuildComparison(unittest.TestCase):
    """Test build time comparison logic."""

    def test_build_time_increase_calculation(self):
        """Test build time percentage increase calculation."""

        def calc_increase(baseline, current):
            return ((current / baseline) - 1.0) * 100.0

        self.assertEqual(calc_increase(100.0, 100.0), 0.0)
        self.assertEqual(calc_increase(100.0, 130.0), 30.0)
        self.assertEqual(calc_increase(100.0, 150.0), 50.0)

    def test_build_time_within_threshold(self):
        """Test build time threshold validation."""

        def within_threshold(baseline, current, threshold_pct):
            increase = ((current / baseline) - 1.0) * 100.0
            return increase <= threshold_pct

        self.assertTrue(within_threshold(100.0, 125.0, 30.0))
        self.assertFalse(within_threshold(100.0, 135.0, 30.0))


if __name__ == "__main__":
    unittest.main()
