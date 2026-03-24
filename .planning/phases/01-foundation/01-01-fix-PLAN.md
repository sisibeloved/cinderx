---
phase: 01-foundation
plan: 01-fix
type: execute
wave: 1
depends_on: []
files_modified:
  - cinderx/Jit/jit_rt.h
  - cinderx/Jit/jit_rt.cpp
autonomous: true
gap_closure: true
requirements:
  - JIT-RT-01
must_haves:
  truths:
    - "All 6 missing JITRT_* functions have JIT_RUNTIME_API macro in header"
    - "All 6 missing JITRT_* functions have JIT_RUNTIME_API macro in implementation"
    - "Build passes without errors"
    - "Symbol table shows all JITRT functions as external symbols (T)"
  artifacts:
    - path: "cinderx/Jit/jit_rt.h"
      provides: "Function declarations with JIT_RUNTIME_API macro"
      contains: "JIT_RUNTIME_API before JITRT_LoadGlobal, JITRT_CallFunctionEx, JITRT_CallFunctionExAwaited, JITRT_MatchKeys, JITRT_AllocateAndLinkGenAndInterpreterFrame, JITRT_UnlinkGenFrameAndReturnGenDataFooter"
    - path: "cinderx/Jit/jit_rt.cpp"
      provides: "Function implementations with JIT_RUNTIME_API macro"
      contains: "JIT_RUNTIME_API before JITRT_LoadGlobal, JITRT_CallFunctionEx, JITRT_CallFunctionExAwaited, JITRT_MatchKeys"
  key_links:
    - from: "jit_rt.h declarations"
      to: "jit_rt.cpp implementations"
      via: "JIT_RUNTIME_API macro consistency"
      pattern: "JIT_RUNTIME_API.*JITRT_"
---

# Fix Plan: Add JIT_RUNTIME_API to 6 Missing JITRT Functions

## Context

This is a **gap closure plan** to address verification failures from Phase 01. The VERIFICATION.md identified that 6 JITRT_* functions are missing the `JIT_RUNTIME_API` macro, which could allow LTO to inline them and cause runtime crashes.

### Gap Details (from 01-VERIFICATION.md)

**Problem:** 6 JITRT_* functions missing JIT_RUNTIME_API macro in declarations

| Function | Header Line | Status |
|----------|-------------|--------|
| JITRT_LoadGlobal | 168 | Missing JIT_RUNTIME_API |
| JITRT_CallFunctionEx | 219 | Missing JIT_RUNTIME_API |
| JITRT_CallFunctionExAwaited | 225 | Missing JIT_RUNTIME_API |
| JITRT_MatchKeys | 610 | Missing JIT_RUNTIME_API |
| JITRT_AllocateAndLinkGenAndInterpreterFrame | 59 | Missing JIT_RUNTIME_API |
| JITRT_UnlinkGenFrameAndReturnGenDataFooter | 72 | Missing JIT_RUNTIME_API |

**Impact:** LTO may inline these functions, breaking JIT-compiled code that expects them at specific addresses.

## Objective

Add `JIT_RUNTIME_API` macro to all 6 missing function declarations in `jit_rt.h` and verify/correct corresponding implementations in `jit_rt.cpp`.

**Purpose:** Ensure all JITRT runtime entry points are marked `noinline` and `visibility("default")` to prevent LTO inlining.

**Output:** Updated jit_rt.h and jit_rt.cpp with 100% JIT_RUNTIME_API coverage.

## Execution Context

@$HOME/.config/opencode/get-shit-done/workflows/execute-plan.md

## Context

@cinderx/Jit/jit_rt.h
@cinderx/Jit/jit_rt.cpp

### JIT_RUNTIME_API Macro Definition (from jit_rt.h:15-16)

```cpp
#define JIT_RUNTIME_API \
    __attribute__((noinline, visibility("default")))
```

### Functions to Fix - Header Declarations

**In jit_rt.h:**

1. **Line 58-64** - JITRT_AllocateAndLinkGenAndInterpreterFrame (missing before return type)
   ```cpp
   // CURRENT (missing macro):
   std::pair<PyThreadState*, jit::GenDataFooter*>
   JITRT_AllocateAndLinkGenAndInterpreterFrame(...)
   
   // TARGET (add macro):
   JIT_RUNTIME_API std::pair<PyThreadState*, jit::GenDataFooter*>
   JITRT_AllocateAndLinkGenAndInterpreterFrame(...)
   ```

