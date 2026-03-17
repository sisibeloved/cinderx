# Recursive Generator JIT Optimization Design

**Date**: 2026-03-17
**Status**: Draft
**Author**: Claude Code (based on brainstorming session)

## 1. Problem Statement

### Current Situation

JIT-compiling recursive generators with `yield from` causes a 1.8-1.9x performance regression compared to CPython interpreter:

- **CPython baseline (ARM hardware)**: ~29.8ms
- **CinderX JIT (ARM hardware)**: ~57.2ms (1.92x slower)
- **Docker ARM64 QEMU**: ~35.7ms (CPython) vs ~67.5ms (CinderX JIT, 1.89x slower)

This regression is specific to recursive generators. Non-recursive generators and stack-based iterators perform well:
- Simple generators: JIT ~same as CPython
- Stack-based iterators (non-recursive): JIT 3.1x faster than CPython

### Root Cause Hypothesis

The regression appears to be caused by inefficient code generation for recursive generator patterns, specifically:
- Generator frame creation/destruction overhead
- Yield-from state machine implementation
- Suboptimal memory access patterns or register allocation

## 2. Optimization Goal

### Primary Objective

Eliminate the 1.8-1.9x performance regression and restore JIT-compiled recursive generators to at least CPython interpreter baseline performance.

### Quantitative Targets

| Metric | Current | Target |
|--------|---------|--------|
| CPython baseline (Docker ARM64) | ~35.7ms | N/A |
| CinderX JIT (Docker ARM64) | ~67.5ms | **≤35.7ms** |
| Slowdown factor | 1.89x | **≤1.0x** |

### Constraints

1. **No performance regression for other code**: Non-recursive generators, normal functions, and other JIT-compiled code must not slow down
2. **Pass existing tests**: Must pass all CinderX test suites (test_jit*.py, test_cinderx.py, etc.)
3. **ARM Docker validation**: Must validate with pyperformance generators benchmark in ARM Docker container

### Optimization Scope

- **Phase 1**: Optimize `Tree.__iter__` pattern specifically (recursive + yield from on self attributes)
- **Future**: Consider generalization to similar patterns based on learnings

## 3. Diagnostic Phase (Phase 0)

### 3.1 macOS Local Validation (Fast Iteration)

**Objective**: Locate performance bottleneck quickly with easy iteration

**Checkpoint 1: JIT Execution Path Verification**
```python
import cinderx.jit as jit
jit.enable()
jit.force_compile(Node.__iter__)

# Verify compilation succeeded
assert jit.is_jit_compiled(Node.__iter__)
print(f"Compiled size: {jit.get_compiled_size(Node.__iter__)}")

# Run and check for deopt
tree = build_tree(15)
for _ in tree:
    pass

# Check deopt count (should be 0 or very small)
```

**Checkpoint 2: Segmented Timing**
Insert timing points in `Node.__iter__` to measure:
- Frame creation time
- Yield-from delegation time
- Value yield time
- Frame cleanup time

**Checkpoint 3: Baseline Comparison**
Compare three implementations:
- Simple generator (known to have normal JIT performance)
- Recursive generator (currently slow)
- Stack-based iterator (known to be 3.1x faster)

### 3.2 Docker ARM64 Validation

Replicate macOS findings in Docker ARM64 QEMU environment to confirm bottleneck consistency.

**Output**: Performance bottleneck identification report pinpointing which stage consumes the most time.

## 4. Optimization Phase (Based on Diagnostic Results)

### 4.1 If Bottleneck is Generator Frame Creation/Destruction

**Optimization Strategy A: Frame Pooling**

**Mechanism**:
- Reuse frame objects for recursive generators
- Mark recursive generators in HIR and generate fast path
- Create frame only once, reuse on subsequent yield/resume

**Implementation Locations**:
- `cinderx/Jit/hir/builder.cpp` - Mark recursive patterns during HIR construction
- `cinderx/Jit/generators_*.cpp` - Add frame pooling logic
- `cinderx/Jit/lir/generator.cpp` - Generate fast path code

**Expected Improvement**: 30-50%

### 4.2 If Bottleneck is Yield-From State Machine

**Optimization Strategy B: Inline Yield-From**

**Mechanism**:
- Detect `yield from self.left` pattern
- Generate inline state transition code to avoid function call overhead
- Similar to CPython's `SEND` + `YIELD_FROM` fast path

**Implementation Locations**:
- `cinderx/Jit/hir/builder.cpp` - Specialize `emitYieldFrom()`
- `cinderx/Jit/hir/hir.h` - Add `InlineYieldFrom` instruction

**Expected Improvement**: 20-40%

### 4.3 If Bottleneck is Memory Access/Register Allocation

**Optimization Strategy C: Improved Register Allocation**

**Mechanism**:
- Reserve dedicated registers for recursive generators (self, left, right)
- Reduce stack spill/load operations
- Optimize register usage for `CheckField` / `LoadAttr`

**Implementation Locations**:
- `cinderx/Jit/lir/generator.cpp` - Improve register allocation strategy
- `cinderx/Jit/hir/simplify.cpp` - Apply similar approach to existing `simplifyIsTruthy()`

**Expected Improvement**: 10-30%

### 4.4 If Above Strategies Are Insufficient

**Optimization Strategy D: HIR Transformation to Stack-Based Iterator**

**Mechanism**:
- Detect `Tree.__iter__` pattern during HIR construction
- Automatically transform to equivalent stack-based HIR
- Generate non-recursive machine code

