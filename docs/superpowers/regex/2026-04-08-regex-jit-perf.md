# Regex Compile JIT Performance Optimization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize CinderX JIT compiled code performance for the regex_compile benchmark, currently 23% slower than CPython baseline (0.806 ms vs 0.657 ms per loop).

**Architecture:** Four independent optimization tasks targeting different layers of the JIT pipeline: refcount overhead (D1/D2), code layout (F1), redundant instruction elimination (C1/C2). Each task is independently implementable and testable. Changes are in C++ within the `cinderx/Jit/` directory.

**Tech Stack:** C++17, CinderX JIT compiler (HIR → LIR → native code), Python 3.14, pyperf benchmarking on ARM64 (kunpeng)

---

## Baseline Performance

| Config | Time | Per-loop |
|--------|------|----------|
| CPython (no JIT) | 65.7 ms / 100 loops | 0.657 ms |
| CinderX JIT (4 functions) | 80.6 ms / 100 loops | 0.806 ms |

**Compiled functions:** `bench_regex_compile` (249 HIR lines), `re._compiler:compile` (521), `re._parser:parse` (482), `re._compiler:_code` (124)

**Benchmark commands** (run on kunpeng via `ssh kunpeng`):
```bash
# CPython baseline
/root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/bench_regex_cpython.py

# CinderX JIT
PYTHONJITENABLE=1 /root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/bench_regex_jit.py

# HIR dump
PYTHONJITENABLE=1 PYTHONJITDUMPFINALHIR=1 PYTHONJITLOGFILE=/tmp/hir.log /root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/dump_regex_hir.py
```

**Build on kunpeng:**
```bash
cd /root/cinderx && pip3.14 install -e .
```

**Sync code to kunpeng:**
```bash
rsync -avz --exclude='.git' --exclude='build' --exclude='_deps' --exclude='*.pyc' --exclude='__pycache__' --exclude='venv' /Users/luchen/Agents-Repo/GSD/cinderx/ kunpeng:/root/cinderx/
```

---

## File Map

| File | Responsibility | Task |
|------|---------------|------|
| `cinderx/Jit/hir/instr_effects.cpp` | Instruction memory effects / arbitrary execution | D1 |
| `cinderx/Jit/hir/hir_ops.cpp` | HIR instruction definitions | D2 |
| `cinderx/Jit/hir/hir.h` | HIR instruction class definitions | D2 |
| `cinderx/Jit/jit_rt.cpp` | Runtime helpers (Py_INCREF/DECREF loops) | D2 |
| `cinderx/Jit/jit_rt.h` | Runtime helper declarations | D2 |
| `cinderx/Jit/hir/refcount_insertion.cpp` | Refcount insertion pass + BatchDecref/Incref grouping | D2 |
| `cinderx/Jit/lir/generator.cpp` | LIR lowering for HIR instructions | D2 |
| `cinderx/Jit/codegen/autogen.cpp` | Codegen dispatch for native instructions | D2 |
| `cinderx/Jit/lir/blocksorter.cpp` | LIR basic block ordering | F1 |
| `cinderx/Jit/hir/simplify.cpp` | HIR simplification pass | C1, C2 |
| `cinderx/Jit/hir/simplify.h` | Simplify pass interface | C1, C2 |
| `cinderx/RuntimeTests/hir_tests/refcount_insertion_test.txt` | Refcount insertion test expectations | D2 |

---

## Task D1: Narrow XDecref Arbitrary Execution for Known-Safe Types

**Impact:** Medium (~3-5%) — keeps borrow support alive for XDecref of known-safe types, preventing Incref insertion
**Risk:** Low — only affects type propagation precision, correctness is guaranteed by deopt guards
**Files:**
- Modify: `cinderx/Jit/hir/instr_effects.cpp:543-558` (arbitrary execution list)
- Modify: `cinderx/Jit/hir/instr_effects.cpp:214-221` (Decref/XDecref effects)

**Problem:** In `instr_effects.cpp` line 553, `kXDecref` is unconditionally marked as `hasArbitraryExecution() == true`. This means every XDecref kills ALL borrow support (line 592-593 of refcount_insertion.cpp, `invalidateBorrowSupport` with `AManagedHeapAny`). But for types with known destructors that don't execute arbitrary Python code (e.g., `LongExact`, `UnicodeExact`, `FloatExact`, `TupleExact`, `ListExact`, `DictExact`), the XDecref is safe and should not invalidate borrow support.

