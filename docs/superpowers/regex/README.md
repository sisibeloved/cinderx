# Regex Compile Benchmark - CinderX JIT Optimization

## Directory Contents

| File | Description |
|------|-------------|
| `2026-04-08-regex-jit-perf.md` | Implementation plan (historical reference) |
| `hir_initial.log` | HIR dump of 3 force-compiled functions |
| `hir_full.log` | Full HIR dump of 5 force-compiled functions (8810 lines) |

## Final Benchmark Results (kunpeng ARM64, pyperformance, 2026-04-09)

| Config | regex_compile | Notes |
|--------|-------------|-------|
| CPython 3.14 | 155 ms ± 1 ms | Baseline |
| CinderX JIT (no optimizations) | 219 ms ± 7 ms | +41% vs CPython |
| **CinderX JIT (D1+D2)** | **213 ms ± 5 ms** | **-2.7% vs unoptimized JIT** |

## Adopted Optimizations (D1 + D2)

### D1: Narrow XDecref arbitrary execution for known-safe types

**Files changed:** `cinderx/Jit/hir/instr_effects.cpp`

XDecref was unconditionally marked as `hasArbitraryExecution()`, killing all borrow support. Now only returns true when the operand type has a non-trivial destructor.

### D2: Add BatchIncref for consecutive Incref runs

**Files changed:** `hir_ops.h`, `hir.h`, `instr_effects.cpp`, `jit_rt.h`, `jit_rt.cpp`, `lir/generator.cpp`, `refcount_insertion.cpp`

Mirrors existing `BatchDecref` optimization — batches 3+ consecutive Incref operations into a single `JITRT_BatchIncref` call, reducing per-instruction overhead.

### D1+D2 Benchmark Detail (custom force_compile script)

| Config | 100 loops | Per-loop |
|--------|-----------|----------|
| CPython | 65.7 ms | 0.657 ms |
| JIT no-opt | 80.6 ms | 0.806 ms |
| JIT D1 only | 77.6 ms | 0.776 ms (-3.7%) |
| JIT D1+D2 | 75.3 ms | 0.753 ms (-6.6%) |

## Rejected Optimizations

| Optimization | Result | Reason |
|-------------|--------|--------|
| F1: Cold block marking | No measurable improvement | Deopt exits already in cold section |
| C1: LoadGlobalCSE | No measurable improvement | Few duplicate loads within same block |
| C2: GuardIsCSE | No measurable improvement | Few duplicate guards within same block |

## Why JIT is Still 37% Slower Than CPython

1. **Guard overhead** — every type check adds a runtime guard
2. **Refcount ops** — even with batching, more refcount work than pure C path
3. **No C function inlining** — `re.compile()` spends most time in `_sre` C extension
4. **`_parse` too large for JIT** — 7428-line HIR crashes when compiled

## Benchmark Commands

```bash
# pyperformance (standard)
cd /root/cinderx && \
PYTHONJITENABLEJITLISTWILDCARDS=1 \
PYTHONJITLISTFILE=/home/jit_list.txt \
PYTHONPATH="$PWD/scripts/arm/pyperf_env_hook:$PYTHONPATH" \
PYTHONJITTYPEANNOTATIONGUARDS=1 \
PYTHONJITENABLEHIRINLINER=1 \
PYTHONJITAUTO=2 \
PYTHONJITSPECIALIZEDOPCODES=1 \
/root/.pyenv/versions/3.14.3/bin/python3.14 -m pyperformance run \
  --affinity=3 --warmup 3 -b regex_compile \
  --inherit-environ http_proxy,https_proxy,LD_LIBRARY_PATH,PYTHONJITAUTO,PYTHONJITSPECIALIZEDOPCODES,PYTHONJITENABLEHIRINLINER,PYTHONJITTYPEANNOTATIONGUARDS,PYTHONPATH,PYTHONJITLISTFILE,PYTHONJITENABLEJITLISTWILDCARDS

# JIT list file: /home/jit_list.txt
# re._compiler:*
# re._parser:*
# re:compile
```

## Build & Sync Commands

```bash
# Sync local code to remote
rsync -avz --exclude='.git' --exclude='build' --exclude='*.pyc' --exclude='__pycache__' --exclude='venv' --exclude='scratch' /Users/luchen/Agents-Repo/GSD/cinderx/ kunpeng:/root/cinderx/

# Build on kunpeng (both system python and pyperformance venv)
ssh kunpeng 'cd /root/cinderx && pip3.14 install -e . 2>&1 | tail -5'
ssh kunpeng '/root/cinderx/venv/cpython3.14-*/bin/python -m pip install -e /root/cinderx 2>&1 | tail -5'
```
