# Findings & Decisions

## Requirements
- Analyze the current branch of `/Users/luchen/Repo/cinderx` relative to official CPython source in `/Users/luchen/Repo/cpython`.
- Use `ebf955df7a89ed0c7968f79faec1de49f61ed7cb` as the benchmark baseline reference.
- Produce a detailed plan, not code changes.
- Explain likely causes for regressions in these benchmarks, prioritized: `coroutines`, `comprehensions`, `richards`, `richards_super`, `go`, `deltablue`, `raytrace`, `nqueens`, `float`, `generators`, `python_startup`.
- Focus on Arm vs AMD performance differences; possible causes include x86-specific wins, Arm-specific regressions, or larger x86 uplift than Arm.
- The main performance environment is isolated Linux Arm.
- Local macOS Arm can be used for functional probing, reproducer reduction, dump generation, and path validation, but not as final performance evidence.
- Because the target environment is network-isolated, the preferred workflow is: analyze likely difference points first, then generate one-click scripts that collect the minimum confirmation data in the isolated environment.

## Research Findings
- Skills in use for this turn: `using-superpowers`, `writing-plans`, `planning-with-files`.
- `planning-with-files` helper `session-catchup.py` was unavailable at the expected path, so planning files were initialized manually.
- The upstream baseline commit `ebf955df7a89ed0c7968f79faec1de49f61ed7cb` is available in `/Users/luchen/Repo/cpython` but not in the local `/Users/luchen/Repo/cinderx` history, so direct `git diff <commit>...HEAD` inside `cinderx` does not work.
- The comparison method therefore needs to be cross-repo and path-based: compare `cinderx` HEAD working tree against `/Users/luchen/Repo/cpython` at commit `ebf955...`, then focus on runtime hot paths relevant to the benchmark list.
- `cinderx` is an extension-style repository, not a full CPython source tree. The relevant deltas versus stock CPython are concentrated in:
  - `cinderx/Interpreter/3.14/*` for interpreter-loop changes
  - `cinderx/Jit/*` for compilation/runtime/codegen behavior
  - `cinderx/StaticPython/*` and checked-container paths
  - startup glue such as `setup.py`, `cinderx/PythonBin/sitecustomize.py`, and the ARM pyperformance setup scripts
- Existing local deliverables already document verified ARM issues and fixes in:
  - interpreter overhead vs CPython
  - `raytrace` mixed-numeric deopts
  - `float` accumulator and `**2` lowering
  - `generators` attr/decref expansion
  - mutable `LOAD_GLOBAL` guards
- Current branch recent commits are heavily concentrated in JIT HIR/LIR optimization work, especially:
  - mixed numeric guards
  - float fast paths
  - generator attr/decref lowering
  - list slice / len arithmetic / compact-long loop unboxing
- Current code shows ARM-specific defaults enabled in OSS 3.14:
  - `ENABLE_ADAPTIVE_STATIC_PYTHON` default on ARM in `setup.py`
  - `ENABLE_LIGHTWEIGHT_FRAMES` default on ARM in `setup.py`
  - pyperformance worker env auto-loads CinderX through generated `sitecustomize.py`
- Current interpreter-loop deltas relative to CPython include:
  - delayed adaptive enablement via `Ci_DelayAdaptiveCode`, `Ci_AdaptiveThreshold`, and `is_adaptive_enabled()`
  - extra `adaptive_enabled` parameter threaded through tail-call interpreter helpers
  - conditional `ADVANCE_ADAPTIVE_COUNTER`
  - `CI_SET_ADAPTIVE_INTERPRETER_ENABLED_STATE` and `CI_UPDATE_CALL_COUNT`
  - custom PEP 523 and awaitable/coroutine handling through `Ci_EvalFrame`, `JitCoro_GetAwaitableIter`, and `JitGen_yf`
- Current JIT code includes an explicit benchmark-informed policy:
  - exact int guards on specialized numeric opcodes are only kept for code objects with a backedge
  - float exact guards remain enabled for float-only leaf helpers
