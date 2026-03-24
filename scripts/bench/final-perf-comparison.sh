#!/bin/bash
# Final performance comparison: Baseline vs LTO
set -e

BASELINE_WHEEL="${1:-/tmp/cinderx-baseline.whl}"
LTO_WHEEL="${2:-/tmp/cinderx-lto-final.whl}"

echo "=== CinderX Performance Comparison ==="
echo "Date: $(date)"
echo ""
echo "Baseline: $BASELINE_WHEEL"
echo "LTO: $LTO_WHEEL"
echo ""

# Verify wheels exist
if [ ! -f "$BASELINE_WHEEL" ]; then
    echo "❌ Baseline wheel not found: $BASELINE_WHEEL"
    exit 1
fi

if [ ! -f "$LTO_WHEEL" ]; then
    echo "❌ LTO wheel not found: $LTO_WHEEL"
    echo ""
    echo "Waiting for LTO build to complete..."
    for i in {1..20}; do
        sleep 30
        if [ -f "$LTO_WHEEL" ]; then
            echo "✅ LTO wheel ready!"
            break
        fi
        echo "[$(date +%H:%M:%S)] Waiting... ($i/20)"
    done
fi

# Show wheel sizes
echo "=== Wheel Sizes ==="
echo "Baseline: $(ls -lh "$BASELINE_WHEEL" | awk '{print $5}')"
echo "LTO: $(ls -lh "$LTO_WHEEL" | awk '{print $5}')"
echo ""

# Performance test function
run_perf_test() {
    local wheel="$1"
    local name="$2"

    python3 -m venv "/tmp/perf-test-$name"
    source "/tmp/perf-test-$name/bin/activate"

    pip install -q "$wheel"

    python3 << 'PY'
import sys
import time
import statistics

# JIT warmup
def warmup():
    for i in range(10000):
        pass

warmup()

# Test 1: Function calls
def test_func_calls(n=2000000):
    def add(a, b):
        return a + b

    times = []
    for _ in range(5):
        start = time.perf_counter()
        for i in range(n):
            add(i, i+1)
        times.append(time.perf_counter() - start)

    return statistics.median(times)

# Test 2: Loops
def test_loops(n=2000000):
    times = []
    for _ in range(5):
        start = time.perf_counter()
        total = 0
        for i in range(n):
            total += i
        times.append(time.perf_counter() - start)

    return statistics.median(times)

# Test 3: List operations
def test_list_ops(n=200000):
    times = []
    for _ in range(5):
        start = time.perf_counter()
        data = [i for i in range(n)]
        total = sum(data)
        times.append(time.perf_counter() - start)

    return statistics.median(times)

# Run tests
print(f"{test_func_calls():.6f},{test_loops():.6f},{test_list_ops():.6f}")
PY

    deactivate
    rm -rf "/tmp/perf-test-$name"
}

# Test baseline
echo "=== Testing Baseline ==="
BASELINE_RESULTS=$(run_perf_test "$BASELINE_WHEEL" "baseline")
echo "Baseline: $BASELINE_RESULTS"

# Test LTO
echo ""
echo "=== Testing LTO ==="
LTO_RESULTS=$(run_perf_test "$LTO_WHEEL" "lto")
echo "LTO: $LTO_RESULTS"

# Parse results
IFS=',' read -r BASELINE_FUNC BASELINE_LOOP BASELINE_LIST <<< "$BASELINE_RESULTS"
IFS=',' read -r LTO_FUNC LTO_LOOP LTO_LIST <<< "$LTO_RESULTS"

echo ""
echo "=== Performance Results ==="
echo ""
echo "Baseline (no LTO):"
echo "  Function calls: ${BASELINE_FUNC}s"
echo "  Loops: ${BASELINE_LOOP}s"
echo "  List operations: ${BASELINE_LIST}s"
echo ""
echo "LTO enabled:"
echo "  Function calls: ${LTO_FUNC}s"
echo "  Loops: ${LTO_LOOP}s"
echo "  List operations: ${LTO_LIST}s"
echo ""

# Calculate improvements
python3 << PY
baseline_func = float("${BASELINE_FUNC:-0}")
baseline_loop = float("${BASELINE_LOOP:-0}")
baseline_list = float("${BASELINE_LIST:-0}")

lto_func = float("${LTO_FUNC:-0}")
lto_loop = float("${LTO_LOOP:-0}")
lto_list = float("${LTO_LIST:-0}")

if baseline_func > 0 and lto_func > 0:
    func_imp = ((baseline_func / lto_func) - 1) * 100
    loop_imp = ((baseline_loop / lto_loop) - 1) * 100
    list_imp = ((baseline_list / lto_list) - 1) * 100

    avg_imp = (func_imp + loop_imp + list_imp) / 3

    print("=" * 50)
    print("Performance Improvements:")
    print(f"  Function calls: {func_imp:+.2f}%")
    print(f"  Loops: {loop_imp:+.2f}%")
    print(f"  List operations: {list_imp:+.2f}%")
    print(f"  Average: {avg_imp:+.2f}%")
    print("=" * 50)
    print("")

    if avg_imp >= 5.0 and avg_imp <= 10.0:
        print("✅ Performance target MET (+5%~+10%)")
    elif avg_imp > 10.0:
        print("✨ Performance EXCEEDS target (>%+10%)")
    elif avg_imp > 0:
        print("⚠️  Performance improvement below target (<5%)")
    else:
        print("❌ Performance REGRESSION")
else:
    print("❌ Invalid test results")
PY

echo ""
echo "=== Test Complete ==="