Additionally, `kDecref` and `kXDecref` share the same effects logic (lines 214-221), but only `kXDecref` is in the arbitrary execution list. This asymmetry means `Decref` of an unknown type is treated better than `XDecref` of a known-safe type.

- [ ] **Step 1: Add type-aware arbitrary execution check**

In `cinderx/Jit/hir/instr_effects.cpp`, modify the `hasArbitraryExecution()` function (around line 553). Change the `kXDecref` case from unconditional `true` to check if the operand type is known-safe:

```cpp
// Before (line 553):
case Opcode::kXDecref:

// After — move kXDecref out of the unconditional list and add a conditional case:
```

Remove `case Opcode::kXDecref:` from the unconditional true list (lines 543-558). Add a new case before the `default:` that checks the type:

```cpp
case Opcode::kXDecref: {
  // If the operand is None, it can't execute arbitrary code.
  auto op_type = inst.GetOperand(0)->type();
  if (op_type <= TNoneType || op_type <= TNullptr) {
    return false;
  }
  // If the type has a known destructor, the decref won't execute arbitrary
  // Python code (it's a C-level tp_dealloc, not __del__).
  if (op_type.runtimePyTypeDestructor().has_value()) {
    return false;
  }
  return true;
}
```

- [ ] **Step 2: Build and run unit tests**

```bash
ssh kunpeng 'cd /root/cinderx && pip3.14 install -e . 2>&1 | tail -5'
# Run refcount insertion tests
ssh kunpeng 'cd /root/cinderx && /root/.pyenv/versions/3.14.3/bin/python3.14 -m pytest cinderx/RuntimeTests/ -k refcount -x 2>&1 | tail -20'
```

- [ ] **Step 3: Run HIR comparison and benchmark**

```bash
# Dump HIR and compare Incref/Decref count before/after
ssh kunpeng 'PYTHONJITENABLE=1 PYTHONJITDUMPFINALHIR=1 PYTHONJITLOGFILE=/tmp/hir_d1.log /root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/dump_regex_hir.py'
# Count Incref/Decref instructions
ssh kunpeng 'grep -c "Incref\|Decref\|XDecref\|XIncref" /tmp/regex_compile_hir_full.log /tmp/hir_d1.log'
# Run benchmark
ssh kunpeng 'PYTHONJITENABLE=1 /root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/bench_regex_jit.py'
```

- [ ] **Step 4: Commit**

```bash
git add cinderx/Jit/hir/instr_effects.cpp
git commit -m "perf(jit): narrow XDecref arbitrary execution for known-safe types

XDecref was unconditionally marked as having arbitrary execution,
killing all borrow support and forcing Incref insertion. For types
with known destructors (LongExact, UnicodeExact, etc.), the decref
is safe and does not execute Python code. This change keeps borrow
support alive for these cases, reducing Incref/Decref pairs."
```

---

## Task D2: Add BatchIncref for Consecutive Incref Runs

**Impact:** Low-Medium (~1-3%) — groups consecutive Incref into a single function call, reducing N atomic ops to 1 call
**Risk:** Low — mirrors existing BatchDecref mechanism exactly
**Files:**
- Modify: `cinderx/Jit/hir/hir_ops.cpp:2320-2333` (add BatchIncref instruction)
- Modify: `cinderx/Jit/hir/hir.h` (add BatchIncref class, if needed — BatchDecref is defined via macro)
- Modify: `cinderx/Jit/jit_rt.h` (declare JITRT_BatchIncref)
- Modify: `cinderx/Jit/jit_rt.cpp` (implement JITRT_BatchIncref)
- Modify: `cinderx/Jit/hir/instr_effects.cpp` (add BatchIncref effects, same as BatchDecref)
- Modify: `cinderx/Jit/hir/refcount_insertion.cpp:1244-1291` (add optimizeLongIncrefRuns)
- Modify: `cinderx/Jit/lir/generator.cpp:1974-1983` (lower BatchIncref to kVarArgCall)

- [ ] **Step 1: Define BatchIncref instruction**

In `cinderx/Jit/hir/hir_ops.cpp`, after the existing BatchDecref definition (line ~2333), add:

