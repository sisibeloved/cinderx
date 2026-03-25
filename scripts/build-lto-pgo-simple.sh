#!/bin/bash
# Build CinderX with LTO + PGO (simplified version)
# Two-phase build:
# Phase 1: Generate profile data
# Phase 2: Use profile data for optimization
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="/tmp/cinderx-pgo-build"

echo "=== CinderX LTO + PGO Build ==="
echo "Project: $PROJECT_ROOT"
echo "Time: $(date)"
echo ""

# Clean
rm -rf "$PROJECT_ROOT"/dist/*.whl
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

PROXY_PORT="${PROXY_PORT:-7890}"

# ============================================================================
# Phase 1: Build with PGO instrumentation
# ============================================================================

echo "=== Phase 1: Building instrumented version ==="
echo "This will collect profiling data during benchmark runs"
echo ""

docker run --rm --platform linux/arm64 \
  --add-host=host.docker.internal:host-gateway \
  -v "$PROJECT_ROOT:/cinderx" \
  -v "$BUILD_DIR:/pgo-data" \
  -w /cinderx \
  -e CINDERX_ENABLE_LTO=1 \
  -e CINDERX_BUILD_JOBS=2 \
  -e http_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e https_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e no_proxy="localhost,127.0.0.1,.internal" \
  -e DEBIAN_FRONTEND=noninteractive \
  cinderx-cpython-baseline:arm64 \
  bash -c '
    set -ex

    echo "System: $(uname -m), Python: $(python3 --version)"
    echo "GCC: $(gcc --version | head -1)"
    echo ""

    # Install dependencies
    apt-get update -qq
    apt-get install -y -qq cmake build-essential 2>&1 | tail -3
    python3 -m pip install -q build 2>&1 | grep -v WARNING || true

    echo ""
    echo "=== Building instrumented version ==="

    # Configure with PGO generate
    mkdir -p build
    cd build
    cmake .. \
      -DCMAKE_BUILD_TYPE=Release \
      -DENABLE_LTO=ON \
      -DENABLE_PGO_GENERATE=ON \
      -DCMAKE_C_COMPILER=/usr/bin/gcc \
      -DCMAKE_CXX_COMPILER=/usr/bin/g++ \
      -DPY_VERSION=3.14 \
      -DPython_ROOT_DIR=/usr/local \
      2>&1 | tail -20

    echo ""
    echo "=== Compiling (this may take a while) ==="
    make -j2 2>&1 | tail -10

    echo ""
    echo "✅ Instrumented build complete"
    ls -lh lib/_cinderx.so || echo "No .so file yet"
  '

echo ""
echo "✅ Phase 1 complete: Instrumented version built"
echo ""

# ============================================================================
# Phase 2: Collect profile data
# ============================================================================

echo "=== Phase 2: Collecting profile data ==="
echo "Running benchmarks to generate PGO profile..."
echo ""

docker run --rm --platform linux/arm64 \
  --add-host=host.docker.internal:host-gateway \
  -v "$PROJECT_ROOT:/cinderx" \
  -v "$BUILD_DIR:/pgo-data" \
  -w /cinderx \
  -e PYTHONPATH="/cinderx/build/lib:$PYTHONPATH" \
  -e PYTHONJITHUGEPAGES=0 \
  -e http_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e https_proxy="http://host.docker.internal:$PROXY_PORT" \
  cinderx-cpython-baseline:arm64 \
  bash -c '
    set -ex

    echo "Running PGO training benchmarks..."
    echo ""

    # Training workload
    python3 << "PY"
import sys
import time

print("=== PGO Training Start ===")
print("Warming up JIT...")

# Warmup JIT
for i in range(100000):
    pass

print("Training function calls...")
# Training 1: Function calls (important for inlining)
def compute(a, b, c):
    return a * b + c

for i in range(2000000):
    compute(i, i+1, i+2)

print("Training loops...")
# Training 2: Loops (important for vectorization)
total = 0
for i in range(2000000):
    total += i * 2

print("Training data structures...")
# Training 3: List operations
data = [i * 2 for i in range(500000)]
total = sum(data)

# Training 4: Dict operations
d = {}
for i in range(200000):
    d[str(i)] = i
    _ = d.get(str(i))

# Training 5: String operations
s = ""
for i in range(50000):
    s += str(i)

# Training 6: Class operations
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def distance(self):
        return (self.x ** 2 + self.y ** 2) ** 0.5

points = [Point(i, i+1) for i in range(100000)]
distances = [p.distance() for p in points]

print("✅ PGO training complete")
PY

    echo ""
    echo "=== Checking for profile data ==="
    # GCC stores .gcda files in the build directory
    find build -name "*.gcda" | head -10
    echo ""

    # Count profile data files
    GCDA_COUNT=$(find build -name "*.gcda" | wc -l)
    echo "✅ Found $GCDA_COUNT profile data files"

    if [ "$GCDA_COUNT" -eq 0 ]; then
      echo "⚠️  No profile data generated, but continuing..."
    fi
  '

echo ""
echo "✅ Phase 2 complete: Profile data collected"
echo ""

# ============================================================================
# Phase 3: Build optimized version with profile data
# ============================================================================

echo "=== Phase 3: Building optimized version with PGO data ==="
echo ""

docker run --rm --platform linux/arm64 \
  --add-host=host.docker.internal:host-gateway \
  -v "$PROJECT_ROOT:/cinderx" \
  -v "$BUILD_DIR:/pgo-data" \
  -w /cinderx \
  -e CINDERX_ENABLE_LTO=1 \
  -e CINDERX_BUILD_JOBS=2 \
  -e http_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e https_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e no_proxy="localhost,127.0.0.1,.internal" \
  -e DEBIAN_FRONTEND=noninteractive \
  cinderx-cpython-baseline:arm64 \
  bash -c '
    set -ex

    echo "=== Rebuilding with PGO optimization ==="

    # Check for profile data
    GCDA_COUNT=$(find build -name "*.gcda" | wc -l)
    echo "Using $GCDA_COUNT profile data files"

    # Reconfigure with PGO use
    cd build
    cmake .. \
      -DCMAKE_BUILD_TYPE=Release \
      -DENABLE_LTO=ON \
      -DENABLE_PGO_USE=ON \
      -DCMAKE_C_COMPILER=/usr/bin/gcc \
      -DCMAKE_CXX_COMPILER=/usr/bin/g++ \
      -DPY_VERSION=3.14 \
      -DPython_ROOT_DIR=/usr/local \
      2>&1 | tail -20

    echo ""
    echo "=== Rebuilding with profile data ==="
    make -j2 clean
    make -j2 2>&1 | tail -10

    echo ""
    echo "=== Building wheel ==="
    cd /cinderx
    rm -rf dist/
    python3 -m build --wheel 2>&1 | tail -30

    echo ""
    if ls dist/*.whl 2>/dev/null; then
      echo "✅ PGO-optimized wheel created:"
      ls -lh dist/*.whl
    else
      echo "❌ No wheel found"
      exit 1
    fi
  '

BUILD_EXIT=$?

if [ $BUILD_EXIT -eq 0 ]; then
  echo ""
  echo "=== Build Successful ==="
  ls -lh "$PROJECT_ROOT"/dist/*.whl

  # Save wheel
  cp "$PROJECT_ROOT"/dist/*.whl /tmp/cinderx-lto-pgo.whl
  echo ""
  echo "✅ Saved to: /tmp/cinderx-lto-pgo.whl"
  ls -lh /tmp/cinderx-lto-pgo.whl

  echo ""
  echo "=== Size Comparison ==="
  echo "Baseline: $(ls -lh /tmp/cinderx-baseline.whl | awk '{print $5}')"
  echo "LTO only: $(ls -lh /tmp/cinderx-lto-optimized.whl | awk '{print $5}')"
  echo "LTO+PGO:  $(ls -lh /tmp/cinderx-lto-pgo.whl | awk '{print $5}')"
else
  echo ""
  echo "❌ Build failed"
  exit 1
fi
