#!/bin/bash
# Full comparison: CPython baseline vs CPython + CinderX (baseline and optimized)
set -e

SAMPLES=${SAMPLES:-10}
WARMUP=${WARMUP:-3}

echo "========================================"
echo "  CinderX Performance Comparison"
echo "========================================"
echo "Samples: $SAMPLES"
echo "Warmup:  $WARMUP"
echo ""

# Prepare benchmark
echo "=== Preparing benchmark ==="
mkdir -p /root/benchmarks
python3 << 'PY'
import urllib.request
import pathlib

url = "https://raw.githubusercontent.com/python/pyperformance/main/pyperformance/data-files/benchmarks/bm_generators/run_benchmark.py"
output_path = pathlib.Path("/root/benchmarks/run_benchmark.py")

if not output_path.exists():
    print(f"Downloading {url}...")
    urllib.request.urlretrieve(url, output_path)
    print(f"✓ Saved to {output_path}")
else:
    print(f"✓ Benchmark already exists at {output_path}")
PY

echo ""

# Test 1: CPython baseline
echo "========================================"
echo "  Test 1: CPython Baseline"
echo "========================================"
/scripts/test-baseline.sh 2>&1 | tee /tmp/baseline.txt

echo ""

# Test 2: CinderX (no optimization)
echo "========================================"
echo "  Test 2: CinderX (no optimization)"
echo "========================================"
ENABLE_OPTIMIZATION=0 /scripts/test-cinderx.sh 2>&1 | tee /tmp/cinderx-baseline.txt

echo ""

# Test 3: CinderX (with optimization)
echo "========================================"
echo "  Test 3: CinderX (optimized)"
echo "========================================"
ENABLE_OPTIMIZATION=1 /scripts/test-cinderx.sh 2>&1 | tee /tmp/cinderx-optimized.txt

echo ""

# Compare results
echo "========================================"
echo "  COMPARISON"
echo "========================================"

python3 << 'PY'
import re

def extract_time(filename, pattern="Result"):
    with open(filename) as f:
        content = f.read()
    # Look for "Result: X.XXXXXXs" or "XXX Result: X.XXXXXXs"
    match = re.search(rf'(?:\w+\s+)?{pattern}:\s+([\d.]+)s', content)
    if match:
        return float(match.group(1))
    return None

baseline = extract_time('/tmp/baseline.txt', 'Baseline Result')
cinderx_baseline = extract_time('/tmp/cinderx-baseline.txt', 'CinderX Result')
cinderx_optimized = extract_time('/tmp/cinderx-optimized.txt', 'CinderX Result')

print(f"CPython Baseline:        {baseline:.6f}s")
print(f"CinderX (no opt):        {cinderx_baseline:.6f}s")
print(f"CinderX (optimized):     {cinderx_optimized:.6f}s")
print()

if baseline and cinderx_baseline:
    speedup_base = baseline / cinderx_baseline
    delta_base = (speedup_base - 1.0) * 100
    print(f"Speedup (CinderX):       {speedup_base:.4f}x ({delta_base:+.2f}%)")

if baseline and cinderx_optimized:
    speedup_opt = baseline / cinderx_optimized
    delta_opt = (speedup_opt - 1.0) * 100
    print(f"Speedup (CinderX+opt):   {speedup_opt:.4f}x ({delta_opt:+.2f}%)")

if cinderx_baseline and cinderx_optimized:
    speedup_vs_cinderx = cinderx_baseline / cinderx_optimized
    delta_vs_cinderx = (speedup_vs_cinderx - 1.0) * 100
    print(f"Optimization benefit:    {speedup_vs_cinderx:.4f}x ({delta_vs_cinderx:+.2f}%)")

# Save results
import json
from datetime import datetime

results = {
    "timestamp": datetime.now().isoformat(),
    "samples": $SAMPLES,
    "warmup": $WARMUP,
    "baseline": baseline,
    "cinderx_baseline": cinderx_baseline,
    "cinderx_optimized": cinderx_optimized,
}

if baseline and cinderx_baseline:
    results["speedup_cinderx"] = baseline / cinderx_baseline
if baseline and cinderx_optimized:
    results["speedup_cinderx_optimized"] = baseline / cinderx_optimized

with open("/results/comparison.json", "w") as f:
    json.dump(results, f, indent=2)
    print(f"\nResults saved to /results/comparison.json")
PY

echo ""
echo "========================================"
