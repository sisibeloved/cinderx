#!/bin/bash
set -e

echo "========================================"
echo "CinderX ARM64 LTO Testing Environment"
echo "========================================"
echo ""

# Show environment info
echo "Environment:"
echo "  Architecture: $(uname -m)"
echo "  Kernel: $(uname -r)"
echo "  Python: $(python3 --version)"
echo "  GCC: $(gcc --version | head -1)"
echo "  Clang: $(clang --version | head -1)"
echo ""

# Handle command
case "${1:-}" in
    --help|-h|"")
        echo "Usage: docker run cinderx-arm:latest [COMMAND]"
        echo ""
        echo "Commands:"
        echo "  build-baseline    Build CinderX without LTO"
        echo "  build-lto         Build CinderX with LTO enabled"
        echo "  build-pgo         Build CinderX with PGO enabled"
        echo "  test              Run quick validation tests"
        echo "  bench             Run full benchmark suite"
        echo "  shell             Start interactive shell"
        echo "  --help            Show this help message"
        echo ""
        echo "Environment Variables:"
        echo "  CINDERX_ENABLE_LTO=0|1    Enable LTO (default: 0)"
        echo "  CINDERX_ENABLE_PGO=0|1    Enable PGO (default: 0)"
        echo ""
        ;;
    build-baseline)
        echo "Building CinderX (baseline, no LTO)..."
        cd /workspace
        CINDERX_ENABLE_LTO=0 CINDERX_ENABLE_PGO=0 \
            python3 setup.py build_ext --inplace
        ;;
    build-lto)
        echo "Building CinderX with LTO..."
        cd /workspace
        CINDERX_ENABLE_LTO=1 CINDERX_ENABLE_PGO=0 \
            python3 setup.py build_ext --inplace
        ;;
    build-pgo)
        echo "Building CinderX with PGO..."
        cd /workspace
        CINDERX_ENABLE_LTO=1 CINDERX_ENABLE_PGO=1 \
            python3 setup.py build_ext --inplace
        ;;
    test)
        echo "Running quick validation tests..."
        cd /workspace
        python3 -c "import cinderx; print(f'CinderX loaded: {cinderx.is_initialized()}')"
        python3 -m pytest cinderx/PythonLib/test_cinderx/test_lto_regression.py -v || true
        ;;
    bench)
        echo "Running benchmark suite..."
        /workspace/docker/arm/scripts/run-full-suite.sh
        ;;
    shell)
        echo "Starting interactive shell..."
        exec /bin/bash
        ;;
    *)
        echo "Unknown command: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac
