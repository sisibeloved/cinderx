---
phase: 01-foundation
plan: 01
duration: 20min
completed_date: 2026-03-23
---

# Phase 01 Plan 01: Protect JIT Runtime Functions from LTO Inlining

## Summary

Successfully added `JIT_RUNTIME_API` macro with `__attribute__((noinline, visibility("default")))` to all JITRT_* runtime functions, preventing LTO from inlining them and causing incorrect code generation and runtime crashes.

## Commits

| Commit | Message | Files |
|--------|---------|-------|
| df2426d9 | feat(01-01): add JIT_RUNTIME_API macro and mark all JITRT functions | jit_rt.h, jit_rt.cpp |

## Changes Made

### cinderx/Jit/jit_rt.h
- Added `JIT_RUNTIME_API` macro definition after includes
- Marked **113** JITRT_* function declarations with the macro
- Preserved struct definitions (JITRT_StaticCallReturn, JITRT_StaticCallFPReturn) unchanged
- Preserved extern variable (JITRT_IterDoneSentinel) unchanged

### cinderx/Jit/jit_rt.cpp
- Marked **113** JITRT_* function definitions with the macro
- All function implementations now carry the noinline attribute

## Verification

### Build Verification
- ✅ CinderX module imports successfully: `python3 -c "import cinderx"`
- ✅ No compilation errors

### Symbol Table Verification
- ✅ 124 JITRT-related symbols visible in `_cinderx.so`
- ✅ All functions appear as external symbols (T flag in nm output)
- ✅ No inlined functions (no I flag)
- ✅ Example symbols:
  - `JITRT_Call(_object*, _object* const*, unsigned long, _object*)` - T
  - `JITRT_Cast(_object*, _typeobject*)` - T
  - `JITRT_Decref(_object*)` - T
  - `JITRT_GenSend(...)` - T

## Technical Details

### JIT_RUNTIME_API Macro
```cpp
#define JIT_RUNTIME_API \
    __attribute__((noinline, visibility("default")))
```

**Attributes:**
- `noinline`: Prevents LTO from inlining the function
- `visibility("default")`: Ensures the symbol is exported and callable from JIT-compiled code

### Why This Matters
When LTO inlines JIT runtime functions:
1. JIT-compiled code generates direct calls to these functions
2. LTO inlines the function bodies into the runtime library
3. At runtime, JIT code calls addresses that no longer match
4. This leads to crashes or silent data corruption

The `noinline` attribute ensures these helper functions remain as distinct entry points that JIT code can reliably call.

## Deviations from Plan

None - plan executed exactly as written.

## Metrics

| Metric | Value |
|--------|-------|
| Files Modified | 2 |
| Function Declarations Marked | 113 |
| Function Definitions Marked | 113 |
| Lines Changed | 235 insertions, 231 deletions |
| Build Status | ✅ Passing |
| Import Test | ✅ Passing |
| Symbol Verification | ✅ All external (T) |

## Related Requirements

- FR-001: Prevent LTO inlining of JIT runtime functions

## Next Steps

Plan 01-01 is complete. The JIT runtime functions are now protected from LTO inlining, which enables safe LTO builds for the CinderX extension.
