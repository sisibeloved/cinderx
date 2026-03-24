#!/bin/bash
#
# Run full pyperformance suite for comprehensive validation
#
# This script runs the complete pyperformance benchmark suite
# and generates detailed reports for LTO performance analysis.
#
# Usage:
#   ./docker/arm/scripts/run-full-suite.sh
#   ./docker/arm/scripts/run-full-suite.sh --output results/
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/results"

# Default configuration
ITERATIONS=5
WARMUP=1

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --iterations)
            ITERATIONS="$2"
            shift 2
            ;;
        --warmup)
            WARMUP="$2"
            shift 2
            ;;
        --fast)
            ITERATIONS=1
            WARMUP=0
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --output DIR         Output directory (default: ./results)"
            echo "  --iterations N       Number of iterations (default: 5)"
            echo "  --warmup N           Number of warmup runs (default: 1)"
            echo "  --fast               Quick mode (1 iteration, no warmup)"
            echo "  --help, -h           Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

mkdir -p "${OUTPUT_DIR}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "========================================"
echo "CinderX Full Benchmark Suite"
echo "========================================"
echo "Output directory: ${OUTPUT_DIR}"
echo "Iterations: ${ITERATIONS}"
echo "Warmup: ${WARMUP}"
echo ""

# Verify CinderX is installed and working
echo "Verifying CinderX installation..."
cd "${PROJECT_ROOT}"
python3 -c "import cinderx; print(f'CinderX: {cinderx.is_initialized()}')"
python3 -c "import cinderx; print(f'LTO Enabled: {cinderx.is_lto_enabled()}')"
echo ""

# Run 5-benchmark quick subset first
echo "Running 5-benchmark quick subset..."
python3 "${PROJECT_ROOT}/scripts/bench/run_pyperf_subset.py" \
    --iterations "${ITERATIONS}" \
    --warmup "${WARMUP}" \
    --output "${OUTPUT_DIR}/quick-benchmark-${TIMESTAMP}.json"

echo "Quick subset completed."
echo ""

# Run full pyperformance suite
echo "Running full pyperformance suite..."
echo "This may take 30-60 minutes..."
echo ""

cd "${PROJECT_ROOT}"
python3 -m pyperformance run \
    --python=python3 \
    --output "${OUTPUT_DIR}/pyperformance-full-${TIMESTAMP}.json"

echo ""
echo "Full suite completed."
echo ""

# Generate summary
echo "========================================"
echo "Benchmark Summary"
echo "========================================"
echo ""
echo "Results saved to:"
echo "  Quick: ${OUTPUT_DIR}/quick-benchmark-${TIMESTAMP}.json"
echo "  Full:  ${OUTPUT_DIR}/pyperformance-full-${TIMESTAMP}.json"
echo ""
echo "To compare with baseline:"
echo "  python3 scripts/bench/compare_lto_impact.py \\"
echo "    --baseline ${OUTPUT_DIR}/baseline-quick.json \\"
echo "    --lto ${OUTPUT_DIR}/quick-benchmark-${TIMESTAMP}.json"
echo ""

echo "========================================"
echo "Full Suite: COMPLETED"
echo "========================================"
