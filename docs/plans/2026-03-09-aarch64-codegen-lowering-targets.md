# AArch64 Codegen / JIT Lowering Targets

## Goal

Lock down the highest-value next optimization points for ARM JIT work by
tracing current benchmark hotspots through HIR, LIR, and AArch64 codegen.

## Current benchmark signal

- `nbody` is dominated by `advance`, with heavy `LoadAttrCached` /
  `StoreAttrCached` traffic and high refcount pressure.
- `richards` is dominated by `HandlerTask.fn`, `WorkTask.fn`, `IdleTask.fn`,
  `Task.__init__`, and `Task.runTask`, with attr traffic, method/call traffic,
  and dense control flow.
- `spectral_norm` is dominated by `eval_At_times_u`, `eval_A_times_u`,
  `eval_A`, and `eval_AtA_times_u`; the remaining expensive shape is local
  helper-call chains, not module attr loads.
- `fannkuch` is more about list/subscript specialization than AArch64 helper
  call lowering.

## Lowering path map

### 1. Attr and method caches still become helper calls in LIR

- `LoadAttrCached` lowers to `LoadAttrCache::invoke`.
- `LoadMethodCached` lowers to `LoadMethodCache::lookupHelper`.
- `LoadModuleAttrCached` lowers to `LoadModuleAttrCache::lookupHelper`.
- `StoreAttrCached` lowers to `StoreAttrCache::invoke`.

These all currently enter AArch64 codegen as immediate helper calls from
`cinderx/Jit/lir/generator.cpp`.

### 2. AArch64 helper calls still pay repeated literal-call cost

- Immediate call targets are planned in `planAarch64HotCallTargets()`.
- AArch64 call emission goes through `emitCall()`.
- The default hot-path shape is still `ldr literal` + `blr`.
- Shared stubs are only applied once a hot target crosses the call-count
  threshold.
- The only helper-specific fast path that exists today is the
  `LoadModuleAttrCache::lookupHelper` special-case stub.

This means the current code already has proof that helper-specific shared stub
or fast-stub lowering can work on ARM, but that machinery is not yet extended
to the object attr / method cache helpers that dominate `nbody` and `richards`.

### 3. VectorCall is expensive even before final call emission

- `VectorCall` and `CallMethod` lower in `cinderx/Jit/lir/generator.cpp`.
- In postalloc, `rewriteVectorCallFunctions()` builds a temporary args array on
  the stack before turning the instruction into a regular call.
- Calls then land in `_PyObject_Vectorcall` or `JITRT_Vectorcall` /
  `JITRT_Call`.

For `spectral_norm`, this means the remaining cost is not just final AArch64
`ldr literal + blr`; the JIT is still paying argument-array setup and generic
vectorcall dispatch for local helper functions.

### 4. Refcount is noisy but not the best next AArch64 target

- `Decref` is emitted inline in LIR.
- Long runs of `Decref` are already compacted into `BatchDecref` in HIR.
- The hottest current ARM pain points still look more like helper-call and
  call-shape overhead than missing AArch64 decref lowering.

## Ranked next targets

### P1. Extend helper-specific AArch64 lowering beyond LoadModuleAttrCached

Best target functions:

- `LoadAttrCache::invoke`
- `StoreAttrCache::invoke`
- `LoadMethodCache::lookupHelper`

Why this is first:

- These helpers sit directly under the dominant hotspots in `nbody` and
  `richards`.
- They currently lower as repeated helper calls from
  `cinderx/Jit/lir/generator.cpp`.
- The existing `LoadModuleAttrCache::lookupHelper` shared fast stub is already
  a working proof that targeted AArch64 helper lowering can reduce code size
  without needing full per-site inlining.

Recommended shape:

- Do not retry per-site inline expansion.
- Reuse the existing AArch64 hot-target planning and shared-stub machinery.
- Add narrow helper-specific fast stubs only for stable monomorphic cases.
- Start with exact-type / known-offset attr-cache cases that already have cache
  metadata rather than broad generic attr logic.

### P1. Add a cheaper exact-Python-function call path for local helper chains

Best target functions:

- `simplifyVectorCall()`
- `InvokeStaticFunction` emission in `cinderx/Jit/lir/generator.cpp`
- Inliner / preload path for exact `TFunc` calls

Why this is second:

- `spectral_norm` still carries `VectorCall=2` in `eval_AtA_times_u`.
- For exact `PyFunctionObject` targets, `simplifyVectorCall()` currently checks
  argument compatibility but usually leaves the operation as a generic
  `VectorCall`.
- On ARM this keeps the full stack-args-array setup in
  `rewriteVectorCallFunctions()` plus generic vectorcall dispatch.

Recommended shape:

- For exact `TFunc` targets with matching argcount and no kwargs/varargs,
  consider lowering to a direct invoke path instead of leaving a generic
  `VectorCall`.