```cpp
// batch increment references
DEFINE_SIMPLE_INSTR(BatchIncref, (TObject), Operands<>);
```

- [ ] **Step 2: Add runtime implementation**

In `cinderx/Jit/jit_rt.h`, after the BatchDecref declaration, add:

```cpp
DECLARE_JITRT_METHOD(BatchIncref);
```

In `cinderx/Jit/jit_rt.cpp`, after JITRT_BatchDecref (around line 2432), add:

```cpp
void JITRT_BatchIncref(PyObject* const* args, std::size_t nargs) {
  for (std::size_t i = 0; i < nargs; i++) {
    Py_INCREF(args[i]);
  }
}
```

- [ ] **Step 3: Add instruction effects**

In `cinderx/Jit/hir/instr_effects.cpp`, add a case for `kBatchIncref` next to `kBatchDecref` (line 211):

```cpp
case Opcode::kBatchIncref:
  return {false, AEmpty, {inst.NumOperands()}, AOther};
```

Note: BatchIncref should NOT be in the `hasArbitraryExecution()` list (same as Incref).

- [ ] **Step 4: Lower to LIR**

In `cinderx/Jit/lir/generator.cpp`, find the BatchDecref lowering (lines 1974-1983) and add identical lowering for BatchIncref:

```cpp
case Opcode::kBatchIncref: {
  auto& binstr = dynamic_cast<const hir::BatchIncref&>(instr);
  emitVarArgCall(binstr, rt_entrypoints::JITRT_BatchIncref);
  break;
}
```

- [ ] **Step 5: Add optimizeLongIncrefRuns pass**

In `cinderx/Jit/hir/refcount_insertion.cpp`, add a function after `optimizeLongDecrefRuns` (line 1291). This mirrors BatchDecref but for Incref:

```cpp
void optimizeLongIncrefRuns(Function& irfunc) {
  constexpr int kMinimumNumberOfIncrefsToOptimize = 3;

  for (auto& block : irfunc.cfg.GetRPOTraversal()) {
    auto cur_iter = block->begin();
    while (cur_iter != block->end()) {
      if (!cur_iter->IsIncref()) {
        ++cur_iter;
        continue;
      }

      // Count consecutive Increfs
      int num = 0;
      auto count_iter = cur_iter;
      while (count_iter != block->end() && count_iter->IsIncref()) {
        num++;
        ++count_iter;
      }

      if (num < kMinimumNumberOfIncrefsToOptimize) {
        std::advance(cur_iter, num);
        continue;
      }

      auto batch_incref = BatchIncref::create(num);
      batch_incref->copyBytecodeOffset(*cur_iter);
      batch_incref->InsertBefore(*cur_iter);

      for (int i = 0; i < num; i++) {
        JIT_CHECK(cur_iter->IsIncref(), "Unexpected non-incref in run");
        batch_incref->SetOperand(i, cur_iter->GetOperand(0));
        auto old_instr = cur_iter++;
        old_instr->unlink();
        delete &(*old_instr);
      }
    }
  }
}
```

Then call it in `RefcountInsertion::Run()` after `optimizeLongDecrefRuns` (line 1450):

```cpp
optimizeLongDecrefRuns(func);
optimizeLongIncrefRuns(func);  // ADD THIS LINE
```

- [ ] **Step 6: Add IsIncref method to Instruction**

Check if `IsIncref()` exists. If not, add it to `cinderx/Jit/hir/hir.h` near `IsDecref()`:

```cpp
bool IsIncref() const {
  return opcode() == Opcode::kIncref || opcode() == Opcode::kXIncref;
}
```

- [ ] **Step 7: Build, test, benchmark**

```bash
ssh kunpeng 'cd /root/cinderx && pip3.14 install -e . 2>&1 | tail -5'
ssh kunpeng 'PYTHONJITENABLE=1 /root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/bench_regex_jit.py'
```

- [ ] **Step 8: Commit**