2. **Line 71-72** - JITRT_UnlinkGenFrameAndReturnGenDataFooter (missing before return type)
   ```cpp
   // CURRENT (missing macro):
   std::pair<jit::JitGenObject*, jit::GenDataFooter*>
   JITRT_UnlinkGenFrameAndReturnGenDataFooter(PyThreadState* tstate);
   
   // TARGET (add macro):
   JIT_RUNTIME_API std::pair<jit::JitGenObject*, jit::GenDataFooter*>
   JITRT_UnlinkGenFrameAndReturnGenDataFooter(PyThreadState* tstate);
   ```

3. **Line 167-168** - JITRT_LoadGlobal
   ```cpp
   // CURRENT (missing macro):
   PyObject*
   JITRT_LoadGlobal(PyObject* globals, PyObject* builtins, PyObject* name);
   
   // TARGET (add macro):
   JIT_RUNTIME_API PyObject*
   JITRT_LoadGlobal(PyObject* globals, PyObject* builtins, PyObject* name);
   ```

4. **Line 218-219** - JITRT_CallFunctionEx
   ```cpp
   // CURRENT (missing macro):
   PyObject*
   JITRT_CallFunctionEx(PyObject* func, PyObject* pargs, PyObject* kwargs);
   
   // TARGET (add macro):
   JIT_RUNTIME_API PyObject*
   JITRT_CallFunctionEx(PyObject* func, PyObject* pargs, PyObject* kwargs);
   ```

5. **Line 224-225** - JITRT_CallFunctionExAwaited
   ```cpp
   // CURRENT (missing macro):
   PyObject*
   JITRT_CallFunctionExAwaited(PyObject* func, PyObject* pargs, PyObject* kwargs);
   
   // TARGET (add macro):
   JIT_RUNTIME_API PyObject*
   JITRT_CallFunctionExAwaited(PyObject* func, PyObject* pargs, PyObject* kwargs);
   ```

6. **Line 609-610** - JITRT_MatchKeys
   ```cpp
   // CURRENT (missing macro):
   PyObject*
   JITRT_MatchKeys(PyThreadState* tstate, PyObject* subject, PyObject* keys);
   
   // TARGET (add macro):
   JIT_RUNTIME_API PyObject*
   JITRT_MatchKeys(PyThreadState* tstate, PyObject* subject, PyObject* keys);
   ```

### Functions to Fix - Implementation Definitions

**In jit_rt.cpp:**

1. **Line 713** - JITRT_AllocateAndLinkGenAndInterpreterFrame - ALREADY HAS JIT_RUNTIME_API
2. **Line 794** - JITRT_UnlinkGenFrameAndReturnGenDataFooter - ALREADY HAS JIT_RUNTIME_API
3. **Line 878** - JITRT_LoadGlobal - MISSING JIT_RUNTIME_API
4. **Line 1133** - JITRT_CallFunctionEx - MISSING JIT_RUNTIME_API
5. **Line 1138** - JITRT_CallFunctionExAwaited - MISSING JIT_RUNTIME_API
6. **Line 2320** - JITRT_MatchKeys - MISSING JIT_RUNTIME_API (estimated location)

## Tasks

