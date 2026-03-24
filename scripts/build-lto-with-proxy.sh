#!/bin/bash
# Build CinderX LTO wheel using existing image with proper proxy
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building CinderX LTO wheel (with proxy) ==="
echo "Project root: $PROJECT_ROOT"
echo "Time: $(date)"
echo ""

# Remove old wheels
rm -f "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl

# Detect Clash proxy port
PROXY_PORT="${PROXY_PORT:-7890}"

echo "Detected Clash proxy: host.docker.internal:$PROXY_PORT"
echo ""

# Build using pre-built image with proper proxy configuration
docker run --rm --platform linux/arm64 \
  --add-host=host.docker.internal:host-gateway \
  -v "$PROJECT_ROOT:/cinderx" \
  -w /cinderx \
  -e CINDERX_ENABLE_LTO=1 \
  -e CINDERX_BUILD_JOBS=2 \
  -e PYTHONJITHUGEPAGES=0 \
  -e http_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e https_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e HTTP_PROXY="http://host.docker.internal:$PROXY_PORT" \
  -e HTTPS_PROXY="http://host.docker.internal:$PROXY_PORT" \
  -e no_proxy="localhost,127.0.0.1,.internal" \
  -e NO_PROXY="localhost,127.0.0.1,.internal" \
  cinderx-cpython-baseline:arm64 \
  bash -c '
    set -e

    echo "=== System Information ==="
    echo "Platform: $(uname -m)"
    echo "Python: $(python3 --version)"
    echo "GCC: $(gcc --version | head -1)"
    echo "LLVM: $(llvm-ar --version 2>&1 | head -1)"
    echo ""

    echo "=== Testing Proxy Connectivity ==="
    echo "Proxy: $http_proxy"
    if curl -s --proxy "$http_proxy" -I https://www.google.com > /dev/null 2>&1; then
      echo "✅ Proxy working!"
    else
      echo "⚠️  Proxy test failed, but continuing..."
    fi
    echo ""

    echo "=== Installing Build Dependencies ==="
    # Try with proxy first, then without if fails
    if ! apt-get update -qq 2>&1 | tail -5; then
      echo "apt-get update failed with proxy, trying without..."
      unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
      apt-get update -qq 2>&1 | tail -5
    fi

    apt-get install -y -qq cmake build-essential 2>&1 | tail -5 || {
      echo "Warning: Some packages may already be installed"
    }

    echo "cmake: $(which cmake)"
    echo "gcc: $(which gcc)"
    echo ""

    echo "=== Installing Python Build Tools ==="
    pip install -q build 2>&1 | grep -v notice || true
    echo ""

    echo "=== Building CinderX with LTO ==="
    echo "Start time: $(date)"
    export CMAKE_BUILD_PARALLEL_LEVEL=2

    python3 -m build --wheel 2>&1 | tail -30

    echo ""
    echo "Build completed at $(date)"
    ls -lh dist/cinderx-*-linux_aarch64.whl
  '

echo ""
echo "=== Build Successful ==="
ls -lh "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl
