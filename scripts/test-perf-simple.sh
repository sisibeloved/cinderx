#!/bin/bash
# Simple performance test for CinderX wheels
set -e

echo "=== CinderX Performance Comparison ==="
echo ""

test_wheel() {
  local wheel="$1"
  local name="$2"

  echo "Testing $name..."

  # Clean
  rm -rf "/tmp/venv-$name"
  python3 -m venv "/tmp/venv-$name"
  source "/tmp/venv-$name/bin/activate"

  # Install
  pip install -q "$wheel"

  # Run benchmark
  python3 -c '
import time

# Warmup
for i in range(10000):
    pass

# Test
def add(a, b):
    return a + b

times = []
for _ in range(3):
    start = time.time()
    for i in range(2000000):
        add(i, i+1)
    times.append(time.time() - start)

result = sorted(times)[1]
print(f"'$name': {result:.3f}s")
'

  deactivate
}

echo "Function Call Performance (2M iterations):"
echo "-------------------------------------------"
test_wheel "/tmp/cinderx-baseline.whl" "Baseline"
test_wheel "/tmp/cinderx-lto-optimized.whl" "LTO"
test_wheel "/tmp/cinderx-lto-pgo.whl" "LTO+PGO"

echo ""
echo "=== Complete ==="
