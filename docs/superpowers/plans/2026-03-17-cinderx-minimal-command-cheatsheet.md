# CinderX 最小命令清单

## 1. 本地安装 CinderX 到 CPython venv

```bash
cd /Users/luchen/Repo/cinderx

python3.14 -m venv /tmp/cinderx314-local

ENABLE_STATIC_PYTHON=0 \
ENABLE_ADAPTIVE_STATIC_PYTHON=0 \
ENABLE_LIGHTWEIGHT_FRAMES=0 \
CC=gcc-15 \
CXX=g++-15 \
/tmp/cinderx314-local/bin/python -m pip install -e . --no-build-isolation
```

## 2. 最小 smoke：确认 CinderX / JIT 可用

```bash
cd /Users/luchen/Repo/cinderx

PYTHONPATH=cinderx/PythonLib /tmp/cinderx314-local/bin/python - <<'PY'
import cinderx
import cinderx.jit as jit

assert cinderx.is_initialized()
jit.enable()

def f(n):
    s = 0
    for i in range(n):
        s += i
    return s

assert jit.force_compile(f)
assert jit.is_jit_compiled(f)
print("ok", jit.get_compiled_size(f))
PY
```

## 3. 本地 direct-run 一个 pyperformance benchmark

```bash
cd /Users/luchen/Repo/cinderx

/tmp/cinderx314-local/bin/python scripts/arm/bench_pyperf_direct.py \
  --module-path /Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_generators/run_benchmark.py \
  --bench-func bench_generators \
  --bench-args-json "[1]" \
  --samples 3 \
  --prewarm-runs 1 \
  --compile-strategy all \
  --specialized-opcodes
```

## 4. 本地用 benchmark 名跑 quick validation

```bash
cd /Users/luchen/Repo/cinderx

/tmp/cinderx314-local/bin/python scripts/arm/run_local_pyperf_matrix.py \
  --pyperformance-root /Users/luchen/Repo/pyperformance \
  --benchmark coroutines \
  --mode baseline \
  --python /tmp/cinderx314-local/bin/python \
  --samples 3 \
  --prewarm-runs 1
```

## 5. 交叉编译并反汇编

```bash
aarch64-linux-gnu-gcc -O3 -c probe.c -o probe.aarch64.o
aarch64-linux-gnu-objdump -dr probe.aarch64.o > probe.aarch64.objdump.txt

x86_64-linux-gnu-gcc -O3 -c probe.c -o probe.x86_64.o
x86_64-linux-gnu-objdump -dr probe.x86_64.o > probe.x86_64.objdump.txt
```

## 6. 远端 Linux Arm 标准构建 + pyperformance

```bash
INCOMING_DIR=/root/work/incoming \
WORKDIR=/root/work/cinderx-main \
PYTHON=/opt/python-3.14/bin/python3.14 \
DRIVER_VENV=/root/venv-cinderx314 \
BENCH=richards \
AUTOJIT=50 \
PARALLEL=1 \
SKIP_PYPERF=0 \
RECREATE_PYPERF_VENV=1 \
/root/work/incoming/remote_update_build_test.sh
```

## 7. 手工直跑远端 pyperformance

```bash
. /root/venv-cinderx314/bin/activate
python -m pyperformance run --debug-single-value -b richards -o /root/work/arm-sync/richards.json
```
