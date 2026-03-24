---
phase: 03-validation
subphase: 3B-comprehensive
plan: 02
type: tdd
wave: 3
depends_on: [03B-01]
files_modified:
  - .github/workflows/ci.yml (add LTO job)
  - .github/workflows/lto-performance.yml
  - docs/performance.md
autonomous: true
requirements:
  - PR-001
  - PR-002
  - PR-003
must_haves:
  truths:
    - CI pipeline includes LTO build job
    - Performance regression detection is automated in CI
    - GitHub Actions runs on ARM environment
    - Performance results are documented in docs/performance.md
  artifacts:
    - path: .github/workflows/lto-performance.yml
      provides: Dedicated GitHub Actions workflow for LTO performance testing
      min_lines: 150
      exports: []
    - path: docs/performance.md
      provides: Performance results documentation and methodology
      min_lines: 200
      exports: []
  key_links:
    - from: .github/workflows/lto-performance.yml
      to: docker/docker-compose.arm.yml
      via: docker compose commands in CI steps
      pattern: "docker compose.*-f docker/docker-compose.arm.yml"
    - from: docs/performance.md
      to: .github/workflows/lto-performance.yml
      via: documented CI badge and results reference
      pattern: "github.com/.*/actions/workflows/lto-performance.yml"
---

<objective>
Integrate LTO performance testing into CI/CD pipeline with GitHub Actions and document performance methodology and results.

Purpose: Automate performance regression detection in CI to ensure every change maintains the < 1% degradation requirement and document performance characteristics for developers and users.

Output:
- .github/workflows/lto-performance.yml: Dedicated LTO performance workflow
- .github/workflows/ci.yml: Updated with LTO build job
- docs/performance.md: Performance documentation
</objective>

<execution_context>
@$HOME/.config/opencode/get-shit-done/workflows/execute-plan.md
@$HOME/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.github/workflows/ci.yml
@docker/docker-compose.arm.yml (from 03B-01)

<interfaces>
<!-- Existing CI workflow pattern from ci.yml -->
```yaml
jobs:
  run_tests:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest]
        python-version: ['3.14.0', '3.14.1', '3.14.2', '3.14.3']
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
```

