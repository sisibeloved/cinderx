#!/usr/bin/env python3
"""Comprehensive performance test for CinderX LTO+PGO"""
import sys
import time

# Check CinderX status
has_cinderx = False
try:
    import cinderx
    import cinderx.jit
    cinderx.jit.auto()
    has_cinderx = True
    print("✓ CinderX JIT enabled")
except ImportError:
    print("✗ Standard Python (no CinderX)")

print()

# Test functions
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

def compute_complex(a, b, c):
    return (a * b + c) / (a + 1)

# Warmup phase
print("=== Warmup Phase (100K iterations) ===")
warmup_start = time.time()
for i in range(100000):
    compute_complex(i, i+1, i+2)
warmup_elapsed = time.time() - warmup_start
print(f"Warmup completed in {warmup_elapsed:.3f}s")
print()

# Test 1: Simple function calls
print("=== Test 1: Simple Function Calls (2M iterations) ===")
times = []
for run in range(5):
    start = time.time()
    for i in range(2000000):
        compute_complex(i, i+1, i+2)
    elapsed = time.time() - start
    times.append(elapsed)
    print(f"  Run {run+1}: {elapsed:.3f}s")
test1_median = sorted(times)[2]
print(f"Median: {test1_median:.3f}s")
print()

# Test 2: Loops and arithmetic
print("=== Test 2: Loops and Arithmetic (5M iterations) ===")
times = []
for run in range(5):
    start = time.time()
    total = 0
    for i in range(5000000):
        total += i * 2 - 1
    elapsed = time.time() - start
    times.append(elapsed)
    print(f"  Run {run+1}: {elapsed:.3f}s")
test2_median = sorted(times)[2]
print(f"Median: {test2_median:.3f}s")
print()

# Test 3: List comprehensions
print("=== Test 3: List Operations (200K elements) ===")
times = []
for run in range(5):
    start = time.time()
    data = [i * 2 for i in range(200000)]
    result = sum(data)
    elapsed = time.time() - start
    times.append(elapsed)
    print(f"  Run {run+1}: {elapsed:.3f}s")
test3_median = sorted(times)[2]
print(f"Median: {test3_median:.3f}s")
print()

# Summary
print("=" * 50)
print("PERFORMANCE SUMMARY")
print("=" * 50)
print(f"Test 1 (Function Calls): {test1_median:.3f}s")
print(f"Test 2 (Loops):         {test2_median:.3f}s")
print(f"Test 3 (Lists):         {test3_median:.3f}s")
print()
overall = (test1_median + test2_median + test3_median) / 3
print(f"Overall Average:        {overall:.3f}s")
print("=" * 50)
