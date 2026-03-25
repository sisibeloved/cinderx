#!/usr/bin/env python3
"""Performance validation for CinderX LTO+PGO"""
import time

# Function to test
def add(a, b):
    return a + b

# Warmup JIT
for i in range(10000):
    pass

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
