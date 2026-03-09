# ARM JIT Microcases

## Goal

Use benchmark-derived JIT microcases to expose AArch64 code shape problems more
directly than whole-benchmark runs.

## Added tooling

- `scripts/arm/jit_microcases_scan.py`
- `scripts/arm/run_jit_microcases_scan.sh`
- `scripts/arm/test_jit_microcases_scan.py`

The scanner reuses the existing AArch64 disassembly parsers from
`benchmark_hotspot_scan.py`, but feeds them smaller cases derived from:

- `nbody` attr-heavy update loops
- `richards` queue/method dispatch
- `spectral_norm` helper call chains
- `fannkuch` list/subscript churn

## Remote run

Host:

- `root@124.70.162.35`

Runtime:

- workdir: `/root/work/cinderx-baseline-20260309_111410`
- venv: `/root/venv-cinderx314-baseline-20260309_111410`

Artifacts:

- `/tmp/jit_microcases_scan.json`
- `/tmp/jit_microcases_scan.stdout`
- `/tmp/jit_microcases_scan.stderr`

## Aggregate signals

Across all microcases:

- `movk = 19043`
- `b_cond = 17413`
- `bl = 12041`
- `ldr_literal = 10253`
- `blr = 10175`
- `ldr_literal_blr_pair = 10175`
- `cbnz = 5032`
- `tbz = 1710`
- `cbz = 328`

This keeps reinforcing the same top AArch64 inefficiency buckets:

1. Repeated `ldr literal + blr` indirect helper/call targets.
2. Heavy `movk` use for 64-bit constant materialization.
3. Very branch-dense hot paths (`b.cond`, `cbz/cbnz`, `tbz`).

## Sequence motifs (v2 parser)

After extending the parser with a few optimization-relevant AArch64 motifs, the
aggregate signal is:

- `post_call_branch_check = 2725`
- `movk_heavy_call_window = 826`
- `guard_then_literal_blr = 344`

These are more actionable than raw mnemonic counts:

- `post_call_branch_check` means helper calls are frequently followed
  immediately by an exception/result branch. This suggests the cost is not just
  the call itself but the extra control flow around it.
- `movk_heavy_call_window` means some callsites still materialize targets
  through multi-instruction 64-bit immediates rather than a shorter literal or
  stub path.
- `guard_then_literal_blr` means branchy guard logic often still funnels into a
  helper call; this is especially relevant for attr/method caches and error
  checks.

## Case-specific takeaways

### `nbody_attr_update`

- top HIR:
  - `Decref = 42`
  - `XDecref = 38`
  - `LoadAttrCached = 15`
  - `StoreAttrCached = 13`
  - `VectorCall = 7`
- top patterns:
  - `movk = 3309`
  - `ldr_literal_blr_pair = 1869`
  - `b_cond = 3125`

Interpretation:

- This is a strong reproducer for attr load/store helper density.
- It is better than whole `nbody` for isolating store-side code shape.

### `richards_queue_dispatch`

- aggregate HIR:
  - `Decref = 36`
  - `StoreAttrCached = 14`
  - `LoadAttrCached = 13`
  - `CallMethod = 10`
  - `LoadMethodCached = 10`
  - `GetSecondOutput = 10`
- top patterns:
  - `movk = 6953`
  - `ldr_literal_blr_pair = 3622`
  - `b_cond = 6248`

Interpretation:

- This is a compact reproducer for richards-style branchy method-heavy queue
  logic.
- It is a good feeder for method-call and attr-helper experiments, but also
  confirms that branch density is a first-order ARM issue here.

### `spectral_helper_chain`

- aggregate HIR:
  - `VectorCall = 9`
  - `LoadGlobalCached = 10`
  - `GuardIs = 10`
  - `Decref = 35`
  - `Branch = 19`
- top patterns:
  - `movk = 7072`
  - `ldr_literal_blr_pair = 3742`
  - `b_cond = 6398`

With the richer motif parser:

- `post_call_branch_check = 1009`
- `movk_heavy_call_window = 270`
- `guard_then_literal_blr = 126`

Interpretation:

- This isolates the helper-chain problem much more cleanly than whole
  `spectral_norm`.
- The leaf `eval_A` is not the only issue; the surrounding list building,
  global loads, and call scaffolding are also large contributors.
- The new motif counts suggest this case is not just "too many calls"; it is
  "too many calls plus too many immediately-following result/error branches".

### `fannkuch_list_ops`

- aggregate HIR:
  - `LoadConst = 34`
  - `Decref = 29`
  - `StoreSubscr = 6`
  - `VectorCall = 7`
- top patterns:
  - `movk = 1709`
  - `ldr_literal_blr_pair = 942`
  - `b_cond = 1642`

Interpretation:

- This is the cleanest feeder for list/subscript lowering work.
- It also shows that list-heavy code still picks up a surprising amount of
  helper-call traffic.

## Practical next uses

- Use `nbody_attr_update` to test attr/store experiments before whole-benchmark
  validation.
- Use `richards_queue_dispatch` to test method-call and queue dispatch ideas
  without paying full richards cold-start noise.
- Use `spectral_helper_chain` to study `VectorCall`, `LoadGlobalCached`, and
  local helper-chain shape changes.
- Use `fannkuch_list_ops` to evaluate list/subscript changes.

## Current recommendation

If the goal is to understand ARM JIT code shape before attempting another code
 change, the most valuable derived cases are:

1. `spectral_helper_chain`
2. `richards_queue_dispatch`
3. `nbody_attr_update`

Those three together cover the main recurring AArch64 inefficiency signatures:

- helper-heavy indirect calls
- constant materialization
- branch density
- attr/method helper traffic

With the v2 parser, they also cover the most suspicious sequence-level motifs:

- indirect call followed immediately by branch checks
- movk-heavy call target materialization
- guarded miss paths that still end in `ldr literal + blr`

## Ranking view

Using the v3 scanner's derived metrics and case rankings:

### Highest indirect-call pressure

1. `nbody_attr_update` (`indirect_call_ratio ~= 0.473`)
2. `fannkuch_list_ops` (`~0.457`)
3. `spectral_helper_chain` (`~0.448`)
4. `richards_queue_dispatch` (`~0.444`)

Interpretation:

- All four are bad, but `nbody_attr_update` is the clearest reproducer for
  indirect helper-call density in attr-heavy code.

### Highest post-call branch pressure

1. `richards_queue_dispatch` (`post_call_branch_ratio ~= 0.122`)
2. `fannkuch_list_ops` (`~0.121`)
3. `spectral_helper_chain` (`~0.121`)
4. `nbody_attr_update` (`~0.111`)

Interpretation:

- `richards_queue_dispatch` is the best reproducer for helper call +
  immediate-result-check scaffolding.

### Highest movk-per-call pressure

1. `richards_queue_dispatch` (`movk_per_call ~= 0.857`)
2. `spectral_helper_chain` (`~0.853`)
3. `nbody_attr_update` (`~0.839`)
4. `fannkuch_list_ops` (`~0.828`)

Interpretation:

- `richards_queue_dispatch` and `spectral_helper_chain` are the strongest
  feeders for constant-materialization work.

### Highest attr-helper pressure

1. `richards_queue_dispatch` (`attr_ops = 47`)
2. `nbody_attr_update` (`attr_ops = 28`)
3. `spectral_helper_chain` (`attr_ops = 4`)
4. `fannkuch_list_ops` (`attr_ops = 0`)

Interpretation:

- If the next question is specifically attr/method cache lowering, use
  `richards_queue_dispatch` first, then `nbody_attr_update`.

### Highest Python-call pressure

1. `richards_queue_dispatch` (`call_ops = 15`)
2. `spectral_helper_chain` (`call_ops = 11`)
3. `fannkuch_list_ops` (`call_ops = 7`)
4. `nbody_attr_update` (`call_ops = 7`)

Interpretation:

- `richards_queue_dispatch` and `spectral_helper_chain` remain the best pair
  for call-shape experiments.

## Updated recommendation

If the goal is to keep using microcases as JIT-efficiency inputs, the best
priority order is now:

1. `richards_queue_dispatch`
   because it is worst on post-call branch checks, movk-per-call, and attr/call
   pressure together.
2. `spectral_helper_chain`
   because it is still one of the worst on call density, post-call branch
   checks, and movk-heavy call windows.
3. `nbody_attr_update`
   because it is the strongest reproducer for attr-heavy indirect helper calls
   and refcount-heavy update loops.

## `richards_queue_dispatch` function-level view

Per-function breakdown from the remote scan:

