# Recursive Generator JIT Optimization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate 1.8-1.9x performance regression in JIT-compiled recursive generators (Tree.__iter__ pattern)

**Architecture:** Data-driven optimization - diagnose bottleneck first, then apply targeted fix (frame pooling / yield-from inlining / register allocation), fallback to HIR transformation if needed

**Tech Stack:** Python 3.14, CinderX JIT, C++ (HIR/LIR), Docker ARM64 QEMU

---

## Chunk 1: Diagnostic Phase (Phase 0)

**Working Directory:** `/Users/luchen/Agents-Repo/Claude-Code/cinderx`

### Task 1: Create Diagnostic Infrastructure

**Files:**
- Create: `scripts/diagnostics/benchmark_recursive_generator.py`
- Create: `scripts/diagnostics/` directory if needed

- [ ] **Step 1: Create diagnostic directories**

Run:
```bash
cd /Users/luchen/Agents-Repo/Claude-Code/cinderx
mkdir -p scripts/diagnostics
mkdir -p docs/superpowers/diagnostics
```

Expected: Both directories created successfully

- [ ] **Step 2: Write benchmark harness script**

Create `scripts/diagnostics/benchmark_recursive_generator.py`:

```python
#!/usr/bin/env python3
"""
Benchmark harness for recursive generator performance analysis.
Compares CPython interpreter vs CinderX JIT for Tree.__iter__ pattern.
"""

import sys
import time
import statistics
from pathlib import Path

# Add PythonLib to path for cinderx imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cinderx" / "PythonLib"))

class Node:
    """Tree node with recursive generator iterator."""

    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        if self.left:
            yield from self.left
        yield self.value
        if self.right:
            yield from self.right


class StackNode:
    """Tree node with stack-based (non-recursive) iterator."""

    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        stack = [(self, False, False)]
        while stack:
            node, left_done, right_done = stack.pop()
            if not left_done and node.left:
                stack.append((node, True, False))
                stack.append((node.left, False, False))
            elif not right_done:
                yield node.value
                if node.right:
                    stack.append((node, True, True))
                    stack.append((node.right, False, False))


def build_tree(node_cls, depth):
    """Build balanced binary tree."""
    if depth == 0:
        return None
    mid = 2 ** (depth - 1)
    return node_cls(
        mid,
        build_tree(node_cls, depth - 1),
        build_tree(node_cls, depth - 1)
    )


def traverse(tree):
    """Traverse tree and return sum."""
    s = 0
    for v in tree:
        s += v
    return s


def bench(tree, iterations=10):
    """Benchmark tree traversal."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        traverse(tree)
        times.append(time.perf_counter() - start)
    return statistics.mean(times), statistics.stdev(times)


def main():
    print("=" * 60)
    print("Recursive Generator Performance Diagnostic")
    print("=" * 60)

    depth = 15
    iterations = 15

    # Test 1: Recursive generator (baseline)
    print("\n[1] Recursive Generator (Tree.__iter__)")
    tree1 = build_tree(Node, depth)
    mean, std = bench(tree1, iterations)
    print(f"    Time: {mean*1000:.3f}ms ± {std*1000:.3f}ms")

    # Test 2: Stack-based iterator
    print("\n[2] Stack-Based Iterator (StackNode.__iter__)")
    tree2 = build_tree(StackNode, depth)
    mean2, std2 = bench(tree2, iterations)
    print(f"    Time: {mean2*1000:.3f}ms ± {std2*1000:.3f}ms")
    print(f"    Speedup: {mean/mean2:.2f}x")

    # Test 3: With CinderX JIT (if available)
    try:
        import cinderjit
        cinderjit.enable()

        print("\n[3] CinderX JIT (Recursive Generator)")
        tree3 = build_tree(Node, depth)
        cinderjit.force_compile(Node.__iter__)

        # Warmup
        for _ in range(5):
            traverse(tree3)

        mean3, std3 = bench(tree3, iterations)
        print(f"    Time: {mean3*1000:.3f}ms ± {std3*1000:.3f}ms")
        print(f"    vs baseline: {mean/mean3:.2f}x")
        print(f"    vs stack-based: {mean2/mean3:.2f}x")

        # Compilation info
        print(f"\n    Compiled: {cinderjit.is_jit_compiled(Node.__iter__)}")
        print(f"    Size: {cinderjit.get_compiled_size(Node.__iter__)} bytes")

    except ImportError:
        print("\n[3] CinderX not available, skipping JIT test")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Make script executable**

Run:
```bash
chmod +x scripts/diagnostics/benchmark_recursive_generator.py
```

Expected: No output, permissions updated

- [ ] **Step 4: Test baseline benchmark (without JIT)**

Run:
```bash
python3 scripts/diagnostics/benchmark_recursive_generator.py 2>&1 | tee docs/superpowers/diagnostics/macos-baseline.txt
```

Expected output (approximate - actual values depend on hardware):
```
============================================================
Recursive Generator Performance Diagnostic
============================================================

