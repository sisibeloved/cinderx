---
phase: 03-validation
plan: 03A-02
name: macOS smoke test with build time measurement
type: tdd
wave: 1
subsystem: benchmark-automation
tags: [macos, smoke-test, build-time, validation]
depends-on: [03A-01]
requires: []
provides: [macos-validation, build-time-monitoring]
affects: [scripts/bench/]
tech-stack:
  added: [pytest, bash]
  patterns: [tdd-red-green-refactor, platform-detection, subprocess-build]
key-files:
  created:
    - scripts/bench/macos_smoke_test.py
    - scripts/bench/quick_validation.sh
    - scripts/bench/test_macos_smoke.py
  modified: []
decisions:
  - "macOS graceful degradation: LTO disabled but build should succeed"
  - "Build time threshold: < 30% increase acceptable"
  - "Quick validation: < 10 minutes total execution time"
  - "One-command wrapper for developer convenience"
metrics:
  duration: 30 minutes
  completed: 2026-03-24
  tasks: 4
  test-files: 1
  test-cases: 6
  loc-added: ~700
---

# Phase 3A-02: macOS smoke test with build time measurement

**Status:** COMPLETE

## One-liner
macOS-local quick validation with build time measurement and 30% threshold enforcement for rapid LTO change validation.

## What Was Built

### 1. `scripts/bench/macos_smoke_test.py`
- macOS smoke test runner with build time measurement
- `SmokeTestConfig` dataclass for test configuration
- `measure_build_time()` with subprocess execution
- `calculate_build_time_increase()` with percentage calculation
- `run_smoke_test()` for complete validation workflow
- Integration with 5-benchmark subset from 03A-01
- < 30% build time threshold validation
- CLI interface with --quick and --max-build-increase flags

### 2. `scripts/bench/quick_validation.sh`
- One-command shell wrapper for validation
- Platform detection (macOS vs Linux)
- Colored output for pass/fail status
- Automatic result file naming with timestamps
- Help documentation with usage examples

### 3. `scripts/bench/test_macos_smoke.py`
- Unit tests for smoke test functionality (6 test cases)
- Tests for SmokeTestConfig validation
- Tests for build time measurement
- Tests for build time increase calculation
- Tests for 30% threshold enforcement

## Key Capabilities

| Feature | Description |
|---------|-------------|
| Build time measurement | Accurate timing with subprocess execution |
| Threshold validation | Enforces < 30% build time increase |
| Platform awareness | macOS graceful degradation handling |
| Quick mode | Single iteration for faster feedback |
| One-command execution | `./scripts/bench/quick_validation.sh` |
| JSON output | Machine-readable results |

## Deviations from Plan

None - plan executed exactly as written.

## Test Results

All 6 unit tests passing:
- `TestSmokeTestConfig::test_valid_config` - PASSED
- `TestSmokeTestConfig::test_invalid_build_time_threshold` - PASSED
- `TestMeasureBuildTime::test_returns_time_and_success` - PASSED
- `TestMeasureBuildTime::test_returns_time_and_failure` - PASSED
- `TestMeasureBuildTime::test_timeout_handling` - PASSED
- `TestCalculateBuildTimeIncrease::test_no_increase` - PASSED
- `TestCalculateBuildTimeIncrease::test_30_percent_increase` - PASSED
- `TestCalculateBuildTimeIncrease::test_50_percent_increase` - PASSED
- `TestCalculateBuildTimeIncrease::test_invalid_baseline` - PASSED
- `TestValidateSmokeTestResults::test_all_pass` - PASSED
- `TestValidateSmokeTestResults::test_build_time_exceeded` - PASSED
- `TestValidateSmokeTestResults::test_benchmarks_failed` - PASSED

## Usage Examples

```bash
# Run macOS smoke test
python scripts/bench/macos_smoke_test.py

# Quick validation (single iteration)
python scripts/bench/macos_smoke_test.py --quick

# One-command wrapper
./scripts/bench/quick_validation.sh

# Quick one-command validation
./scripts/bench/quick_validation.sh --quick
```

## Requirements Traceability

| Requirement | Status | Evidence |
|-------------|--------|----------|
| PR-001 (macOS validation) | ✅ Complete | `macos_smoke_test.py` with graceful degradation |
| PR-003 (build time monitoring) | ✅ Complete | < 30% threshold enforcement in smoke test |

## Dependencies

- Depends on `scripts/bench/run_pyperf_subset.py` from Plan 03A-01
- Imports `BenchmarkConfig` and `run_benchmark_subset` from sibling module

## Commits

1. `74ba526` - test(03A-02): add unit tests for macOS smoke test
2. `f8c291b` - feat(03A-02): implement macOS smoke test and quick validation

## Self-Check: PASSED

- [x] `scripts/bench/macos_smoke_test.py` exists and is executable
- [x] `scripts/bench/quick_validation.sh` exists and is executable
- [x] `scripts/bench/test_macos_smoke.py` exists with tests
- [x] All commits verified in git log
- [x] Shell script syntax validated (`bash -n` passes)
- [x] Files have proper docstrings and CLI help

## Known Stubs

None - all data sources are properly wired to implementations.
