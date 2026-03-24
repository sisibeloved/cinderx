#!/bin/bash
# Build CinderX LTO wheel using openEuler with proper proxy configuration
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building CinderX LTO wheel (openEuler ARM64) ==="
echo "Project root: $PROJECT_ROOT"
echo "Time: $(date)"
echo ""

# Remove old wheels
rm -f "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl

# Detect proxy port from Clash config
PROXY_PORT="${PROXY_PORT:-7890}"

echo "Using proxy: host.docker.internal:$PROXY_PORT"
echo ""

# Build using openEuler with proper proxy
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
  openeuler/openeuler:24.03-lts-sp1 \
  bash -c '
    set -e

    echo "=== System Information ==="
    cat /etc/os-release | grep -E "^(NAME|VERSION)="
    echo "Kernel: $(uname -r)"
    echo "Arch: $(uname -m)"
    echo ""

    echo "=== Installing Dependencies ==="
    # openEuler uses dnf (like Fedora/RHEL)
    dnf install -y \
      python3.14 \
      python3.14-devel \
      python3.14-pip \
      cmake \
      make \
      llvm \
      llvm-devel \
      git \
      which \
      2>&1 | tail -10

    echo ""
    echo "=== Verifying LLVM Tools ==="
    which llvm-ar || echo "llvm-ar not found, creating symlink..."
    if [ ! -f /usr/bin/llvm-ar ]; then
      # Find and link LLVM tools
      LLVM_VER=$(ls /usr/lib64/llvm* | head -1 | grep -oP "llvm-\K[0-9]+" || echo "")
      if [ -n "$LLVM_VER" ]; then
        ln -sf /usr/bin/llvm-ar-$LLVM_VER /usr/local/bin/llvm-ar
        ln -sf /usr/bin/llvm-profdata-$LLVM_VER /usr/local/bin/llvm-profdata
        ln -sf /usr/bin/llvm-ranlib-$LLVM_VER /usr/local/bin/llvm-ranlib
      else
        # Use generic paths
        ln -sf /usr/lib64/llvm/bin/llvm-ar /usr/local/bin/llvm-ar
        ln -sf /usr/lib64/llvm/bin/llvm-profdata /usr/local/bin/llvm-profdata
        ln -sf /usr/lib64/llvm/bin/llvm-ranlib /usr/local/bin/llvm-ranlib
      fi
    fi

    echo "llvm-ar: $(which llvm-ar 2>/dev/null || echo 'NOT FOUND')"
    echo "llvm-profdata: $(which llvm-profdata 2>/dev/null || echo 'NOT FOUND')"
    echo ""

    echo "=== Installing Python Build Tools ==="
    python3.14 -m pip install --upgrade pip build 2>&1 | grep -v "WARNING: Running pip as" || true
    echo ""

    echo "=== Building CinderX with LTO ==="
    echo "LTO: Enabled"
    echo "Jobs: $CINDERX_BUILD_JOBS"
    echo "Start time: $(date)"
    echo ""

    export CMAKE_BUILD_PARALLEL_LEVEL=$CINDERX_BUILD_JOBS

    # Build wheel
    python3.14 -m build --wheel 2>&1 | tail -30

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
echo "  1. Test wheel: pip install dist/cinderx-*.whl"
echo "  2. Run validation: python scripts/bench/validate_lto_performance.py"
