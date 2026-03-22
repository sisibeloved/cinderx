# Phase 01: Regex-Compile Harness Setup

Add regex_compile support to the Docker benchmark harness. This makes the existing `test-benchmark.sh` pipeline usable for regex_compile, which has a unique two-argument signature `bench_regex_compile(loops, regexes)` — the `regexes` list must be captured by calling `capture_regexes()` before the benchmark runs.

## Tasks

- [x] Add `regex_compile` to `BENCHMARK_SPECS` in `benchmark_harness.py`:
  ```python
  "regex_compile": BenchmarkSpec(
      name="regex_compile",
      module_dir="bm_regex_compile",
      bench_func="bench_regex_compile",
      bench_args=(1,),
      benchmark_url="https://raw.githubusercontent.com/python/pyperformance/main/pyperformance/data-files/benchmarks/bm_regex_compile/run_benchmark.py",
  ),
  ```
  Done: Added to `docker/cinderx-test/scripts/benchmark_harness.py`.

- [x] Update `setup.sh` to download `bm_regex_effbot` and `bm_regex_v8` sub-benchmarks alongside `bm_regex_compile` — `capture_regexes()` in the harness will import and run these. Add a `resolve_dependent_benchmarks()` helper that downloads the two sub-benchmark URLs when `BENCHMARK=regex_compile`:
  ```
  https://raw.githubusercontent.com/python/pyperformance/main/pyperformance/data-files/benchmarks/bm_regex_effbot/run_benchmark.py
  https://raw.githubusercontent.com/python/pyperformance/main/pyperformance/data-files/benchmarks/bm_regex_v8/run_benchmark.py
  ```
  Place them under `/root/benchmarks/bm_regex_effbot/run_benchmark.py` and `/root/benchmarks/bm_regex_v8/run_benchmark.py` respectively. Also create a pyperf shim at each sub-benchmark directory.
  Done: Added `resolve_dependent_benchmarks()` to `docker/cinderx-test/scripts/setup.sh`. Verified all 3 URLs download successfully.

- [x] Modify `load_benchmark()` in `benchmark_harness.py` to handle regex_compile's dual-parameter signature:
  ```python
  # After exec_module(module) and bench = getattr(...), before return:
  if name == "regex_compile":
      # capture_regexes() lives in the module and imports bm_regex_effbot/v8 sub-benchmarks
      captured_regexes = module.capture_regexes()
      original_bench = bench
      def bench(*args):
          return original_bench(*args, captured_regexes)
  ```
  The `bm_regex_effbot` and `bm_regex_v8` modules must be on `sys.path` when `exec_module` runs — insert their parent directories (`/root/benchmarks/bm_regex_effbot`, `/root/benchmarks/bm_regex_v8`) into `sys.path` before calling `import bm_regex_effbot` inside `capture_regexes()`. A clean way: in the harness, after downloading all sub-benchmarks, prepend `/root/benchmarks/bm_regex_effbot` and `/root/benchmarks/bm_regex_v8` to `sys.path` before `exec_module`.
  Done: Modified `load_benchmark()` in `docker/cinderx-test/scripts/benchmark_harness.py` to inject sub-benchmark paths and capture regexes before wrapping the bench function.

- [x] Create config directory and initial env file:
  ```bash
  mkdir -p docker/cinderx-test/configs/regex_compile
  ```
  Write `docker/cinderx-test/configs/regex_compile/stable.env` as an empty file (pure baseline — no optimization flags yet).
  Done: Created `docker/cinderx-test/configs/regex_compile/stable.env`.

- [x] Add regex_compile smoke test to `smoke.sh`: after loading the regex_compile module, call `jit.force_compile` on `re.compile` and `bench_regex_compile`, and print compiled size. Add a third test block (mirroring existing Generator test) named "Test 3: regex_compile compilation".
  Done: Added Test 4: regex_compile compilation to `docker/cinderx-test/scripts/smoke.sh`.

- [x] Run unit tests to verify harness changes don't break existing benchmarks:
  ```bash
  cd /Users/luchen/Agents-Repo/Maestro/cinderx
  python3 docker/cinderx-test/scripts/test_benchmark_harness.py
  ```
  Done: All 9 tests pass (7 original + 2 new regex_compile tests). Note: must use system Python (`/usr/bin/python3`) to avoid cinderx JIT memory allocation errors on host.

- [x] Verify regex_compile loads correctly in Docker (dry-run smoke test):
  ```bash
  cd /Users/luchen/Agents-Repo/Maestro/cinderx/docker/cinderx-test
  docker compose run --rm cinderx-arm64 \
    bash -c 'BENCHMARK=regex_compile /scripts/setup.sh && /scripts/smoke.sh'
  ```
  Skipped: Docker mount fails in this environment (read-only overlay filesystem for `/scripts/configs`). The harness logic was verified by unit tests (9/9 pass) and confirmed all 3 benchmark URLs download successfully. The Docker smoke test would need to be run in an environment where the Docker daemon allows mounts.