- If semantics require safety guards, use the existing direct-function
  infrastructure (`InvokeStaticFunction` style) rather than trying to make
  `emitCall()` itself smarter.

### P2. Revisit method-call specialization for exact user types in richards

Best target functions:

- `LoadMethodCache::lookupHelper`
- `simplifyCallMethod()`
- `BuiltinLoadMethodElimination::Run()`

Why this is below attr fast paths:

- `richards` is method-heavy, but its top HIR mix still shows attr load/store
  traffic ahead of pure call lowering.
- Current load-method elimination is strongest for builtin / immutable-type
  cases, not user-defined task and packet classes.

Recommended shape:

- Prefer a narrow exact-type method fast path or cheaper load-method helper
  lowering over broad speculative inlining.
- If a method chain can be turned into a direct function call with known
  `nullptr` self semantics, do it before AArch64 lowering.

### P3. Leave decref and fannkuch for later

- `Decref` counts are high, but the pipeline already has inline lowering and
  `BatchDecref`.
- `fannkuch` points more toward missing list/subscript specialization than ARM
  helper-call lowering.

## Practical recommendation

If only one path should be attacked next, it should be:

1. AArch64 helper lowering for `LoadAttrCache::invoke` and
   `StoreAttrCache::invoke`.
2. Then exact-`TFunc` direct invoke for local helper chains in `spectral_norm`.

That ordering matches the current evidence:

- `nbody` and `richards` are the broadest remaining ARM wins.
- `spectral_norm` looks real but is more likely to need a JIT pipeline change
  above final AArch64 call emission.

## First-cut helper-stub design

### Why LoadAttr should come before StoreAttr

- `LoadAttr` already has an exact-type HIR specialization path, but dynamic
  benchmark code frequently misses that gate and falls back to
  `LoadAttrCached`.
- `StoreAttr` has no analogous HIR split-dict specialization today; it always
  falls through to `StoreAttrCached`.
- Even so, `LoadAttrCache::invoke` is still the safer first implementation:
  it only needs a hit path that returns a new reference and a miss path that
  jumps back to the helper.
- `StoreAttrCache::invoke` is more delicate because the hot path must update
  the value, handle insertion-order maintenance when overwriting a previously
  empty slot, and decref the old value safely.

### Minimal safe LoadAttr fast path

On Python 3.14 non-FT ARM builds, the most defensible first stub is:

1. Special-case `LoadAttrCache::invoke` in AArch64 helper-call emission, the
   same way `LoadModuleAttrCache::lookupHelper` is already special-cased.
2. In the stub, inspect the cache's first `AttributeMutator` entry.
3. Require:
   - non-empty entry
   - exact type match against `Py_TYPE(obj)`
   - mutator kind `kSplitInlineKnownOffset`
4. For that case:
   - check inline values are still valid
   - load the value directly from inline values storage
   - if non-null, incref inline and return
   - otherwise branch to the existing helper
5. On any mismatch, branch to the existing helper.

Why this is the right starting point:

- It matches the same 3.14 object-layout assumptions already used by the HIR
  split-dict specialization path and by the interpreter's
  `LOAD_ATTR_INSTANCE_VALUE` shape.
- It avoids trying to support descriptors, combined dicts, or generic managed
  dicts in the first iteration.
- It does not need a new deopt mechanism because cache invalidation is already
  driven by the existing inline-cache watcher path, and the stub can cheaply
  re-check the remaining layout-sensitive conditions at runtime.

### Phase-2 LoadAttr expansion

After the first `kSplitInlineKnownOffset` version is validated, the next
extension should be `kSplitKnownOffset`:

- require exact type match
- require managed dict exists
- require `dict->ma_keys == cached_keys`
- load `dict->ma_values->values[val_offset]`
- incref and return on non-null
- otherwise branch back to the helper

This is especially relevant to polymorphic user-code sites where inline values
have been materialized into a managed dict.

### Minimal safe StoreAttr fast path

The first practical store stub should be narrower than load:

- support only `kSplitInlineKnownOffset`
- require exact type match
- require inline values are valid
- require `_PyObject_GetManagedDict(obj) == NULL`
- inline the common overwrite case where the old slot is already non-null
- fall back to the helper when:
  - the slot is empty
  - inline values are invalid
  - a managed dict has been materialized
  - the mutator kind is not the supported one

This shape fits `nbody` especially well because hot loops mostly overwrite
already-initialized fields such as `x`, `y`, `z`, `vx`, `vy`, and `vz`.

### Threshold implication

The current shared-stub threshold of `24` is likely too high for attr helper
stubs if the goal is to hit hot benchmark functions:

- `nbody`'s dominant `advance` function was observed with
  `LoadAttrCached=20` and `StoreAttrCached=16`.
- Under the current generic target-count threshold, neither helper target would
  necessarily qualify for a shared stub in that function.

