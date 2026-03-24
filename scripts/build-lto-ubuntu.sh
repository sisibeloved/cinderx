#!/bin/bash
# Build CinderX LTO wheel using Ubuntu 24.04 with GCC 14 and proper proxy
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building CinderX LTO wheel (Ubuntu ARM64 with GCC 14) ==="
echo "Project root: $PROJECT_ROOT"
echo "Time: $(date)"
echo ""

# Remove old wheels
rm -f "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl

# Detect proxy port
PROXY_PORT="${PROXY_PORT:-7890}"

echo "Using proxy: host.docker.internal:$PROXY_PORT"
echo ""

# Build using Ubuntu 24.04 with proper proxy
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
  ubuntu:24.04 \
  bash -c '
    set -e

    echo "=== System Information ==="
    cat /etc/os-release | grep -E "^(NAME|VERSION)="
    echo "Kernel: $(uname -r)"
    echo "Arch: $(uname -m)"
    echo ""

    echo "=== Testing Proxy ==="
    export http_proxy https_proxy
    echo "Proxy: $http_proxy"
    if timeout 10 curl -s --proxy "$http_proxy" -I https://www.google.com > /dev/null 2>&1; then
      echo "✅ Proxy working!"
    else
      echo "⚠️  Proxy test failed, trying direct connection..."
      unset http_proxy https_proxy
    fi
    echo ""

    echo "=== Installing System Dependencies ==="
    apt-get update -qq 2>&1 | tail -5
    apt-get install -y -qq \
      build-essential \
      cmake \
      llvm-19 \
      llvm-19-dev \
      llvm-19-tools \
      python3.14 \
      python3.14-dev \
      python3.14-venv \
      2>&1 | tail -10

    echo ""
    echo "=== Compiler Information ==="
    gcc --version | head -1
    g++ --version | head -1
    cmake --version | head -1
    echo ""

    echo "=== Setting up LLVM Tools ==="
    ln -sf /usr/bin/llvm-ar-19 /usr/local/bin/llvm-ar
    ln -sf /usr/bin/llvm-profdata-19 /usr/local/bin/llvm-profdata
    ln -sf /usr/bin/llvm-ranlib-19 /usr/local/bin/llvm-ranlib
    ln -sf /usr/bin/llvm-nm-19 /usr/local/bin/llvm-nm

    echo "llvm-ar: $(which llvm-ar)"
    echo "llvm-profdata: $(which llvm-profdata)"
    echo ""

    echo "=== Installing Python Build Tools ==="
    python3.14 -m pip install --upgrade pip build 2>&1 | grep -v "WARNING: Running pip as" || true
    echo ""

    echo "=== Building CinderX with LTO ==="
    echo "Start time: $(date)"
    echo ""

    export CMAKE_BUILD_PARALLEL_LEVEL=2

    python3.14 -m build --wheel 2>&1 | tail -40

    echo ""
    echo "=== Build Complete ==="
    echo "End time: $(date)"
    echo ""
    ls -lh dist/cinderx-*-linux_aarch64.whl 2>/dev/null || {
      echo "ERROR: Wheel not found!"
      exit 1
    }
  '

echo ""
echo "=== Build Successful ==="
ls -lh "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl
echo ""
echo "Next steps:"
echo "  1. Test: pip install dist/cinderx-*.whl"
echo "  2. Validate: python scripts/bench/validate_lto_performance.py"