- The plan should now optimize for offline execution:
  - convert each likely difference point into a small number of measurable checks
  - package those checks into one-click scripts instead of relying on iterative interactive exploration in the isolated environment

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Structure the work as repository-state check -> diff mapping -> benchmark correlation -> prioritized plan | Keeps the deliverable evidence-based and easy to execute later |
| Organize benchmark analysis by shared root-cause cluster before per-benchmark detail | Several listed benchmarks likely regress for the same reason |
| Distinguish three cause categories in the final analysis: x86-only uplift, ARM-only regression, and larger x86 uplift than ARM | Matches the user's decision frame |
| Treat local macOS Arm only as a piercing/probing platform | Useful for reproducer validation and dump generation, but not acceptable as final performance evidence |
| Prefer script generation after difference-point analysis instead of ad hoc remote commands | The Linux Arm environment is isolated, so batchable one-click data collection is more efficient and repeatable |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Missing planning skill helper script | Continued with manual file creation |
| Upstream baseline commit not reachable from `cinderx` history | Switched to cross-repo file/tree comparison |

## Resources
- `/Users/luchen/Repo/cinderx`
- `/Users/luchen/Repo/cpython`
- Upstream comparison commit: `ebf955df7a89ed0c7968f79faec1de49f61ed7cb`
- `/tmp/cpython-ebf955`
- `/Users/luchen/Repo/cinderx/plans/2026-02-27-cinderx-vs-cpython-314-interpreter/deliverable.md`
- `/Users/luchen/Repo/cinderx/docs/plans/2026-03-10-raytrace-cpython-vs-cinderx-jit-analysis.md`
- `/Users/luchen/Repo/cinderx/plans/2026-03-12-float-accumulator-entry-promotion/findings.md`
- `/Users/luchen/Repo/cinderx/plans/2026-03-12-generators-attr-decref/findings.md`

## Visual/Browser Findings
- No visual artifacts used.

---
*Update this file after every 2 view/browser/search operations*
*This prevents visual information from being lost*