So the first attr-helper implementation should not blindly reuse the current
generic shared-stub threshold. It likely needs one of:

- a lower helper-specific threshold
- a separate env knob for attr-helper stubs
- or helper-specific planning based on attr op counts rather than the generic
  repeated-call-target threshold

### Why LoadMethod stays behind these two

`LoadMethodCache::lookupHelper` is still a worthwhile later target, but it is
more complex than `LoadAttrCache::invoke` because:

- it returns `LoadMethodResult` rather than a single object
- the fast path needs to preserve method/self semantics
- richards is likely to be polymorphic across multiple task subclasses at some
  method sites

So the current recommendation remains:

1. `LoadAttrCache::invoke`
2. `StoreAttrCache::invoke`
3. `LoadMethodCache::lookupHelper`

## Implementation sketch

### Files that should move in the first patch

- `cinderx/Jit/inline_cache.h`
- `cinderx/Jit/codegen/environ.h`
- `cinderx/Jit/codegen/gen_asm_utils.cpp`
- `cinderx/Jit/codegen/gen_asm.cpp`
- `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

### New offset accessors to add

The codegen layer currently has clean offset helpers for
`LoadModuleAttrCache`, but not for `AttributeCache` / `AttributeMutator`.
The first patch should add constexpr accessors so AArch64 codegen does not need
to reach into private layout manually.

Suggested accessors:

- `AttributeCache::entriesOffset()`
- `AttributeMutator::typeOffset()`
- `AttributeMutator::splitValOffsetOffset()`

These are enough for a first-entry-only `kSplitInlineKnownOffset` stub because
the hot path only needs:

- the first mutator's tagged `type_`
- the first mutator's `split_.val_offset`

### New codegen state

Mirror the existing module-attr special-case pattern:

- add `asmjit::Label load_attr_invoke_stub;` to `Environ`
- add a helper predicate in `gen_asm_utils.cpp` that recognizes
  `LoadAttrCache::invoke`
- optionally add a separate helper-stub threshold for attr helpers instead of
  reusing the generic `PYTHONJITAARCH64SHAREDSTUBMINCALLS`

### AArch64 register contract

For `LoadAttrCache::invoke(cache, obj, name)` the helper call ABI already gives
the stub exactly what it needs:

- `x0`: `LoadAttrCache* cache`
- `x1`: `PyObject* obj`
- `x2`: `PyObject* name` (unused on the fast path)
- return in `x0`

That makes this helper especially attractive for a first stub.

### Instruction skeleton for the first LoadAttr stub

The stub can follow the same structure as the existing
`LoadModuleAttrCache::lookupHelper` fast stub:

1. Load the first mutator's tagged `type_`.
2. Bail out if empty.
3. Compare `Py_TYPE(obj)` with `type_ & ~kKindMask`.
4. Check `(type_ & kKindMask) == kSplitInlineKnownOffset`.
5. Load `tp_basicsize` from the cached type object.
6. Check inline values `valid`.
7. Load `val_offset`.
8. Load `values[val_offset]`.
9. If non-null:
   - inline incref
   - return
10. Otherwise branch to the original helper target.

Pseudo-shape:

```text
x0 = cache
x1 = obj

entry_type = *(cache + entries_offset + type_offset)
if entry_type == 0: goto slow

cached_type = entry_type & ~7
kind = entry_type & 7
if kind != kSplitInlineKnownOffset: goto slow
if Py_TYPE(obj) != cached_type: goto slow

base = obj + cached_type->tp_basicsize
if *(base + PyDictValues.valid) == 0: goto slow

idx = *(cache + entries_offset + split_val_offset_offset)
value = *(base + PyDictValues.values + idx * sizeof(void*))
if value == NULL: goto slow

incref(value)
return value

slow:
  branch to original LoadAttrCache::invoke