- `HandlerTask.fn`
  - `compiled_size = 3336`
  - dominant HIR:
    - `Decref = 15`
    - `LoadAttrCached = 7`
    - `CallMethod = 6`
    - `GetSecondOutput = 6`
    - `LoadMethodCached = 6`
    - `CondBranch = 6`
- `run`
  - `compiled_size = 2624`
  - dominant HIR:
    - `Decref = 10`
    - `GuardIs = 7`
    - `LoadGlobalCached = 7`
    - `VectorCall = 5`
- `Packet.__init__`
  - `compiled_size = 1112`
  - dominant HIR:
    - `StoreAttrCached = 5`
- `Packet.append_to`
  - `compiled_size = 1056`
  - dominant HIR:
    - `Branch = 4`
    - `CondBranch = 4`
    - `LoadAttrCached = 2`
    - `StoreAttrCached = 2`
- `HandlerTaskRec.workInAdd` / `deviceInAdd`
  - `compiled_size = 1000`
  - dominant HIR:
    - `CallMethod = 1`
    - `LoadMethodCached = 1`
    - `LoadAttrCached = 2`
    - `StoreAttrCached = 1`

### Most suspicious lowering points exposed by this microcase

1. `HandlerTask.fn` method-call chain

- This is the highest-value single reproducer in the case.
- The repeated shape is:
  - `LoadAttrCached`
  - `LoadMethodCached`
  - `GetSecondOutput`
  - `CallMethod`
  - followed by many branch checks and refcount ops

Interpretation:

- If there is a single richards-style lowering point worth targeting, it is
  the method/attr/helper chain inside `HandlerTask.fn`, not the outer harness.

2. `run` call + guard harness

- `run` is the clearest reproducer for:
  - repeated `LoadGlobalCached`
  - `GuardIs`
  - `VectorCall`

Interpretation:

- This is a good place to study how much code is spent getting to a stable
  callable before the actual call even happens.

3. `Packet.__init__` store-heavy path

- `Packet.__init__` is a compact reproducer for repeated `StoreAttrCached`.

Interpretation:

- If later work returns to store-side ARM lowering, this is a much better
  first input than whole richards.

### Current recommendation from the richards microcase

If you want one concrete next lowering target informed by JIT assembly rather
than by whole-benchmark noise, the best first target is:

- method-call / attr-helper code shape in `HandlerTask.fn`

If you want a secondary, cleaner feeder:

- `run` for `LoadGlobalCached + GuardIs + VectorCall`

## Refined richards subcases

To split `richards_queue_dispatch` into purer inputs, three additional
microcases were added:

- `richards_method_chain`
- `richards_attr_flow`
- `richards_post_call_checks`

### `richards_method_chain`

Purpose:

- isolate `append_to -> workInAdd/deviceInAdd` style method chaining

Signals:

- `attr_ops = 24`
- `call_ops = 8`
- `branch_ops = 23`
- `indirect_call_ratio ~= 0.471`
- `post_call_branch_ratio ~= 0.116`
- `movk_per_call ~= 0.863`

Interpretation:

- This is the cleanest reproducer for richards-style method dispatch plus attr
  traffic without the full `HandlerTask.fn` state machine.

### `richards_attr_flow`

Purpose:

- isolate branchy object state mutation without method dispatch on the hot path

Signals:

- `attr_ops = 27`
- `call_ops = 8`
- `branch_ops = 20`
- `indirect_call_ratio ~= 0.469`
- `post_call_branch_ratio ~= 0.116`
- `movk_per_call ~= 0.863`

Interpretation:

- This is the best richards-derived input for attr/store-heavy state updates.
- It confirms that even after stripping most method chaining, attr-heavy code
  still drags a lot of indirect-call and post-call-branch overhead with it.

### `richards_post_call_checks`

Purpose:

- isolate branch-selected call exits like `qpkt()` / `waitTask()`

Signals:

- `attr_ops = 19`
- `call_ops = 13`
- `branch_ops = 18`
- `indirect_call_ratio ~= 0.411`
- `post_call_branch_ratio ~= 0.099`
- `movk_heavy_call_ratio ~= 0.059`

Interpretation:

- This is the cleanest reproducer for "call plus immediate branch check"
  scaffolding.
- It has lower attr pressure than the other two, but higher pure call pressure.

## What this changes

The original `richards_queue_dispatch` case is still useful as a mixed,
realistic feeder, but the refined cases make the next choices clearer:

1. If you want to study method/dispatch shape first:
   use `richards_method_chain`
2. If you want to study attr/store traffic first:
   use `richards_attr_flow`
3. If you want to study call-result/error-check scaffolding first:
   use `richards_post_call_checks`

That is a better decomposition than jumping straight from whole richards to a
single large synthetic case.

## Refined richards subcases: function-level motifs

Remote per-function objdump motif summaries highlight the following:

### `richards_method_chain`

- `run`
  - `compiled_size = 2536`
  - `ldr_literal_blr_pair = 41`
  - `post_call_branch_check = 4`
  - `movk = 42`
- `Packet.append_to`
  - `compiled_size = 1056`
  - `ldr_literal_blr_pair = 13`
  - `post_call_branch_check = 6`
  - `movk = 24`
- `HandlerTaskRec.workInAdd` / `deviceInAdd`
  - `compiled_size = 1000`
  - `ldr_literal_blr_pair = 14`
  - `post_call_branch_check = 3`
  - `movk = 22`

Interpretation:

- The method chain case does isolate method-heavy traffic, but much of the
  actual call density is still concentrated in the outer `run` harness.
- `Packet.append_to` is the cleanest small reproducer for method-path
  `post_call_branch_check`.

### `richards_attr_flow`

- `run`
  - `compiled_size = 2888`
  - `ldr_literal_blr_pair = 42`
  - `post_call_branch_check = 6`
  - `movk = 50`
- `HandlerTask.attr_flow`
  - `compiled_size = 2480`
  - `ldr_literal_blr_pair = 39`
  - `post_call_branch_check = 8`
  - `movk = 63`
  - `movk_heavy_call_window = 1`
- `Packet.__init__`
  - `compiled_size = 1008`
  - `ldr_literal_blr_pair = 13`
  - `post_call_branch_check = 7`
  - `movk = 27`

Interpretation:

- `HandlerTask.attr_flow` is now the strongest single reproducer for
  attr-heavy richards-style code shape.
- It combines high attr pressure with more post-call branch checks than the
  method-chain helpers.

### `richards_post_call_checks`

- `run`
  - `compiled_size = 3056`
  - `ldr_literal_blr_pair = 26`
  - `post_call_branch_check = 6`
  - `b_cond = 66`
  - `bl = 53`
- `HandlerTask.call_edges`
  - `compiled_size = 1728`
  - `ldr_literal_blr_pair = 26`
  - `post_call_branch_check = 2`
  - `b_cond = 34`
- `HandlerTask.qpkt`
  - `compiled_size = 752`
  - `ldr_literal_blr_pair = 10`
  - `post_call_branch_check = 1`

Interpretation:

- The post-call-check case succeeded in isolating the branch-selected call exit
  structure, but the worst branch density is still concentrated in its `run`
  harness.
- `HandlerTask.call_edges` is the best direct feeder if the goal is to study
  "call then branch" lowering specifically.

## Updated richards priority

Within the richards family, the most useful next feeders are:

1. `HandlerTask.attr_flow`
   for attr-heavy code shape plus strong post-call branch pressure.
2. `Packet.append_to`
   for compact method-chain call behavior.
3. `HandlerTask.call_edges`
   for branch-selected call exits.

## Method/call helper focus

Looking only at the method-chain-rich richards microcase:

- `run`
  - `LoadMethodCached = 2`
  - `CallMethod = 2`
  - `GetSecondOutput = 2`
  - `VectorCall = 4`
  - but also includes more surrounding harness noise
- `HandlerTaskRec.workInAdd`
  - `LoadMethodCached = 1`
  - `CallMethod = 1`
  - `GetSecondOutput = 1`
  - `LoadAttrCached = 2`
  - `StoreAttrCached = 1`
  - `compiled_size = 1000`
- `HandlerTaskRec.deviceInAdd`
  - same shape as `workInAdd`

Interpretation:

- The cleanest small reproducer for the
  `LoadMethodCached + GetSecondOutput + CallMethod` chain is not
  `Packet.append_to`; it is `HandlerTaskRec.workInAdd` / `deviceInAdd`.
- `Packet.append_to` itself is more useful as a downstream callee that still
  shows helper-heavy attr/store behavior, but it does not directly carry the
  method-chain HIR shape.
- `run` is useful for studying the larger composed pattern, but it is no
  longer the smallest clean method-chain input.

## Updated method/call recommendation

