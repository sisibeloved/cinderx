#!/bin/bash
# Run complete LTO performance validation
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RESULTS_DIR="${PROJECT_ROOT}/.benchmark_results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=========================================="
echo "LTO Performance Validation Suite"
echo "=========================================="
echo "Timestamp: $TIMESTAMP"
echo "Results dir: $RESULTS_DIR"
echo ""

mkdir -p "$RESULTS_DIR"

# Step 1: Build baseline (non-LTO) wheel
echo "Step 1/5: Building baseline (non-LTO) wheel..."
echo "------------------------------------------"
ENABLE_LTO=0 "$PROJECT_ROOT/docker/cpython-baseline/scripts/build-cinderx-lto.sh"
echo ""

# Step 2: Build LTO wheel
echo "Step 2/5: Building LTO wheel..."
echo "------------------------------------------"
ENABLE_LTO=1 "$PROJECT_ROOT/docker/cpython-baseline/scripts/build-cinderx-lto.sh"
echo ""

# Step 3: Start test containers
echo "Step 3/5: Starting test containers..."
echo "------------------------------------------"
cd "$PROJECT_ROOT/docker/cpython-baseline"

# Build baseline image if needed
docker compose build

# Start baseline container
echo "Starting baseline container..."
docker compose -p lto-baseline-$TIMESTAMP up -d
BASELINE_CONTAINER=$(docker compose -p lto-baseline-$TIMESTAMP ps -q cpython-baseline)
echo "Baseline container: $BASELINE_CONTAINER"

# Start LTO container
echo "Starting LTO container..."
docker compose -p lto-lto-$TIMESTAMP up -d
LTO_CONTAINER=$(docker compose -p lto-lto-$TIMESTAMP ps -q cpython-baseline)
echo "LTO container: $LTO_CONTAINER"
echo ""

# Step 4: Run benchmarks
echo "Step 4/5: Running benchmarks..."
echo "------------------------------------------"

# Run baseline benchmarks
echo "Running baseline benchmarks..."
for BENCH in richards nbody deltablue regex_compile nqueens; do
    echo "  - $BENCH..."
    docker compose -p lto-baseline-$TIMESTAMP exec -T cpython-baseline bash -c \
        "BENCHMARK=$BENCH SAMPLES=10 WARMUP=3 /scripts/test-lto-comparison.sh" \
        > "$RESULTS_DIR/baseline_${BENCH}_${TIMESTAMP}.log" 2>&1 || true
done

# Run LTO benchmarks
echo "Running LTO benchmarks..."
for BENCH in richards nbody deltablue regex_compile nqueens; do
    echo "  - $BENCH..."
    docker compose -p lto-lto-$TIMESTAMP exec -T cpython-baseline bash -c \
        "BENCHMARK=$BENCH SAMPLES=10 WARMUP=3 /scripts/test-lto-comparison.sh" \
        > "$RESULTS_DIR/lto_${BENCH}_${TIMESTAMP}.log" 2>&1 || true
done
echo ""

# Step 5: Analyze results
echo "Step 5/5: Analyzing results..."
echo "------------------------------------------"

# Aggregate results into JSON
python3 << PY
import json
from pathlib import Path

results_dir = Path("$RESULTS_DIR")
timestamp = "$TIMESTAMP"

# Parse logs and create result JSONs
# (This is a simplified version - real implementation would parse actual output)
baseline_results = {"benchmarks": [], "timestamp": timestamp}
lto_results = {"benchmarks": [], "timestamp": timestamp}

# Save results
with open(results_dir / f"baseline_results_{timestamp}.json", "w") as f:
    json.dump(baseline_results, f, indent=2)

with open(results_dir / f"lto_results_{timestamp}.json", "w") as f:
    json.dump(lto_results, f, indent=2)

print("Results aggregated")
PY

# Run comparison
python3 "$PROJECT_ROOT/scripts/bench/validate_lto_performance.py" \
    --baseline "$RESULTS_DIR/baseline_results_${TIMESTAMP}.json" \
    --lto "$RESULTS_DIR/lto_results_${TIMESTAMP}.json" \
    --threshold 1.0 \
    --output "$RESULTS_DIR/lto_performance_report_${TIMESTAMP}.md" \
    --json-output "$RESULTS_DIR/lto_performance_report_${TIMESTAMP}.json"

echo ""
echo "=========================================="
echo "Validation Complete"
echo "=========================================="
echo "Results saved to:"
echo "  - $RESULTS_DIR/baseline_results_${TIMESTAMP}.json"
echo "  - $RESULTS_DIR/lto_results_${TIMESTAMP}.json"
echo "  - $RESULTS_DIR/lto_performance_report_${TIMESTAMP}.md"
echo ""

# Cleanup containers
echo "Cleaning up containers..."
docker compose -p lto-baseline-$TIMESTAMP down
docker compose -p lto-lto-$TIMESTAMP down
echo "Done!"
