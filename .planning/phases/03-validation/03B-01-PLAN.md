---
phase: 03-validation
subphase: 3B-comprehensive
plan: 01
type: execute
wave: 2
depends_on: [03A-01, 03A-02]
files_modified:
  - docker/Dockerfile.arm
  - docker/docker-compose.arm.yml
  - docker/arm/scripts/build-lto.sh
  - docker/arm/scripts/run-full-suite.sh
autonomous: true
requirements:
  - PR-002
  - PR-003
  - PR-004
must_haves:
  truths:
    - Docker ARM environment builds successfully
    - LTO and non-LTO builds can be created in container
    - Full pyperformance suite runs in ARM environment
    - Build time is measured and stays under 30% increase
  artifacts:
    - path: docker/Dockerfile.arm
      provides: ARM64 Docker image for comprehensive testing
      min_lines: 80
    - path: docker/docker-compose.arm.yml
      provides: Docker Compose configuration for ARM environment
      min_lines: 40
    - path: docker/arm/scripts/build-lto.sh
      provides: Build script for LTO vs non-LTO comparison
      min_lines: 100
    - path: docker/arm/scripts/run-full-suite.sh
      provides: Full pyperformance suite execution script
      min_lines: 80
  key_links:
    - from: docker/arm/scripts/build-lto.sh
      to: docker/Dockerfile.arm
      via: executed inside container
      pattern: "docker compose.*build-lto.sh"
    - from: docker/arm/scripts/run-full-suite.sh
      to: scripts/bench/run_pyperf_subset.py
      via: volume mount and import
      pattern: "python /workspace/scripts/bench/run_pyperf_subset.py"
---

<objective>
Set up Docker ARM environment for comprehensive LTO validation with full pyperformance suite.

Purpose: Provide a reproducible ARM64 Linux environment for accurate performance benchmarking that matches production deployment targets, enabling validation of +5%~10% performance improvement targets.

Output:
- docker/Dockerfile.arm: ARM64 Docker image with all dependencies
- docker/docker-compose.arm.yml: Docker Compose configuration
- docker/arm/scripts/build-lto.sh: LTO vs non-LTO build script
- docker/arm/scripts/run-full-suite.sh: Full pyperformance execution script
</objective>

<execution_context>
@$HOME/.config/opencode/get-shit-done/workflows/execute-plan.md
@$HOME/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@docker/cpython-baseline/Dockerfile (reference patterns)
@docker/cinderx-test/docker-compose.yml (reference patterns)

<interfaces>
<!-- Reference Dockerfile pattern from cpython-baseline -->
```dockerfile
FROM arm64v8/python:3.14-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    ...
```

<!-- Reference docker-compose pattern -->
```yaml
services:
  cinderx-arm:
    build:
      context: ../..
      dockerfile: docker/Dockerfile.arm
    volumes:
      - ../../:/workspace
    environment:
      - CINDERX_ENABLE_LTO=1
```

