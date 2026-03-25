#!/usr/bin/env python3
"""Check if CinderX JIT is active and run performance test"""
import sys
import time

# Check CinderX status
try:
    import cinderx
    print(f"✓ CinderX loaded: {cinderx.__file__}")
    try:
        import cinderx.jit
        print(f"✓ CinderX JIT module available")
        cinderx.jit.auto()
        print(f"✓ JIT enabled via cinderx.jit.auto()")
    except Exception as e:
        print(f"✗ JIT not available: {e}")
except ImportError as e:
    print(f"✗ CinderX not loaded: {e}")

print()

# Function to test
def add(a, b):
    return a + b

# Warmup JIT
print("Warming up JIT...")
for i in range(10000):
    add(i, i+1)

print()

# Performance test
print("Running function call performance test (2M iterations)...")
times = []
for run in range(5):
    start = time.time()
    for i in range(2000000):
        add(i, i+1)
    elapsed = time.time() - start
    times.append(elapsed)
    print(f"  Run {run+1}: {elapsed:.3f}s")

median = sorted(times)[2]
print(f"\nMedian time: {median:.3f}s")
