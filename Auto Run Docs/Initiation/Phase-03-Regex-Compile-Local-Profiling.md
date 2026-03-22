# Phase 03: macOS Local Profiling

Set up a local macOS environment to rapidly profile regex_compile and identify JIT bottlenecks. Results feed directly into Phase 04 optimization decisions.

## Tasks

- [ ] Create an isolated uv venv for regex_compile local testing:
  ```bash
  cd /Users/luchen/Agents-Repo/Maestro/cinderx
  uv venv .venv-regex-local --python python3.14
  source .venv-regex-local/bin/activate
  ```
  Verify: `which python` should point to the venv. Deactivate when done.

- [ ] Check for a local CinderX wheel (macOS arm64) in `dist/`:
  ```bash
  ls dist/cinderx-*-macosx_*.whl 2>/dev/null || echo "no macos wheel found"
  ```
  If no macOS wheel exists, check if the project supports `pip install -e .` on macOS (look at `pyproject.toml` or `setup.py`). If editable install works on Apple Silicon, install CinderX in the venv.

- [ ] Verify the local pyperformance benchmarks are readable:
  ```bash
  ls ~/Repo/pyperformance/benchmarks/bm_regex_compile/run_benchmark.py
  ls ~/Repo/pyperformance/benchmarks/bm_regex_effbot/run_benchmark.py
  ls ~/Repo/pyperformance/benchmarks/bm_regex_v8/run_benchmark.py
  ```
  Confirm all three files exist and are readable (project brief confirms they are read-only, do not modify them).

- [ ] Create a helper script to pre-capture the regexes list used by `bench_regex_compile`:
  Write `scripts/arm/capture_regex_compile_regexes.py` that:
  - Sets up the same `capture_regexes()` logic as in `bm_regex_compile/run_benchmark.py`
  - Adds both `~/Repo/pyperformance/benchmarks/bm_regex_effbot` and `~/Repo/pyperformance/benchmarks/bm_regex_v8` to `sys.path` before importing
  - Runs `capture_regexes()` and prints the result as a JSON-encoded list
  - Example invocation: `python3 scripts/arm/capture_regex_compile_regexes.py > /tmp/regexes.json`

- [ ] Run CinderX JIT profiling of regex_compile using `bench_pyperf_direct.py`:
  ```bash
  source /Users/luchen/Agents-Repo/Maestro/cinderx/.venv-regex-local/bin/activate
  REGEXES=$(python3 scripts/arm/capture_regex_compile_regexes.py)
  python3 scripts/arm/bench_pyperf_direct.py \
    --module-path ~/Repo/pyperformance/benchmarks/bm_regex_compile/run_benchmark.py \
    --module-name bm_regex_compile \
    --bench-func bench_regex_compile \
    --bench-args-json "[1, $REGEXES]" \
    --samples 5 \
    --prewarm-runs 3 \
    --compile-strategy none \
    --output results_local/regex_compile_interp.json
  ```
  Run with `--compile-strategy none` first (interpreter baseline), then with `--compile-strategy backedge` (JIT baseline). Compare the two.

- [ ] Collect HIR/LIR and deopt statistics. Extend the `bench_pyperf_direct.py` invocation with `--compile-strategy all` and focus on the deopt output in the JSON:
  - Identify the top 5 deopt reasons (qualname, lineno, description, reason, count)
  - Identify which functions were actually JIT-compiled vs failed to compile
  - Look for "handled-subscript" or "guard failure" patterns matching prior JIT optimizations (e.g. deepcopy, nqueens patterns)

- [ ] Identify the bottleneck and document in the optimization plan:
  Update `docs/research/regex-compile-optimization-plan.md`:
  - Hotspot functions (from deopt data): list qualnames and deopt counts
  - Probable root causes: type changes, guard failures, unexpected branching
  - Recommended JIT flag approach: match patterns from `configs/generators/stable.env` and `configs/mdp/stable.env` to analogous regex_compile scenarios
  - Link back to `[[regex-compile-baseline]]` using wiki-link syntax
