#!/bin/bash
# Performance comparison: Baseline vs LTO
set -e

echo "=== CinderX Performance Comparison ==="
echo "Date: $(date)"
echo ""

# Check for wheels
BASELINE_WHEEL=$(ls dist/cinderx-*-linux_aarch64.whl | grep -v "lto" | head -1)
LTO_WHEEL="dist/cinderx-2026.3.24.0-cp314-cp314-linux_aarch64.whl"

if [ ! -f "$LTO_WHEEL" ]; then
  echo "❌ LTO wheel not found: $LTO_WHEEL"
  exit 1
fi

if [ ! -f "$BASELINE_WHEEL" ]; then
  echo "❌ Baseline wheel not found"
  echo "Available wheels:"
  ls -lh dist/*.whl
  exit 1
fi

echo "Baseline wheel: $BASELINE_WHEEL"
echo "LTO wheel: $LTO_WHEEL"
echo ""

# Get sizes
BASELINE_SIZE=$(du -m "$BASELINE_WHEEL" | cut -f1)
LTO_SIZE=$(du -m "$LTO_WHEEL" | cut -f1)

echo "=== Wheel Sizes ==="
echo "Baseline: ${BASELINE_SIZE}M"
echo "LTO: ${LTO_SIZE}M"
echo ""

# Simple performance test using Python built-in benchmarks
echo "=== Installing and Testing Wheels ==="

# Test baseline
echo ""
echo ">>> Testing Baseline wheel..."
python3 -m venv /tmp/cinderx-baseline
source /tmp/cinderx-baseline/bin/activate
pip install -q "$BASELINE_WHEEL"
python3 -c "
import sys
import time

# Simple JIT warmup
def warmup():
    for i in range(1000):
        pass

warmup()

# Micro-benchmark: function calls
def test_func_calls(n=1000000):
    def add(a, b):
        return a + b
    start = time.perf_counter()
    for i in range(n):
        add(i, i+1)
    return time.perf_counter() - start

# Micro-benchmark: loop performance
def test_loops(n=1000000):
    start = time.perf_counter()
    total = 0
    for i in range(n):
        total += i
    return time.perf_counter() - start

# Micro-benchmark: list operations
def test_list_ops(n=100000):
    start = time.perf_counter()
    data = [i for i in range(n)]
    total = sum(data)
    return time.perf_counter() - start

print('Baseline Results:')
print(f'  Function calls: {test_func_calls():.4f}s')
print(f'  Loops: {test_loops():.4f}s')
print(f'  List ops: {test_list_ops():.4f}s')
"

BASELINE_RESULTS=$(python3 -c "
import sys
import time

def warmup():
    for i in range(1000):
        pass

warmup()

def test_func_calls(n=1000000):
    def add(a, b):
        return a + b
    start = time.perf_counter()
    for i in range(n):
        add(i, i+1)
    return time.perf_counter() - start

def test_loops(n=1000000):
    start = time.perf_counter()
    total = 0
    for i in range(n):
        total += i
    return time.perf_counter() - start

def test_list_ops(n=100000):
    start = time.perf_counter()
    data = [i for i in range(n)]
    total = sum(data)
    return time.perf_counter() - start

print(f'{test_func_calls():.4f},{test_loops():.4f},{test_list_ops():.4f}')
" 2>/dev/null)

deactivate

# Test LTO
echo ""
echo ">>> Testing LTO wheel..."
python3 -m venv /tmp/cinderx-lto
source /tmp/cinderx-lto/bin/activate
pip install -q "$LTO_WHEEL"

LTO_RESULTS=$(python3 -c "
import sys
import time

def warmup():
    for i in range(1000):
        pass

warmup()

def test_func_calls(n=1000000):
    def add(a, b):
        return a + b
    start = time.perf_counter()
    for i in range(n):
        add(i, i+1)
    return time.perf_counter() - start

def test_loops(n=1000000):
    start = time.perf_counter()
    total = 0
    for i in range(n):
        total += i
    return time.perf_counter() - start

def test_list_ops(n=100000):
    start = time.perf_counter()
    data = [i for i in range(n)]
    total = sum(data)
    return time.perf_counter() - start

print(f'{test_func_calls():.4f},{test_loops():.4f},{test_list_ops():.4f}')
" 2>/dev/null)

deactivate

echo ""
echo "=== Performance Comparison ==="

# Parse results
IFS=',' read -r BASELINE_FUNC BASELINE_LOOP BASELINE_LIST <<< "$BASELINE_RESULTS"
IFS=',' read -r LTO_FUNC LTO_LOOP LTO_LIST <<< "$LTO_RESULTS"

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
baseline_func = float("${BASELINE_FUNC:-}")
baseline_loop = float("${BASELINE_LOOP:-}")
baseline_list = float("${BASELINE_LIST:-}")

lto_func = float("${LTO_FUNC:-}")
lto_loop = float("${LTO_LOOP:-}")
lto_list = float("${LTO_LIST:-}")

func_imp = ((baseline_func / lto_func) - 1) * 100
loop_imp = ((baseline_loop / lto_loop) - 1) * 100
list_imp = ((baseline_list / lto_list) - 1) * 100

avg_imp = (func_imp + loop_imp + list_imp) / 3

print("Performance Improvements:")
print(f"  Function calls: {func_imp:+.2f}%")
print(f"  Loops: {loop_imp:+.2f}%")
print(f"  List operations: {list_imp:+.2f}%")
print(f"  Average: {avg_imp:+.2f}%")
print("")

if avg_imp >= 5.0:
    print("✅ Performance target MET (+5%~+10%)")
elif avg_imp > 0:
    print("⚠️  Performance improvement below target (<5%)")
else:
    print("❌ Performance REGRESSION")
PY

echo ""
echo "=== Cleanup ==="
rm -rf /tmp/cinderx-baseline /tmp/cinderx-lto
echo "Done!"