```bash
git add cinderx/Jit/hir/hir_ops.cpp cinderx/Jit/hir/hir.h cinderx/Jit/jit_rt.h cinderx/Jit/jit_rt.cpp cinderx/Jit/hir/instr_effects.cpp cinderx/Jit/hir/refcount_insertion.cpp cinderx/Jit/lir/generator.cpp
git commit -m "perf(jit): add BatchIncref for consecutive Incref runs

Mirrors the existing BatchDecref optimization. Groups runs of 3+
consecutive Incref instructions into a single BatchIncref call,
reducing N atomic Py_INCREF operations to one function call.
On ARM64, each atomic Incref costs ~5-10ns (ldadd), so batching
3 Increfs saves ~10-20ns per call site."
```

---

## Task F1: Mark Error/Deopt Blocks as Cold for Large Functions

**Impact:** Low-Medium (~2-5%) — improves icache locality for hot paths in `re._compiler:compile` (521 HIR lines) and `re._parser:parse` (482 HIR lines)
**Risk:** Low — uses existing cold code section infrastructure, controlled by config flag
**Files:**
- Create: `cinderx/Jit/hir/cold_block_marking.h`
- Create: `cinderx/Jit/hir/cold_block_marking.cpp`
- Modify: `cinderx/Jit/compiler.cpp:78-153` (add pass to pipeline)
- Modify: `cinderx/Jit/lir/generator.cpp:592-594` (extend cold block marking)

**Problem:** The `re._compiler:compile` function has a 521-line HIR with cold paths like the SRE_FLAG_DEBUG check (bb4, ~40 lines) and error paths (bb10 with `error()` raise, bb5 with `unbalanced parenthesis`). These cold blocks are currently laid out inline with hot code, wasting icache. CinderX has a `CodeSection::kCold` mechanism but it's only used for dealloc blocks and deopt exit trampolines.

- [ ] **Step 1: Create ColdBlockMarking pass header**

Create `cinderx/Jit/hir/cold_block_marking.h`:

```cpp
#pragma once

#include "cinderx/Jit/hir/pass.h"

namespace jit::hir {

// Marks HIR blocks that are unlikely to execute as having cold successors.
// This information is later used by the LIR generator to place cold blocks
// in a separate code section for better icache locality.
class ColdBlockMarking : public Pass {
 public:
  ColdBlockMarking() : Pass(PassConfig::kCleanCFG) {}
  char const* name() const override { return "ColdBlockMarking"; }
  void Run(Function& func) override;
};

} // namespace jit::hir
```

- [ ] **Step 2: Implement ColdBlockMarking pass**

Create `cinderx/Jit/hir/cold_block_marking.cpp`:

```cpp
#include "cinderx/Jit/hir/cold_block_marking.h"
#include "cinderx/Jit/hir/hir.h"

namespace jit::hir {

void ColdBlockMarking::Run(Function& func) {
  for (auto& block : func.cfg.blocks) {
    for (auto& instr : *block) {
      // Blocks containing Deopt are error-handling blocks
      if (instr.IsDeopt()) {
        block->setCold(true);
        break;
      }
      // Blocks containing Raise are error paths
      if (instr.IsRaise()) {
        block->setCold(true);
        break;
      }
    }
  }
}

} // namespace jit::hir
```

**Note:** This requires adding `setCold(bool)` / `isCold()` to `hir::BasicBlock`. Check if it already exists; if not, add a `bool cold_{false}` field to `cinderx/Jit/hir/hir.h` in the BasicBlock class.

- [ ] **Step 3: Propagate cold marking to LIR**

In `cinderx/Jit/lir/generator.cpp`, find where blocks are generated (around line 3045-3064). When translating an HIR block that is marked cold, mark the corresponding LIR block as `kCold`:

```cpp
// In the block emission loop, after binding the label:
if (getConfig().multiple_code_sections && hir_block->isCold()) {
  basicblock->setSection(codegen::CodeSection::kCold);
}
```

This requires maintaining a mapping from HIR blocks to LIR blocks, or propagating the cold flag during LIR generation.

- [ ] **Step 4: Add pass to compiler pipeline**

In `cinderx/Jit/compiler.cpp`, add the pass after `DeadCodeElimination` (line 129) and before the second `CleanCFG` (line 130):

```cpp
runPass(jit::hir::ColdBlockMarking{}, irfunc, callback);
```

- [ ] **Step 5: Build, test, benchmark**

