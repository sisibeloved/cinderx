# Auto-JIT Full Admission Crash Investigation

## Summary

This report investigates whether removing practical admission limits for CinderX JIT causes `pyperformance` failures, and whether the observed crashes are environment-specific or real CinderX JIT correctness issues.

The key conclusion is:

- the crash is reproducible locally
- it is not specific to `mdp` business logic itself
- it happens before the benchmark's own hot functions are reached
- it occurs while CinderX JIT is actively compiling and executing early import/bootstrap paths

This makes it a real CinderX JIT correctness/stability problem under aggressive auto-JIT admission, not just a production-environment mismatch.

## Question

We wanted to answer two questions:

1. If we effectively remove the usual whitelist protection and run with aggressive auto-JIT admission, does `pyperformance` systematically fail?
2. If it does fail, how much work would be required to make this mode usable?

## Test Environment

All local reproduction used:

- the current source tree of this repository
- local `pyperformance` source from `$HOME/Repo/pyperformance`
- project-local Python environment under `.venv`
- `PYTHONJITHUGEPAGES=0`

For worker processes, the source-tree CinderX and hook were injected with:

- `PYTHONPATH="scripts/arm/pyperf_env_hook:cinderx/PythonLib:$HOME/Repo/pyperformance"`

To avoid whitelist interference, the following variables were explicitly cleared:

- `PYTHONJITLISTFILE`
- `PYTHONJITENABLEJITLISTWILDCARDS`
- `CINDERX_JITLIST_ENTRIES`

## Full-Suite Result

### `pyperformance` excluding `dask`

A near-full local run excluding `dask` completed successfully and produced a valid result JSON.

This matters because it disproves the strongest version of the original concern:

- aggressive JIT admission does **not** immediately cause broad, system-wide `pyperformance` failure on the local machine

### `dask`

`dask` initially appeared to be the first blocking benchmark, but separate repro showed that this is not a CinderX-specific failure.

Without the CinderX JIT hook, `dask` still got stuck waiting for a local TCP scheduler/worker connection.

Therefore:

- `dask` is an environment/runtime orchestration problem in this setup
- it is not useful as evidence for a CinderX JIT correctness bug

## Focused Reproduction: `mdp`

The next step was to reproduce the failure on a single benchmark with the same style of JIT configuration used in the real environment.

The key environment shape was:

```bash
env \
  -u PYTHONJITLISTFILE \
  -u PYTHONJITENABLEJITLISTWILDCARDS \
  -u CINDERX_JITLIST_ENTRIES \
  PYTHONJITAUTO=1 \
  PYTHONJITSPECIALIZEDOPCODES=1 \
  PYTHONJITENABLEHIRINLINER=1 \
  PYTHONJITTYPEANNOTATIONGUARDS=1 \
  PYTHONJITDUMPSTATS=1 \
  PYTHONJITDUMPFINALHIR=1 \
  PYTHONJITLOGFILE=/tmp/jit.log \
  PYTHONJITHUGEPAGES=0 \
  PYTHONPATH="scripts/arm/pyperf_env_hook:cinderx/PythonLib:$HOME/Repo/pyperformance" \
  "$HOME/Repo/pyperformance/.venvs/dev-3.14-opt-homebrew-opt-python@3.14-bin-python3.14/bin/python" \
  -u "$HOME/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_mdp/run_benchmark.py" \
  --debug-single-value \
  --inherit-environ PYTHONJITAUTO,PYTHONJITSPECIALIZEDOPCODES,PYTHONPATH,PYTHONJITHUGEPAGES,PYPERFORMANCE_RUNID,PYTHONJITDUMPFINALHIR,PYTHONJITTYPEANNOTATIONGUARDS,PYTHONJITENABLEHIRINLINER,PYTHONJITLOGFILE,PYTHONJITDUMPSTATS \
  --warmups=3 \
  --output /tmp/out.json
```

### Result

Local repro matched the real-environment symptom class:

- `PYTHONJITAUTO=1`: worker died
- `PYTHONJITAUTO=0`: worker also died