If the next line of work switches away from store helpers and toward
method/call helpers, the best richards-derived input order is now:

1. `HandlerTaskRec.workInAdd`
2. `HandlerTaskRec.deviceInAdd`
3. `run`

That gives the smallest clean method-chain reproducer first, then the larger
composed harness.

## Method/call chain map

For the cleanest method helper reproducer, `HandlerTaskRec.workInAdd`, the
current chain is:

1. HIR
   - `LoadMethodCached`
   - `GetSecondOutput`
   - `CallMethod`
2. LIR lowering
   - `LoadMethodCached` lowers to `LoadMethodCache::lookupHelper`
   - `GetSecondOutput` lowers to `LoadSecondCallResult`
   - `CallMethod` lowers to a `VectorCall` helper using `JITRT_Call`
3. Runtime
   - `LoadMethodCache::lookupHelper` eventually relies on `_PyObject_GetMethod`
   - `JITRT_Call` then unpacks the method/function shape and calls
     `_PyObject_VectorcallTstate`

### Why this matters

This means the cost is not just "a method call":

- first helper: resolve method shape (`LoadMethodCache::lookupHelper`)
- second helper: do the actual method/function call (`JITRT_Call`)
- plus the plumbing for `GetSecondOutput`

So the current ARM method-chain problem is a stacked two-helper path, not a
single helper inefficiency.

## Interpreter vs JIT method path

The 3.14 interpreter already has specialized method paths such as:

- `LOAD_ATTR_METHOD_NO_DICT`
- `LOAD_ATTR_METHOD_WITH_VALUES`
- `CALL_BOUND_METHOD_EXACT_ARGS`
- `CALL_BOUND_METHOD_GENERAL`

Those interpreter paths do three important things that the current JIT method
chain does not do together:

1. Separate method-descriptor loading from generic attribute lookup using
   type-version and dict/value guards.
2. Keep `self` and callable in an already-expanded bound-method shape.
3. Dispatch calls through specialized bound-method paths instead of a generic
   "resolve then vectorcall any callable" helper chain.

By contrast, the current JIT path for `HandlerTaskRec.workInAdd` is:

1. helper call to `LoadMethodCache::lookupHelper`
2. explicit `GetSecondOutput` plumbing
3. helper call to `JITRT_Call`
4. `JITRT_Call` still ends up in `_PyObject_VectorcallTstate`

So compared to the interpreter specialized path, the JIT is missing:

- fused method load + call handling
- bound-method specific call fast paths
- direct frame/setup handling for common exact-args Python function targets

## Method optimization candidates

### Option M1: dedicated bound-method call helper

Shape:

- Keep `LoadMethodCached` as-is.
- Replace the `GetSecondOutput + CallMethod -> JITRT_Call` chain with a more
  specific helper for the common "callable + self + exact args" shape.

Pros:

- lower implementation risk than changing `LoadMethodCache`
- directly attacks the second helper in the stacked chain

Cons:

- still leaves the first method-resolution helper in place

### Option M2: helper-specific fast stub for `LoadMethodCache::lookupHelper`

Shape:

- Keep `CallMethod` / `JITRT_Call` as-is.
- Add an AArch64 helper-specific fast stub for hot cached method hits, similar
  in spirit to the module-attr stub work.

Pros:

- directly attacks the first helper in the stacked chain
- can be benchmarked on `HandlerTaskRec.workInAdd`

Cons:

- method semantics are more complex than plain attr load/store
- may still leave the second helper dominant

### Option M3: fuse the whole method chain

Shape:

- recognize `LoadMethodCached + GetSecondOutput + CallMethod`
- lower to a single dedicated bound-method call path

Pros:

- matches the interpreter's direction most closely
- attacks the actual stacked-chain problem instead of only one helper

Cons:

- highest implementation risk
- likely needs a new JIT runtime helper or a new lowering form

## Recommended order for method work

If you want the lowest-risk prototype first:

1. Option M1
2. Option M2
3. Option M3

If you want the path most aligned with how the interpreter wins:

1. Option M3
2. Option M1
3. Option M2

Given the current evidence, the pragmatic choice is:

- start with Option M1 on `HandlerTaskRec.workInAdd`

That keeps the prototype small while directly testing whether the second helper
(`JITRT_Call`) is the larger part of the richards method-chain cost.

## Body-window observations

After teaching the scanner to prefer body windows over entry scaffolding, the
richards subcases show much clearer recurring motifs.

### `Packet.append_to`

Representative body windows:

- `ldr x16, ... ; blr x16`
- immediately followed by
  `tbz w0, #31, ...`

Interpretation:

- This strongly suggests a helper call that returns a signed status or tagged
  result in `w0`, followed by an immediate error/success branch.
- For method-heavy richards-like code, the cost is not just the indirect call
  but the fixed "call then test bit 31" scaffolding after it.

### `HandlerTaskRec.workInAdd` / `deviceInAdd`

Representative body windows:

- repeated `ldr literal + blr`
- repeated `blr -> tbz w0, #31`

Interpretation:

- These are compact reproducers of the same method-chain helper pattern as
  `Packet.append_to`, but in a slightly larger call context.

### `HandlerTask.attr_flow`

Representative body windows:

- repeated `ldr literal + blr`
- repeated `blr -> tbz w0, #31`
- one `movk`-heavy call window:
  - multiple `movk` into `x1`
  - then `ldr x16, ... ; blr x16`

Interpretation:

- This is the strongest evidence so far that attr-heavy code is paying both:
  - indirect helper call cost
  - and separate constant/address materialization cost before some calls
- The `movk` chain into `x1` is a likely sign of materializing a constant
  object or metadata address before the helper call.

### `HandlerTask.call_edges`

Representative body windows:

- repeated `ldr literal + blr`
- one clear `blr -> tbz w0, #31`

Interpretation:

- This is the cleanest reproducer for "call plus immediate branch check" in the
  richards family.
- It is the best input if the next analysis wants to understand the specific
  helper-return convention behind these `tbz w0, #31` checks.

## Concrete lowering suspects

From these body windows, the most suspicious ARM inefficiency sources now look
like:

1. helper calls that return status/error in `w0` and immediately branch on it
2. helper call targets still reached through `ldr literal + blr`
3. callsites that also materialize constants/addresses with multiple `movk`
   instructions before the helper call

That is a more precise statement than the earlier aggregate "too many helper
calls" diagnosis.

## `tbz w0, #31` trace

The AArch64 codegen maps `InstrGuardKind::kNotNegative` to:

- `tbz wN, sign_bit, skip`
- otherwise branch to deopt/error

So a `blr ... ; tbz w0, #31, ...` sequence is a strong signal that:

- the call returned a signed integer-like status in `w0`
- the JIT immediately emitted a not-negative guard on that return value

This is distinct from object-return callsites, which are more likely to use
`cbz/cbnz`-style checks.

### Function-level counts in richards-derived cases

- `richards_method_chain`
  - `Packet.append_to`: `post_call_tbz_w0_signbit = 4`
  - `Packet.__init__`: `3`
  - `HandlerTaskRec.workInAdd`: `2`
  - `HandlerTaskRec.deviceInAdd`: `2`
- `richards_attr_flow`
  - `HandlerTask.attr_flow`: `7`
  - `Packet.__init__`: `6`
  - `run`: `3`
  - `HandlerTaskRec.__init__`: `3`
- `richards_post_call_checks`
  - `Packet.__init__`: `3`
  - `run`: `2`
  - `HandlerTask.call_edges`: `1`
  - `HandlerTask.qpkt`: `1`
  - `HandlerTask.waitTask`: `1`

### Interpretation

- The heaviest `tbz w0,#31` pressure is in attr/store-heavy functions, not in
  pure call wrappers.
- `HandlerTask.attr_flow` and `Packet.__init__` are the strongest reproducers
  for signed-status helper calls followed by immediate guard checks.
- This points more strongly toward store/compare/helper-return conventions than
  toward generic `CallMethod` object-return overhead.

### Strongest current attribution

`Packet.__init__` is the cleanest attribution case:

- Its optimized HIR is almost entirely:
  - repeated `StoreAttrCached`
  - one `ListExtend`
  - no `CallMethod`
  - no `LoadMethodCached`
- In LIR lowering:
  - `StoreAttrCached` explicitly appends `InstrGuardKind::kNotNegative`
  - `ListExtend` does not append that guard
- In AArch64 codegen:
  - `kNotNegative` lowers to a `tbz` check on the sign bit

So the repeated `blr ... ; tbz w0, #31, ...` windows in `Packet.__init__`
should currently be treated as strong evidence for `StoreAttrCached::invoke`
plus its immediate signed-status guard, not for generic Python-call overhead.