[1] Recursive Generator (Tree.__iter__)
    Time: 12.000-15.000ms ± 0.100-0.300ms

[2] Stack-Based Iterator (StackNode.__iter__)
    Time: 3.000-5.000ms ± 0.050-0.150ms
    Speedup: 2.8-4.0x

[3] CinderX not available, skipping JIT test
============================================================
```

**Success criteria:**
- Baseline (recursive): 10-16ms range
- Stack-based: 2-6ms range
- Stack-based faster than recursive by 2.5-4.5x

Note: Values outside these ranges may indicate platform differences or performance variations. That's OK for diagnostic purposes - we're looking for relative performance patterns, not absolute numbers.

- [ ] **Step 5: Commit diagnostic harness**

Run:
```bash
git add scripts/diagnostics/benchmark_recursive_generator.py docs/superpowers/diagnostics/
git commit -m "diag: add recursive generator benchmark harness

Baseline comparison for recursive vs stack-based iterators.
Measures performance to identify JIT optimization opportunities."
```

Expected: Git commit created successfully

---

### Task 2: Add Segmented Timing Analysis

**Files:**
- Create: `scripts/diagnostics/profile_generator_phases.py`

- [ ] **Step 1: Write phase profiler script**

Create `scripts/diagnostics/profile_generator_phases.py`:

```python
#!/usr/bin/env python3
"""
Profile individual phases of generator execution to identify bottlenecks.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cinderx" / "PythonLib"))


class ProfiledNode:
    """Node with instrumented __iter__ for phase timing."""

    # Class-level counters for timing
    frame_create_time = 0.0
    yield_from_delegate_time = 0.0
    yield_value_time = 0.0
    frame_cleanup_time = 0.0
    call_count = 0

    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        # Measure frame creation (first time only per call)
        start_frame = time.perf_counter()
        ProfiledNode.call_count += 1
        ProfiledNode.frame_create_time += time.perf_counter() - start_frame

        try:
            # Measure yield-from delegation
            if self.left:
                start_delegate = time.perf_counter()
                for v in self.left:
                    ProfiledNode.yield_from_delegate_time += time.perf_counter() - start_delegate

                    # Measure value yield
                    start_yield = time.perf_counter()
                    yield v
                    ProfiledNode.yield_value_time += time.perf_counter() - start_yield

                    start_delegate = time.perf_counter()

            # Measure yield of own value
            start_yield = time.perf_counter()
            yield self.value
            ProfiledNode.yield_value_time += time.perf_counter() - start_yield

            # Measure yield-from delegation (right)
            if self.right:
                start_delegate = time.perf_counter()
                for v in self.right:
                    ProfiledNode.yield_from_delegate_time += time.perf_counter() - start_delegate

                    start_yield = time.perf_counter()
                    yield v
                    ProfiledNode.yield_value_time += time.perf_counter() - start_yield

                    start_delegate = time.perf_counter()

        finally:
            # Measure cleanup
            start_cleanup = time.perf_counter()
            pass
            ProfiledNode.frame_cleanup_time += time.perf_counter() - start_cleanup

    @classmethod
    def reset_stats(cls):
        cls.frame_create_time = 0.0
        cls.yield_from_delegate_time = 0.0
        cls.yield_value_time = 0.0
        cls.frame_cleanup_time = 0.0
        cls.call_count = 0

    @classmethod
    def print_stats(cls):
        total = (cls.frame_create_time + cls.yield_from_delegate_time +
                 cls.yield_value_time + cls.frame_cleanup_time)

        print(f"\nPhase Timing Breakdown:")
        print(f"  Total measured time: {total*1000:.3f}ms")
        print(f"  Frame creation:      {cls.frame_create_time*1000:.3f}ms ({cls.frame_create_time/total*100:.1f}%)")
        print(f"  Yield-from delegate: {cls.yield_from_delegate_time*1000:.3f}ms ({cls.yield_from_delegate_time/total*100:.1f}%)")
        print(f"  Yield value:         {cls.yield_value_time*1000:.3f}ms ({cls.yield_value_time/total*100:.1f}%)")
        print(f"  Frame cleanup:       {cls.frame_cleanup_time*1000:.3f}ms ({cls.frame_cleanup_time/total*100:.1f}%)")
        print(f"  Call count:          {cls.call_count}")


def build_profiled_tree(depth):
    """Build profiled tree."""
    if depth == 0:
        return None
    mid = 2 ** (depth - 1)
    return ProfiledNode(
        mid,
        build_profiled_tree(depth - 1),
        build_profiled_tree(depth - 1)
    )


def main():
    print("=" * 60)
    print("Generator Phase Profiling")
    print("=" * 60)

    depth = 15

    # Build and traverse profiled tree
    print(f"\nBuilding tree (depth={depth})...")
    tree = build_profiled_tree(depth)

    print("Traversing tree...")
    ProfiledNode.reset_stats()

    s = 0
    for v in tree:
        s += v

    print(f"Sum: {s}")
    ProfiledNode.print_stats()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make executable**

Run:
```bash
chmod +x scripts/diagnostics/profile_generator_phases.py
```

Expected: No output

- [ ] **Step 3: Test phase profiler**

Run:
```bash
python3 scripts/diagnostics/profile_generator_phases.py
```

Expected output:
```
============================================================
Generator Phase Profiling
============================================================

Building tree (depth=15)...
Traversing tree...
Sum: <large number>

Phase Timing Breakdown:
  Total measured time: ~12-14ms
  Frame creation:      ~Xms (X%)
  Yield-from delegate: ~Yms (Y%)
  Yield value:         ~Zms (Z%)
  Frame cleanup:       ~Wms (W%)
  Call count: 2^15 - 1 = 32767

============================================================
```

Note: Percentages will identify the bottleneck phase

- [ ] **Step 4: Commit phase profiler**

Run:
```bash
git add scripts/diagnostics/profile_generator_phases.py
git commit -m "diag: add generator phase profiler

Instruments generator execution to measure time spent in:
- Frame creation
- Yield-from delegation
- Value yielding
- Frame cleanup

Helps identify bottleneck for targeted optimization."
```

Expected: Commit created

---

### Task 3: Verify JIT Execution Path

**Files:**
- Create: `scripts/diagnostics/verify_jit_path.py`

- [ ] **Step 1: Write JIT verification script**

Create `scripts/diagnostics/verify_jit_path.py`:

```python
#!/usr/bin/env python3
"""
Verify that JIT compilation is working correctly for recursive generators.
Check for deoptimizations and compilation status.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cinderx" / "PythonLib"))

