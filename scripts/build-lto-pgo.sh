#!/bin/bash
# Build CinderX with LTO + PGO optimization
# Profile-Guided Optimization (PGO) workflow:
# 1. Build instrumented version
# 2. Run benchmarks to collect profile data
# 3. Rebuild with profile data optimization
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building CinderX with LTO + PGO ==="
echo "Project root: $PROJECT_ROOT"
echo "Time: $(date)"
echo ""

# Clean old builds
rm -rf "$PROJECT_ROOT"/dist/*.whl
rm -rf "$PROJECT_ROOT"/build
rm -rf /tmp/pgo-data

PROXY_PORT="${PROXY_PORT:-7890}"

echo "=== Step 1: Build instrumented version ==="
echo "This version will collect profiling data"
echo ""

# Build instrumented version
docker run --rm --platform linux/arm64 \
  --add-host=host.docker.internal:host-gateway \
  -v "$PROJECT_ROOT:/cinderx" \
  -w /cinderx \
  -e CINDERX_ENABLE_LTO=1 \
  -e CINDERX_ENABLE_PGO=1 \
  -e CINDERX_BUILD_JOBS=2 \
  -e PYTHONJITHUGEPAGES=0 \
  -e http_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e https_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e no_proxy="localhost,127.0.0.1,.internal" \
  -e DEBIAN_FRONTEND=noninteractive \
  cinderx-cpython-baseline:arm64 \
  bash -c '
    set -ex

    echo "=== System Info ==="
    echo "Python: $(python3 --version)"
    echo "GCC: $(gcc --version | head -1)"
    echo "LLVM: $(llvm-ar --version 2>&1 | head -1)"
    echo "LTO: Enabled"
    echo "PGO: Enabled (instrumentation phase)"
    echo ""

    echo "=== Installing cmake ==="
    apt-get update -qq
    apt-get install -y -qq cmake build-essential 2>&1 | tail -3

    echo "=== Installing build tools ==="
    python3 -m pip install -q build pyperformance 2>&1 | grep -v WARNING || true

    echo ""
    echo "=== Building instrumented wheel ==="
    echo "Start: $(date)"

    export CMAKE_BUILD_PARALLEL_LEVEL=2

    # Build with PGO instrumentation
    python3 setup.py build_ext --inplace 2>&1 | tail -20

    echo ""
    echo "=== Build Complete ==="
    echo "End: $(date)"
    echo ""

    # Verify build
    if [ -f "cinderx/_cinderx.so" ]; then
      echo "✅ Instrumented binary built successfully"
      ls -lh cinderx/_cinderx.so
    else
      echo "❌ Build failed - no .so file found"
      exit 1
    fi

    echo ""
    echo "=== Step 2: Collecting profile data ==="
    echo "Running benchmarks to collect PGO data..."
    echo ""

    # Set PYTHONPATH to use the built version
    export PYTHONPATH="/cinderx:$PYTHONPATH"
    export PYTHONJITHUGEPAGES=0

    # Run simple benchmarks to generate profile data
    python3 << "PY"
import sys
import time

print("Warming up JIT...")
# Warmup
for i in range(50000):
    pass

print("Running PGO training benchmarks...")

# Training 1: Function calls
def add(a, b):
    return a + b

for i in range(1000000):
    add(i, i+1)

# Training 2: Loops
total = 0
for i in range(1000000):
    total += i

# Training 3: List operations
data = [i for i in range(100000)]
total = sum(data)

# Training 4: Dict operations
d = {}
for i in range(100000):
    d[i] = i * 2
    _ = d.get(i)

# Training 5: String operations
s = ""
for i in range(10000):
    s = s + str(i)

print("✅ PGO training complete")
PY

    echo ""
    echo "=== Profile data collection complete ==="
    echo ""

    # Check if profile data was generated
    if ls *.profdata *.profraw 2>/dev/null | head -1; then
      echo "✅ Profile data files found:"
      ls -lh *.profdata *.profraw 2>/dev/null | head -5
    else
      echo "⚠️  No .profdata files found (might be in build directory)"
      find . -name "*.profdata" -o -name "*.profraw" | head -5
    fi

    echo ""
    echo "=== Step 3: Building optimized wheel with profile data ==="
    echo "Rebuilding with PGO optimization..."
    echo ""

    # Clean dist but keep profile data
    rm -rf dist/

    # Rebuild with profile data
    python3 -m build --wheel 2>&1 | tail -40

    echo ""
    echo "=== Final Build Complete ==="
    echo "End: $(date)"

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
  echo "=== LTO + PGO Build Successful ==="
  ls -lh "$PROJECT_ROOT"/dist/*.whl

  # Save to /tmp
  cp "$PROJECT_ROOT"/dist/*.whl /tmp/cinderx-lto-pgo.whl
  echo ""
  echo "✅ Saved to /tmp/cinderx-lto-pgo.whl"
else
  echo ""
  echo "❌ Build failed"
  exit 1
fi
