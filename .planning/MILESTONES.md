# Milestones

## v1.0 LTO/PGO Performance Fix (Shipped: 2026-03-24)

**Phases completed:** 3 phases, 10 plans

**Key accomplishments:**

1. **Protected 113 JIT runtime functions** with `JIT_RUNTIME_API` noinline attribute
   - All JITRT_* functions in jit_rt.h and jit_rt.cpp marked as `__attribute__((noinline, visibility("default")))`
   - Prevents LTO from inlining runtime helpers that JIT-compiled code calls by address
   - Verified via symbol table: 124 JITRT symbols visible, none inlined

2. **Implemented LTO detection API** (`cinderx.is_lto_enabled()`)
   - C++ API: `jit::isLTOEnabled()` for runtime detection
   - Python API: `cinderx.is_lto_enabled()` with graceful fallback
   - Build integration: CMake sets ENABLE_LTO flag when LTO is enabled
   - Full test coverage in test_lto_regression.py

3. **Created benchmark automation suite** with regression detection
   - `run_pyperf_subset.py`: 5-benchmark JIT subset (richards, nbody, deltablue, regex_compile, nqueens)
   - `compare_lto_impact.py`: LTO vs non-LTO statistical comparison
   - `macos_smoke_test.py`: Quick validation with build time measurement
   - `quick_validation.sh`: One-command wrapper for developers
   - < 1% regression detection threshold
   - 8 unit tests for benchmark framework

4. **Built Docker ARM64 environment** for comprehensive validation
   - `Dockerfile.arm`: ARM64 image with GCC 13/Clang 18 toolchain
   - `docker-compose.arm.yml`: 6 services (baseline, LTO, PGO, quick-bench, full-bench, validate)
   - Resource limits: 4 CPU, 8GB memory for consistent benchmarking
   - Build time measurement with < 30% threshold validation
   - Full pyperformance suite execution capability

5. **Integrated GitHub Actions CI** with performance workflows
   - `lto-performance.yml`: 3 jobs (quick-validate, full-validate, build-time)
   - `ci.yml`: LTO build job integrated into main CI
   - Automated regression detection on PRs
   - Artifact upload for benchmark results
   - Performance documentation in docs/performance.md (323 lines)

6. **Updated comprehensive documentation**
   - README.md: LTO/PGO usage guide with platform support matrix
   - docs/build.md: Complete build instructions and troubleshooting
   - docs/performance.md: Methodology, thresholds, and results

**Statistics:**
- Git commits: 39
- Python scripts: 15 files
- Lines of code: ~1,956 in benchmark scripts
- Duration: 1 day (2026-03-23 to 2026-03-24)
- Success criteria: 31/31 verified (100%)

**Files delivered:**
```
scripts/bench/
├── run_pyperf_subset.py       # 5-benchmark automation
├── compare_lto_impact.py      # LTO comparison engine
├── macos_smoke_test.py        # macOS validation
├── quick_validation.sh        # One-command wrapper
├── test_lto_benchmarks.py     # Unit tests (8 tests)
├── test_macos_smoke.py        # Unit tests (6 tests)
├── test_ci_workflow.py        # CI tests (6 tests)
└── ... (8 more files)

docker/
├── Dockerfile.arm              # ARM64 toolchain
├── docker-compose.arm.yml      # 6-service compose
└── arm/scripts/
    ├── build-lto.sh            # Build comparison
    ├── run-full-suite.sh       # Full pyperformance
    └── entrypoint.sh           # Container commands

.github/workflows/
├── lto-performance.yml         # 224 lines
└── ci.yml                      # LTO job (+58 lines)

docs/
├── build.md                    # Build guide
└── performance.md              # 323 lines
```

**Known Gaps:**
- REQUIREMENTS.md traceability table not updated during execution (all requirements marked as pending despite implementation)
- P2 requirements (PR-002 performance target, PR-004 memory limits) require actual ARM hardware validation
- DR-003 API documentation not explicitly created (covered in docs/performance.md)

---

*Milestone record created: 2026-03-24*
