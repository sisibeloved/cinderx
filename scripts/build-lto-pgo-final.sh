#!/bin/bash
# Build CinderX LTO + PGO wheel - FINAL VERSION
# Based on successful build-lto-python314.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building CinderX LTO + PGO wheel ==="
echo "Project root: $PROJECT_ROOT"
echo "Time: $(date)"
echo ""

# Remove old wheels
rm -f "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl

# Proxy configuration
PROXY_PORT="${PROXY_PORT:-7890}"

echo "Using proxy: host.docker.internal:$PROXY_PORT"
echo ""

# Build using pre-built image with PGO support
# Phase 1: Instrumented build + data collection + Optimized build
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

    echo "=== System Information ==="
    cat /etc/os-release | grep -E "^(NAME|VERSION)="
    echo "Kernel: $(uname -r)"
    echo "Arch: $(uname -m)"
    echo "Python: $(python3 --version)"
    python3 -c "import sys; print(f\"Python path: {sys.executable}\")"
    echo "GCC: $(gcc --version | head -1)"
    echo "LLVM: $(llvm-ar --version 2>&1 | head -1)"
    echo "LTO: Enabled"
    echo "PGO: Enabled"
    echo ""

    echo "=== Installing Build Dependencies ==="
    for attempt in 1 2 3; do
      echo "Attempt $attempt/3..."

      if [ $attempt -eq 1 ]; then
        apt-get update -qq 2>&1 | tail -3
      else
        unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
        apt-get update -qq 2>&1 | tail -3
      fi

      if apt-get install -y -qq cmake build-essential 2>&1 | tail -5; then
        echo "✓ Dependencies installed successfully"
        break
      else
        if [ $attempt -lt 3 ]; then
          echo "Attempt $attempt failed, retrying in 5 seconds..."
          sleep 5
        else
          echo "⚠️  All attempts failed, but continuing..."
        fi
      fi
    done

    echo ""
    echo "=== Verifying Tools ==="
    echo "cmake: $(which cmake 2>/dev/null || echo "NOT FOUND")"
    echo "gcc: $(which gcc 2>/dev/null || echo "NOT FOUND")"
    echo "llvm-ar: $(which llvm-ar 2>/dev/null || echo "NOT FOUND")"
    echo ""

    echo "=== Installing Python Build Tools ==="
    python3 -m pip install --upgrade pip build 2>&1 | grep -v "WARNING: Running pip as" || true
    echo ""

    echo "=== Phase 1: Building with PGO instrumentation ==="
    echo "Start time: $(date)"
    echo ""

    export CMAKE_BUILD_PARALLEL_LEVEL=2

    # Build instrumented version first
    python3 setup.py build_ext --inplace 2>&1 | grep -E "(Building|error|warning)" | tail -20 || true

    echo ""
    echo "=== Phase 2: Collecting PGO profile data ==="
    export PYTHONPATH="/cinderx:$PYTHONPATH"

    python3 << "PY"
import sys
import time

print("=== PGO Training Start ===")
print("Warming up JIT...")

# Warmup JIT
for i in range(100000):
    pass

print("Training function calls...")
# Function calls (important for inlining)
def compute(a, b, c):
    return a * b + c

for i in range(2000000):
    compute(i, i+1, i+2)

print("Training loops...")
# Loops (important for optimization)
total = 0
for i in range(2000000):
    total += i * 2

print("Training data structures...")
# List operations
data = [i * 2 for i in range(500000)]
sum(data)

# Dict operations
d = {}
for i in range(200000):
    d[str(i)] = i

# String operations
s = ""
for i in range(100000):
    s += str(i)

print("✅ PGO training complete")
PY

    echo ""
    echo "Checking for profile data..."
    GCDA_COUNT=$(find build -name "*.gcda" 2>/dev/null | wc -l || echo "0")
    echo "Found $GCDA_COUNT profile data files"

    if [ "$GCDA_COUNT" -gt 0 ]; then
      echo "Sample files:"
      find build -name "*.gcda" | head -5
    fi

    echo ""
    echo "=== Phase 3: Building optimized wheel ==="
    echo "Time: $(date)"
    echo ""

    # Clean dist
    rm -rf dist/

    # Build optimized wheel
    python3 -m build --wheel 2>&1 | tail -50

    BUILD_EXIT=$?

    echo ""
    echo "=== Build Summary ==="
    echo "End time: $(date)"

    if [ $BUILD_EXIT -ne 0 ]; then
      echo "❌ Build failed with exit code: $BUILD_EXIT"
      exit 1
    fi

    echo ""
    if ls dist/cinderx-*-linux_aarch64.whl 1>/dev/null 2>&1; then
      echo "✅ Wheel created successfully:"
      ls -lh dist/cinderx-*-linux_aarch64.whl
    else
      echo "ERROR: Wheel not found!"
      exit 1
    fi
  '

BUILD_EXIT=$?

if [ $BUILD_EXIT -eq 0 ]; then
  echo ""
  echo "=== Build Successful ==="
  ls -lh "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl

  # Save wheel
  cp "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl /tmp/cinderx-lto-pgo.whl
  echo ""
  echo "✅ Saved to: /tmp/cinderx-lto-pgo.whl"

  # Compare sizes
  echo ""
  echo "=== Size Comparison ==="
  echo "Baseline: $(ls -lh /tmp/cinderx-baseline.whl 2>/dev/null | awk '{print $5}' || echo "N/A")"
  echo "LTO only: $(ls -lh /tmp/cinderx-lto-optimized.whl 2>/dev/null | awk '{print $5}' || echo "N/A")"
  echo "LTO+PGO:  $(ls -lh /tmp/cinderx-lto-pgo.whl | awk '{print $5}')"
else
  echo ""
  echo "❌ Build failed"
  exit 1
fi
