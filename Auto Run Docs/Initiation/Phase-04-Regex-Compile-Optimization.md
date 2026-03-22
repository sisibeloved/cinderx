# Phase 04: Optimization Execution

Implement and measure JIT optimizations for regex_compile based on Phase 03 profiling. Iterate until CinderX JIT performance meets or exceeds the CPython JIT baseline (84ms).

## Tasks

- [ ] Read Phase 03 findings from `docs/research/regex-compile-optimization-plan.md` and `docs/research/regex-compile-baseline.md` before starting. The optimization strategy is determined by those documents.

- [ ] Backup the current `stable.env` before modifying:
  ```bash
  cp docker/cinderx-test/configs/regex_compile/stable.env \
     docker/cinderx-test/configs/regex_compile/stable.env.bak.$(date +%Y%m%d)
  ```

- [ ] Implement initial JIT flags in `stable.env` based on Phase 03 analysis. Common patterns from prior optimizations (`configs/generators/stable.env`, `configs/mdp/stable.env`) that may apply:
  - `PYTHONJIT_ARM_*_INT_CLAMP_MIN_MAX` — for loop counter comparisons
  - `PYTHONJIT_ARM_*_FRACTION_MIN_COMPARE` — for comparison ops in regex inner loops
  - `PYTHONJIT_ARM_*_PRIORITY_COMPARE_ADD` — for combining regex operations
  - `PYTHONJIT_ARM_*_HANDLED_SUBSCRIPT` — if subscript deopts appear in Phase 03 data
  Add flags one or few at a time (not all at once) so the impact of each can be measured.

- [ ] Build Arm64 wheel and run comparison in Docker:
  ```bash
  cd /Users/luchen/Agents-Repo/Maestro/cinderx/docker/cinderx-test
  ./scripts/build-wheel.sh
  RESULTS_DIR=./results_regex_compile_opt_$(date +%Y%m%d_%H%M%S) \
  BENCHMARK=regex_compile \
  SAMPLES=10 \
  WARMUP=3 \
  ./test-benchmark.sh
  ```
  Compare "OPTIMIZED" median time against the Phase 02 baseline and the 84ms CPython JIT target.

- [ ] Measure the speedup: if `speedup >= 1.0x` vs baseline and `optimized_ms <= 84ms`, the goal is met — record the winning flag combination in `stable.env` and update the optimization plan document.

- [ ] Iterate if the goal is not met: use Phase 03 local profiling to drill into remaining hotspots, add or adjust flags, and re-run. Log each iteration's flag combination and result in `docs/research/regex-compile-optimization-plan.md` as a decision record:
  ```yaml
  ---
  iteration: N
  flags: ["PYTHONJIT_ARM_*_FLAG=value", ...]
  result_ms: X.XX
  speedup_vs_baseline: Y.YYx
  ---
  ```

- [ ] Finalize: when the goal is met, clean up backup files and update the optimization plan with the final winning configuration and total speedup achieved.
