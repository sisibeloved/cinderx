# Phase 02: Baseline Data Collection

Build the Arm64 CinderX wheel and run the full benchmark comparison in Docker to get the CinderX JIT baseline for regex_compile. Also record the target CPython JIT baseline from the intranet environment.

## Tasks

- [ ] Verify project isolation before building:
  ```bash
  cd /Users/luchen/Agents-Repo/Maestro/cinderx
  git branch  # confirm on bench-cur-7c361dce-maestro
  git status  # no uncommitted changes that would contaminate the build
  ```
  If there are uncommitted changes, create a backup commit before proceeding:
  ```bash
  git add -A && git commit -m "WIP backup before regex_compile baseline"
  ```

- [ ] Build Arm64 CinderX wheel (single-threaded to avoid OOM):
  ```bash
  cd /Users/luchen/Agents-Repo/Maestro/cinderx/docker/cinderx-test
  ./scripts/build-wheel.sh
  ```
  This outputs a wheel to `dist/cinderx-*-linux_aarch64.whl`. Verify the output file exists.

- [ ] Run CinderX JIT baseline + optimized comparison in Docker with an isolated results directory:
  ```bash
  cd /Users/luchen/Agents-Repo/Maestro/cinderx/docker/cinderx-test
  RESULTS_DIR=./results_regex_compile_$(date +%Y%m%d_%H%M%S) \
  BENCHMARK=regex_compile \
  SAMPLES=10 \
  WARMUP=3 \
  ./test-benchmark.sh
  ```
  This runs two consecutive benchmarks: "BASELINE" (no opt env vars) and "OPTIMIZED" (reads `stable.env`, which is currently empty so results should match). Record both median times.

- [ ] Run CinderX JIT smoke test inside the running container to confirm JIT is active and regex_compile is JIT-compiled:
  ```bash
  docker compose run --rm cinderx-arm64 \
    bash -c 'BENCHMARK=regex_compile /scripts/setup.sh && /scripts/smoke.sh'
  ```
  Confirm "Test 3: regex_compile compilation" prints a compiled size and no errors.

- [ ] Record the CPython JIT baseline from the intranet environment. The target is 84ms per the project brief. Record the exact measured value in a structured note:
  - Create `docs/research/regex-compile-baseline.md` with YAML front matter:
    ```yaml
    ---
    type: report
    title: regex_compile Baseline Measurements
    created: 2026-03-22
    tags: [regex-compile, baseline, arm64]
    related:
      - '[[Regex-Compile-Optimization-Plan]]'
    ---
    ```
  - Document: CPython JIT intranet measurement (ms), CinderX JIT Docker measurement (s converted to ms), gap percentage, measurement conditions (samples, warmup, env).

- [ ] Create the optimization plan document (`docs/research/regex-compile-optimization-plan.md`) as a placeholder to be filled in Phase 03:
  ```yaml
  ---
  type: report
  title: regex_compile Optimization Plan
  created: 2026-03-22
  tags: [regex-compile, optimization, jit]
  related:
    - '[[regex-compile-baseline]]'
  ---
  ```
  Fill in the "Current gap" section using the baseline measurements above.
