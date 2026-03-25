#!/bin/bash
# Simplified LTO + PGO build using setup.py
set -e

echo "=== CinderX LTO + PGO Build (Simplified) ==="
echo "Time: $(date)"
echo ""

PROJECT_ROOT="/Users/luchen/Agents-Repo/OpenCode/cinderx"
PROXY_PORT="${PROXY_PORT:-7890}"

# Clean
rm -rf "$PROJECT_ROOT"/dist/*.whl
rm -rf "$PROJECT_ROOT"/build

echo "=== Step 1: Build with PGO instrumentation ==="
echo ""

docker run --rm --platform linux/arm64 \
  --add-host=host.docker.internal:host-gateway \
  -v "$PROJECT_ROOT:/cinderx" \
  -w /cinderx \
  -e CINDERX_ENABLE_LTO=1 \
  -e CINDERX_BUILD_JOBS=2 \
  -e PYTHONJITHUGEPAGES=0 \
  -e http_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e https_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e no_proxy="localhost,127.0.0.1,.internal" \
  cinderx-cpython-baseline:arm64 \
  bash -c '
    set -e

    echo "Installing dependencies..."
    apt-get update -qq && apt-get install -y -qq cmake build-essential 2>&1 | tail -3
    python3 -m pip install -q build 2>&1 | grep -v WARNING || true

    echo ""
    echo "Building with PGO instrumentation..."
    export CMAKE_BUILD_PARALLEL_LEVEL=2

    # Set CMake args for PGO generate
    export CINDERX_CMAKE_ARGS="-DENABLE_LTO=ON -DENABLE_PGO_GENERATE=ON"

    python3 setup.py build_ext --inplace 2>&1 | tail -20

    echo ""
    echo "✅ Instrumented build complete"

    echo ""
    echo "=== Step 2: Collecting profile data ==="
    export PYTHONPATH="/cinderx:$PYTHONPATH"

    python3 << "PY"
import sys
print("Running PGO training...")

# JIT warmup
for i in range(50000):
    pass

# Training workloads
def add(a, b): return a + b
for i in range(1000000): add(i, i+1)

total = 0
for i in range(1000000): total += i

data = [i for i in range(100000)]
sum(data)

print("✅ Training complete")
PY

    echo ""
    echo "Profile data files:"
    find build -name "*.gcda" | wc -l
    find build -name "*.gcda" | head -5

    echo ""
    echo "=== Step 3: Building optimized wheel ==="

    # Rebuild with PGO use
    export CINDERX_CMAKE_ARGS="-DENABLE_LTO=ON -DENABLE_PGO_USE=ON"

    python3 -m build --wheel 2>&1 | tail -30

    if ls dist/*.whl 2>/dev/null; then
      echo ""
      echo "✅ Wheel created:"
      ls -lh dist/*.whl
    else
      echo "❌ No wheel"
      exit 1
    fi
  '

if ls "$PROJECT_ROOT"/dist/*.whl 2>/dev/null; then
  cp "$PROJECT_ROOT"/dist/*.whl /tmp/cinderx-lto-pgo.whl
  echo ""
  echo "=== Build Successful ==="
  echo "Saved to: /tmp/cinderx-lto-pgo.whl"
  ls -lh /tmp/cinderx-lto-pgo.whl
else
  echo "❌ Build failed"
  exit 1
fi
