#!/bin/bash
# Run generators benchmark using downloaded benchmark file
set -e

SAMPLES=${SAMPLES:-10}
WARMUP=${WARMUP:-3}

echo "=== Generators benchmark ==="
echo "Samples: $SAMPLES, Warmup: $WARMUP"
echo ""

python3 << PY
import sys
import time
import statistics

# Add benchmark directory to path
sys.path.insert(0, "/root/benchmarks")
from run_benchmark import bench_generators

# Warmup
print(f"Warming up ({WARMUP} runs)...")
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

print(f"\nResult: {avg:.6f}s ± {stdev:.6f}s")
PY