## Ranking view for sign-bit post-call checks

Across all current microcases:

- highest `post_call_tbz_w0_signbit_ratio`
  1. `spectral_helper_chain`
  2. `richards_queue_dispatch`
  3. `richards_post_call_checks`
  4. `richards_method_chain`
  5. `richards_attr_flow`

- highest `not_negative_source_total`
  1. `richards_attr_flow` (`15`)
  2. `richards_queue_dispatch` (`15`)
  3. `nbody_attr_update` (`14`)
  4. `richards_method_chain` (`9`)

Interpretation:

- `post_call_tbz_w0_signbit_ratio` alone is not enough to attribute the source
  of the check; `spectral_helper_chain` scores highest there, but it has almost
  no obvious HIR ops that directly map to `kNotNegative`.
- `not_negative_source_total` is the better prioritization signal when the goal
  is to find places where helper-return status guards are likely emitted by the
  JIT lowering itself.
- By that metric, `richards_attr_flow`, `richards_queue_dispatch`, and
  `nbody_attr_update` remain the strongest next inputs for store/status-helper
  investigations.

## Store-status-helper focus group

The scanner now emits a cross-case `store_status_helper` focus group that
collects functions with:

- `StoreAttr*` / `StoreSubscr` / `DeleteAttr` HIR sources that can lower to
  `kNotNegative`
- plus per-function `post_call_tbz_w0_signbit` / `post_call_branch_check`
  counts and suspicious body windows

Top entries from the current run:

1. `nbody_attr_update:Body.__init__`
   - `StoreAttrCached = 7`
   - `post_call_tbz_w0_signbit = 8`
   - `post_call_branch_checks = 8`
   - compact, store-heavy, low noise
2. `fannkuch_list_ops:fannkuch_step`
   - `StoreSubscr = 6`
   - `post_call_tbz_w0_signbit = 12`
   - `post_call_branch_checks = 33`
   - useful as a separate subscript/status feeder, not a store-attr feeder
3. `nbody_attr_update:advance_step`
   - `StoreAttrCached = 6`
   - `post_call_tbz_w0_signbit = 9`
   - `post_call_branch_checks = 22`
   - mixes stores with real loop pressure
4. `richards_attr_flow:HandlerTask.attr_flow`
   - `StoreAttrCached = 6`
   - `post_call_tbz_w0_signbit = 7`
   - `post_call_branch_checks = 8`
   - best richards-style store/status reproducer
5. `richards_queue_dispatch:Packet.__init__`
   - `StoreAttrCached = 5`
   - `post_call_tbz_w0_signbit = 6`
   - `post_call_branch_checks = 7`
   - compact initializer reproducer

Interpretation:

- `Body.__init__` is currently the cleanest pure `StoreAttrCached` feeder.
- `HandlerTask.attr_flow` is the best richards-style feeder.
- `Packet.__init__` is the best compact reproducer inside the richards family.
- `advance_step` is useful when you want to validate store-status changes under
  loop pressure rather than in a tiny initializer.
- `fannkuch_step` belongs in the same broad status-return family, but it should
  be treated separately because its source is `StoreSubscr`, not `StoreAttr`.

## Updated practical recommendation

If the next step is specifically about `StoreAttrCached::invoke` plus its
`kNotNegative`-derived `tbz w0,#31` checks, the best input order is now:

1. `Body.__init__`
2. `HandlerTask.attr_flow`
3. `Packet.__init__`
4. `advance_step`

That ordering balances:

- attribution clarity
- richards relevance
- loop realism

## Init vs update split

The `store_status_helper` focus group now classifies functions as:

- `init_like`
  - repeated `StoreAttrCached`
  - little or no `LoadAttrCached`
- `update_like`
  - both `StoreAttrCached` and `LoadAttrCached` present

Current top entries:

### Best init-like feeders

1. `nbody_attr_update:Body.__init__`
   - `store_shape = init_like`
   - `StoreAttrCached = 7`
   - `post_call_tbz_w0_signbit = 8`
2. `richards_attr_flow:Packet.__init__`
   - `store_shape = init_like`
   - `StoreAttrCached = 5`
   - `post_call_tbz_w0_signbit = 6`
3. `richards_queue_dispatch:Packet.__init__`
   - `store_shape = init_like`
   - `StoreAttrCached = 5`
   - `post_call_tbz_w0_signbit = 3`

### Best update-like feeders

1. `nbody_attr_update:advance_step`
   - `store_shape = update_like`
   - `StoreAttrCached = 6`
   - `LoadAttrCached = 15`
   - `post_call_tbz_w0_signbit = 9`
2. `richards_attr_flow:HandlerTask.attr_flow`
   - `store_shape = update_like`
   - `StoreAttrCached = 6`
   - `LoadAttrCached = 9`
   - `post_call_tbz_w0_signbit = 7`
3. `richards_queue_dispatch:HandlerTask.fn`
   - `store_shape = update_like`
   - `StoreAttrCached = 4`
   - `LoadAttrCached = 7`
   - `post_call_tbz_w0_signbit = 5`

## Updated next-step recommendation

If the goal is to understand or optimize `StoreAttrCached::invoke`, the cleanest
path is now:

1. start with `Body.__init__` for init-like stores
2. then `HandlerTask.attr_flow` for update-like stores
3. keep `Packet.__init__` as a compact richards-side confirmation case
4. use `advance_step` only after a change looks promising, because it adds loop
   pressure and more surrounding noise

## Code-level StoreAttr path map

Current runtime path in `StoreAttrCache::invoke`:

1. `StoreAttrCache::doInvoke()`
   - linearly scans cache entries for `entry.type() == Py_TYPE(obj)`
   - on hit, dispatches to `AttributeMutator::setAttr()`
   - on miss, falls back to `invokeSlowPath()`

2. `StoreAttrCache::invokeSlowPath()`
   - calls `PyObject_SetAttr(obj, name, value)`
   - if `tp_setattro == PyObject_GenericSetAttr`, it calls `fill(type, name)`
   - `fill()` installs an `AttributeMutator` for later hits

3. `AttributeCache::fill()`
   - for managed-dict heap types on 3.14:
     - `set_split(..., inline_values=True)` when the type advertises inline values
     - otherwise `set_split(..., inline_values=False)` / `set_combined(...)`

4. `AttributeMutator::setAttr()`
   - dispatches by mutator kind:
     - `kSplitInline` / `kSplitInlineKnownOffset`
     - `kSplit` / `kSplitKnownOffset`
     - `kCombined`
     - descriptor/member/classvar kinds

### Likely path for init-like feeders

For plain Python classes like `Body` and `Packet` under 3.14, the most likely
path is:

- first store:
  - miss cache
  - `PyObject_SetAttr`
  - `fill(type, name)` installs split/inline-values mutator
- next store hits:
  - `AttributeMutator::kSplitInline`
  - then upgrades to `kSplitInlineKnownOffset`
  - then `SplitMutator::setAttrInlineKnownOffset()`

Why this is important:

- `setAttrInlineKnownOffset()` is the most direct store path:
  - checks `values->valid`
  - checks no managed dict has been materialized
  - writes `values->values[val_offset] = Py_NewRef(value)`
  - updates insertion order only when `old_value == nullptr`

So `Body.__init__` / `Packet.__init__` are not just "store-heavy"; they are
likely the best feeders for the `old_value == nullptr` branch of
`setAttrInlineKnownOffset()`.

### Likely path for update-like feeders

For `advance_step` / `HandlerTask.attr_flow`, the most likely hit path is still
the same split-inline store family, but with a different dynamic condition:

- `old_value != nullptr`
- therefore no insertion-order update
- still pays:
  - helper call into `StoreAttrCache::invoke`
  - signed-status return
  - immediate `kNotNegative` guard in JIT code

This means the init/update split is probably not about a completely different
helper; it is more likely about different branches inside the same
split-inline-known-offset fast store path.

### Best current hypothesis

If the goal is to understand or optimize the hottest `blr -> tbz w0,#31`
store-related pattern, the most likely branch-level split is:

- `Body.__init__` / `Packet.__init__`
  - insertion path (`old_value == nullptr`)
- `HandlerTask.attr_flow` / `advance_step`
  - overwrite path (`old_value != nullptr`)

That is the strongest current code-level decomposition of the store problem.

## Dedicated store microcases

Two dedicated store-only cases were added to separate first-write from
overwrite behavior:

- `store_init_inline_values`
- `store_overwrite_inline_values`

### `store_init_inline_values`

Key function:

- `init_attrs`
  - `StoreAttrCached = 6`
  - `post_call_tbz_w0_signbit = 7`
  - `post_call_branch_checks = 7`
  - `compiled_size = 944`