- 2026-03-14: Deep-dive pivoted to single-benchmark attribution for pyperformance coroutines; need the exact bm_coroutines benchmark source to map interpreter/JIT paths to benchmark behavior.
- 2026-03-14: Located pyperformance benchmark source at `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_coroutines/run_benchmark.py`; `coroutines` is recursive `async fibonacci(25)` driven by repeated `coro.send(None)`, so the hot path is coroutine creation (`_Py_MakeCoro`), awaitable resolution (`_PyEval_GetAwaitable`), resume/suspend (`SEND`/`YIELD_VALUE`), and coroutine teardown rather than asyncio scheduler overhead.
- 2026-03-14: For the interpreter path, CinderX replaces CPython's `_PyCoro_GetAwaitableIter` / `_PyEval_GetAwaitable` with `JitCoro_GetAwaitableIter` / `Ci_PyEval_GetAwaitable`, which add JIT coroutine type checks (`JitCoro_CheckExact`, `jitgen_is_coroutine`) and a broader `JitGen_yf()` path.
- 2026-03-14: Cross-compiled a reduced helper probe with `aarch64-linux-gnu-gcc 15.2.0` and `x86_64-linux-gnu-gcc 15.2.0`. In both ISAs the CinderX helper version is materially longer than the CPython version, but the AArch64 expansion is larger because each extra exact-type check becomes an extra `bl` + `cbz/cbnz` chain plus additional reloads. This matches the user-observed platform-ratio drop pattern.
- 2026-03-14: JIT-side `GET_AWAITABLE` lowering in `HIRBuilder::emitGetAwaitable()` does not collapse the coroutine checks away; it explicitly emits `CallCFunc<JitCoro_GetAwaitableIter>`, exact-type branches for both `PyCoro_Type` and Cinder coroutine type, then `CallCFunc<JitGen_yf>` and an exception path. Native generator resume code is also structurally heavier on AArch64 because `gen_asm.cpp` relies on repeated `ptr_resolve()` + `ldr/str` sequences where x86_64 uses shorter base+disp forms.
- 2026-03-14: Located `bm_comprehensions` at `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_comprehensions/run_benchmark.py`. The benchmark is dominated by list/dict comprehensions, generator expressions under `any()`, repeated dataclass/enum attribute loads, and `list.sort()` on tuples; it is not a pure `LIST_APPEND` microbenchmark.
- 2026-03-14: For `comprehensions`, CinderX interpreter overrides `LIST_APPEND` and `MAP_ADD` to call `Ci_ListOrCheckedList_Append` and `Ci_DictOrChecked_SetItem` instead of the direct CPython list/dict primitives. This inserts checked-container compatibility logic into a very hot comprehension path.
- 2026-03-14: JIT LIR preserves the same generic container path: `Opcode::kListAppend` lowers to `Ci_ListOrCheckedList_Append` and `Opcode::kSetDictItem` lowers to `Ci_DictOrChecked_SetItem`, so JIT mode does not recover the original direct list/dict write shape.
- 2026-03-14: Cross-compiled `comprehensions` probes with `aarch64-linux-gnu-gcc 15.2.0` and `x86_64-linux-gnu-gcc 15.2.0`. `cpy_map_add` compiles to a trivial tail jump into `PyDict_SetItem`, while `cx_map_add` expands into two type checks plus branchy dispatch to either `PyDict_SetItem` or `Ci_CheckedDict_SetItem`. On AArch64 that means extra `bl` + `cbz/cbnz` + register reloads; on x86_64 it still expands, but into a denser `call/test/jcc` sequence.
- 2026-03-14: CinderX JIT `LOAD_ATTR_INSTANCE_VALUE` adds `inline_values_valid_guard`, which requires loading `tp_basicsize`, computing an extra address into inline values storage, loading a `valid` byte, and combining that with the type-version guard. A reduced probe shows this stays compact on x86_64 but is more address-generation heavy on AArch64.
- 2026-03-14: Located `bm_richards` at `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_richards/run_benchmark.py`. The benchmark is dominated by tiny object methods, linked-list packet append, task scheduling, and repeated attribute/method traffic (`LOAD_ATTR`, `STORE_ATTR`, `LOAD_METHOD`, `CALL_METHOD`), not arithmetic.
- 2026-03-14: Local bytecode inspection of `Packet.append_to`, `Task.addPacket`, `Task.runTask`, `Task.qpkt`, `HandlerTask.fn`, `WorkTask.fn`, `schedule`, and `Richards.run` confirms richards is call-heavy and attribute-heavy: small methods chain into other small methods with almost no numeric work to hide dispatch overhead.
- 2026-03-14: For `richards`, the most relevant CinderX deltas versus CPython are interpreter bookkeeping (`CI_UPDATE_CALL_COUNT`, `adaptive_enabled`, `IS_PEP523_HOOKED`) and JIT attr/call lowering rather than checked-container code. This matches the existing interpreter-overhead deliverable already calling out these costs as high-priority for richards-like workloads.
- 2026-03-14: Cross-compiled a reduced richards probe showing that adding even a small CinderX-style bookkeeping branch (`if (adaptive_enabled) *call_count += 1`) to a tiny hot helper like `addPacket()` lengthens both ISAs, but AArch64 expands into more explicit branch and load/store steps relative to x86_64.
- 2026-03-14: Cross-compiled a reduced attr-guard probe for `LOAD_ATTR_INSTANCE_VALUE`-style checks. Compared with a plain type-version guard, the CinderX-style guard adds `tp_basicsize` load + extra address generation + `valid` byte load; this remains compact on x86_64 but is more load/address-generation heavy on AArch64.
- 2026-03-14: `bm_richards_super` keeps the same scheduler/tiny-helper structure as `richards` but each task handler now begins with `super().fn(pkt, r)`. That extra base-method dispatch makes the benchmark even more sensitive to CinderX method-entry bookkeeping and attr/call glue; it should be treated as an amplified `richards`, not a separate numeric case.
- 2026-03-14: `bm_go` is object-graph heavy rather than arithmetic heavy. Bytecode inspection of `Square.move/find/remove` and `Board.useful` shows repeated attribute reads/writes, tiny helper calls, global timestamp updates, and set/list/history traffic. This makes it a strong fit for the same attr-guard + tiny-helper-entry cost cluster as `richards`, with even denser object-field traffic.
- 2026-03-14: `bm_deltablue` is another tiny-helper/object-graph benchmark. `Planner.incremental_add`, `Planner.add_propagate`, `Constraint.satisfy`, `Variable.add_constraint`, and `ScaleConstraint.execute` are dominated by short method calls, attribute traffic, and small container operations rather than long arithmetic kernels. This again points to interpreter bookkeeping and attr-guard expansion as the primary Arm-vs-x86 ratio driver.
- 2026-03-14: `bm_raytrace` remains the clearest JIT-specific benchmark. Existing repo findings already establish the historical root cause: overcompiling tiny mixed-numeric helpers (`Vector.dot`, `Vector.scale`, `Point.__sub__`, `Sphere.intersectionTime`) produced large guard/deopt storms. Current branch code already contains narrowing work to avoid that exact-int-guard failure mode on no-backedge helpers, so residual platform-ratio gaps should now be interpreted mainly through helper-call lowering and AArch64 code-shape costs.
- 2026-03-14: `bm_nqueens` is better modeled as a generator/container/control-flow benchmark than as an integer benchmark. `permutations()` and `n_queens()` are generators, the hot path repeatedly builds tuples and sets from generator expressions, and the benchmark depends heavily on generator resume/yield plus short-lived container objects. This aligns it more closely with the generator/runtime cluster than with numeric JIT benchmarks.
- 2026-03-14: `bm_float` is a float-heavy `__slots__` object benchmark. Existing branch-local findings already confirm two important historical CinderX causes: float-accumulator entry promotion and `x ** 2` lowering. Those fixes mean the current branch has already improved part of the original CinderX-vs-CPython gap; any remaining Arm-vs-x86 skew is more likely to come from slot/attr guard cost than from the worst float specialization failures.
- 2026-03-14: `bm_generators` is explicitly a generator runtime benchmark: recursive `yield from` over a binary tree plus `Tree.left/value/right` attr access. Existing findings show that low-local generator attr lowering was previously missing and that remaining pressure is now concentrated in decref/batch-decref behavior, making this benchmark primarily about generator attr/resume/decref rather than about generic loop speed.
- 2026-03-14: `bm_python_startup` is fundamentally different from the steady-state benchmarks. The pyperformance remote setup script writes a `sitecustomize.py` that imports `cinderx.jit` and enables the JIT at startup for benchmark subprocesses, while the repo also ships a `sitecustomize.py` that imports `cinderx`. Combined with Arm-only default feature enablement in `setup.py`, this makes `python_startup` primarily a startup-injection cost benchmark rather than an execution-core benchmark.
- 2026-03-14: After completing all per-benchmark deep dives, the benchmark set cleanly partitions into four root-cause clusters: (1) interpreter bookkeeping + attr guard (`richards`, `richards_super`, `go`, `deltablue`), (2) coroutine/generator runtime (`coroutines`, `generators`, `nqueens`), (3) JIT numeric/helper shape (`raytrace`, `float`), and (4) startup injection (`python_startup`).
- 2026-03-14: The follow-on optimization design intentionally targets platform-ratio recovery rather than generic speedups. It organizes the work into six aggressive change packages: tiny-helper bookkeeping throttle, exact-layout attr fast path, coroutine/awaitable fast path, generator attr/decref compaction, pure container-write fast path, numeric leaf/float-slot specialization, plus startup autoload policy changes for `python_startup`.
- 2026-03-14: The implementation plan expands that design into 11 executable tasks. The recommended first execution wave is `python_startup` autoload policy + tiny-helper bookkeeping throttle + exact-layout attr fast path + pure container-write fast path, because those four changes touch the broadest set of ratio-regressed benchmarks and should show the fastest Arm-relative recovery.