class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

    def __iter__(self):
        if self.left:
            yield from self.left
        yield self.value
        if self.right:
            yield from self.right


def build_tree(depth):
    if depth == 0:
        return None
    mid = 2 ** (depth - 1)
    return Node(mid, build_tree(depth - 1), build_tree(depth - 1))


def main():
    print("=" * 60)
    print("JIT Execution Path Verification")
    print("=" * 60)

    try:
        import cinderjit
    except ImportError:
        print("\nERROR: CinderX not available")
        print("Please build and install CinderX first:")
        print("  pip install -e . --no-build-isolation")
        return 1

    print("\n[1] Enabling JIT...")
    cinderjit.enable()
    print("    ✓ JIT enabled")

    print("\n[2] Force compiling Node.__iter__...")
    cinderjit.force_compile(Node.__iter__)
    print("    ✓ Compilation requested")

    print("\n[3] Checking compilation status...")
    is_compiled = cinderjit.is_jit_compiled(Node.__iter__)
    print(f"    Compiled: {is_compiled}")

    if is_compiled:
        size = cinderjit.get_compiled_size(Node.__iter__)
        print(f"    Code size: {size} bytes")
    else:
        print("    ERROR: Function not compiled!")
        return 1

    print("\n[4] Building test tree...")
    tree = build_tree(10)
    print("    ✓ Tree built (depth=10)")

    print("\n[5] Running traversal (should use JIT code)...")
    result = list(tree)
    expected = list(range(1, 2**10))

    if result == expected:
        print("    ✓ Correctness verified")
    else:
        print("    ERROR: Result mismatch!")
        print(f"    Expected {len(expected)} items, got {len(result)}")
        return 1

    print("\n[6] Checking for deoptimizations...")
    # Note: CinderX may not expose deopt count directly, but we check what we can
    print("    (Deopt checking not yet implemented - verify manually with JIT_LOG)")

    print("\n" + "=" * 60)
    print("✓ All checks passed")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Make executable**

