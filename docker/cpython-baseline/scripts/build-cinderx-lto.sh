#!/bin/bash
# Build CinderX wheel with LTO enabled for ARM64 Linux
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ENABLE_LTO=${ENABLE_LTO:-1}
ENABLE_PGO=${ENABLE_PGO:-0}

echo "=== Building CinderX ARM64 wheel with LTO ==="
echo "Project root: $PROJECT_ROOT"
echo "LTO enabled: $ENABLE_LTO"
echo "PGO enabled: $ENABLE_PGO"
echo ""

# Check if already built
WHEEL_PATTERN="cinderx-*-linux_aarch64.whl"
if ls "$PROJECT_ROOT"/dist/$WHEEL_PATTERN 1> /dev/null 2>&1; then
  echo "Found existing wheel:"
  ls -lh "$PROJECT_ROOT"/dist/$WHEEL_PATTERN
  echo ""

  # In non-interactive mode, automatically rebuild
  if [[ -t 0 ]]; then
    # Interactive mode - ask user
    read -p "Rebuild? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "Using existing wheel"
      exit 0
    fi
  else
    # Non-interactive mode - auto rebuild
    echo "Auto-rebuilding (non-interactive mode)..."
  fi

  # Remove old wheel
  rm -f "$PROJECT_ROOT"/dist/$WHEEL_PATTERN
fi

# Build using Docker
docker run --rm --platform linux/arm64 \
  -v "$PROJECT_ROOT:/cinderx" \
  -w /cinderx \
  -e CINDERX_ENABLE_LTO=$ENABLE_LTO \
  -e CINDERX_ENABLE_PGO=$ENABLE_PGO \
  python:3.14-slim bash -c '
    set -e

    echo "Installing build dependencies..."
    apt-get update -qq > /dev/null 2>&1
    apt-get install -y -qq build-essential cmake git llvm-ar llvm-profdata > /dev/null 2>&1
    pip install --quiet build 2>&1 | grep -v notice

    echo ""
    echo "Building wheel with LTO=$CINDERX_ENABLE_LTO PGO=$CINDERX_ENABLE_PGO..."
    echo "Build configuration:"
    echo "  LTO: $([[ "$CINDERX_ENABLE_LTO" == "1" ]] && echo "Enabled" || echo "Disabled")"
    echo "  PGO: $([[ "$CINDERX_ENABLE_PGO" == "1" ]] && echo "Enabled" || echo "Disabled")"
    echo ""

    # Single-threaded build to avoid OOM on ARM
    export CMAKE_BUILD_PARALLEL_LEVEL=1
    export CINDERX_BUILD_JOBS=1

    # Time the build
    start_time=$(date +%s.%N)
    python -m build --wheel 2>&1 | tail -10
    end_time=$(date +%s.%N)
    duration=$(echo "$end_time - $start_time" | bc)

    echo ""
    echo "✓ Build complete (took ${duration}s):"
    ls -lh dist/cinderx-*-linux_aarch64.whl

    # Verify LTO status if enabled
    if [[ "$CINDERX_ENABLE_LTO" == "1" ]]; then
      echo ""
      echo "Verifying LTO symbols..."
      if command -v nm &> /dev/null; then
        LTO_SYMBOLS=$(nm -C dist/*.whl 2>/dev/null | grep -i "JITRT_" | head -3 || echo "No JITRT symbols found")
        echo "$LTO_SYMBOLS"
      fi
    fi
  '

echo ""
echo "=== Build successful ==="
echo "Wheel: $(ls -1 $PROJECT_ROOT/dist/cinderx-*-linux_aarch64.whl)"
echo ""
echo "To test this wheel:"
echo "  cd docker/cpython-baseline"
echo "  docker compose -p lto-test up -d"
echo "  docker compose -p lto-test exec cpython-benchmark /scripts/test-lto-comparison.sh"
