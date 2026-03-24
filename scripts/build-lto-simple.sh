#!/bin/bash
# Build CinderX LTO wheel using pre-built Docker image
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building CinderX LTO wheel (using pre-built image) ==="
echo "Project root: $PROJECT_ROOT"
echo "Time: $(date)"
echo ""

# Remove old wheels
rm -f "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl

# Build using pre-built image
docker run --rm --platform linux/arm64 \
  -v "$PROJECT_ROOT:/cinderx" \
  -w /cinderx \
  -e CINDERX_ENABLE_LTO=1 \
  -e CINDERX_BUILD_JOBS=1 \
  -e PYTHONJITHUGEPAGES=0 \
  cinderx-cpython-baseline:arm64 \
  bash -c '
    set -e

    echo "Platform: $(uname -m)"
    echo "Python: $(python3 --version)"
    echo "LLVM: $(llvm-ar --version 2>&1 | head -1)"
    echo ""

    # Install build dependencies if needed
    echo "Installing build dependencies..."
    apt-get update -qq && apt-get install -y -qq cmake build-essential > /dev/null 2>&1 || {
      echo "Warning: apt-get failed, trying without update..."
      apt-get install -y cmake build-essential 2>&1 | tail -5
    }
    pip install -q build 2>&1 | grep -v notice || true

    echo "Building wheel with LTO..."
    export CMAKE_BUILD_PARALLEL_LEVEL=1

    start=$(date +%s)
    python -m build --wheel 2>&1 | tail -20
    end=$(date +%s)

    echo ""
    echo "Build duration: $((end - start)) seconds"
    echo ""
    ls -lh dist/cinderx-*-linux_aarch64.whl
  '

echo ""
echo "=== Build complete ==="
ls -lh "$PROJECT_ROOT"/dist/cinderx-*-linux_aarch64.whl