Run:
```bash
chmod +x scripts/diagnostics/verify_jit_path.py
```

Expected: No output

- [ ] **Step 3: Test verification script (will fail without CinderX)**

Run:
```bash
python3 scripts/diagnostics/verify_jit_path.py
```

Expected output (before CinderX build):
```
============================================================
JIT Execution Path Verification
============================================================

ERROR: CinderX not available
Please build and install CinderX first:
  pip install -e . --no-build-isolation
```

Note: This is expected - will pass after Task 4

- [ ] **Step 4: Commit verification script**

Run:
```bash
git add scripts/diagnostics/verify_jit_path.py
git commit -m "diag: add JIT execution path verifier

Checks that:
- JIT is enabled and functional
- Node.__iter__ is compiled
- Compiled code produces correct results
- No obvious execution path issues"
```

Expected: Commit created

---

### Task 4: Run Diagnostic Suite in macOS

**Working Directory:** `/Users/luchen/Agents-Repo/Claude-Code/cinderx`

- [ ] **Step 0: Check build prerequisites**

Run:
```bash
gcc-15 --version | head -1
g++-15 --version | head -1
python3 --version
```

Expected:
```
gcc-15 (GCC) 15.x.x
g++-15 (GCC) 15.x.x
Python 3.14.x
```

If commands fail, install GCC 15 first or modify build command to use `clang` instead.

- [ ] **Step 1: Build CinderX locally**

Run:
```bash
cd /Users/luchen/Agents-Repo/Claude-Code/cinderx

ENABLE_STATIC_PYTHON=0 \
ENABLE_ADAPTIVE_STATIC_PYTHON=0 \
ENABLE_LIGHTWEIGHT_FRAMES=0 \
CC=gcc-15 \
CXX=g++-15 \
python3 -m pip install -e . --no-build-isolation
```

Expected:
- Build completes in 2-5 minutes
- Final output: `Successfully installed cinderx-VERSION`
- No build errors

If build takes longer than 5 minutes, check for:
- Missing dependencies (should auto-install)
- Compiler warnings (acceptable, but errors are not)
- Disk space issues

- [ ] **Step 2: Verify JIT is working**

Run:
```bash
python3 scripts/diagnostics/verify_jit_path.py
```

Expected output:
```
============================================================
JIT Execution Path Verification
============================================================

[1] Enabling JIT...
    ✓ JIT enabled

[2] Force compiling Node.__iter__...
    ✓ Compilation requested

[3] Checking compilation status...
    Compiled: True
    Code size: <2000-3000> bytes

[4] Building test tree...
    ✓ Tree built (depth=10)

[5] Running traversal (should use JIT code)...
    ✓ Correctness verified

[6] Checking for deoptimizations...
    (Deopt checking not yet implemented - verify manually with JIT_LOG)

============================================================
✓ All checks passed
============================================================
```

- [ ] **Step 3: Run benchmark with JIT**

Run:
```bash
python3 scripts/diagnostics/benchmark_recursive_generator.py 2>&1 | tee docs/superpowers/diagnostics/macos-jit-baseline.txt
```