```bash
ssh kunpeng 'cd /root/cinderx && pip3.14 install -e . 2>&1 | tail -5'
# Enable multiple_code_sections and run
ssh kunpeng 'PYTHONJITENABLE=1 /root/.pyenv/versions/3.14.3/bin/python3.14 -c "
import cinderx; cinderx.init()
from cinderx.jit import force_compile
# ... test that cold blocks work
"'
ssh kunpeng 'PYTHONJITENABLE=1 /root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/bench_regex_jit.py'
```

- [ ] **Step 6: Commit**

```bash
git add cinderx/Jit/hir/cold_block_marking.h cinderx/Jit/hir/cold_block_marking.cpp cinderx/Jit/compiler.cpp cinderx/Jit/lir/generator.cpp cinderx/Jit/hir/hir.h
git commit -m "perf(jit): add ColdBlockMarking pass for better icache locality

Marks HIR blocks containing Deopt or Raise as cold, so they are
placed in the cold code section during codegen. This improves
icache locality for hot paths, especially in large compiled
functions like re._compiler:compile (521 HIR lines)."
```

---

## Task C1: Add LoadGlobalCached CSE to Simplify Pass

**Impact:** Low (~1-2%) — eliminates redundant global loads in `bench_regex_compile` (2 duplicate `LoadGlobalCached<1; "re">` in the inner loop)
**Risk:** Low — only eliminates loads when no intervening store could invalidate the cache
**Files:**
- Modify: `cinderx/Jit/hir/simplify.cpp:3519-3632` (add simplifyLoadGlobalCached)

**Problem:** In `bench_regex_compile`, the hot loop (bb16) loads the `re` module twice: once for `re.purge()` and once for `re.compile()`. Between these two loads, only `VectorCall<0>` (purge) runs, which doesn't modify global variables. The second load is redundant. Currently, there is no CSE for `LoadGlobalCached`.

- [ ] **Step 1: Add simplifyLoadGlobalCached to simplify.cpp**

Add a new simplification function near line 2088 (where `simplifyLoadAttrCached` is). The function checks if an identical `LoadGlobalCached` with the same `name_idx` has already been seen in the current block, and if no intervening instruction stores to globals:

```cpp
Register* simplifyLoadGlobalCached(
    Instr& instr,
    BlockInfo const&,
    ConstRef<Instr> const&,
    Phis const&) {
  auto& lg = dynamic_cast<LoadGlobalCached&>(instr);
  // Walk backwards in the same block to find a prior LoadGlobalCached
  // with the same name_idx
  for (auto cur = instr.prev; cur != nullptr; cur = cur->prev) {
    if (cur->opcode() == Opcode::kLoadGlobalCached) {
      auto& prev_lg = dynamic_cast<LoadGlobalCached&>(*cur);
      if (prev_lg.nameIdx() == lg.nameIdx()) {
        // Found a previous load of the same global
        // The previous load already has a GuardIs after it, so we can
        // reuse the guarded result
        return prev_lg.GetOutput();
      }
    }
    // Any instruction that may store to globals invalidates the cache
    if (cur->hasSideEffects() || cur->mayStore()) {
      break;
    }
  }
  return nullptr;
}
```

Then add the case to `simplifyInstr()` (around line 3519):

```cpp
case Opcode::kLoadGlobalCached:
  result = simplifyLoadGlobalCached(instr, block_info, cur_instr, phis);
  break;
```

- [ ] **Step 2: Build, test, benchmark**

```bash
ssh kunpeng 'cd /root/cinderx && pip3.14 install -e . 2>&1 | tail -5'
# Verify HIR no longer has duplicate LoadGlobalCached
ssh kunpeng 'PYTHONJITENABLE=1 PYTHONJITDUMPFINALHIR=1 PYTHONJITLOGFILE=/tmp/hir_c1.log /root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/dump_regex_hir.py'
# Check that bench_regex_compile has fewer LoadGlobalCached
ssh kunpeng 'grep -c "LoadGlobalCached" /tmp/hir_c1.log'
ssh kunpeng 'PYTHONJITENABLE=1 /root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/bench_regex_jit.py'
```

- [ ] **Step 3: Commit**

```bash
git add cinderx/Jit/hir/simplify.cpp
git commit -m "perf(jit): add CSE for LoadGlobalCached in simplify pass

Eliminates redundant global variable loads within a basic block
when no intervening store could invalidate the cache. In the
regex_compile benchmark, this removes a duplicate 're' module
load in the hot loop."
```

