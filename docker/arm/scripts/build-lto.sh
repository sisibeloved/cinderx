#!/bin/bash
#
# Build LTO vs non-LTO and compare build times
#
# This script builds CinderX twice (baseline and LTO) and measures
# the build time difference to ensure it stays under 30%.
#
# Usage:
#   ./docker/arm/scripts/build-lto.sh
#   ./docker/arm/scripts/build-lto.sh --output results/
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/results"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --output DIR    Output directory for results (default: ./results)"
            echo "  --help, -h      Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

mkdir -p "${OUTPUT_DIR}"

echo "========================================"
echo "CinderX LTO Build Comparison"
echo "========================================"
echo "Output directory: ${OUTPUT_DIR}"
echo ""

# Function to measure build time
measure_build() {
    local name="$1"
    local enable_lto="$2"
    local output_file="$3"

    echo "Building: ${name}"
    echo "  LTO: ${enable_lto}"
    echo "  Output: ${output_file}"

    # Clean previous build
    rm -rf "${PROJECT_ROOT}/build"
    rm -f "${PROJECT_ROOT}"/*.so

    # Set environment
    export CINDERX_ENABLE_LTO="${enable_lto}"
    export CINDERX_ENABLE_PGO=0

    # Measure build time
    local start_time end_time duration
    start_time=$(date +%s.%N)

    if /usr/bin/time -v python3 "${PROJECT_ROOT}/setup.py" build_ext --inplace 2>"${output_file}"; then
        end_time=$(date +%s.%N)
        duration=$(echo "${end_time} - ${start_time}" | bc)
        echo "  Duration: ${duration}s"
        echo "  Status: SUCCESS"
        echo "${duration}"
        return 0
    else
        echo "  Status: FAILED"
        return 1
    fi
}

# Build baseline (no LTO)
echo "Step 1/2: Building baseline (no LTO)"
echo "----------------------------------------"
BASELINE_TIME=$(measure_build "baseline" 0 "${OUTPUT_DIR}/build-baseline.log")
BASELINE_STATUS=$?

if [[ ${BASELINE_STATUS} -ne 0 ]]; then
    echo "ERROR: Baseline build failed"
    exit 1
fi

echo ""
echo "Baseline build time: ${BASELINE_TIME}s"
echo ""

# Save baseline build
cp "${OUTPUT_DIR}/build-baseline.log" "${OUTPUT_DIR}/build-baseline-final.log"

# Build with LTO
echo "Step 2/2: Building with LTO"
echo "----------------------------------------"
LTO_TIME=$(measure_build "LTO" 1 "${OUTPUT_DIR}/build-lto.log")
LTO_STATUS=$?

if [[ ${LTO_STATUS} -ne 0 ]]; then
    echo "ERROR: LTO build failed"
    exit 1
fi

echo ""
echo "LTO build time: ${LTO_TIME}s"
echo ""

# Calculate increase
INCREASE_PCT=$(echo "scale=2; (((${LTO_TIME} / ${BASELINE_TIME}) - 1) * 100)" | bc)

echo "========================================"
echo "Build Time Comparison"
echo "========================================"
echo "Baseline:  ${BASELINE_TIME}s"
echo "LTO:       ${LTO_TIME}s"
echo "Increase:  ${INCREASE_PCT}%"
echo ""

# Create JSON report
cat > "${OUTPUT_DIR}/build-comparison.json" <<EOF
{
  "baseline_build_time_seconds": ${BASELINE_TIME},
  "lto_build_time_seconds": ${LTO_TIME},
  "increase_percentage": ${INCREASE_PCT},
  "threshold_percentage": 30.0,
  "passed": $(echo "${INCREASE_PCT} <= 30.0" | bc -l),
  "timestamp": "$(date -Iseconds)"
}
EOF

# Check threshold
if (( $(echo "${INCREASE_PCT} > 30.0" | bc -l) )); then
    echo "ERROR: Build time increase (${INCREASE_PCT}%) exceeds 30% threshold"
    echo "========================================"
    echo "RESULT: FAILED"
    echo "========================================"
    exit 1
else
    echo "Build time increase is within threshold (≤ 30%)"
    echo "========================================"
    echo "RESULT: PASSED"
    echo "========================================"
fi

echo ""
echo "Results saved to:"
echo "  - ${OUTPUT_DIR}/build-baseline.log"
echo "  - ${OUTPUT_DIR}/build-lto.log"
echo "  - ${OUTPUT_DIR}/build-comparison.json"
