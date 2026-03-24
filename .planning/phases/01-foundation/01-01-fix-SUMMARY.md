---
phase: 01-foundation
plan: 01-fix
type: gap-closure
subsystem: jit_runtime
completed: 2026-03-23
---

# Phase 01 Plan 01-fix: Add JIT_RUNTIME_API to 6 Missing JITRT Functions

## Summary

Fixed incomplete JIT_RUNTIME_API macro coverage for 6 JITRT runtime entry point functions to prevent LTO inlining that could cause runtime crashes.

## Changes Made

### Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `cinderx/Jit/jit_rt.h` | +6, -6 | Added JIT_RUNTIME_API to 6 function declarations |
| `cinderx/Jit/jit_rt.cpp` | +3, -3 | Added JIT_RUNTIME_API to 3 function implementations |

### Functions Fixed

#### Header Declarations (jit_rt.h) - 6 functions

1. **Line 58** - `JITRT_AllocateAndLinkGenAndInterpreterFrame` - Added JIT_RUNTIME_API
2. **Line 71** - `JITRT_UnlinkGenFrameAndReturnGenDataFooter` - Added JIT_RUNTIME_API
3. **Line 167** - `JITRT_LoadGlobal` - Added JIT_RUNTIME_API
4. **Line 218** - `JITRT_CallFunctionEx` - Added JIT_RUNTIME_API
5. **Line 224** - `JITRT_CallFunctionExAwaited` - Added JIT_RUNTIME_API
6. **Line 609** - `JITRT_MatchKeys` - Added JIT_RUNTIME_API

#### Implementation Definitions (jit_rt.cpp) - 3 functions

1. **Line 878** - `JITRT_LoadGlobal` - Added JIT_RUNTIME_API
2. **Line 1133** - `JITRT_CallFunctionEx` - Added JIT_RUNTIME_API
3. **Line 1138** - `JITRT_CallFunctionExAwaited` - Added JIT_RUNTIME_API

**Note:** `JITRT_MatchKeys` is only declared in jit_rt.h but implemented elsewhere (wrapper around CPython's match_keys). The other 3 functions already had JIT_RUNTIME_API in the implementation.

## Verification Results

### Coverage Counts

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Header JIT_RUNTIME_API count | ~115 | 121 | +6 |
| Implementation JIT_RUNTIME_API count | ~114 | 117 | +3 |

### Success Criteria

- [x] All 6 function declarations have JIT_RUNTIME_API in jit_rt.h
- [x] All 3 implementable functions have JIT_RUNTIME_API in jit_rt.cpp
- [x] Changes committed (fdddf6fe)

## Impact

**Problem Prevented:** LTO (Link Time Optimization) may inline functions without `__attribute__((noinline, visibility(