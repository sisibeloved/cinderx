#!/bin/bash
# Build CinderX wheel with LTO for quick experiments
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ENABLE_LTO=${ENABLE_LTO:-1}

echo "=== Building CinderX ARM64 wheel (quick experiment) ==="
echo "LTO: $([[ "$ENABLE_LTO" == "1" ]] && echo "Enabled" || echo "Disabled")"
echo ""

# Build using Docker
docker run --rm --platform linux/arm64 \
  -v "$PROJECT_ROOT:/cinderx" \
  -w /cinderx \
  -e CINDERX_ENABLE_LTO=$ENABLE_LTO \
  python:3.14-slim bash -c '
    set -e

    echo "Installing dependencies..."
    apt-get update -qq > /dev/null 2>&1
    apt-get install -y -qq build-essential cmake git llvm-ar > /dev/null 2>&1
    pip install --quiet build 2>&1 | grep -v notice

    echo "Building wheel..."
    export CMAKE_BUILD_PARALLEL_LEVEL=1
    export CINDERX_BUILD_JOBS=1
    python -m build --wheel 2>&1 | tail -5

    echo ""
    echo "✓ Done:"
    ls -lh dist/cinderx-*-linux_aarch64.whl
  '

echo ""
echo "=== Build complete ==="
echo "Wheel: $(ls -1 $PROJECT_ROOT/dist/cinderx-*-linux_aarch64.whl)"
echo ""
echo "Next: docker compose -p lto-exp up -d"
