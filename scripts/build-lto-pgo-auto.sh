#!/bin/bash
# Build CinderX with LTO + PGO using built-in setup.py PGO support
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building CinderX LTO + PGO (Built-in PGO Workflow) ==="
echo "Project: $PROJECT_ROOT"
echo "Time: $(date)"
echo ""

# Clean
rm -rf "$PROJECT_ROOT"/dist/*.whl
rm -rf "$PROJECT_ROOT"/build
rm -rf "$PROJECT_ROOT"/scratch

PROXY_PORT="${PROXY_PORT:-7890}"

echo "Using proxy: host.docker.internal:$PROXY_PORT"
echo ""

# Build using CinderX's built-in PGO workflow
# setup.py will automatically:
# 1. Build instrumented version
# 2. Run profiling workload
# 3. Rebuild with profile data
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
    echo "Python: $(python3 --version)"
    python3 -c "import sys; print(f\"Python path: {sys.executable}\")"
    echo "GCC: $(gcc --version | head -1)"
    echo "LLVM: $(llvm-ar --version 2>&1 | head -1)"
    echo "LTO: Enabled"
    echo "PGO: Enabled (using built-in setup.py workflow)"
    echo ""

    echo "=== Installing Build Dependencies ==="
    apt-get update -qq 2>&1 | tail -3
    apt-get install -y -qq cmake build-essential 2>&1 | tail -3
    python3 -m pip install --upgrade pip setuptools wheel build 2>&1 | grep -v "WARNING: Running pip as" || true
    echo ""

    echo "=== Building with LTO + PGO ==="
    echo "This will run the complete 3-stage PGO workflow:"
    echo "  1. Build instrumented version"
    echo "  2. Run profiling workload"
    echo "  3. Rebuild with profile data"
    echo ""
    echo "Start time: $(date)"
    echo ""

    # Set parallel build
    export CMAKE_BUILD_PARALLEL_LEVEL=2

    # Run setup.py build with PGO enabled
    # This triggers the built-in _run_with_pgo() workflow
    python3 setup.py build 2>&1 | tee /tmp/pgo-build.log | tail -50

    BUILD_EXIT=${PIPESTATUS[0]}

    echo ""
    echo "=== Build Phase Complete ==="
    echo "End time: $(date)"

    if [ $BUILD_EXIT -ne 0 ]; then
      echo "❌ Build failed with exit code: $BUILD_EXIT"
      exit 1
    fi

    echo ""
    echo "=== Building Wheel ==="

    # Clean dist
    rm -rf dist/

    # Build wheel from the optimized build
    python3 -m build --wheel 2>&1 | tee /tmp/wheel-build.log | tail -50

    WHEEL_EXIT=${PIPESTATUS[0]}

    echo ""
    if [ $WHEEL_EXIT -eq 0 ] && ls dist/cinderx-*-linux_aarch64.whl 1>/dev/null 2>&1; then
      echo "✅ LTO + PGO wheel created successfully:"
      ls -lh dist/cinderx-*-linux_aarch64.whl

      # Check if profile data was generated
      echo ""
      echo "=== Profile Data Check ==="
      GCDA_COUNT=$(find scratch -name "*.gcda" 2>/dev/null | wc -l || echo "0")
      echo "Found $GCDA_COUNT .gcda profile data files"

      if [ "$GCDA_COUNT" -gt 0 ]; then
        echo "Sample profile files:"
        find scratch -name "*.gcda" | head -5
      fi
    else
      echo "❌ Wheel build failed"
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