---

## Task C2: Add GuardIs Deduplication to Simplify Pass

**Impact:** Low (~1-2%) — eliminates redundant GuardIs in `bench_regex_compile` (2 `GuardIs` for same `re` module object)
**Risk:** Low — replaces redundant guard with Assign, semantics unchanged
**Files:**
- Modify: `cinderx/Jit/hir/simplify.cpp:3519-3632` (add simplifyGuardIs)

**Problem:** In `bench_regex_compile`, bb16 has two `GuardIs` for the `re` module object at the same address. The second guard is redundant because the first already proved the value matches. Currently there is no `simplifyGuardIs` function.

- [ ] **Step 1: Add simplifyGuardIs to simplify.cpp**

Add near `simplifyGuardType` (line 433):

```cpp
Register* simplifyGuardIs(
    Instr& instr,
    BlockInfo const&,
    ConstRef<Instr> const& cur_instr,
    Phis const&) {
  auto& guard = dynamic_cast<GuardIs&>(instr);
  // Walk backwards in the same block to find a GuardIs with the same target
  for (auto cur = instr.prev; cur != nullptr; cur = cur->prev) {
    if (cur->opcode() == Opcode::kGuardIs) {
      auto& prev_guard = dynamic_cast<GuardIs&>(*cur);
      if (prev_guard.target() == guard.target() &&
          prev_guard.GetOperand(0) == guard.GetOperand(0)) {
        // Same target and same source — this guard is redundant
        return prev_guard.GetOutput();
      }
    }
    // If the source register is redefined, stop
    if (cur->hasOutput() && cur->GetOutput() == guard.GetOperand(0)) {
      break;
    }
  }
  return nullptr;
}
```

Then add the case to `simplifyInstr()`:

```cpp
case Opcode::kGuardIs:
  result = simplifyGuardIs(instr, block_info, cur_instr, phis);
  break;
```

- [ ] **Step 2: Build, test, benchmark**

```bash
ssh kunpeng 'cd /root/cinderx && pip3.14 install -e . 2>&1 | tail -5'
ssh kunpeng 'PYTHONJITENABLE=1 PYTHONJITDUMPFINALHIR=1 PYTHONJITLOGFILE=/tmp/hir_c2.log /root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/dump_regex_hir.py'
ssh kunpeng 'grep -c "GuardIs" /tmp/hir_c2.log'
ssh kunpeng 'PYTHONJITENABLE=1 /root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/bench_regex_jit.py'
```

- [ ] **Step 3: Commit**

```bash
git add cinderx/Jit/hir/simplify.cpp
git commit -m "perf(jit): add GuardIs deduplication in simplify pass

Eliminates redundant GuardIs with the same target and source
within a basic block. The second guard is replaced with an
Assign from the first guard's output."
```

---

## Verification Plan

After all tasks are implemented, run the full verification:

1. **Build all tasks together:**
```bash
rsync -avz --exclude='.git' --exclude='build' --exclude='_deps' --exclude='*.pyc' --exclude='__pycache__' --exclude='venv' /Users/luchen/Agents-Repo/GSD/cinderx/ kunpeng:/root/cinderx/
ssh kunpeng 'cd /root/cinderx && pip3.14 install -e . 2>&1 | tail -5'
```

2. **Run benchmark 3 times and average:**
```bash
ssh kunpeng 'for i in 1 2 3; do echo "Run $i:"; PYTHONJITENABLE=1 /root/.pyenv/versions/3.14.3/bin/python3.14 /tmp/bench_regex_jit.py; done'
```

3. **Compare with baseline:**
- CPython baseline: 0.657 ms/loop
- JIT baseline (before optimization): 0.806 ms/loop
- Target: < 0.75 ms/loop (reduce gap by 35%+)

4. **Run other benchmarks to check for regressions:**
```bash
# Quick regression check on other workloads
ssh kunpeng '/root/.pyenv/versions/3.14.3/bin/python3.14 -m pyperformance run --benchmarks=richards --fast --output=/tmp/richards_check.json 2>&1 | grep Mean'
```

5. **Verify each task independently by cherry-picking:**
Each commit should be independently testable. If a regression is found, bisect by reverting individual commits.
