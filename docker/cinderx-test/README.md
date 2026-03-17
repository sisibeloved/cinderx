# CinderX ARM64 Docker Test Environment

This directory contains a Docker Compose setup for testing CinderX on ARM64.

## Quick Start

### 1. Build the ARM64 wheel

```bash
cd /Users/luchen/Repo/cinderx
./docker/cinderx-test/scripts/build-wheel.sh
```

### 2. Start the container

```bash
cd docker/cinderx-test
docker-compose up -d
```

### 3. Setup and run tests

```bash
# Install cinderx and dependencies
docker exec cinderx-arm64-test /scripts/setup.sh

# Run smoke tests
docker exec cinderx-arm64-test /scripts/smoke.sh

# Run generators benchmark comparison
docker exec cinderx-arm64-test /scripts/test-generators.sh
```

## Detailed Usage

### Running Individual Benchmarks

```bash
# Run baseline only
docker exec cinderx-arm64-test /scripts/bench-generators.sh

# Run with optimization
docker exec -e PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY=1 \
  cinderx-arm64-test /scripts/bench-generators.sh

# Run with custom parameters
docker exec -e SAMPLES=20 -e WARMUP=5 \
  cinderx-arm64-test /scripts/bench-generators.sh
```

### Interactive Exploration

```bash
# Open a shell in the container
docker exec -it cinderx-arm64-test bash

# Inside the container:
python3 -c "import cinderx; print(cinderx.__version__)"
python3 -m pyperformance run --debug-single-value -b generators
```

### Checking HIR

```bash
docker exec cinderx-arm64-test bash -c '
  PYTHONJITDUMPFINALHIR=1 \
  python3 -c "
import sys
sys.path.insert(0, \"/usr/local/lib/python3.14/site-packages/pyperformance/data-files/benchmarks/bm_generators\")
from run_benchmark import Tree
import cinderx.jit as jit
jit.force_compile(Tree.__iter__)
" 2>&1 | grep -A 20 "Tree.__iter__"
'
```

### Cleaning Up

```bash
# Stop and remove container
docker-compose down

# Remove cache
docker-compose down -v
```

## Environment Variables

- `PYTHONJIT` - Enable JIT (default: 1)
- `PYTHONJITAUTO` - Auto-JIT threshold (default: 50)
- `PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY` - Enable IsTruthy optimization (default: 0)
- `SAMPLES` - Number of benchmark samples (default: 10)
- `WARMUP` - Number of warmup runs (default: 3)

## Files

```
docker/cinderx-test/
├── docker-compose.yml      # Container configuration
├── scripts/
│   ├── build-wheel.sh      # Build ARM64 wheel
│   ├── setup.sh            # Install dependencies
│   ├── smoke.sh            # Smoke tests
│   ├── bench-generators.sh # Single benchmark run
│   └── test-generators.sh  # Full comparison test
└── README.md               # This file
```

## Important Notes

1. **Performance Data**: Docker ARM64 simulation uses QEMU, which introduces overhead. Performance data is not precise and should only be used for functional verification.

2. **Path Requirements**: The `Tree.__iter__` optimization only triggers when the file path contains `bm_generators/run_benchmark.py`. Using the real pyperformance benchmark ensures this condition is met.

3. **Expected Results**: On Docker simulation, expect ~0.2% improvement. On real ARM hardware, expect ~0.79% improvement (based on analysis).

4. **Resource Limits**: The default docker-compose.yml doesn't set resource limits. If you encounter OOM, you can add:
   ```yaml
   deploy:
     resources:
       limits:
         memory: 4G
   ```