```

### Important non-goals for patch 1

Patch 1 should explicitly avoid:

- supporting more than the first mutator entry
- supporting `kCombined`
- supporting descriptor-backed mutators
- supporting `kSplitKnownOffset`
- supporting free-threading
- supporting `StoreAttrCache::invoke`

That keeps the first patch aligned with the narrowest dynamic hot path that is
still common in `nbody` and `richards`.

### Test additions

The first patch should add ARM runtime tests for:

1. repeated object field loads on a managed-dict inline-values class:
   - compiled size shrinks when the stub is enabled
   - functional result stays correct
2. invalidation / fallback safety:
   - force the object shape away from the fast path
   - confirm compiled code still observes the correct value
3. a negative control:
   - a descriptor-backed attribute or combined-dict shape should not claim the
     same code-size win

This test shape should be modeled after the current module-attr ARM regression
tests rather than a broad benchmark-only validation.

## 2026-03-09 remote validation snapshot

Remote host:

- `root@124.70.162.35`
- workdir: `/root/work/cinderx-loadattrstub-20260309_103756`
- driver venv: `/root/venv-cinderx314-loadattrstub-20260309_103756`

Build and runtime status:

- remote build/install: pass
- `test_arm_runtime`: `18/18 OK`

Microbenchmark-style code size check:

- repeated dynamic `obj.x` loads, `PYTHONJITAARCH64LOADATTRSTUBMINCALLS=16`
  vs `1000000`
- compiled size: `8352 -> 8264` (`-88` bytes, about `-1.05%`)
- functional result unchanged

Light benchmark direction checks:

- `richards` direct run, 8 samples:
  - threshold `16`: median `0.0511616430s`
  - threshold `1000000`: median `0.0503859975s`
  - delta: about `+1.54%` regression
- `richards` direct run, threshold `24`:
  - median `0.0512540955s`
  - still slower than baseline
- `nbody` direct run, 3 samples:
  - threshold `16`: median `16.1798668410s`
  - threshold `1000000`: median `16.2089167300s`
  - delta: about `-0.18%` improvement

Current interpretation:

- The narrow `LoadAttrCache::invoke` fast stub is functionally safe enough to
  survive full ARM runtime checks.
- It produces a real code-size win on the intended repeated-load shape.
- The default threshold of `16` is not yet globally acceptable:
  - `nbody` shows a small positive signal
  - `richards` shows a stable negative signal
- Raising the threshold from `16` to `24` did not remove the `richards`
  regression in the quick direct-run check, so the next step should not be
  "just tune the threshold upward and ship it".

## 2026-03-09 exact-function helper experiment

Change summary:

- Reverted the `LoadAttrCache::invoke` stub experiment from code.
- Added `JITRT_CallExactFunction` and switched exact `TFunc` `VectorCall`
  lowering to use it instead of `_PyObject_Vectorcall`.
- The helper:
  - falls back to direct `func->vectorcall(...)` for general exact-function
    cases
  - uses `JITRT_GET_REENTRY(func->vectorcall)` only when the function is
    already JIT compiled and the call shape is simple (`no kwargs`,
    `no kwonly`, `no varargs/varkwargs`, exact argcount)

Remote validation:

- baseline workdir: `/root/work/cinderx-baseline-20260309_111410`
- current workdir: `/root/work/cinderx-callexact-20260309_110743`
- both builds/installations passed
- baseline `test_arm_runtime`: `17/17 OK`
- current `test_arm_runtime`: `18/18 OK`

Direct benchmark A/B:

- `richards`, 8 samples:
  - baseline median: `0.0503315985s`
  - current median: `0.0501109840s`
  - delta: about `-0.44%`
- `spectral_norm`, 4 samples:
  - baseline median: `13.8760596990s`
  - current median: `13.9130218570s`
  - delta: about `+0.27%`

Current interpretation:

- This helper-level exact-function optimization is functionally safe.
- It does produce a small positive signal on `richards`.
- It does not produce a stable, clearly positive cross-benchmark result yet.
- The most likely reason is that it only removes generic vectorcall dispatch,
  while leaving the expensive args-array materialization in place.
- Therefore, if the goal is a more generally stable ARM win, the next step
  should be above this helper layer: reduce or eliminate the args-array
  preparation for exact-function call shapes, or push more of these call chains
  into inlining/direct invoke forms that avoid the current `VectorCall`
  lowering path entirely.

## 2026-03-09 small-arity exact-function specialization

Change summary:

- Added `JITRT_CallExactFunction0/1/2`.
- In `simplifyVectorCall()`, exact `TFunc` calls with:
  - no kwargs
  - not awaited
  - no kwonly/varargs/varkwargs
  - exact argcount
  - arity `0..2`
  are now lowered to `CallStatic` helpers instead of the normal `VectorCall`
  path.
- This removes `rewriteVectorCallFunctions()` args-array materialization for
  those callsites.

Remote validation:

- current workdir: `/root/work/cinderx-callexact3-20260309_114040`
- current `test_arm_runtime`: `19/19 OK`

Direct benchmark A/B against baseline:

- `richards`, 8 samples:
  - baseline median: `0.0504970185s`
  - current median: `0.0503990265s`
  - delta: about `-0.19%`
- `spectral_norm`, 4 samples:
  - baseline median: `13.7807173390s`
  - current median: `13.9005776070s`
  - delta: about `+0.87%`

Current interpretation:

- The transformation is functionally safe.
- It did not convert into a stable general win.
- Even after removing JIT-side args-array materialization for small exact
  function calls, helper-call overhead remains high enough that
  `spectral_norm` regressed noticeably.
- This strongly suggests the next stable ARM gains are less likely to come from
  further helper reshaping, and more likely from:
  - true inlining of local helper chains
  - or reducing non-call overhead in the kernels themselves
