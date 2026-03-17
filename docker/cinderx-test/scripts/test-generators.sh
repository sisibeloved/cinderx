#!/bin/bash
# Run full generators benchmark comparison: baseline vs optimized
set -e

SAMPLES=${SAMPLES:-10}
WARMUP=${WARMUP:-3}

echo "========================================"
echo "  Generators Benchmark Comparison"
echo "========================================"
echo "Samples: $SAMPLES"
echo "Warmup:  $WARMUP"
echo ""

# Baseline
echo "=== BASELINE (no optimization) ==="
PYTHONJIT=1 \
PYTHONJITAUTO=50 \
PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY=0 \
/scripts/bench-generators.sh 2>&1 | tee /tmp/baseline.txt

echo ""

# Optimized
echo "=== OPTIMIZED (PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY=1) ==="
PYTHONJIT=1 \
PYTHONJITAUTO=50 \
PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY=1 \
/scripts/bench-generators.sh 2>&1 | tee /tmp/optimized.txt

echo ""

# Compare
echo "========================================"
echo "  COMPARISON"
echo "========================================"

python3 << PY
import re
import statistics

def extract_time(filename):
    with open(filename) as f:
        content = f.read()
    match = re.search(r'Result: ([\d.]+)s', content)
    if match:
        return float(match.group(1))
    return None

baseline = extract_time('/tmp/baseline.txt')
optimized = extract_time('/tmp/optimized.txt')

if baseline and optimized:
    speedup = baseline / optimized
    delta = (speedup - 1.0) * 100

    print(f"Baseline:  {baseline:.6f}s")
    print(f"Optimized: {optimized:.6f}s")
    print(f"Speedup:   {speedup:.4f}x")
    print(f"Delta:     {delta:+.2f}%")
    print()

    if speedup > 1.0:
        print("✓ Optimization IMPROVES performance")
    else:
        print("✗ Optimization DEGRADES performance")
else:
    print("ERROR: Could not extract timing data")
    exit(1)
PY

echo ""
echo "========================================"
