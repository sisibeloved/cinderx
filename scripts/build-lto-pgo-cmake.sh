#!/bin/bash
# Build CinderX LTO + PGO using direct CMake invocation
set -e

echo "=== CinderX LTO + PGO Build (CMake Direct) ==="
echo "Time: $(date)"
echo ""

PROJECT_ROOT="/Users/luchen/Agents-Repo/OpenCode/cinderx"
PROXY_PORT="${PROXY_PORT:-7890}"

# Clean
rm -rf "$PROJECT_ROOT"/dist/*.whl
rm -rf "$PROJECT_ROOT"/build-pgo

mkdir -p "$PROJECT_ROOT"/build-pgo

echo "=== Phase 1: Instrumented Build ==="
echo ""

docker run --rm --platform linux/arm64 \
  --add-host=host.docker.internal:host-gateway \
  -v "$PROJECT_ROOT:/cinderx" \
  -w /cinderx/build-pgo \
  -e http_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e https_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e no_proxy="localhost,127.0.0.1,.internal" \
  -e DEBIAN_FRONTEND=noninteractive \
  cinderx-cpython-baseline:arm64 \
  bash -c '
    set -ex

    echo "Installing cmake..."
    apt-get update -qq
    apt-get install -y -qq cmake build-essential 2>&1 | tail -3

    echo ""
    echo "=== Configuring with PGO instrumentation ==="

    cmake .. \
      -DCMAKE_BUILD_TYPE=Release \
      -DENABLE_LTO=ON \
      -DENABLE_PGO_GENERATE=ON \
      -DPY_VERSION=3.14 \
      -DPython_ROOT_DIR=/usr/local \
      -DCMAKE_C_COMPILER=/usr/bin/gcc \
      -DCMAKE_CXX_COMPILER=/usr/bin/g++ \
      2>&1 | grep -E "PGO|LTO|error" | head -20

    echo ""
    echo "=== Building instrumented version ==="
    make -j2 2>&1 | tail -20

    echo ""
    if [ -f "_cinderx.so" ]; then
      echo "✅ Instrumented build complete"
      ls -lh _cinderx.so
    else
      echo "❌ Build failed"
      exit 1
    fi

    echo ""
    echo "=== Phase 2: PGO Training ==="
    export PYTHONPATH="/cinderx/build-pgo:$PYTHONPATH"
    export PYTHONJITHUGEPAGES=0

    python3 << "PY"
import sys
print("=== PGO Training ===")
sys.path.insert(0, "/cinderx/build-pgo")

# Import cinderx to trigger JIT
import cinderx

# Warmup
for i in range(100000):
    pass

# Training
def add(a, b): return a + b
for i in range(2000000): add(i, i+1)

total = 0
for i in range(2000000): total += i

data = [i for i in range(200000)]
sum(data)

print("✅ Training complete")
PY

    echo ""
    echo "Checking for profile data..."
    find . -name "*.gcda" | head -10
    GCDA_COUNT=$(find . -name "*.gcda" | wc -l)
    echo "Found $GCDA_COUNT profile data files"

    if [ "$GCDA_COUNT" -eq 0 ]; then
      echo "⚠️  No profile data, but continuing..."
    fi

    echo ""
    echo "=== Phase 3: Rebuilding with PGO ==="

    cd /cinderx/build-pgo
    rm -rf CMakeCache.txt CMakeFiles

    cmake .. \
      -DCMAKE_BUILD_TYPE=Release \
      -DENABLE_LTO=ON \
      -DENABLE_PGO_USE=ON \
      -DPY_VERSION=3.14 \
      -DPython_ROOT_DIR=/usr/local \
      -DCMAKE_C_COMPILER=/usr/bin/gcc \
      -DCMAKE_CXX_COMPILER=/usr/bin/g++ \
      2>&1 | grep -E "PGO|LTO|error" | head -20

    echo ""
    make -j2 clean
    make -j2 2>&1 | tail -20

    echo ""
    echo "=== Building wheel ==="
    cd /cinderx
    python3 -m pip install -q build 2>&1 | grep -v WARNING || true
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
  ls -lh /tmp/cinderx-lto-pgo.whl

  echo ""
  echo "=== Size Comparison ==="
  echo "Baseline: $(ls -lh /tmp/cinderx-baseline.whl 2>/dev/null | awk '{print $5}' || echo "N/A")"
  echo "LTO only: $(ls -lh /tmp/cinderx-lto-optimized.whl 2>/dev/null | awk '{print $5}' || echo "N/A")"
  echo "LTO+PGO:  $(ls -lh /tmp/cinderx-lto-pgo.whl | awk '{print $5}')"
else
  echo "❌ Build failed"
  exit 1
fi