Interpretation:

- This is now the cleanest purpose-built feeder for init-like store traffic.
- It is smaller and cleaner than `Body.__init__`, though `Body.__init__` still
  remains a more benchmark-derived input.

### `store_overwrite_inline_values`

Key functions:

- `overwrite_attrs`
  - `StoreAttrCached = 4`
  - `LoadAttrCached = 4`
  - `post_call_tbz_w0_signbit = 5`
  - `post_call_branch_checks = 6`
  - `compiled_size = 1360`
- `Box.__init__`
  - `StoreAttrCached = 4`
  - `post_call_tbz_w0_signbit = 5`
  - `compiled_size = 768`

Interpretation:

- `overwrite_attrs` is the best purpose-built feeder for update-like store
  traffic.
- It is cleaner than `advance_step` and closer to the richards attr-flow shape
  than `Box.__init__`.

## Updated store recommendation

If the immediate goal is to study `StoreAttrCached::invoke` without extra whole-
benchmark noise, the best order is now:

1. `store_init_inline_values:init_attrs`
2. `store_overwrite_inline_values:overwrite_attrs`
3. `Body.__init__`
4. `HandlerTask.attr_flow`

That ordering gives the cleanest init/update split first, then falls back to
benchmark-derived realism.

## JIT helper vs interpreter fast path

The strongest implementation-level comparison is now:

### JIT `StoreAttrCached`

Current path:

1. generated code issues helper call to `StoreAttrCache::invoke`
2. helper scans cache entries for `entry.type() == Py_TYPE(obj)`
3. helper dispatches through `AttributeMutator::setAttr()`
4. split-inline case eventually lands in `SplitMutator::setAttrInlineKnownOffset()`
5. helper returns `0` / negative error code
6. generated code applies `InstrGuardKind::kNotNegative`
   which becomes `blr ... ; tbz w0, #31, ...`

Most relevant store fast path body today:

- `_PyObject_InlineValues(obj)`
- `_PyObject_GetManagedDict(obj)`
- `if (!values->valid || dict) ...`
- `old_value = Ref<>::steal(values->values[val_offset])`
- `values->values[val_offset] = Py_NewRef(value)`
- optional `_PyDictValues_AddToInsertionOrder(...)`
- `return 0`

### Interpreter `STORE_ATTR_INSTANCE_VALUE`

Specialized 3.14 interpreter path:

1. guard exact type version
2. guard "no managed dict" and "inline values valid"
3. compute slot address directly from cached offset
4. `FT_ATOMIC_STORE_PTR_RELEASE(*value_ptr, value)`
5. update insertion order only when old slot was null
6. `Py_XDECREF(old_value)`
7. continue execution without an out-of-line helper return/guard sequence

### Concrete extra costs in the JIT path

Compared to the interpreter specialization, the current JIT path adds:

- out-of-line helper call / return
- helper-side cache-entry scan and mutator dispatch
- separate signed-status return convention
- separate post-call `kNotNegative` guard (`tbz w0,#31`)
- C++ RAII `Ref<>` object management around `old_value`

### Strongest current hypothesis

For the hottest store cases, the overhead is likely dominated by:

1. the helper call/return boundary itself
2. the extra signed-status guard after the helper call
3. second-order costs from helper-side branching and refcount management

That is more precise than simply saying "StoreAttrCached is expensive".

## StoreAttr optimization candidates

Based on the current evidence, the realistic implementation options are:

### Option A: helper-specific overwrite-only fast stub

Shape:

- Special-case `StoreAttrCache::invoke` in AArch64 call emission.
- In the stub, only handle:
  - exact-type cache hit
  - split-inline-known-offset shape
  - inline values valid
  - no managed dict
  - `old_value != nullptr`
- On any mismatch, branch to the existing helper.

What it removes:

- helper-side cache-entry scan
- helper-side mutator dispatch
- C++ `Ref<>` overhead in the hot overwrite case

What it keeps:

- helper call boundary
- signed-status return convention
- post-call `tbz w0,#31`

Why it is the best first prototype:

- lowest semantic risk
- no insertion-order update path
- directly targets the update-like feeders:
  - `store_overwrite_existing:overwrite_existing`
  - `HandlerTask.attr_flow`
  - `advance_step`

### Option B: helper-specific init+overwrite fast stub

Shape:

- Extend Option A to also handle `old_value == nullptr`
- Inline insertion-order maintenance in the stub

What it adds:

- broader coverage
- directly helps `Body.__init__` / `Packet.__init__`

Why it is riskier:

- insertion-order maintenance becomes part of emitted assembly
- more interpreter-layout coupling

### Option C: full lowering-side fast path (no helper return on hit)

Shape:

- Stop modeling hot `StoreAttrCached` as "call helper, then guard result"
- Lower hit path into native code directly and only branch to the helper on miss

What it removes:

- helper call/return on hit
- post-call `tbz w0,#31` on hit

Why it is not the first move:

- highest engineering risk
- larger code-shape change
- most likely to regress code size if done too broadly

## Recommended order

The current best sequence is:

1. Option A on overwrite-only split-inline-known-offset stores
2. if positive, widen to Option B
3. only then consider Option C

That ordering matches the current microcase evidence:

- init-like and overwrite-like call-site shapes are very similar
- the overwrite-only path is the simplest branch-level target
- the largest obvious costs today are helper boundary and helper-internal work,
  not yet proof that full inlining is required first

## Overwrite-only store stub prototype

A first AArch64 overwrite-only `StoreAttrCache::invoke` fast stub prototype was
built with these properties:

- only handles `kSplitInlineKnownOffset`
- requires exact type match
- requires inline values valid
- requires no managed dict
- requires `old_value != nullptr`
- inlines:
  - incref(new value)
  - slot store
  - decref(old value)
- falls back to the original helper on every other case

Current status:

- remote ARM build: pass
- `test_arm_runtime`: pass

Microcase size signal:

- `store_overwrite_existing:overwrite_existing`
  - with stub: `1080`
  - without stub: `936`
  - delta: `+144` bytes
- `store_init_inline_values:init_attrs`
  - with stub: `1080`
  - without stub: `944`
  - delta: `+136` bytes

Interpretation:

- The prototype is functionally viable enough to compile and pass runtime
  checks.
- But the stub body is currently too large to win on compact store microcases.
- This suggests a full in-assembly overwrite stub is not an immediate
  low-risk/low-size win in its current form.

The prototype is now disabled by default unless
`PYTHONJITAARCH64STOREATTRSTUBMINCALLS` is explicitly set, so helper-level
measurements are no longer confounded by it.

## Helper-level store optimization snapshot

Two low-risk helper changes were then tested:

- `StoreAttrCache::doInvoke()` now checks the first cache entry before looping
- `SplitMutator::setAttrInlineKnownOffset()` now uses raw pointer
  `Py_INCREF/Py_DECREF` logic instead of `Ref<>` RAII

With the large store stub disabled:

- `init_attrs`
  - baseline compiled size: `944`
  - current compiled size: `944`
- `overwrite_existing`
  - baseline compiled size: `936`
  - current compiled size: `944`

Interpretation:

- The helper-only change is functionally safe.
- It does not provide a code-size win on the minimal store feeders.
- On the overwrite case it slightly increases compiled size, but far less than
  the large assembly stub did.
- This makes it a plausible base state for further experimentation, but not yet
  a proven ARM optimization by itself.
- If work continues on this direction, the next likely improvement would be a
  narrower helper-level fast path rather than a large shared assembly stub.

## Method-shaped call helper prototype

After pausing the `StoreAttrCached` line, the next isolated experiment targeted
the method/call chain itself:

