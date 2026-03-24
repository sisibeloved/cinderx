#!/bin/bash
#
# Quick validation script for CinderX LTO changes
#
# This script provides a single-command validation that:
# - Runs on macOS (smoke test with graceful degradation)
# - Runs on Linux (full validation where available)
# - Completes in under 10 minutes
# - Provides clear pass/fail output
#
# Usage:
#   ./scripts/bench/quick_validation.sh
#   ./scripts/bench/quick_validation.sh --quick
#   ./scripts/bench/quick_validation.sh --verbose
#

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Default options
QUICK_MODE=""
VERBOSE=""
OUTPUT_DIR="${PROJECT_ROOT}/.benchmark_results"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            QUICK_MODE="--quick"
            shift
            ;;
        --verbose|-v)
            VERBOSE="--verbose"
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --quick         Quick mode: single iteration, faster feedback"
            echo "  --verbose, -v   Enable verbose output"
            echo "  --output-dir    Directory for results (default: .benchmark_results)"
            echo "  --help, -h      Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                      # Standard validation"
            echo "  $0 --quick              # Quick validation (~5 min)"
            echo "  $0 --verbose            # Verbose output"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Create output directory
mkdir -p "${OUTPUT_DIR}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Detect platform
PLATFORM=$(uname -s)
ARCH=$(uname -m)

echo "=============================================="
echo "CinderX LTO Quick Validation"
echo "=============================================="
echo "Platform: ${PLATFORM} (${ARCH})"
echo "Timestamp: ${TIMESTAMP}"
echo "Output: ${OUTPUT_DIR}"
echo ""

# Change to project root
cd "${PROJECT_ROOT}"

# Platform-specific validation
case "${PLATFORM}" in
    Darwin)
        echo -e "${YELLOW}Running macOS Smoke Test${NC}"
        echo "Note: LTO is not supported on macOS."
        echo "Testing graceful degradation and basic functionality."
        echo ""
        
        PYTHON_CMD=$(command -v python3 || command -v python)
        if [[ -z "${PYTHON_CMD}" ]]; then
            echo -e "${RED}Error: Python not found${NC}"
            exit 1
        fi
        
        OUTPUT_FILE="${OUTPUT_DIR}/macos_smoke_${TIMESTAMP}.json"

        # Required for JIT to work on macOS
        export PYTHONJITHUGEPAGES=0

        if "${PYTHON_CMD}" "${SCRIPT_DIR}/macos_smoke_test.py" \
            ${QUICK_MODE} \
            ${VERBOSE} \
            --output "${OUTPUT_FILE}"; then
            echo ""
            echo -e "${GREEN}✅ macOS Smoke Test PASSED${NC}"
            echo "Results saved to: ${OUTPUT_FILE}"
            exit 0
        else
            echo ""
            echo -e "${RED}❌ macOS Smoke Test FAILED${NC}"
            echo "Results saved to: ${OUTPUT_FILE}"
            exit 1
        fi
        ;;
        
    Linux)
        echo -e "${YELLOW}Running Linux Quick Validation${NC}"
        echo "Note: Full LTO validation requires Docker ARM environment."
        echo "Running subset validation only."
        echo ""
        
        PYTHON_CMD=$(command -v python3 || command -v python)
        if [[ -z "${PYTHON_CMD}" ]]; then
            echo -e "${RED}Error: Python not found${NC}"
            exit 1
        fi
        
        # For Linux, we can run a simplified version
        # that doesn't require full Docker setup
        OUTPUT_FILE="${OUTPUT_DIR}/linux_quick_${TIMESTAMP}.json"

        # Required for JIT to work properly
        export PYTHONJITHUGEPAGES=0

        echo "Step 1: Running 5-benchmark subset..."
        if "${PYTHON_CMD}" "${SCRIPT_DIR}/run_pyperf_subset.py" \
            --iterations 3 \
            --output "${OUTPUT_FILE}"; then
            echo ""
            echo -e "${GREEN}✅ Linux Quick Validation PASSED${NC}"
            echo "Results saved to: ${OUTPUT_FILE}"
            echo ""
            echo "Note: For full LTO validation including build time comparison,"
            echo "      use the Docker ARM environment (Phase 3B)."
            exit 0
        else
            echo ""
            echo -e "${RED}❌ Linux Quick Validation FAILED${NC}"
            exit 1
        fi
        ;;
        
    *)
        echo -e "${RED}Error: Unsupported platform: ${PLATFORM}${NC}"
        echo "Supported platforms: Darwin (macOS), Linux"
        exit 1
        ;;
esac
