#!/bin/bash
# Compare LTO vs non-LTO CinderX performance
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BENCHMARK=${BENCHMARK:-generators}
SAMPLES=${SAMPLES:-10}
WARMUP=${WARMUP:-3}
THRESHOLD_PCT=${THRESHOLD_PCT:-1.0}

echo "=== LTO Performance Comparison Test ==="
echo "Benchmark: $BENCHMARK"
echo "Samples: $SAMPLES, Warmup: $WARMUP"
echo "Regression threshold: ${THRESHOLD_PCT}%"
echo ""

# Find CinderX wheel
export SCRIPT_DIR
eval "$(python3 <<'PY'
import glob
import os
import sys

sys.path.insert(0, os.environ["SCRIPT_DIR"])
from benchmark_harness import cinderx_wheel_glob

matches = sorted(glob.glob(str(cinderx_wheel_glob())))
if not matches:
    raise SystemExit("ERROR: no CinderX wheel found under /dist")
print(f'CINDERX_WHEEL="{matches[-1]}"')
PY
)"

echo "Using wheel: $CINDERX_WHEEL"
echo ""

# Install CinderX
python3 -m pip install --quiet "$CINDERX_WHEEL"

# Function to run benchmark and extract average time
run_benchmark() {
    local name="$1"
    local enable_lto="$2"

    echo "Testing: $name (LTO=$enable_lto)"

    # Set environment
    export BENCHMARK SAMPLES WARMUP
    export ENABLE_LTO=$enable_lto

    # Run benchmark and capture output
    python3 << PY
import os
import sys
import time
import statistics
import json

samples = int(os.environ["SAMPLES"])
warmup = int(os.environ["WARMUP"])
benchmark = os.environ["BENCHMARK"]
enable_lto = os.environ["ENABLE_LTO"] == "1"

# Import and configure CinderX
import cinderx
import cinderx.jit as jit

jit.enable()
lto_status = cinderx.is_lto_enabled() if hasattr(cinderx, 'is_lto_enabled') else False

print(f"CinderX JIT: enabled")
print(f"LTO status: {'enabled' if lto_status else 'disabled'}")

if enable_lto and not lto_status:
    print("WARNING: LTO requested but not detected in binary!")

sys.path.insert(0, "$SCRIPT_DIR")
from benchmark_harness import load_benchmark, resolve_benchmark

spec = resolve_benchmark(benchmark)
module, bench = load_benchmark("/root/benchmarks", benchmark)
bench_args = spec.bench_args

# Warmup
print(f"Warming up ({warmup} runs)...")
for _ in range(warmup):
    bench(*bench_args)

# Measure
print(f"Measuring ({samples} runs)...")
times = []
for i in range(samples):
    start = time.perf_counter()
    bench(*bench_args)
    end = time.perf_counter()
    elapsed = end - start
    times.append(elapsed)
    if (i + 1) % 5 == 0:
        print(f"  Progress: {i+1}/{samples}")

# Calculate statistics
avg = statistics.mean(times)
stdev = statistics.stdev(times) if len(times) > 1 else 0.0
median = statistics.median(times)

# Output results as JSON for parsing
result = {
    "name": "$name",
    "lto_enabled": lto_status,
    "average": avg,
    "median": median,
    "stdev": stdev,
    "samples": samples,
}

print(f"\n--- RESULT JSON ---")
print(json.dumps(result))
print(f"--- END JSON ---\n")

print(f"$name Result: avg={avg:.6f}s, median={median:.6f}s, stdev={stdev:.6f}s")
PY
}

# Test non-LTO baseline
echo "=========================================="
echo "Phase 1: Baseline (non-LTO)"
echo "=========================================="
BASELINE_OUTPUT=$(run_benchmark "Baseline" "0")
BASELINE_JSON=$(echo "$BASELINE_OUTPUT" | sed -n '/--- RESULT JSON ---/,/--- END JSON ---/p' | sed '1d;$d')
BASELINE_AVG=$(echo "$BASELINE_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['average'])")

echo ""

# Test LTO
echo "=========================================="
echo "Phase 2: LTO Optimized"
echo "=========================================="
LTO_OUTPUT=$(run_benchmark "LTO" "1")
LTO_JSON=$(echo "$LTO_OUTPUT" | sed -n '/--- RESULT JSON ---/,/--- END JSON ---/p' | sed '1d;$d')
LTO_AVG=$(echo "$LTO_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin)['average'])")

echo ""

# Calculate performance delta
echo "=========================================="
echo "Performance Comparison"
echo "=========================================="

DELTA=$(python3 << PY
baseline = $BASELINE_AVG
lto = $LTO_AVG
threshold = $THRESHOLD_PCT

# Calculate percentage change (negative = improvement)
delta_pct = ((lto / baseline) - 1.0) * 100.0

print(f"Baseline average: {baseline:.6f}s")
print(f"LTO average:      {lto:.6f}s")
print(f"Delta:            {delta_pct:+.2f}%")
print(f"Threshold:        {threshold:.1f}%")
print("")

# Determine status
if abs(delta_pct) <= threshold:
    status = "PASS (within noise threshold)"
    exit_code = 0
elif delta_pct < 0:
    status = f"PASS (improvement: {abs(delta_pct):.2f}%)"
    exit_code = 0
else:
    status = f"FAIL (regression: {delta_pct:.2f}% > {threshold:.1f}%)"
    exit_code = 1

print(f"Status: {status}")

# Write comparison report
import json
report = {
    "baseline_avg": baseline,
    "lto_avg": lto,
    "delta_pct": delta_pct,
    "threshold_pct": threshold,
    "passed": exit_code == 0,
    "status": status,
}

with open("/results/lto-comparison.json", "w") as f:
    json.dump(report, f, indent=2)

print(f"\nReport saved to: /results/lto-comparison.json")
exit(exit_code)
PY
)

RESULT=$?

echo ""
if [ $RESULT -eq 0 ]; then
    echo "✓ LTO performance test PASSED"
else
    echo "✗ LTO performance test FAILED"
fi

exit $RESULT