This remained true even after explicitly clearing jit-list related variables.

## Narrowing the Failure

To understand whether the crash came from benchmark logic or from surrounding runtime activity, the benchmark was reduced step by step.

### 1. Import only

Importing `bm_mdp/run_benchmark.py` directly succeeded under both:

- `PYTHONJITAUTO=1`
- `PYTHONJITAUTO=0`

### 2. Call `bench_mdp(1)` directly

Directly importing the module and calling `bench_mdp(1)` also succeeded under both:

- `PYTHONJITAUTO=1`
- `PYTHONJITAUTO=0`

### 3. Run the worker command directly

Running the worker-style benchmark command directly reproduced the crash immediately:

- with `PYTHONJITAUTO=1`
- with `PYTHONJITAUTO=0`

This is the most important narrowing result:

- the failure does not require the outer `pyperformance run` driver
- the failure is not in the benchmark module import itself
- the failure is not in `bench_mdp(1)` as a direct business-logic call
- the failure is triggered by the `pyperf` benchmark-worker execution path under aggressive auto-JIT admission

## Evidence That This Is Really CinderX JIT

The JIT log files contained large amounts of final HIR output, including functions such as:

- `_frozen_importlib_external:_path_stat`
- `typing:*`
- `enum:*`
- `dataclasses:*`

That proves:

- CinderX JIT was active
- the process was producing CinderX final HIR
- this was not a fallback-to-interpreter or "not actually running JIT" case

## Native Crash Backtrace

The local repro was then run under `lldb`.

For `PYTHONJITAUTO=1`, the process stopped with:

- `EXC_BAD_ACCESS`
- invalid address access in `PyImport_Import`

The relevant stack was:

```text
PyImport_Import
PyImport_ImportModuleAttr
PyImport_ImportModuleAttrString
PyFile_OpenCodeObject
_io_open_code
_cinderx.so: JITRT_Vectorcall
_cinderx.so: jitVectorcall
...
Py_RunMain
```

This is the critical result.

It shows:

- the process crashes in Python import/bootstrap machinery
- the path goes through `_cinderx.so`
- the crash happens after CinderX JIT has already taken over execution for some early functions

## Interpretation

The crash is best understood as:

- an aggressive auto-JIT admission bug in early import/bootstrap execution
- not a benchmark-specific `mdp` logic bug
- not a jit-list-only configuration problem
- not a problem unique to the real environment

The benchmark merely provides a reliable way to reach that early execution pattern.

## Why `mdp` Still Matters

Although `mdp` itself is not the direct root cause, it is still useful because it gives a reproducible, simple benchmark entry point that exposes the issue.

It is therefore a good canary workload for:

- aggressive auto-JIT admission
- startup/import-path JIT correctness
- early stdlib/importlib compatibility

## Estimated Fix Scope

### Option 1: Tactical mitigation

Goal:

- make aggressive admission usable enough for experimentation

Likely approach:

- further narrow auto-JIT eligibility during import/bootstrap
- keep early stdlib/importlib paths out of aggressive admission

Estimated effort:

- small to medium
- roughly 1 to 3 engineer-days

### Option 2: Root-cause fix

Goal:

- actually support this aggressive admission mode without crashing

Likely approach:

- continue from the `lldb` stack
- identify which exact function or call pattern compiled by `jitVectorcall` corrupts import/bootstrap state
- fix the underlying correctness issue in JIT/runtime interaction

Estimated effort:

- medium and uncertain
- likely several days to more than a week

## Current Assessment

At this point the evidence supports the following assessment:

- aggressive auto-JIT admission is not broadly unusable across all local `pyperformance`
- but it is **not safe yet**
- there is at least one real CinderX JIT correctness problem in startup/import-related execution
- making this mode "production-safe" is not a trivial config change

The lowest-risk next step would be:

- first add a tactical admission guard around early import/bootstrap paths

The highest-value engineering step, if this mode is strategically important, would be:

- continue root-cause analysis from the captured `lldb` stack

