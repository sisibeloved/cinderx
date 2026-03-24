#!/bin/bash
# Build CinderX LTO wheel - FINAL VERSION with proper proxy and error handling
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building CinderX LTO wheel (Ubuntu ARM64) ==="
echo "Project root: $PROJECT_ROOT"
echo "Time: $(date)"
echo ""

# Remove old wheels
rm -f "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl

# Detect proxy port
PROXY_PORT="${PROXY_PORT:-7890}"

echo "=== Proxy Configuration ==="
echo "Using proxy: host.docker.internal:$PROXY_PORT"
echo ""

# Build using Ubuntu 24.04
docker run --rm --platform linux/arm64 \
  --add-host=host.docker.internal:host-gateway \
  -v "$PROJECT_ROOT:/cinderx" \
  -w /cinderx \
  -e CINDERX_ENABLE_LTO=1 \
  -e CINDERX_BUILD_JOBS=2 \
  -e PYTHONJITHUGEPAGES=0 \
  ubuntu:24.04 \
  bash -c '
    set -ex

    echo "=== System Information ==="
    cat /etc/os-release | grep -E "^(NAME|VERSION)="
    echo "Kernel: $(uname -r)"
    echo "Arch: $(uname -m)"
    echo ""

    echo "=== Installing System Dependencies ==="
    # Update package list
    apt-get update -qq 2>&1 | tail -3

    # Install build dependencies (with retry logic)
    for i in 1 2 3; do
      echo "Attempt $i/3..."
      if apt-get install -y -qq \
        build-essential \
        cmake \
        llvm-19 \
        llvm-19-dev \
        llvm-19-tools \
        python3 \
        python3-dev \
        python3-pip \
        2>&1 | tail -5; then
        echo "✓ Dependencies installed successfully"
        break
      else
        echo "Attempt $i failed, retrying in 5 seconds..."
        sleep 5
      fi
    done

    echo ""
    echo "=== Compiler Information ==="
    gcc --version | head -1 || echo "GCC not found"
    g++ --version | head -1 || echo "G++ not found"
    cmake --version | head -1 || echo "CMake not found"
    echo ""

    echo "=== Setting up LLVM Tools ==="
    # Create symlinks for LLVM 19 tools
    ln -sf /usr/bin/llvm-ar-19 /usr/local/bin/llvm-ar 2>/dev/null || true
    ln -sf /usr/bin/llvm-profdata-19 /usr/local/bin/llvm-profdata 2>/dev/null || true
    ln -sf /usr/bin/llvm-ranlib-19 /usr/local/bin/llvm-ranlib 2>/dev/null || true

    echo "llvm-ar: $(which llvm-ar 2>/dev/null || echo 'NOT FOUND')"
    echo "llvm-profdata: $(which llvm-profdata 2>/dev/null || echo 'NOT FOUND')"
    echo ""

    echo "=== Installing Python Build Tools ==="
    python3 -m pip install --upgrade pip build 2>&1 | grep -v "WARNING: Running pip as" || true
    echo ""

    echo "=== Building CinderX with LTO ==="
    echo "Start time: $(date)"
    echo ""
    echo "LTO: Enabled"
    echo "Jobs: 2"
    echo ""

    export CMAKE_BUILD_PARALLEL_LEVEL=2

    # Build wheel
    python3 -m build --wheel 2>&1 | tail -50

    BUILD_EXIT_CODE=$?

    echo ""
    echo "=== Build Summary ==="
    echo "End time: $(date)"

    if [ $BUILD_EXIT_CODE -ne 0 ]; then
        echo "❌ Build failed with exit code: $BUILD_EXIT_CODE"
        exit 1
    fi

    echo ""
    ls -lh dist/cinderx-*-linux_aarch64.whl 2>/dev/null || {
      echo "ERROR: Wheel not found!"
      exit 1
    }

    echo ""
    echo "✅ Build successful!"
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