**Implementation Locations**:
- `cinderx/Jit/hir/builder.cpp` - Add pattern detection
- New file: `cinderx/Jit/hir/generator_transforms.cpp`

**Expected Improvement**: 200-300% (but high implementation complexity)

**Decision Point**: Only pursue Strategy D if Strategies A/B/C combined achieve <50% of target improvement.

## 5. Verification and Testing

### 5.1 Unit Tests

**New Test File**: `test_recursive_generator_perf.py`

```python
class TestRecursiveGeneratorOptimization:
    def test_tree_iter_compiled(self):
        """Verify Tree.__iter__ is JIT compiled"""
        jit.force_compile(Node.__iter__)
        assert jit.is_jit_compiled(Node.__iter__)

    def test_tree_iter_no_deopt(self):
        """Verify no frequent deopt at runtime"""
        tree = build_tree(10)
        for _ in tree:
            pass
        # Check deopt count should be 0 or very small

    def test_correctness(self):
        """Verify optimized result is correct"""
        tree = build_tree(15)
        result = list(tree)
        expected = list(range(1, 2**15))
        assert result == expected

    def test_performance_regression(self):
        """Verify performance at least matches CPython"""
        # Run 15 times, take median
        # assert median_time <= CPython_baseline * 1.05  # Allow 5% tolerance
```

### 5.2 Regression Tests

**Must Pass Existing Tests**:
- `test_jit.py` - All JIT basic tests
- `test_jit_generators.py` - Generator-related tests (if exists)
- `test_cinderx.py` - CinderX comprehensive tests

**Performance Regression Check**:
- Run full pyperformance in Docker ARM64
- Compare all benchmarks before/after optimization
- Confirm no benchmark regresses >2%

### 5.3 ARM Docker Validation Procedure

```bash
# In cpython-baseline container
cd /root/bm_generators

# 1. Install new version
pip install /dist/cinderx-*.whl --force-reinstall

# 2. Correctness verification
python3 -c "
import sys
sys.path.insert(0, '/root/bm_generators')
from run_benchmark import Tree, build_tree
import cinderx.jit as jit
jit.enable()
jit.force_compile(Tree.__iter__)
tree = build_tree(15)
assert list(tree) == list(range(1, 2**15))
print('Correctness OK')
"

# 3. Performance verification
python3 << 'PY'
import sys, statistics
sys.path.insert(0, '/root/bm_generators')
from run_benchmark import bench_generators
import cinderx.jit as jit
jit.enable()

# Warmup
for _ in range(5):
    bench_generators(1)

# Measure
times = []
for _ in range(15):
    times.append(bench_generators(1))

print(f'CinderX JIT: {statistics.mean(times)*1000:.3f}ms ± {statistics.stdev(times)*1000:.3f}ms')
print(f'Target: ≤35.7ms')
PY
```

## 6. Implementation Roadmap

### Phase 0: Diagnosis (1-2 days)
- [ ] macOS local: Verify JIT execution path, confirm no frequent deopt
- [ ] macOS local: Segmented timing to locate bottleneck (frame creation vs yield-from vs other)
- [ ] Docker ARM64: Replicate bottleneck, confirm consistency
- [ ] **Deliverable**: Performance bottleneck identification report

### Phase 1: Quick Optimization (2-3 days)
- [ ] Select matching optimization strategy (A/B/C) based on diagnosis results
- [ ] Implement optimization (expected to modify 1-3 files)
- [ ] Unit test verification
- [ ] Docker ARM64 performance verification
- [ ] **Go/No-Go Decision Point**: If improvement ≥50%, proceed to Phase 3; otherwise proceed to Phase 2

### Phase 2: Deep Optimization (3-5 days, conditional)
- [ ] Implement Strategy D (HIR transformation to stack-based iterator)
- [ ] Full correctness testing
- [ ] Docker ARM64 performance verification
- [ ] Regression testing

### Phase 3: Integration and Validation (1-2 days)
- [ ] Run full CinderX test suite
- [ ] Run full pyperformance in Docker ARM64
- [ ] Confirm no regression in other benchmarks
- [ ] Code review
- [ ] Documentation update

**Total Estimated Time**: 4-10 days (depending on whether Phase 2 is needed)

## 7. Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Diagnosis finds unclear bottleneck | Medium | Delay | Multi-angle analysis (perf, manual instrumentation, HIR dump) |
| Phase 1 optimization insufficient | Medium | More time needed | Go/No-Go mechanism, timely switch to Phase 2 |
| Phase 2 high implementation complexity | High | Delay | Can lower target (accept partial improvement) |
| Optimization causes other benchmark regressions | Low | Blocks release | Rollback mechanism + full regression testing |
| ARM Docker and real hardware behave differently | Low | Misjudgment | Reserve time for real hardware validation |

## 8. Success Criteria

The optimization will be considered successful if:

1. **Performance**: CinderX JIT on recursive generators (Tree.__iter__) ≤ 35.7ms in ARM Docker (at least matching CPython baseline)
2. **Correctness**: All existing CinderX tests pass
3. **No Regressions**: No other pyperformance benchmark regresses >2%
4. **Maintainability**: Code changes are well-documented and reviewed

## 9. Future Work

If this optimization is successful, potential follow-up work includes:

1. **Generalization**: Extend optimization to similar recursive generator patterns beyond Tree.__iter__
2. **Proactive Optimization**: Add heuristics to detect and optimize recursive generators automatically
3. **Documentation**: Document best practices for writing JIT-friendly recursive generators
4. **Monitoring**: Add performance regression tests to CI/CD pipeline
