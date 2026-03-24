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
| Runtime Performance | +5% ~ +10% improvement | >= -1% (no degradation) | **Must** |
| Build Time | < 30% increase | <= 30% | **Must** |
| Memory Usage | < 10% increase (optional) | <= 8GB peak RSS | **Nice** |

### Benchmark-Specific Targets

| Benchmark | Target Improvement | Threshold |
|-----------|-------------------|-----------|
| richards | +5% ~ +10% | >= -1% |
| nbody | +3% ~ +8% | >= -1% |
| deltablue | +3% ~ +8% | >= -1% |
| Geometric Mean | +3% ~ +5% | >= -1% |

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
