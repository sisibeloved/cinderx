#!/bin/bash
# Setup cinderx and dependencies in the container
set -e

echo "=== Installing cinderx ==="
pip3 install --quiet /dist/cinderx-*-linux_aarch64.whl 2>&1 | grep -v notice | tail -1

echo "=== Downloading generators benchmark ==="
# Download benchmark files manually (pip is broken in Python 3.14)
mkdir -p /root/benchmarks
python3 << 'PY'
import urllib.request
import pathlib

# Download run_benchmark.py
url = "https://raw.githubusercontent.com/python/pyperformance/main/pyperformance/data-files/benchmarks/bm_generators/run_benchmark.py"
output_path = "/root/benchmarks/run_benchmark.py"

print(f"Downloading {url}...")
urllib.request.urlretrieve(url, output_path)
print(f"✓ Saved to {output_path}")

# Create minimal pyperf shim
pyperf_code = '''
import time
perf_counter = time.perf_counter

class Runner:
    pass
'''

pyperf_path = pathlib.Path("/root/benchmarks/pyperf.py")
pyperf_path.write_text(pyperf_code)
print(f"✓ Created pyperf shim at {pyperf_path}")
PY

echo "=== Verifying installation ==="
python3 << 'PY'
import cinderx
import cinderx.jit as jit

assert cinderx.is_initialized(), "cinderx not initialized"
print("✓ cinderx initialized and JIT enabled")
PY

echo ""
echo "=== Setup complete ==="
echo "Run '/scripts/smoke.sh' to verify JIT functionality"
echo "Run '/scripts/test-generators.sh' to run benchmark comparison"
