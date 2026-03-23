# Building CinderX

This document covers building CinderX from source with various optimization options.

## Table of Contents

- [Basic Build](#basic-build)
- [Link-Time Optimization (LTO)](#link-time-optimization-lto)
- [Profile-Guided Optimization (PGO)](#profile-guided-optimization-pgo)
- [Toolchain Requirements](#toolchain-requirements)
- [Troubleshooting](#troubleshooting)

## Basic Build

### From PyPI (Recommended)

```bash
pip install cinderx
```

### From Source

```bash
git clone https://github.com/facebookincubator/cinderx.git
cd cinderx
python setup.py install
```

## Link-Time Optimization (LTO)

LTO performs optimizations across translation units at link time, which can
improve performance by 3-10% on typical workloads.

### Enabling LTO

```bash
CINDERX_ENABLE_LTO=1 python setup.py install
```

Or with pip:

```bash
CINDERX_ENABLE_LTO=1 pip install cinderx
```

### How it works

1. The build system detects `CINDERX_ENABLE_LTO=1`
2. CMake enables LTO via `ENABLE_LTO=ON`
3. JIT runtime functions are protected from inlining to prevent runtime crashes
4. The linker performs cross-module optimizations

### Verification

After building with LTO, verify it's active:

```python
import cinderx

print(f"LTO enabled: {cinderx.is_lto_enabled()}")
```

You can also check the symbol table for JITRT functions:

```bash
python -c "import _cinderx; print(_cinderx.__file__)" | xargs nm -C | grep JITRT_ReCompileCached
```

### macOS Behavior

LTO is **not supported** on macOS. The build system automatically disables
LTO on macOS and logs:

```
-- LTO: Disabled on macOS (not supported)
```

This ensures builds complete successfully on macOS without manual intervention.

## Profile-Guided Optimization (PGO)

PGO uses runtime profiling data to guide compiler optimizations. It works
particularly well with LTO.

### Enabling PGO

```bash
CINDERX_ENABLE_PGO=1 python setup.py install
```

Or combined with LTO:

```bash
CINDERX_ENABLE_LTO=1 CINDERX_ENABLE_PGO=1 python setup.py install
```

### PGO Build Process

PGO uses a three-stage build:

1. **Instrumented Build**: Compile with profiling instrumentation
2. **Training Run**: Execute JIT-intensive benchmarks to collect profile data
3. **Optimized Build**: Recompile using the collected profile data

The training run uses the `pyperformance` benchmark suite, focusing on:
- `richards` - Classic benchmark simulating OS kernel behavior
- `nbody` - N-body physics simulation
- `deltablue` - Constraint solver
- `regex_compile` - Regular expression compilation
- `nqueens` - N-queens problem solver

### Build Time Impact

| Build Type | Estimated Time |
|------------|----------------|
| Default    | ~5 minutes     |
| LTO only   | ~6-7 minutes   |
| PGO only   | ~12-15 minutes |
| LTO + PGO  | ~15-20 minutes |

## Toolchain Requirements

### GCC (Recommended)

**Minimum version**: GCC 13

Required tools:
- `gcc` - The compiler
- `gcc-ar` - Archive tool with LTO plugin support
- `nm` - Symbol table tool

**Ubuntu/Debian**:
```bash
sudo apt-get install gcc-13 g++-13
```

**Fedora/RHEL**:
```bash
sudo dnf install gcc gcc-c++
```

### Clang

**Minimum version**: Clang 18

Required tools:
- `clang` - The compiler
- `llvm-ar` - Archive tool with LTO plugin support
- `llvm-profdata` - Profile data tool (for PGO)

**Ubuntu/Debian**:
```bash
sudo apt-get install clang-18 llvm-18
```

**Fedora/RHEL**:
```bash
sudo dnf install clang llvm
```

### Toolchain Verification

The build system automatically checks for required tools:

```bash
# With Clang + LTO
CC=clang CINDERX_ENABLE_LTO=1 python setup.py install
# Checks: clang, llvm-ar, llvm-profdata

# With GCC + LTO
CC=gcc CINDERX_ENABLE_LTO=1 python setup.py install
# Checks: gcc, gcc-ar, nm
```

Missing tools produce clear error messages:

```
Error: LTO requires llvm-ar but it was not found.
Please install: apt-get install llvm (Debian/Ubuntu)
                 dnf install llvm (Fedora)
Or disable LTO: CINDERX_ENABLE_LTO=0
```

## Troubleshooting

### "undefined reference" errors during link

This usually indicates missing LTO plugin support in the archive tool.

**Solution**: Ensure you're using `gcc-ar` (GCC) or `llvm-ar` (Clang) instead
of the system `ar`.

### Build takes too long

LTO builds use more memory and time. If you're resource-constrained:

```bash
# Disable LTO for faster builds
python setup.py install
```

Or use thin LTO (if available in your toolchain).

### LTO not detected at runtime

Check that the build actually used LTO:

```python
import cinderx

if not cinderx.is_lto_enabled():
    print("LTO was not enabled in this build")
```

Common causes:
- Build was interrupted before completion
- Environment variable was not set during build
- Build cache from non-LTO build was reused

**Solution**: Clean build cache and rebuild:

```bash
python setup.py clean --all
rm -rf build/
CINDERX_ENABLE_LTO=1 python setup.py install
```

### macOS build failures

If you see LTO-related errors on macOS, ensure you have the latest version:

```bash
pip install --upgrade cinderx
```

LTO should be automatically disabled on macOS in recent versions.