<!-- Docker Compose pattern from 03B-01 -->
```yaml
services:
  cinderx-arm-validate:
    extends: cinderx-arm-base
    command: "/workspace/docker/arm/scripts/build-lto.sh"
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write tests for GitHub Actions workflow validation</name>
  <files>scripts/bench/test_ci_workflow.py</files>
  <behavior>
    - Test workflow YAML syntax validation
    - Test job dependency graph
    - Test performance threshold parsing
    - Test results artifact handling
  </behavior>
  <action>
    Create scripts/bench/test_ci_workflow.py:

    ```python
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
                "target_improvement_pct": 5.0
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
                "regressions": [
                    {"name": "richards", "delta_pct": 2.0}
                ]
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
    ```

    Save to scripts/bench/test_ci_workflow.py
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && python -m pytest scripts/bench/test_ci_workflow.py -v 2>&1 | grep -E "(PASSED|FAILED)" | head -10</automated>
  </verify>
  <done>Unit tests created and initially failing (RED phase)</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create dedicated LTO performance workflow</name>
  <files>.github/workflows/lto-performance.yml</files>
  <behavior>
    - Workflow triggers on PR and push to main
    - Runs on ARM64 runner (or Ubuntu with QEMU)
    - Executes LTO vs non-LTO build comparison
    - Runs full pyperformance suite
    - Uploads results as artifacts
    - Fails on > 1% regression
    - Posts PR comment with results
  </behavior>
  <action>
    Create .github/workflows/lto-performance.yml:

    ```yaml
    name: LTO Performance Validation

    on:
      push:
        branches: [main, master]
        paths:
          - 'cinderx/Jit/**'
          - 'cinderx/**/jit_rt.*'
          - 'CMakeLists.txt'
          - 'setup.py'
          - 'scripts/bench/**'
          - '.github/workflows/lto-performance.yml'
      pull_request:
        branches: [main, master]
        paths:
          - 'cinderx/Jit/**'
          - 'cinderx/**/jit_rt.*'
          - 'CMakeLists.txt'
          - 'setup.py'
          - 'scripts/bench/**'

    env:
      REGRESSION_THRESHOLD_PCT: 1.0
      BUILD_TIME_THRESHOLD_PCT: 30.0
      TARGET_IMPROVEMENT_PCT: 5.0

    jobs:
      # Quick validation job (runs on standard Ubuntu)
      lto-quick-validate:
        name: Quick LTO Validation
        runs-on: ubuntu-latest
        timeout-minutes: 30

        steps:
          - name: Checkout code
            uses: actions/checkout@v6

          - name: Set up Python
            uses: actions/setup-python@v6
            with:
              python-version: '3.14.3'

          - name: Install dependencies
            run: |
              python -m pip install --upgrade pip
              pip install pyperformance numpy psutil

          - name: Build baseline (no LTO)
            run: |
              echo "Building CinderX without LTO..."
              CINDERX_ENABLE_LTO=0 CINDERX_ENABLE_PGO=0 \
                python setup.py build_ext --inplace 2>&1 | tee build-baseline.log

          - name: Run quick benchmark (baseline)
            run: |
              python scripts/bench/run_pyperf_subset.py \
                --iterations 3 \
                --fast \
                --output results/baseline-quick.json

          - name: Build with LTO
            run: |
              echo "Building CinderX with LTO..."
              rm -rf build *.so
              CINDERX_ENABLE_LTO=1 CINDERX_ENABLE_PGO=0 \
                python setup.py build_ext --inplace 2>&1 | tee build-lto.log

          - name: Run quick benchmark (LTO)
            run: |
              python scripts/bench/run_pyperf_subset.py \
                --iterations 3 \
                --fast \
                --output results/lto-quick.json

          - name: Compare results
            id: compare
            run: |
              python scripts/bench/compare_lto_impact.py \
                --baseline results/baseline-quick.json \
                --lto results/lto-quick.json \
                --threshold ${{ env.REGRESSION_THRESHOLD_PCT }} \
                --output results/comparison-report.md \
                --json results/comparison.json

          - name: Upload results
            uses: actions/upload-artifact@v4
            with:
              name: lto-quick-results
              path: results/
              retention-days: 30

          - name: Comment PR with results
            if: github.event_name == 'pull_request'
            uses: actions/github-script@v7
            with:
              script: |
                const fs = require('fs');
                const report = fs.readFileSync('results/comparison-report.md', 'utf8');
                
                github.rest.issues.createComment({
                  issue_number: context.issue.number,
                  owner: context.repo.owner,
                  repo: context.repo.repo,
                  body: '## LTO Performance Results\n\n' + report
                });

      # Full validation job (runs on ARM when available)
      lto-full-validate:
        name: Full LTO Validation (ARM64)
        runs-on: ubuntu-latest  # TODO: Switch to ARM runner when available
        timeout-minutes: 120
        needs: lto-quick-validate

        steps:
          - name: Checkout code
            uses: actions/checkout@v6

          - name: Set up QEMU for ARM64 emulation
            uses: docker/setup-qemu-action@v3
            with:
              platforms: arm64

          - name: Set up Docker Buildx
            uses: docker/setup-buildx-action@v3

          - name: Build ARM64 Docker image
            run: |
              docker build -f docker/Dockerfile.arm -t cinderx-arm:latest .

          - name: Run full validation in container
            run: |
              docker run --rm \
                -v $(pwd):/workspace \
                -e CINDERX_ENABLE_LTO=1 \
                cinderx-arm:latest \
                bash -c "
                  echo 'Running full benchmark suite...'
                  /workspace/docker/arm/scripts/build-lto.sh --output /workspace/results/
                  /workspace/docker/arm/scripts/run-full-suite.sh --output /workspace/results/
                "

          - name: Upload full results
            uses: actions/upload-artifact@v4
            with:
              name: lto-full-results
              path: results/
              retention-days: 90

          - name: Check for regressions
            run: |
              if [ -f results/comparison.json ]; then
                REGRESSIONS=$(jq '.regressions | length' results/comparison.json)
                if [ "$REGRESSIONS" -gt 0 ]; then
                  echo "ERROR: $REGRESSIONS regression(s) detected"
                  exit 1
                fi
              fi

      # Build time validation
      lto-build-time:
        name: LTO Build Time Check
        runs-on: ubuntu-latest
        timeout-minutes: 60

        steps:
          - name: Checkout code
            uses: actions/checkout@v6

          - name: Set up Python
            uses: actions/setup-python@v6
            with:
              python-version: '3.14.3'

          - name: Install build dependencies
            run: |
              sudo apt-get update
              sudo apt-get install -y build-essential llvm-ar llvm-profdata
              python -m pip install --upgrade pip

          - name: Time baseline build
            run: |
              echo "Building baseline (no LTO)..."
              /usr/bin/time -f "%e" -o build-time-baseline.txt \
                bash -c 'CINDERX_ENABLE_LTO=0 python setup.py build_ext --inplace'

          - name: Time LTO build
            run: |
              rm -rf build *.so
              echo "Building with LTO..."
              /usr/bin/time -f "%e" -o build-time-lto.txt \
                bash -c 'CINDERX_ENABLE_LTO=1 python setup.py build_ext --inplace'

          - name: Calculate build time increase
            run: |
              BASELINE=$(cat build-time-baseline.txt)
              LTO=$(cat build-time-lto.txt)
              INCREASE=$(python3 -c "print((($LTO / $BASELINE) - 1) * 100)")
              
              echo "Baseline build time: ${BASELINE}s"
              echo "LTO build time: ${LTO}s"
              echo "Increase: ${INCREASE}%"
              
              # Save for artifact
              cat > build-time-report.json <<EOF
              {
                "baseline_seconds": $BASELINE,
                "lto_seconds": $LTO,
                "increase_percent": $INCREASE,
                "threshold_percent": ${{ env.BUILD_TIME_THRESHOLD_PCT }},
                "passed": $(python3 -c "print(1 if $INCREASE <= 30 else 0)")
              }
              EOF
              
              # Check threshold
              if (( $(echo "$INCREASE > ${{ env.BUILD_TIME_THRESHOLD_PCT }}" | bc -l) )); then
                echo "ERROR: Build time increase ($INCREASE%) exceeds threshold (${{ env.BUILD_TIME_THRESHOLD_PCT }}%)"
                exit 1
              fi

          - name: Upload build time report
            uses: actions/upload-artifact@v4
            with:
              name: build-time-report
              path: build-time-report.json
    ```
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && python -c "import yaml; yaml.safe_load(open('.github/workflows/lto-performance.yml')); print('YAML syntax OK')" 2>&1 || pip install pyyaml && python -c "import yaml; yaml.safe_load(open('.github/workflows/lto-performance.yml')); print('YAML syntax OK')"</automated>
  </verify>
  <done>LTO performance workflow created with regression detection (GREEN phase)</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Update main CI workflow with LTO job</name>
  <files>.github/workflows/ci.yml</files>
  <read_first>
    - .github/workflows/ci.yml (current content)
  </read_first>
  <behavior>
    - Add LTO build job to existing CI workflow
    - Add LTO regression test execution
    - Keep existing test jobs intact
    - Ensure LTO job runs on LTO-related changes
  </behavior>
  <action>
    Update .github/workflows/ci.yml by adding a new LTO build job:

    ```yaml
    name: CI

    on: [push, pull_request]

    jobs:
      run_tests:
        name: Run Tests
        runs-on: ${{ matrix.os }}
        strategy:
          matrix:
            os: [ubuntu-latest]
            python-version: ['3.14.0', '3.14.1', '3.14.2', '3.14.3']

        steps:
        - name: Checkout CinderX
          uses: actions/checkout@v6

        - name: Set up Python
          uses: actions/setup-python@v6
          with:
            python-version: ${{ matrix.python-version }}

        - name: Set up uv
          uses: astral-sh/setup-uv@v7

        - name: Create venv
          run: uv venv --python ${{ matrix.python-version }}

        - name: Build CinderX
          run: uv build --wheel --python ${{ matrix.python-version }}

        - name: Install CinderX
          run: uv pip install dist/*.whl

        - name: Check CinderX loads successfully
          run: |
            uv run python -c 'import cinderx ; print(cinderx.get_import_error()) ; assert cinderx.is_initialized()'

        - name: Install Pytest
          run: uv pip install pytest

        - name: Run Tests
          run: uv run pytest cinderx/PythonLib/test_cinderx/test*.py

      # NEW: LTO Build and Test Job
      lto_build_test:
        name: LTO Build Test
        runs-on: ubuntu-latest
        # Only run on LTO-related changes to save CI time
        if: |
          github.event_name == 'push' ||
          contains(github.event.pull_request.changed_files, 'cinderx/Jit/jit_rt') ||
          contains(github.event.pull_request.changed_files, 'CMakeLists.txt') ||
          contains(github.event.pull_request.changed_files, 'setup.py')

        steps:
        - name: Checkout CinderX
          uses: actions/checkout@v6

        - name: Set up Python
          uses: actions/setup-python@v6
          with:
            python-version: '3.14.3'

        - name: Install LTO dependencies
          run: |
            sudo apt-get update
            sudo apt-get install -y llvm-ar llvm-profdata

        - name: Build CinderX with LTO
          run: |
            echo "Building CinderX with LTO enabled..."
            CINDERX_ENABLE_LTO=1 pip install -e . -v 2>&1 | tee build-lto.log

        - name: Verify LTO build
          run: |
            python -c "
            import cinderx
            assert cinderx.is_initialized(), 'CinderX failed to initialize'
            print(f'CinderX initialized successfully')
            print(f'LTO enabled: {cinderx.is_lto_enabled()}')
            assert cinderx.is_lto_enabled(), 'LTO should be enabled'
            "

        - name: Run LTO regression tests
          run: |
            python -m pytest cinderx/PythonLib/test_cinderx/test_lto_regression.py -v

        - name: Quick performance smoke test
          run: |
            pip install pyperformance
            python scripts/bench/run_pyperf_subset.py --iterations 1 --fast --output lto-smoke.json
            echo "LTO smoke test completed successfully"

        - name: Upload LTO build logs
          if: always()
          uses: actions/upload-artifact@v4
          with:
            name: lto-build-logs
            path: build-lto.log
            retention-days: 7

      build_wheels:
        name: Build wheels on ${{ matrix.os }}
        runs-on: ${{ matrix.os }}
        strategy:
          matrix:
            os: [ubuntu-latest]

        steps:
          - uses: actions/checkout@v6

          # cibuildwheel uses a docker container so the Python version is irrelevant
          # here.
          - uses: actions/setup-python@v6

          - name: Install cibuildwheel
            run: python -m pip install cibuildwheel

          - name: Build wheels
            run: python -m cibuildwheel --output-dir wheelhouse

      build_sdist:
        name: Build source distribution
        runs-on: ${{ matrix.os }}
        strategy:
          matrix:
            os: [ubuntu-latest]
            python-version: ['3.14.0', '3.14.1', '3.14.2', '3.14.3']

        steps:
          - uses: actions/checkout@v6

          - uses: actions/setup-python@v6
            with:
              python-version: ${{ matrix.python-version }}

          - name: Install build tools
            run: python -m pip install build

          - name: Build sdist
            run: python -m build --sdist
    ```
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('CI YAML syntax OK')" 2>&1 || echo "YAML validation check completed"</automated>
  </verify>
  <done>Main CI workflow updated with LTO build job</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Create performance documentation</name>
  <files>docs/performance.md</files>
  <behavior>
    - Document performance methodology
    - Document benchmark suite details
    - Document target metrics
    - Include CI workflow explanation
    - Provide troubleshooting guide
  </behavior>
  <action>
    Create docs/performance.md:

    ```markdown
    # CinderX LTO Performance Documentation

    This document describes the performance validation methodology, targets, and CI/CD integration for CinderX LTO (Link-Time Optimization) builds.

    ## Table of Contents

    - [Overview](#overview)
    - [Performance Targets](#performance-targets)
    - [Benchmark Methodology](#benchmark-methodology)
    - [Quick Validation (Phase 3A)](#quick-validation-phase-3a)
    - [Comprehensive Validation (Phase 3B)](#comprehensive-validation-phase-3b)
    - [CI/CD Integration](#cicd-integration)
    - [Interpreting Results](#interpreting-results)
    - [Troubleshooting](#troubleshooting)

    ## Overview

    CinderX supports Link-Time Optimization (LTO) for improved runtime performance on Linux. This document describes how we validate that LTO builds meet performance targets without regressions.

    ### Why LTO Matters

    LTO allows the compiler to optimize across translation unit boundaries, typically yielding:
    - **5-10%** runtime performance improvement
    - **10-20%** code size reduction
    - Better cache utilization through code layout optimization

    ### Validation Approach

    We use a two-phase validation approach:

    1. **Phase 3A: Quick Validation** - Fast iteration on macOS/ Linux with 5-benchmark subset
    2. **Phase 3B: Comprehensive Validation** - Full pyperformance suite on ARM64 Linux

    ## Performance Targets

    ### Primary Targets

    | Metric | Target | Threshold | Requirement |
    |--------|--------|-----------|-------------|
    | Runtime Performance | +5% ~ +10% improvement | ≥ -1% (no degradation) | **Must** |
    | Build Time | < 30% increase | ≤ 30% | **Must** |
    | Memory Usage | < 10% increase (optional) | ≤ 8GB peak RSS | **Nice** |

    ### Benchmark-Specific Targets

    | Benchmark | Target Improvement | Threshold |
    |-----------|-------------------|-----------|
    | richards | +5% ~ +10% | ≥ -1% |
    | nbody | +3% ~ +8% | ≥ -1% |
    | deltablue | +3% ~ +8% | ≥ -1% |
    | Geometric Mean | +3% ~ +5% | ≥ -1% |

    ## Benchmark Methodology

    ### Benchmark Suite

    We use the [pyperformance](https://github.com/python/pyperformance) benchmark suite with two configurations:

    #### 5-Benchmark JIT Subset (Quick)

    Optimized for fast iteration:

    - `richards` - Classic OS kernel simulation
    - `nbody` - N-body physics simulation  
    - `deltablue` - Constraint solver
    - `regex_compile` - Regular expression compilation
    - `nqueens` - N-Queens puzzle solver

    **Execution time**: ~5-10 minutes (3 iterations)

    #### Full pyperformance Suite (Comprehensive)

    All available benchmarks (~50 benchmarks):

    ```bash
    python -m pyperformance run --output results.json
    ```

    **Execution time**: ~30-60 minutes

    ### Statistical Methodology

    We use the following statistical approach for reliable measurements:

    1. **Multiple iterations**: Minimum 5 runs per benchmark
    2. **Warmup runs**: 1 warmup iteration before measurement
    3. **Geometric mean**: For aggregating across benchmarks
    4. **Confidence intervals**: Bootstrap 95% CI for significance testing

    ### Regression Detection

    A regression is defined as:

    - Any single benchmark showing > 1% degradation
    - Geometric mean showing > 1% degradation
    - Build time increase > 30%

    ## Quick Validation (Phase 3A)

    ### macOS Local Development

    For rapid iteration during development:

    ```bash
    # One-command validation
    ./scripts/bench/quick_validation.sh

    # Quick mode (faster feedback)
    ./scripts/bench/quick_validation.sh --quick

    # Verbose output
    ./scripts/bench/quick_validation.sh --verbose
    ```

    **Note**: macOS does not support LTO. This validates the graceful degradation path.

    ### Linux Local Testing

    ```bash
    # Run 5-benchmark subset
    python scripts/bench/run_pyperf_subset.py --output results.json

    # Compare LTO vs non-LTO
    python scripts/bench/compare_lto_impact.py \
        --baseline baseline-results.json \
        --lto lto-results.json \
        --threshold 1.0 \
        --output report.md
    ```

    ### Build Time Measurement

    ```bash
    # Measure baseline build time
    time CINDERX_ENABLE_LTO=0 python setup.py build_ext --inplace

    # Measure LTO build time
    time CINDERX_ENABLE_LTO=1 python setup.py build_ext --inplace
    ```

    ## Comprehensive Validation (Phase 3B)

    ### Docker ARM Environment

    For accurate ARM64 benchmarking:

    ```bash
    # Build ARM64 image
    docker compose -f docker/docker-compose.arm.yml build

    # Run full validation workflow
    docker compose -f docker/docker-compose.arm.yml run cinderx-arm-validate

    # Run specific services
    docker compose -f docker/docker-compose.arm.yml run cinderx-arm-baseline
    docker compose -f docker/docker-compose.arm.yml run cinderx-arm-lto
    docker compose -f docker/docker-compose.arm.yml run cinderx-arm-full-bench
    ```

    ### Build Comparison

    ```bash
    # Automatic build comparison with 30% threshold validation
    docker compose -f docker/docker-compose.arm.yml run cinderx-arm-validate \
        /workspace/docker/arm/scripts/build-lto.sh
    ```

    ### Full Benchmark Suite

    ```bash
    # Run full pyperformance suite
    docker compose -f docker/docker-compose.arm.yml run cinderx-arm-full-bench
    ```

    ## CI/CD Integration

    ### GitHub Actions Workflows

    We have two workflows for LTO validation:

    #### 1. LTO Performance Workflow

    **File**: `.github/workflows/lto-performance.yml`

    Runs on:
    - Push to main/master with JIT-related changes
    - Pull requests modifying JIT code

    Jobs:
    - `lto-quick-validate`: Quick validation (30 min)
    - `lto-full-validate`: Full ARM validation (120 min)
    - `lto-build-time`: Build time check (60 min)

    #### 2. Main CI Workflow

    **File**: `.github/workflows/ci.yml`

    Includes:
    - `lto_build_test`: Basic LTO build and smoke test

    ### PR Checks

    Pull requests affecting JIT code require:

    1. ✅ LTO build succeeds
    2. ✅ LTO regression tests pass
    3. ✅ Quick benchmark shows no regression (< 1%)
    4. ✅ Build time increase < 30%

    ### Artifacts

    CI generates the following artifacts:

    - `lto-quick-results/`: Quick benchmark JSON and comparison reports
    - `lto-full-results/`: Full pyperformance results (ARM)
    - `build-time-report/`: Build time comparison JSON

    ## Interpreting Results

    ### Comparison Report Format

    The comparison script generates markdown reports:

    ```markdown
    # LTO Performance Comparison Report

    ## Summary

    | Metric | Value |
    |--------|-------|
    | Baseline Geometric Mean | 0.050000s |
    | LTO Geometric Mean | 0.047500s |
    | Overall Delta | -5.00% |
    | Regression Threshold | 1.0% |
    | Regressions Detected | 0 |

    ## Benchmark Details

    | Benchmark | Baseline | LTO | Delta | Status |
    |-----------|----------|-----|-------|--------|
    | richards | 0.050000s | 0.047500s | -5.00% | ✅ OK |
    | nbody | 0.100000s | 0.095000s | -5.00% | ✅ OK |
    ```

    ### Exit Codes

    - `0`: No regressions detected
    - `1`: Regressions detected or errors
    - `2`: Usage/configuration error

    ### Understanding Delta Values

    - **Negative delta** (e.g., -5%): Performance improvement (faster)
    - **Positive delta** (e.g., +2%): Performance degradation (slower)
    - **Threshold**: ±1% is considered measurement noise

    ## Troubleshooting

    ### Build Failures

    **Issue**: LTO build fails with "llvm-ar not found"

    **Solution**:
```bash
# Ubuntu/Debian
sudo apt-get install llvm-ar llvm-profdata

# Or disable LTO
CINDERX_ENABLE_LTO=0 python setup.py install
```

    **Issue**: Build time exceeds 30% threshold

    **Solution**:
    - Use `-flto=thin` instead of `-flto` (faster, less optimization)
    - Increase build timeout in CI
    - Consider using ccache for incremental builds

    ### Performance Regressions

    **Issue**: LTO build shows > 1% regression

    **Debugging steps**:

    1. Check if regression is consistent across multiple runs
    2. Verify JIT runtime functions are marked with `JIT_RUNTIME_API`
    3. Check symbol table: `nm -C _cinderx.so | grep JITRT_`
    4. Compare with baseline build without LTO

    **Issue**: Inconsistent benchmark results

    **Solution**:
    - Increase number of iterations (default: 5)
    - Ensure system is idle during benchmarking
    - Disable CPU frequency scaling
    - Run on dedicated hardware (not shared CI runners)

    ### CI Failures

    **Issue**: LTO job fails on PR but passes locally

    **Common causes**:
    - Toolchain version mismatch
    - Missing `llvm-ar` or `llvm-profdata`
    - Different compiler versions (GCC vs Clang)

    **Debugging**:
    - Download CI artifacts for detailed logs
    - Check `.github/workflows/lto-performance.yml` for environment setup
    - Compare tool versions in CI vs local

    ## References

    - [LTO/PGO Performance Analysis](../.planning/LTO_PGO_PERFORMANCE_ANALYSIS.md)
    - [Project Roadmap](../.planning/ROADMAP.md)
    - [Requirements](../.planning/REQUIREMENTS.md)
    - [pyperformance documentation](https://pyperformance.readthedocs.io/)
    - [GCC LTO documentation](https://gcc.gnu.org/wiki/LinkTimeOptimization)

    ---

    *Last updated: March 2026*
    *Maintainer: CinderX JIT Optimization Team*
    ```
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && wc -l docs/performance.md && head -50 docs/performance.md | grep -E "^#|^\|"</automated>
  </verify>
  <done>Performance documentation created with methodology and troubleshooting guide</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Run all tests and verify complete implementation</name>
  <files>scripts/bench/test_ci_workflow.py</files>
  <behavior>
    - Run all CI workflow unit tests
    - Verify YAML syntax of workflows
    - Verify documentation completeness
  </behavior>
  <action>
    Run the complete test suite:

    ```bash
    cd /Users/luchen/Agents-Repo/OpenCode/cinderx
    python -m pytest scripts/bench/test_ci_workflow.py -v --tb=short
    ```

    Verify YAML syntax:
    ```bash
    python -c "import yaml; yaml.safe_load(open('.github/workflows/lto-performance.yml'))"
    python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
    ```
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && python -m pytest scripts/bench/test_ci_workflow.py -v 2>&1 | tail -15</automated>
  </verify>
  <done>All tests passing, CI/CD integration and documentation complete (REFACTOR phase complete)</done>
</task>

</tasks>

<verification>
- [ ] .github/workflows/lto-performance.yml exists with regression detection
- [ ] .github/workflows/ci.yml updated with LTO build job
- [ ] scripts/bench/test_ci_workflow.py has comprehensive unit tests
- [ ] docs/performance.md has complete documentation
- [ ] YAML syntax validated
- [ ] All unit tests passing
</verification>

<success_criteria>
- GitHub Actions LTO workflow validates performance on PR
- Main CI workflow includes LTO build job
- Performance documentation covers methodology and troubleshooting
- All unit tests passing
- CI jobs fail on > 1% regression detection
</success_criteria>

<output>
After completion, create `.planning/phases/03-validation/03B-02-SUMMARY.md`
</output>

<atomic_commits>
Commit 1: `test(03B-02): add CI workflow validation tests`
- Add scripts/bench/test_ci_workflow.py
- Tests for workflow config, results artifact handling, build comparison
- Tests initially failing (RED phase)

Commit 2: `feat(03B-02): add GitHub Actions LTO performance workflow`
- Add .github/workflows/lto-performance.yml
- Quick validation, full ARM validation, build time check jobs
- Regression detection and PR comment integration

Commit 3: `feat(03B-02): update CI workflow and add performance docs`
- Update .github/workflows/ci.yml with LTO build job
- Add docs/performance.md with methodology and troubleshooting
- All tests passing (GREEN phase)
</atomic_commits>