<task type="auto" tdd="true">
  <name>Task 1: Add JIT_RUNTIME_API to header declarations</name>
  <files>cinderx/Jit/jit_rt.h</files>
  <behavior>
    - Verify JIT_RUNTIME_API macro is defined at lines 15-16
    - Add JIT_RUNTIME_API before return type at line 58 (JITRT_AllocateAndLinkGenAndInterpreterFrame)
    - Add JIT_RUNTIME_API before return type at line 71 (JITRT_UnlinkGenFrameAndReturnGenDataFooter)
    - Add JIT_RUNTIME_API before return type at line 167 (JITRT_LoadGlobal)
    - Add JIT_RUNTIME_API before return type at line 218 (JITRT_CallFunctionEx)
    - Add JIT_RUNTIME_API before return type at line 224 (JITRT_CallFunctionExAwaited)
    - Add JIT_RUNTIME_API before return type at line 609 (JITRT_MatchKeys)
  </behavior>
  <action>
    Edit cinderx/Jit/jit_rt.h to add JIT_RUNTIME_API macro to 6 function declarations.
    
    Changes to make:
    1. Line 58: Add `JIT_RUNTIME_API` before `std::pair<PyThreadState*, jit::GenDataFooter*>`
    2. Line 71: Add `JIT_RUNTIME_API` before `std::pair<jit::JitGenObject*, jit::GenDataFooter*>`
    3. Line 167: Add `JIT_RUNTIME_API` before `PyObject*`
    4. Line 218: Add `JIT_RUNTIME_API` before `PyObject*`
    5. Line 224: Add `JIT_RUNTIME_API` before `PyObject*`
    6. Line 609: Add `JIT_RUNTIME_API` before `PyObject*`
    
    Pattern to follow (from working examples in same file):
    - Line 45: `JIT_RUNTIME_API PyThreadState* JITRT_AllocateAndLinkFrame(...)`
    - Line 109: `JIT_RUNTIME_API PyObject* JITRT_CallInterpretedVectorcall(...)`
    
    Note: For multi-line declarations, the macro goes on the same line as the return type.
  </action>
  <verify>
    <automated>grep -n "JIT_RUNTIME_API.*JITRT_" cinderx/Jit/jit_rt.h | grep -E "(LoadGlobal|CallFunctionEx|MatchKeys|AllocateAndLinkGenAndInterpreterFrame|UnlinkGenFrameAndReturnGenDataFooter)" | wc -l</automated>
    <expected>6</expected>
  </verify>
  <done>All 6 function declarations in jit_rt.h have JIT_RUNTIME_API macro</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add JIT_RUNTIME_API to implementation definitions</name>
  <files>cinderx/Jit/jit_rt.cpp</files>
  <behavior>
    - Verify JITRT_AllocateAndLinkGenAndInterpreterFrame at line 713 already has JIT_RUNTIME_API
    - Verify JITRT_UnlinkGenFrameAndReturnGenDataFooter at line 794 already has JIT_RUNTIME_API
    - Add JIT_RUNTIME_API to JITRT_LoadGlobal at line 878 (currently missing)
    - Add JIT_RUNTIME_API to JITRT_CallFunctionEx at line 1133 (currently missing)
    - Add JIT_RUNTIME_API to JITRT_CallFunctionExAwaited at line 1138 (currently missing)
    - Add JIT_RUNTIME_API to JITRT_MatchKeys (find exact line, currently missing)
  </behavior>
  <action>
    Edit cinderx/Jit/jit_rt.cpp to add JIT_RUNTIME_API macro to 4 function definitions
    (2 already have it, 4 need it added).
    
    Changes to make:
    1. Line 878: Add `JIT_RUNTIME_API` before `PyObject* JITRT_LoadGlobal`
    2. Line 1133: Add `JIT_RUNTIME_API` before `PyObject* JITRT_CallFunctionEx`
    3. Line 1138: Add `JIT_RUNTIME_API` before `PyObject* JITRT_CallFunctionExAwaited`
    4. Find JITRT_MatchKeys and add `JIT_RUNTIME_API` before its return type
    
    Note: JITRT_AllocateAndLinkGenAndInterpreterFrame (line 713) and 
    JITRT_UnlinkGenFrameAndReturnGenDataFooter (line 794) already have JIT_RUNTIME_API.
    
    Pattern to follow (from working examples in same file):
    - Line 713: `JIT_RUNTIME_API std::pair<PyThreadState*, jit::GenDataFooter*> JITRT_AllocateAndLinkGenAndInterpreterFrame(...)`
  </action>
  <verify>
    <automated>grep -n "JIT_RUNTIME_API.*JITRT_" cinderx/Jit/jit_rt.cpp | grep -E "(LoadGlobal|CallFunctionEx|MatchKeys)" | wc -l</automated>
    <expected>4</expected>
  </verify>
  <done>All 4 missing implementations in jit_rt.cpp have JIT_RUNTIME_API macro</done>
</task>