Expected output:
```
============================================================
Recursive Generator Performance Diagnostic
============================================================

[1] Recursive Generator (Tree.__iter__)
    Time: ~12-14ms ± 0.2ms

[2] Stack-Based Iterator (StackNode.__iter__)
    Time: ~3-4ms ± 0.1ms
    Speedup: 3.1-3.5x

[3] CinderX JIT (Recursive Generator)
    Time: ~21-23ms ± 0.3ms
    vs baseline: 0.54-0.65x (SLOWER!)
    vs stack-based: 0.17-0.19x

    Compiled: True
    Size: <2000-3000> bytes
============================================================
```

**CRITICAL:** This confirms the 1.8-1.9x regression we're trying to fix!

- [ ] **Step 4: Run phase profiler with JIT**

Run:
```bash
python3 scripts/diagnostics/profile_generator_phases.py 2>&1 | tee docs/superpowers/diagnostics/macos-jit-phases.txt
```

Expected output:
```
============================================================
Generator Phase Profiling
============================================================

Building tree (depth=15)...
Traversing tree...
Sum: <large number>

Phase Timing Breakdown:
  Total measured time: ~21-23ms
  Frame creation:      ~Xms (X%)
  Yield-from delegate: ~Yms (Y%)
  Yield value:         ~Zms (Z%)
  Frame cleanup:       ~Wms (W%)

============================================================
```

**KEY OUTPUT:** The phase with highest % is our optimization target!

- [ ] **Step 5: Create diagnostic report**

Create `docs/superpowers/diagnostics/phase0-report.md`:

```markdown
# Phase 0 Diagnostic Report

**Date**: 2026-03-17
**Platform**: macOS ARM64 (local)

## Summary

[PASTE macos-jit-baseline.txt OUTPUT HERE]

## Phase Timing Analysis

[PASTE macos-jit-phases.txt OUTPUT HERE]

## Bottleneck Identification

Based on profiling results, the primary bottleneck is:

**Phase**: [FRAME CREATION | YIELD-FROM DELEGATION | VALUE YIELDING | FRAME CLEANUP]

**Percentage**: X%

**Root cause hypothesis**:
[Explain why this phase is slow based on the % and expected behavior]

## Next Steps

Optimization strategy selected: **[A | B | C | D]**

- [ ] Strategy A: Frame Pooling (if frame creation/cleanup is bottleneck)
- [ ] Strategy B: Inline Yield-From (if yield-from delegation is bottleneck)
- [ ] Strategy C: Improved Register Allocation (if value yielding is bottleneck)
- [ ] Strategy D: HIR Transformation (if multiple phases or Strategy A-C insufficient)

**Target improvement**: At least 50% (to reach ~10-12ms)

## Docker ARM64 Validation

TODO: Replicate these tests in Docker ARM64 to confirm consistency.
```

- [ ] **Step 6: Commit diagnostic report**

Run:
```bash
git add docs/superpowers/diagnostics/
git commit -m "diag: add Phase 0 diagnostic results (macOS JIT)

Baseline measurements and bottleneck identification for
recursive generator optimization.

Key findings:
- JIT regression: 1.8-1.9x slower than CPython
- Bottleneck phase: [TBD based on results]
- Target: ≤12-14ms (match CPython baseline)"
```

Expected: Commit created

---

## Chunk 1 Complete

**Decision Point:** Based on Phase 0 results, proceed to Chunk 2 with selected optimization strategy.

**Files created in this chunk:**
- `scripts/diagnostics/benchmark_recursive_generator.py`
- `scripts/diagnostics/profile_generator_phases.py`
- `scripts/diagnostics/verify_jit_path.py`
- `docs/superpowers/diagnostics/macos-baseline.txt`
- `docs/superpowers/diagnostics/macos-jit-baseline.txt`
- `docs/superpowers/diagnostics/macos-jit-phases.txt`
- `docs/superpowers/diagnostics/phase0-report.md`

**Next chunk will:**
- Analyze diagnostic results
- Select optimization strategy (A/B/C/D)
- Implement targeted fix
- Verify improvement

---

## Chunk 2: Optimization Implementation (Strategy TBD based on Phase 0 results)

[Will be filled in after Chunk 1 completes and bottleneck is identified]

---

## Chunk 3: Integration and Validation

[Will be filled in after Chunk 2 completes]
