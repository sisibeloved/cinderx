#!/bin/bash
# Quick LTO performance test for experiments
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BENCHMARK=${BENCHMARK:-generators}
SAMPLES=${SAMPLES:-5}
WARMUP=${WARMUP:-1}

echo "=== Quick LTO Test ==="
echo "Benchmark: $BENCHMARK"
echo "Samples: $SAMPLES, Warmup: $WARMUP"
echo ""

# Install CinderX if not already installed
python3 -c "import cinderx" 2>/dev/null || {
  echo "Installing CinderX..."
  pip3 install --quiet /dist/cinderx-*-linux_aarch64.whl 2>&1 | grep -v notice
}

# Run quick benchmark
export BENCHMARK SAMPLES WARMUP
python3 << 'PY'
import os
import sys
import time
import statistics
import cinderx
import cinderx.jit as jit

# Enable JIT
jit.enable()
print(f"JIT enabled: {jit.is_enabled()}")

# Check LTO status
lto_status = "unknown"
if hasattr(cinderx, 'is_lto_enabled'):
    lto_status = "enabled" if cinderx.is_lto_enabled() else "disabled"
print(f"LTO: {lto_status}")

# Load benchmark
sys.path.insert(0, os.environ["SCRIPT_DIR"])
from benchmark_harness import load_benchmark, resolve_benchmark

benchmark = os.environ["BENCHMARK"]
spec = resolve_benchmark(benchmark)
module, bench = load_benchmark("/root/benchmarks", benchmark)
bench_args = spec.bench_args

# Warmup
warmup = int(os.environ["WARMUP"])
print(f"\nWarmup ({warmup} runs)...")
for _ in range(warmup):
    bench(*bench_args)

# Measure
samples = int(os.environ["SAMPLES"])
print(f"Measuring ({samples} runs)...")
times = []
for i in range(samples):
    start = time.perf_counter()
    bench(*bench_args)
    end = time.perf_counter()
    times.append(end - start)

# Calculate
avg = statistics.mean(times)
median = statistics.median(times)
stdev = statistics.stdev(times) if len(times) > 1 else 0.0

print(f"\n=== Results ===")
print(f"Average: {avg:.6f}s")
print(f"Median:  {median:.6f}s")
print(f"StdDev:  {stdev:.6f}s")
print(f"Samples: {samples}")

# Save result
import json
result = {
    "benchmark": benchmark,
    "lto_status": lto_status,
    "average": avg,
    "median": median,
    "stdev": stdev,
    "samples": samples,
}

result_file = f"/results/{benchmark}-lto-quick.json"
with open(result_file, "w") as f:
    json.dump(result, f, indent=2)

print(f"\n✓ Result saved to: {result_file}")
PY

echo ""
echo "=== Test complete ==="
echo "Compare with baseline:"
echo "  BENCHMARK=$BENCHMARK SAMPLES=$SAMPLES ENABLE_LTO=0 /scripts/test-lto-quick.sh"