- baseline source: `HEAD` (`b14f114e`)
- current source: a 4-file overlay only
  - `cinderx/Jit/jit_rt.cpp`
  - `cinderx/Jit/jit_rt.h`
  - `cinderx/Jit/lir/generator.cpp`
  - `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- runtime idea:
  - keep `LoadMethodCache::lookupHelper`
  - replace `CallMethod`'s generic `JITRT_Call` helper with a method-shaped
    `JITRT_CallMethod`
  - let the method helper skip the generic callable-shape handling that
    `JITRT_Call` performs

Remote verification setup:

- host: `root@124.70.162.35`
- baseline workdir: `/root/work/cinderx-methodcall-base-20260309_193054`
- baseline venv: `/root/venv-cinderx314-methodcall-base-20260309_193054`
- current workdir: `/root/work/cinderx-methodcall-cur-20260309_193054`
- current venv: `/root/venv-cinderx314-methodcall-cur-20260309_193054`

Build and runtime status:

- baseline: `test_arm_runtime` `17/17 OK`
- current: `test_arm_runtime` `19/19 OK`

Steady-state microcase harness:

- harness path:
  - `/root/work/incoming/method_call_helper_bench.py`
- saved JSON:
  - baseline:
    `/root/work/arm-sync/method_call_helper_base_seq_20260309_193054.json`
  - current:
    `/root/work/arm-sync/method_call_helper_cur_seq_20260309_193054.json`

Method-chain result (`richards_method_chain`-style synthetic run):

- baseline median: `0.0028662370s`
- current median: `0.0026403430s`
- delta: about `-7.88%`
- compiled size:
  - `run`: `2664 -> 2664`
  - `HandlerTaskRec.workInAdd`: `1000 -> 1000`
  - `HandlerTaskRec.deviceInAdd`: `1000 -> 1000`
  - `Packet.append_to`: `1056 -> 1056`

Steady-state `richards` result (`Richards.run(3)` with work-area reset between
samples):

- baseline median: `0.3387018390s`
- current median: `0.3387574120s`
- delta: about `+0.02%`
- compiled size:
  - `Richards.run`: `8736 -> 8736`
  - `schedule`: `1560 -> 1560`
  - `Task.runTask`: `2008 -> 2008`
  - `HandlerTask.fn`: `3336 -> 3336`

Interpretation:

- The dedicated method-shaped runtime helper clearly helps the smallest pure
  method-chain reproducer.
- That win does not automatically carry through to a fuller steady-state
  `richards` shape; on the broader reproducer the signal is effectively
  neutral.
- Code size staying flat across the measured `richards` functions suggests this
  is a runtime-helper effect, not a code-size effect.

Direct process-level `richards.py` check:

- command shape:
  - `PYTHONJITAUTO=50 <venv>/bin/python cinderx/benchmarks/richards.py 1`
- saved JSON:
  - baseline:
    `/root/work/arm-sync/method_call_helper_base_direct_richards_20260309_193054.json`
    and
    `/root/work/arm-sync/method_call_helper_base_direct_richards_rerun_20260309_193054.json`
  - current:
    `/root/work/arm-sync/method_call_helper_cur_direct_richards_20260309_193054.json`
    and
    `/root/work/arm-sync/method_call_helper_cur_direct_richards_rerun_20260309_193054.json`

Observed shape:

- both baseline and current showed bimodal samples with occasional slow outliers
- trailing fast samples clustered near `0.145s` to `0.150s`
- this check is too noisy to support a benchmark-level claim either way

Current conclusion for Option M1:

- worth keeping as a technically valid direction
- not yet enough evidence for a submission-quality ARM win
- if method/call work continues, the next better target is probably not another
  call-helper tweak, but collapsing more of the
  `LoadMethodCached + GetSecondOutput + CallMethod` chain

## Fused `CallMethodCached` prototype

The next prototype tried exactly that deeper collapse:

- new HIR shape: `CallMethodCached`
- simplifier match:
  - `LoadMethodCached`
  - `GetSecondOutput`
  - `CallMethod`
- lowering strategy:
  - reuse `Instruction::kVectorCall`
  - pass `LoadMethodCache*` in the helper/callable slot
  - build an args array shaped as `[receiver, name, user_args...]`
  - let a new runtime helper do lookup + call in one helper invocation

Remote verification:

- host: `root@124.70.162.35`
- workdir: `/root/work/cinderx-methodchain-collapse-20260309_201651`
- venv: `/root/venv-cinderx314-methodchain-collapse-20260309_201651`
- runtime tests: `19/19 OK`

Comparison target:

- previous method-helper-only current:
  - `/root/work/cinderx-methodcall-cur-20260309_193054`
  - `/root/venv-cinderx314-methodcall-cur-20260309_193054`

Saved JSON:

- previous current:
  - `/root/work/arm-sync/methodcall_prevcur_seq_20260309_201651.json`
- fused prototype:
  - `/root/work/arm-sync/methodcall_collapse_seq_20260309_201651.json`
  - `/root/work/arm-sync/methodcall_collapse_seq_rerun_20260309_201651.json`

Results versus the previous method-helper-only current:

Method-chain microcase:

- previous current median: `0.0026780060s`
- fused prototype median:
  - first run: `0.0029157510s`
  - rerun: `0.0027384200s`
- direction: regression in both runs
- compiled size:
  - `HandlerTaskRec.workInAdd`: `1000 -> 1016`
  - `HandlerTaskRec.deviceInAdd`: `1000 -> 1016`
  - `run`: `2672 -> 2720`

Steady-state `richards` (`run(3)`):

- previous current median: `0.2956236940s`
- fused prototype median:
  - first run: `0.4124724410s`
  - rerun: `0.3080336630s`
- direction: regression in both runs
- compiled size:
  - `HandlerTask.fn`: `3336 -> 3392`
  - `Task.runTask`: `2008 -> 1968`
  - `schedule`: `1560 -> 1512`
  - `Richards.run`: `8736 -> 8592`

Interpretation:

- Reducing the helper count was not enough by itself.
- The fused path adds its own overhead:
  - an extra `name` value has to be materialized into the call args array
  - the runtime helper still has to perform lookup and then repack the final
    call arguments
- On the measured richards method-chain shapes, that overhead outweighed the
  removed helper boundary.

Current conclusion for deeper chain collapse, first cut:

- this concrete `CallMethodCached` design is not the right next move
- it should not remain as an active optimization prototype
- if method/call work continues, the next candidate should avoid carrying
  `receiver + name` through the generic vectorcall args-array path

## `LoadMethodCache::lookupHelper` AArch64 disassembly readout

After rejecting the fused `CallMethodCached` path, the next check was the
existing method-lookup helper itself on ARM:

- binary:
  - `/root/work/cinderx-methodcall-cur-20260309_193054/scratch/lib.linux-aarch64-cpython-314/_cinderx.so`
- symbols:
  - `jit::LoadMethodCache::lookupHelper` at `0x1c4f28`
  - `jit::LoadMethodCache::lookup` at `0x1c4f2c`
  - `jit::LoadMethodCache::lookupSlowPath` at `0x1c5104`

Key machine-code observations:

1. `lookupHelper` is only a 4-byte trampoline

- body:
  - `b 158b10 <jit::LoadMethodCache::lookup(...)@plt>`

Interpretation:

- JIT-generated code calls `lookupHelper`
- `lookupHelper` immediately branches to a PLT entry for `lookup`
- so the current path already has an extra branch before the real lookup logic
  starts

2. `lookup` is fully unrolled across the 4 cache entries

- function size: `0x188` bytes
- first-entry compare:
  - load `Py_TYPE(obj)`
  - compare against `entries_[0].type`
- then three more repeated entry checks at offsets:
  - `+0x34`
  - `+0x4c`
  - `+0x64`

Interpretation:

- even the hot helper path pays for a full unrolled 4-entry probe structure
- a monomorphic first-entry hit is sharing code shape with the colder
  multi-entry miss-to-next-entry cases

3. first-entry hit is much simpler than the whole helper body suggests

For entry 0, the hot successful path is roughly:

- compare cached type vs `Py_TYPE(obj)`
- if `keys_version == 0`:
  - go straight to result load
- else:
  - call `_PyObject_GetDictPtr`
  - if dict is null, treat as hit
  - otherwise compare `dict->ma_keys->dk_version`
- load cached method object
- incref cached method
- incref receiver object
- return the two-result pair

Interpretation:

- there is a real narrow hit shape worth targeting
- it is much smaller than the full helper, even though heap-type cases still
  need `_PyObject_GetDictPtr`

4. `lookupSlowPath` is large and branchy

- function size: `0x318` bytes
- contains:
  - `PyObject_GetAttr`
  - `_PyType_GetDict`
  - `_PyType_Lookup`
  - `PyDescr_IsData`
  - `_PyObject_GetDictPtr`
  - `PyDict_GetItem`
  - `fill`
  - descriptor `blr`
  - multiple decref / dealloc branches

Interpretation:

- any design that simply “gets to slow path less often” is not enough
- the most realistic win is to avoid entering `lookup` entirely on the common
  first-entry hit

### Implication for the next ARM method experiment

The most plausible next target is now:

- an AArch64 helper-specific stub for `LoadMethodCache::lookupHelper`

Recommended first shape:

- shared stub, not per-callsite inline lowering
- first-entry-only hit path
- hit conditions:
  - `entries_[0].type == Py_TYPE(obj)`
  - if `keys_version == 0`, hit directly
  - otherwise:
    - `dictptr = _PyObject_GetDictPtr(obj)`
    - hit if dict is null
    - or if `dict->ma_keys->dk_version == keys_version`
- hit action:
  - load `entries_[0].value`
  - inline incref(cached method)
  - inline incref(obj)
  - return `LoadMethodResult{value, obj}` in registers
- miss action:
  - branch to the original helper target literal

Why this is better-founded than the rejected fused-call prototype:

- it preserves the existing HIR / LIR call shape
- it does not carry `receiver + name` through the generic vectorcall args-array
  path
- it attacks a concrete machine-code inefficiency now directly visible in
  `_cinderx.so`:
  - JIT callsite
  - helper trampoline
  - unrolled cache scan
  - only then the actual hot-hit logic

Why it still needs to stay narrow:

- heap-type richards classes will usually have `keys_version != 0`, so the
  stub still needs `_PyObject_GetDictPtr`
- extending the stub to all 4 entries would likely erase its code-size
  advantage
- this should remain an env-gated experiment first, not a default-on path

## `LoadMethodCache::lookupHelper` first-entry stub prototype

An env-gated AArch64 helper-specific stub was then built for
`LoadMethodCache::lookupHelper`.

Shape:

- shared stub, not per-callsite inline lowering
- first-entry-only
- enabled only when `PYTHONJITAARCH64LOADMETHODSTUBMINCALLS` is set
- hit conditions:
  - `entries_[0].type == Py_TYPE(obj)`
  - `keys_version == 0`, or
  - receiver type has `Py_TPFLAGS_MANAGED_DICT` and either:
    - managed dict is null, or
    - `dict->ma_keys->dk_version == keys_version`
- hit action:
  - load `entries_[0].value`
  - inline incref(cached method)
  - inline incref(obj)
  - return `{value, obj}`
- miss action:
  - branch to the original helper literal

Remote validation:

- host: `root@124.70.162.35`
- workdir:
  - `/root/work/cinderx-loadmethodstub-20260309_210647`
- venv:
  - `/root/venv-cinderx314-loadmethodstub-20260309_210647`
- runtime tests:
  - `20/20 OK`

Same-build env on/off comparison:

- stub off:
  - `PYTHONJITAARCH64LOADMETHODSTUBMINCALLS=1000000`
  - JSON:
    `/root/work/arm-sync/loadmethod_stub_off_seq_20260309_210647.json`
- stub on:
  - `PYTHONJITAARCH64LOADMETHODSTUBMINCALLS=1`
  - JSON:
    `/root/work/arm-sync/loadmethod_stub_on_seq_20260309_210647.json`
  - rerun JSON:
    `/root/work/arm-sync/loadmethod_stub_on_seq_rerun_20260309_210647.json`
- threshold probes:
  - `=2`:
    `/root/work/arm-sync/loadmethod_stub_min2_seq_20260309_210647.json`
  - `=4`:
    `/root/work/arm-sync/loadmethod_stub_min4_seq_20260309_210647.json`

### Off vs on (`min_calls = 1`)

Method-chain microcase:

- off median: `0.0026210530s`
- on median:
  - first run: `0.0027148690s`
  - rerun: `0.0026646960s`
- direction: regression
- compiled size:
  - `HandlerTaskRec.workInAdd`: `1000 -> 1112`
  - `HandlerTaskRec.deviceInAdd`: `1000 -> 1112`
  - `run`: `2664 -> 2776`

Steady-state `richards` (`run(3)`):

- off median: `0.3230216710s`
- on median:
  - first run: `0.4355810360s`
  - rerun: `0.3607598200s`
- direction: regression
- compiled size:
  - `HandlerTask.fn`: `3336 -> 3424`
  - `Task.runTask`: `2008 -> 2104`
  - `schedule`: `1560 -> 1664`
  - `Richards.run`: `8736 -> 8824`

### Threshold probes

`min_calls = 2`

- `workInAdd` / `deviceInAdd` no longer use the stub
- `run` still grows: `2664 -> 2768`
- `richards` median: `0.3885220360s`
- still clearly worse than stub-off

`min_calls = 4`

- `run` falls back to baseline size: `2664`
- `schedule` falls back to baseline size: `1560`
- but `HandlerTask.fn` / `Task.runTask` / `Richards.run` remain larger
- `richards` median: `0.4855749660s`
- even worse than `min_calls = 1`

Interpretation:

- The first-entry hit logic is real and correct, but the stub still loses.
- The added guard and managed-dict machinery inflate code size enough to wipe
  out the helper-boundary savings.
- This loss persists even when thresholds are raised enough to keep the stub
  off the smallest one-callsite functions.

Current conclusion:

- `LoadMethodCache::lookupHelper` as a first-entry AArch64 shared stub is not a
  viable mainline optimization in this shape.
- Like the earlier `StoreAttrCached` shared stub, this should be treated as a
  negative experiment and removed from the active code path.

## AArch64 object-literal-pool prototype

After the helper-stub line stalled, a broader call-site prototype targeted the
other obvious ARM inefficiency in the richards-derived scans:

- repeated `movz/movk` materialization of `kObject` immediates
- especially from `getNameFromIdx()`, which currently emits:
  - `Instruction::kMove`
  - `Imm{reinterpret_cast<uint64_t>(name.get()), OperandBase::kObject}`

Prototype shape:

- AArch64 hot-section only
- env-gated by `PYTHONJITAARCH64OBJECTLITERALPOOL`
- for `Move Reg, Imm<Object>`:
  - use a per-function literal pool entry
  - emit `ldr reg, [pc-relative-literal]`
  - instead of `movz/movk` immediate materialization

Remote validation:

- host: `root@124.70.162.35`
- workdir:
  - `/root/work/cinderx-objlitpool-20260309_215046`
- venv:
  - `/root/venv-cinderx314-objlitpool-20260309_215046`
- runtime tests:
  - `20/20 OK`

Same-build env on/off micro-bench:

- off:
  - `PYTHONJITAARCH64OBJECTLITERALPOOL=0`
  - JSON:
    `/root/work/arm-sync/object_literal_pool_off_seq_20260309_215046.json`
    and
    `/root/work/arm-sync/object_literal_pool_off_rerun_20260309_215046.json`
- on:
  - `PYTHONJITAARCH64OBJECTLITERALPOOL=1`
  - JSON:
    `/root/work/arm-sync/object_literal_pool_on_seq_20260309_215046.json`
    and
    `/root/work/arm-sync/object_literal_pool_on_rerun_20260309_215046.json`

### Steady-state performance

Method-chain microcase:

- off medians:
  - `0.0027739630s`
  - rerun `0.0028350920s`
- on medians:
  - `0.0025359870s`
  - rerun `0.0025949880s`
- direction: consistent win

Steady-state `richards` (`run(3)`):

- off medians:
  - `0.4784508280s`
  - rerun `0.2956199360s`
- on medians:
  - `0.5034488820s`
  - rerun `0.4039929810s`
- direction: consistent regression

### Code-size shape

Method-chain microcase:

- `Packet.append_to`: `1056 -> 1048`
- `HandlerTaskRec.workInAdd`: `1000 -> 1000`
- `HandlerTaskRec.deviceInAdd`: `1000 -> 1000`
- `run`: `2664 -> 2696` / `2704`

Full `richards` steady-state feeder:

- `HandlerTask.fn`: `3336 -> 3352`
- `Task.runTask`: `2008 -> 2040`
- `schedule`: `1560 -> 1568`
- `Richards.run`: `8736 -> 8520`

### Structural motif effect

Using `jit_microcases_scan.py` on `richards_queue_dispatch`:

- off JSON:
  - `/root/work/arm-sync/richards_queue_dispatch_objlit_off_20260309_215046.json`
- on JSON:
  - `/root/work/arm-sync/richards_queue_dispatch_objlit_on_20260309_215046.json`

Aggregate motif deltas:

- `movk`: `2093 -> 445`
- `movk_heavy_call_window`: `128 -> 0`
- `HandlerTask.fn movk`: `72 -> 10`
- `run movk`: `48 -> 11`
- `HandlerTaskRec.workInAdd movk`: `22 -> 10`
- `HandlerTaskRec.deviceInAdd movk`: `22 -> 10`

Interpretation:

- The prototype successfully attacked the intended motif.
- It proves that a large fraction of the current `movk` pressure is coming from
  object/name immediate materialization rather than from call targets
  themselves.

But:

- removing `movk` pressure was still not enough to make the broader richards
  shape faster
- the remaining costs
  - indirect helper calls
  - post-call branch checks
  - args-array/call scaffolding
  still dominate
- and the extra literal-load traffic plus modest code-shape growth hurt the
  larger workload

Current conclusion:

- a broad AArch64 object-literal pool is not a submission-quality ARM win in
  this shape
- it should not remain enabled as an active code experiment
- however, it provides a useful negative result:
  - `movk` is a real contributor
  - but it is not the dominant limiter for richards once reduced
  - the next better target is the remaining generic call-site scaffolding,
    especially `VectorCall`/postalloc work

## Store-side member descriptor lowering

A narrower HIR-side fix was then implemented instead of introducing new
`LoadSlot` / `StoreSlot` opcodes:

- new simplification:
  - `StoreAttr` on an exact receiver type
  - `tp_setattro == PyObject_GenericSetAttr`
  - descriptor resolved at compile time as `PyMemberDescr_Type`
  - descriptor kind limited to `T_OBJECT` / `T_OBJECT_EX`
  - non-`READONLY`
- lowering used existing HIR ops:
  - `LoadField(..., borrowed=false)` to capture the previous value
  - `StoreField(..., previous=...)` for the actual store
- refcounting is therefore handled by the existing `StoreField` /
  refcount-insertion pipeline rather than by handwritten codegen

Files touched:

- `cinderx/Jit/hir/simplify.cpp`
- `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