<task type="auto">
  <name>Task 3: Verify 100% JITRT coverage with symbol table check</name>
  <files>cinderx/Jit/jit_rt.h, cinderx/Jit/jit_rt.cpp</files>
  <action>
    Run comprehensive verification to ensure all JITRT_* functions have JIT_RUNTIME_API:
    
    1. Count total JITRT_* function declarations in header:
       grep -c "^JIT_RUNTIME_API.*JITRT_" cinderx/Jit/jit_rt.h
    
    2. Count total JITRT_* function definitions in implementation:
       grep -c "^JIT_RUNTIME_API.*JITRT_" cinderx/Jit/jit_rt.cpp
    
    3. Verify specific 6 functions are covered:
       - JITRT_LoadGlobal
       - JITRT_CallFunctionEx
       - JITRT_CallFunctionExAwaited
       - JITRT_MatchKeys
       - JITRT_AllocateAndLinkGenAndInterpreterFrame
       - JITRT_UnlinkGenFrameAndReturnGenDataFooter
    
    4. Attempt build verification (if build system available):
       python setup.py build_ext --inplace 2>&1 | head -50
  </action>
  <verify>
    <automated>bash -c 'echo "Header coverage:"; grep -c "JIT_RUNTIME_API.*JITRT_" cinderx/Jit/jit_rt.h; echo "Implementation coverage:"; grep -c "JIT_RUNTIME_API.*JITRT_" cinderx/Jit/jit_rt.cpp'</automated>
    <criteria>Both counts should increase by 6 (or expected base + 6)</criteria>
  </verify>
  <done>Verification confirms all JITRT functions have JIT_RUNTIME_API macro</done>
</task>

## Verification

### Automated Verification Commands

```bash
# 1. Verify all 6 specific functions have JIT_RUNTIME_API in header
echo "=== Header file coverage ==="
for func in JITRT_LoadGlobal JITRT_CallFunctionEx JITRT_CallFunctionExAwaited JITRT_MatchKeys JITRT_AllocateAndLinkGenAndInterpreterFrame JITRT_UnlinkGenFrameAndReturnGenDataFooter; do
  result=$(grep -c "JIT_RUNTIME_API.*$func" cinderx/Jit/jit_rt.h)
  echo "$func: $result occurrences (expected: 1)"
done

# 2. Verify implementations
echo "=== Implementation file coverage ==="
for func in JITRT_LoadGlobal JITRT_CallFunctionEx JITRT_CallFunctionExAwaited JITRT_MatchKeys; do
  result=$(grep -c "JIT_RUNTIME_API.*$func" cinderx/Jit/jit_rt.cpp)
  echo "$func: $result occurrences (expected: 1)"
done

# 3. Total JITRT function count with JIT_RUNTIME_API
echo "=== Total coverage ==="
echo "Header: $(grep -c 'JIT_RUNTIME_API.*JITRT_' cinderx/Jit/jit_rt.h) functions"
echo "Implementation: $(grep -c 'JIT_RUNTIME_API.*JITRT_' cinderx/Jit/jit_rt.cpp) functions"
```

### Success Criteria

1. **All 6 functions have JIT_RUNTIME_API in header**:
   - [ ] JITRT_LoadGlobal
   - [ ] JITRT_CallFunctionEx
   - [ ] JITRT_CallFunctionExAwaited
   - [ ] JITRT_MatchKeys
   - [ ] JITRT_AllocateAndLinkGenAndInterpreterFrame
   - [ ] JITRT_UnlinkGenFrameAndReturnGenDataFooter

2. **All 4 functions have JIT_RUNTIME_API in implementation**:
   - [ ] JITRT_LoadGlobal
   - [ ] JITRT_CallFunctionEx
   - [ ] JITRT_CallFunctionExAwaited
   - [ ] JITRT_MatchKeys
   - (Note: 2 functions already had it)

3. **Build verification** (if possible):
   - [ ] Code compiles without errors
   - [ ] No new warnings introduced

## Commit Strategy

This fix should be committed as a single atomic commit:

```bash
# After all tasks complete
git add cinderx/Jit/jit_rt.h cinderx/Jit/jit_rt.cpp
git commit -m "fix(jit): Add JIT_RUNTIME_API to 6 missing JITRT functions

Add JIT_RUNTIME_API macro to prevent LTO from inlining these runtime
entry points. Missing macro could cause runtime crashes when JIT code
calls functions at incorrect addresses after LTO inlining.

Functions fixed:
- JITRT_LoadGlobal
- JITRT_CallFunctionEx
- JITRT_CallFunctionExAwaited
- JITRT_MatchKeys
- JITRT_AllocateAndLinkGenAndInterpreterFrame
- JITRT_UnlinkGenFrameAndReturnGenDataFooter

Fixes: 01-VERIFICATION.md gap 'Incomplete JIT_RUNTIME_API Coverage'"
```

## Output

After completion, create `.planning/phases/01-foundation/01-01-fix-SUMMARY.md` documenting:
- Functions modified
- Lines changed
- Verification results
- Re-verification recommendation
