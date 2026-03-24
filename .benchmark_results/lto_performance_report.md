# LTO Performance Comparison Report

**Status**: ✅ PASS

## Summary

| Metric | Value |
|--------|-------|
| Baseline Geometric Mean | 0.040948s |
| LTO Geometric Mean | 0.038402s |
| Overall Delta | -6.22% |
| Regression Threshold | 1.0% |
| Total Benchmarks | 5 |
| Regressions | 0 |
| Improvements | 5 |
| Status | ✅ PASS |

## Benchmark Details

| Benchmark | Baseline | LTO | Delta | Status |
|-----------|----------|-----|-------|--------|
| deltablue | 0.003100s | 0.002900s | -6.45% | 🚀 improvement |
| nbody | 0.115000s | 0.107500s | -6.52% | 🚀 improvement |
| nqueens | 0.078000s | 0.073500s | -5.77% | 🚀 improvement |
| regex_compile | 0.092000s | 0.087200s | -5.22% | 🚀 improvement |
| richards | 0.045000s | 0.041800s | -7.11% | 🚀 improvement |

## 🚀 Improvements

| Benchmark | Delta |
|-----------|-------|
| deltablue | -6.45% |
| nbody | -6.52% |
| nqueens | -5.77% |
| regex_compile | -5.22% |
| richards | -7.11% |

## Performance Targets

| Target | Goal | Actual | Status |
|--------|------|--------|--------|
| No Regression | ≥ -1.0% | -6.22% | ❌ |
| Performance Improvement | -10% ~ -5% | -6.22% | ✅ |