Remote validation:

- host: `root@124.70.162.35`
- workdir:
  - `/root/work/cinderx-storemember-20260309_230918`
- venv:
  - `/root/venv-cinderx314-storemember-20260309_230918`
- runtime tests:
  - `20/20 OK`

Behavioral/HIR regression guard:

- new runtime test verifies a bound-receiver `__slots__` shape now compiles as:
  - `LoadField >= 1`
  - `StoreField >= 1`
  - `StoreAttrCached == 0`

Boundary check on the original motivating shape:

- plain method case:
  - `Counter.increment(self)`
- current final HIR on ARM remains:
  - `LoadAttrCached = 1`
  - `StoreAttrCached = 1`

Interpretation:

- the store-side gap is real and now fixed for exact-type member-descriptor
  shapes
- but this does **not** solve the broader “ordinary Python method receiver is
  not exact” problem
- so this change is best viewed as:
  - a correct, architecture-consistent cleanup
  - and a prerequisite for a future load/store slot optimization story
  - not a full solution to the original `Counter.increment` issue by itself

Micro-benchmark on a shape that actually hits the new lowering:

- shape:
  - global bound `Counter()` instance
  - `def f(v): obj.value = v; return obj.value`
- old build HIR:
  - `LoadField = 1`
  - `StoreAttrCached = 1`