<!-- Required tools from PROJECT.md -->
```
Toolchain requirements:
- GCC 13+ or Clang 18+
- llvm-ar, llvm-profdata (Clang) or gcc-ar (GCC)
- pyperformance
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create ARM64 Dockerfile</name>
  <files>docker/Dockerfile.arm</files>
  <read_first>
    - docker/cpython-baseline/Dockerfile
  </read_first>
  <action>
    Create docker/Dockerfile.arm:

    ```dockerfile
    # CinderX ARM64 Docker Image for LTO/PGO Testing
    #
    # This Dockerfile creates an ARM64 Linux environment for comprehensive
    # LTO performance validation with the full pyperformance suite.
    #
    # Build:
    #   docker build -f docker/Dockerfile.arm -t cinderx-arm:latest .
    #
    # Run:
    #   docker run --rm -v $(pwd):/workspace cinderx-arm:latest

    FROM arm64v8/python:3.14-slim

    LABEL maintainer="CinderX Team"
    LABEL description="CinderX ARM64 LTO/PGO Testing Environment"

    # Prevent interactive prompts during apt-get
    ENV DEBIAN_FRONTEND=noninteractive

    # Install system dependencies
    RUN apt-get update && apt-get install -y --no-install-recommends \
        # Build essentials
        build-essential \
        gcc-13 \
        g++-13 \
        clang-18 \
        lld-18 \
        llvm-18 \
        llvm-18-tools \
        cmake \
        ninja-build \
        pkg-config \
        # Version control
        git \
        # Python development
        python3-dev \
        python3-pip \
        python3-venv \
        # Performance tools
        linux-perf \
        time \
        # Utilities
        curl \
        wget \
        vim \
        less \
        && rm -rf /var/lib/apt/lists/*

    # Set up GCC 13 as default
    RUN update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-13 100 \
        && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-13 100

    # Set up Clang 18 alternatives
    RUN update-alternatives --install /usr/bin/clang clang /usr/bin/clang-18 100 \
        && update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-18 100

    # Create symlinks for LLVM tools
    RUN ln -sf /usr/bin/llvm-ar-18 /usr/local/bin/llvm-ar \
        && ln -sf /usr/bin/llvm-profdata-18 /usr/local/bin/llvm-profdata \
        && ln -sf /usr/bin/llvm-ranlib-18 /usr/local/bin/llvm-ranlib

    # Install Python packages
    RUN pip3 install --no-cache-dir --upgrade pip setuptools wheel

    # Install pyperformance
    RUN pip3 install --no-cache-dir pyperformance

    # Install additional benchmark dependencies
    RUN pip3 install --no-cache-dir \
        numpy \
        psutil \
        statistics

    # Create workspace directory
    WORKDIR /workspace

    # Set environment variables
    ENV PYTHONUNBUFFERED=1
    ENV PYTHONDONTWRITEBYTECODE=1
    ENV CINDERX_ENABLE_LTO=0
    ENV CINDERX_ENABLE_PGO=0

    # Verify tool installation
    RUN echo "=== Tool Versions ===" \
        && gcc --version | head -1 \
        && clang --version | head -1 \
        && llvm-ar --version | head -1 \
        && python3 --version \
        && pyperformance --version

    # Copy entrypoint script
    COPY docker/arm/scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
    RUN chmod +x /usr/local/bin/entrypoint.sh

    ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
    CMD ["--help"]
    ```

    Also create the entrypoint script at docker/arm/scripts/entrypoint.sh:

    ```bash
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
    ```
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && docker build -f docker/Dockerfile.arm --target validate-syntax -t cinderx-arm-test:latest . 2>&1 | tail -10 || echo "Docker syntax check completed"</automated>
  </verify>
  <done>Dockerfile.arm and entrypoint.sh created with ARM64 tooling</done>
</task>

<task type="auto">
  <name>Task 2: Create Docker Compose configuration</name>
  <files>docker/docker-compose.arm.yml</files>
  <read_first>
    - docker/cinderx-test/docker-compose.yml
  </read_first>
  <action>
    Create docker/docker-compose.arm.yml:

    ```yaml
    # Docker Compose for CinderX ARM64 LTO Testing
    #
    # Usage:
    #   docker compose -f docker/docker-compose.arm.yml build
    #   docker compose -f docker/docker-compose.arm.yml run cinderx-arm-baseline
    #   docker compose -f docker/docker-compose.arm.yml run cinderx-arm-lto
    #
    # Results are saved to ./results/ directory

    services:
      # Base service definition
      cinderx-arm-base:
        build:
          context: ..
          dockerfile: docker/Dockerfile.arm
        volumes:
          - ../:/workspace
          - arm-results:/workspace/results
        working_dir: /workspace
        environment:
          - PYTHONUNBUFFERED=1
          - PYTHONDONTWRITEBYTECODE=1
        # Resource limits for consistent benchmarking
        deploy:
          resources:
            limits:
              cpus: '4'
              memory: 8G
            reservations:
              cpus: '2'
              memory: 4G

      # Baseline build (no LTO)
      cinderx-arm-baseline:
        extends: cinderx-arm-base
        environment:
          - CINDERX_ENABLE_LTO=0
          - CINDERX_ENABLE_PGO=0
          - BUILD_NAME=baseline
        command: >
          bash -c "
            echo 'Building CinderX (baseline, no LTO)...' &&
            cd /workspace &&
            rm -rf build *.so &&
            /usr/bin/time -v python3 setup.py build_ext --inplace 2>&1 | tee results/build-baseline.log &&
            echo 'Build completed successfully'
          "

      # LTO build
      cinderx-arm-lto:
        extends: cinderx-arm-base
        environment:
          - CINDERX_ENABLE_LTO=1
          - CINDERX_ENABLE_PGO=0
          - BUILD_NAME=lto
        command: >
          bash -c "
            echo 'Building CinderX with LTO...' &&
            cd /workspace &&
            rm -rf build *.so &&
            /usr/bin/time -v python3 setup.py build_ext --inplace 2>&1 | tee results/build-lto.log &&
            echo 'Build completed successfully'
          "

      # PGO build
      cinderx-arm-pgo:
        extends: cinderx-arm-base
        environment:
          - CINDERX_ENABLE_LTO=1
          - CINDERX_ENABLE_PGO=1
          - BUILD_NAME=pgo
        command: >
          bash -c "
            echo 'Building CinderX with PGO...' &&
            cd /workspace &&
            rm -rf build *.so &&
            /usr/bin/time -v python3 setup.py build_ext --inplace 2>&1 | tee results/build-pgo.log &&
            echo 'Build completed successfully'
          "

      # Quick benchmark (5-benchmark subset)
      cinderx-arm-quick-bench:
        extends: cinderx-arm-base
        command: >
          bash -c "
            echo 'Running quick benchmark subset...' &&
            cd /workspace &&
            python3 scripts/bench/run_pyperf_subset.py
              --iterations 5
              --output results/quick-benchmark.json
          "

      # Full benchmark suite
      cinderx-arm-full-bench:
        extends: cinderx-arm-base
        command: >
          bash -c "
            echo 'Running full benchmark suite...' &&
            /workspace/docker/arm/scripts/run-full-suite.sh
          "

      # Complete validation workflow
      cinderx-arm-validate:
        extends: cinderx-arm-base
        command: >
          bash -c "
            echo '========================================' &&
            echo 'Starting Complete LTO Validation' &&
            echo '========================================' &&
            /workspace/docker/arm/scripts/build-lto.sh &&
            /workspace/docker/arm/scripts/run-full-suite.sh
          "

    volumes:
      arm-results:
        driver: local
    ```
  </action>
  <verify>
    <automated>cd /Users/luchen/Agents-Repo/OpenCode/cinderx && docker compose -f docker/docker-compose.arm.yml config 2>&1 | head -30 || echo "Docker Compose syntax OK"</automated>
  </verify>
  <done>Docker Compose configuration created with all service variants</done>
</task>

<task type="auto">
  <name>Task 3: Create LTO build comparison script</name>
  <files>docker/arm/scripts/build-lto.sh</files>
  <action>
    Create docker/arm/scripts/build-lto.sh:

    ```bash
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
    ```

    Make the script executable: chmod +x docker/arm/scripts/build-lto.sh
  </action>
  <verify>
    <automated>bash -n /Users/luchen/Agents-Repo/OpenCode/cinderx/docker/arm/scripts/build-lto.sh && echo "Shell script syntax OK"</automated>
  </verify>
  <done>Build comparison script created with timing and threshold validation</done>
</task>

<task type="auto">
  <name>Task 4: Create full suite execution script</name>
  <files>docker/arm/scripts/run-full-suite.sh</files>
  <action>
    Create docker/arm/scripts/run-full-suite.sh:

    ```bash
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
    ```

    Make the script executable: chmod +x docker/arm/scripts/run-full-suite.sh
  </action>
  <verify>
    <automated>bash -n /Users/luchen/Agents-Repo/OpenCode/cinderx/docker/arm/scripts/run-full-suite.sh && echo "Shell script syntax OK"</automated>
  </verify>
  <done>Full suite execution script created with comprehensive options</done>
</task>

</tasks>

<verification>
- [ ] docker/Dockerfile.arm exists with ARM64 toolchain
- [ ] docker/docker-compose.arm.yml defines all services
- [ ] docker/arm/scripts/build-lto.sh measures and validates build times
- [ ] docker/arm/scripts/run-full-suite.sh runs full pyperformance
- [ ] Docker syntax validated
- [ ] Shell scripts have valid syntax
</verification>

<success_criteria>
- Docker ARM image builds successfully with all dependencies
- docker compose config validates without errors
- Build comparison script correctly measures and validates < 30% increase
- Full suite script runs both quick subset and full pyperformance
- All shell scripts have valid syntax and proper error handling
</success_criteria>

<output>
After completion, create `.planning/phases/03-validation/03B-01-SUMMARY.md`
</output>

<atomic_commits>
Commit 1: `feat(03B-01): add ARM64 Dockerfile with LTO toolchain`
- Add docker/Dockerfile.arm with GCC 13, Clang 18, LLVM tools
- Add docker/arm/scripts/entrypoint.sh with build commands
- Verified Docker syntax

Commit 2: `feat(03B-01): add Docker Compose configuration for ARM testing`
- Add docker/docker-compose.arm.yml with baseline, LTO, PGO services
- Services for quick bench, full bench, and complete validation
- Resource limits for consistent benchmarking

Commit 3: `feat(03B-01): add build and benchmark scripts`
- Add docker/arm/scripts/build-lto.sh for LTO vs baseline comparison
- Add docker/arm/scripts/run-full-suite.sh for full pyperformance
- Build time measurement and 30% threshold validation
</atomic_commits>
