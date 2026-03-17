#!/bin/bash
# Test CPython + CinderX performance
set -e

SAMPLES=${SAMPLES:-10}
WARMUP=${WARMUP:-3}
BENCHMARK=${BENCHMARK:-generators}
ENABLE_OPTIMIZATION=${ENABLE_OPTIMIZATION:-0}

echo "=== CPython + CinderX Test ==="
echo "Benchmark: $BENCHMARK"
echo "Samples: $SAMPLES, Warmup: $WARMUP"
echo "Enable optimization: $ENABLE_OPTIMIZATION"
echo ""

# Run benchmark with CinderX enabled
python3 << PY
import sys
import time
import statistics
import os

# Import and enable CinderX
import cinderx
import cinderx.jit as jit
jit.enable()

print(f"CinderX version: {cinderx.__version__ if hasattr(cinderx, '__version__') else 'unknown'}")
print(f"JIT enabled: {jit.is_enabled()}")

# Set optimization flag
if $ENABLE_OPTIMIZATION:
    os.environ["PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY"] = "1"
    print("Optimization enabled: PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY=1")

# Add benchmark path
sys.path.insert(0, "/root/benchmarks")
from run_benchmark import bench_generators

# Warmup
print(f"\nWarming up ({WARMUP} runs)...")
for _ in range($WARMUP):
    bench_generators(1)

# Measure
print(f"\nMeasuring ({SAMPLES} runs)...")
times = []
for i in range($SAMPLES):
    start = time.perf_counter()
    bench_generators(1)
    end = time.perf_counter()
    elapsed = end - start
    times.append(elapsed)
    print(f"  Run {i+1:2d}: {elapsed:.6f}s")

# Calculate statistics
avg = statistics.mean(times)
stdev = statistics.stdev(times) if len(times) > 1 else 0.0

opt_status = " (optimized)" if $ENABLE_OPTIMIZATION else ""
print(f"\nCinderX Result{opt_status}: {avg:.6f}s ± {stdev:.6f}s")
PY