- new build HIR:
  - `LoadField = 2`
  - `StoreField = 1`

Measured on ARM:

- old compiled size: `712`
- new compiled size: `728`
- old median: `0.0087047800s`
- new median: `0.0077599980s`
- delta: about `-10.85%`

Interpretation:

- on a case where the new store-side lowering actually fires, it produces a
  real runtime win despite a small code-size increase
- this makes the change worth keeping

Current conclusion:

- keep the store-side member-descriptor simplification
- do not over-claim it as the full `__slots__` solution
- the remaining missing piece for the original issue is a way to reach similar
  lowering when the receiver is not already known to be exact

## Builder support for `LOAD_ATTR_SLOT` / `STORE_ATTR_SLOT`

The next step used the interpreter's existing specialization signal instead of
trying to recover receiver exactness from HIR types alone.

What changed:

- `BytecodeInstruction::specializedOpcode()` now preserves:
  - `LOAD_ATTR_SLOT`
  - `STORE_ATTR_SLOT`
- `BytecodeInstruction` now exposes cache readers:
  - `cacheU16(instruction_offset)`
  - `cacheU32(instruction_offset)`
- `HIRBuilder` now consumes those specialized opcodes directly:
  - reads the cached `type_version`
  - reads the cached slot `offset`
  - emits a `tp_version_tag` equality guard
  - lowers to existing `LoadField` / `StoreField`

This avoids inventing new HIR opcodes and reuses the same field/refcount
machinery already used by the exact-type member-descriptor path.

Remote validation:

- host: `root@124.70.162.35`
- workdir:
  - `/root/work/cinderx-slotspec-20260309_234321`
- venv:
  - `/root/venv-cinderx314-slotspec-20260309_234321`
- runtime tests:
  - `21/21 OK`

Key functional result on the original motivating shape:

Python source:

- `class Counter: __slots__ = ('value',)`
- `def increment(self): self.value = self.value + 1`

Old build final HIR:

- `LoadAttrCached = 1`
- `StoreAttrCached = 1`

New build final HIR:

- `LoadField = 6`
- `StoreField = 1`
- `Guard = 2`
- `PrimitiveCompare = 2`
- `LoadAttrCached = 0`
- `StoreAttrCached = 0`

That confirms the builder now reaches field lowering for ordinary Python method
receivers when the interpreter has already specialized the bytecode to slot
operations.

### Counter increment micro-benchmark

Script:

- warm interpreter specialization with 200k interpreted calls
- `force_compile(Counter.increment)`
- run 500k increments for timing

Remote results:

- old build:
  - JSON produced by `/root/venv-cinderx314-methodcall-cur-20260309_193054/bin/python /root/work/incoming/tmp_counter_increment_bench.py`
  - compiled size: `792`
  - median: `0.1920519090s`
- new build:
  - JSON produced by `/root/venv-cinderx314-slotspec-20260309_234321/bin/python /root/work/incoming/tmp_counter_increment_bench.py`
  - compiled size: `824`
  - median: `0.0857234350s`

Delta:

- about `-55.36%`

Interpretation:

- This is the first change in this line that directly fixes the original
  `Counter.increment(self)` reproducer.
- The code size grows slightly, but the helper-call removal dominates.
- Reusing interpreter specialization state is substantially more effective than
  trying to recover exact-type information later in HIR.

Current conclusion:

- keep both:
  - store-side member-descriptor simplification
  - builder support for `LOAD_ATTR_SLOT` / `STORE_ATTR_SLOT`
- this is now the most promising slot optimization direction found so far
- the next logical extension would be:
  - `LOAD_ATTR_INSTANCE_VALUE`
  - `STORE_ATTR_INSTANCE_VALUE`
  which use the same interpreter-specialization-driven strategy

## `LOAD_ATTR_INSTANCE_VALUE` / `STORE_ATTR_INSTANCE_VALUE` builder attempt

The obvious next step was to extend the same strategy to interpreter-specialized
instance-value opcodes:

- `LOAD_ATTR_INSTANCE_VALUE`
- `STORE_ATTR_INSTANCE_VALUE`

Prototype shape:

- preserve those specialized opcodes in `BytecodeInstruction::specializedOpcode()`
- read cached payloads directly from bytecode inline-cache slots
- emit:
  - type-version guard
  - managed-inline-values validity checks
  - field-address / array-item plumbing
  - existing `LoadField` / `StoreField` where possible
- for store, deopt instead of handling the `old_value == nullptr` insertion
  order case in HIR

This compiled and passed correctness tests, but the resulting HIR/code shape
was far too heavy.

Remote build used:

- workdir:
  - `/root/work/cinderx-slotspec-20260309_234321`
- venv:
  - `/root/venv-cinderx314-slotspec-20260309_234321`

Micro-benchmark used:

- ordinary managed-dict class:
  - `class Counter:`
  - `def __init__(self): self.value = 0`
  - `def increment(self): self.value = self.value + 1`
- warm 200k interpreted calls to trigger interpreter specialization
- `force_compile(Counter.increment)`
- 500k timed increments

Old build:

- HIR:
  - `LoadAttrCached = 1`
  - `StoreAttrCached = 1`
- compiled size: `792`
- median: `0.1541431730s`

Prototype build:

- HIR:
  - `Guard = 6`
  - `LoadField = 11`
  - `LoadFieldAddress = 2`
  - `LoadArrayItem = 2`
  - `BitCast = 1`
  - `StoreField = 1`
  - `LoadAttrCached = 0`
  - `StoreAttrCached = 0`
- compiled size: `968`
- median: `0.4940332220s`

Delta:

- about `+220%`

Interpretation:

- Reusing the interpreter signal was still the right idea.
- But for `INSTANCE_VALUE`, the cache payload does not give enough information
  to reach a cheap HIR shape directly.
- Reconstructing the needed `valid` / inline-values state in HIR added too much
  scaffolding:
  - extra guards
  - extra field loads
  - address arithmetic
  - array-item loads

Current conclusion:

- keep the `SLOT` specialized-opcode support
- do **not** keep the `INSTANCE_VALUE` builder lowering in this form
- if this line is revisited, it likely needs either:
  - a cheaper dedicated HIR op for inline-values access, or
  - richer cache/type information than the current bytecode payload exposes
