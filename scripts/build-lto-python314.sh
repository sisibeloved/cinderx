#!/bin/bash
# Build CinderX LTO wheel - FINAL VERSION
# Uses cinderx-cpython-baseline:arm64 (Python 3.14) with proper proxy configuration
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building CinderX LTO wheel (Python 3.14 ARM64) ==="
echo "Project root: $PROJECT_ROOT"
echo "Time: $(date)"
echo ""

# Remove old wheels
rm -f "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl

# Proxy configuration for Clash (TUN mode + global mode)
PROXY_PORT="${PROXY_PORT:-7890}"
PROXY_HOST="host.docker.internal"

echo "=== Proxy Configuration ==="
echo "Clash proxy: $PROXY_HOST:$PROXY_PORT"
echo "Note: Requires Clash in TUN mode + global mode"
echo ""

# Build using pre-built image with Python 3.14
docker run --rm --platform linux/arm64 \
  --add-host=host.docker.internal:host-gateway \
  -v "$PROJECT_ROOT:/cinderx" \
  -w /cinderx \
  -e CINDERX_ENABLE_LTO=1 \
  -e CINDERX_BUILD_JOBS=2 \
  -e PYTHONJITHUGEPAGES=0 \
  -e http_proxy="http://$PROXY_HOST:$PROXY_PORT" \
  -e https_proxy="http://$PROXY_HOST:$PROXY_PORT" \
  -e HTTP_PROXY="http://$PROXY_HOST:$PROXY_PORT" \
  -e HTTPS_PROXY="http://$PROXY_HOST:$PROXY_PORT" \
  -e no_proxy="localhost,127.0.0.1,.internal" \
  -e NO_PROXY="localhost,127.0.0.1,.internal" \
  -e DEBIAN_FRONTEND=noninteractive \
  cinderx-cpython-baseline:arm64 \
  bash -c '
    set -ex

    echo "=== System Information ==="
    echo "Platform: $(uname -m)"
    echo "Python: $(python3 --version)"
    python3 -c "import sys; print(f\"Python path: {sys.executable}\")"
    echo "GCC: $(gcc --version 2>/dev/null | head -1 || echo "Not installed")"
    echo "LLVM: $(llvm-ar --version 2>&1 | head -1 || echo "Not found")"
    echo ""

    echo "=== Testing Proxy ==="
    export http_proxy https_proxy
    echo "Proxy: $http_proxy"
    if timeout 10 curl -s -I https://www.google.com > /dev/null 2>&1; then
      echo "✅ Network working (direct or through proxy)"
    else
      echo "⚠️  Network test failed, but continuing..."
    fi
    echo ""

    echo "=== Installing Build Dependencies ==="
    # Try with proxy first, then retry without if it fails
    for attempt in 1 2 3; do
      echo "Attempt $attempt/3..."

      if [ $attempt -eq 1 ]; then
        # First attempt: use proxy
        apt-get update -qq 2>&1 | tail -3
      else
        # Retry without proxy (in case proxy is the problem)
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

    echo "=== Building CinderX with LTO ==="
    echo "Start time: $(date)"
    echo "LTO: Enabled"
    echo "Build jobs: 2"
    echo ""

    export CMAKE_BUILD_PARALLEL_LEVEL=2

    # Build wheel
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
  echo ""
  echo "Next steps:"
  echo "  1. Test: pip install dist/cinderx-*.whl"
  echo "  2. Validate: python scripts/bench/validate_lto_performance.py"
else
  echo ""
  echo "❌ Build failed"
  exit 1
fi
