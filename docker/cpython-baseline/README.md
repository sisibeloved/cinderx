# CinderX 性能测试环境

## 概述

使用 Docker 容器测试 CinderX 的性能提升。容器基于 Python 3.14 官方镜像，包含编译工具和测试脚本。

## 快速开始

### 1. 构建 CinderX wheel（在宿主机）

```bash
cd /Users/luchen/Repo/cinderx

# 使用 Docker 交叉编译 ARM64 wheel
docker run --rm --platform linux/arm64 \
  -v "$PWD:/cinderx" \
  -w /cinderx \
  python:3.14-slim bash -c '
    apt-get update -qq && apt-get install -y -qq build-essential cmake git > /dev/null 2>&1
    pip install --quiet build
    export CMAKE_BUILD_PARALLEL_LEVEL=1
    export CINDERX_BUILD_JOBS=1
    python -m build --wheel
    ls -lh dist/cinderx-*-linux_aarch64.whl
  '
```

### 2. 启动测试容器

```bash
cd /Users/luchen/Repo/cinderx/docker/cpython-baseline
docker compose up -d
docker compose exec cpython-baseline bash
```

### 3. 在容器内安装 CinderX

```bash
pip install /dist/cinderx-*-linux_aarch64.whl
```

### 4. 准备 benchmark

```bash
python3 << 'PY'
import urllib.request
import pathlib

url = "https://raw.githubusercontent.com/python/pyperformance/main/pyperformance/data-files/benchmarks/bm_generators/run_benchmark.py"
output_path = pathlib.Path("/root/benchmarks/run_benchmark.py")

print(f"Downloading {url}...")
urllib.request.urlretrieve(url, output_path)
print(f"✓ Saved to {output_path}")
PY
```

### 5. 测试 CPython baseline

```bash
python3 << 'PY'
import sys
import time
import statistics

sys.path.insert(0, "/root/benchmarks")
from run_benchmark import bench_generators

# Warmup
for _ in range(3):
    bench_generators(1)

# Measure
times = []
for i in range(10):
    start = time.perf_counter()
    bench_generators(1)
    elapsed = time.perf_counter() - start
    times.append(elapsed)
    print(f"Run {i+1}: {elapsed:.6f}s")

avg = statistics.mean(times)
print(f"\nBaseline: {avg:.6f}s")
PY
```

### 6. 测试 CinderX

```bash
python3 << 'PY'
import sys
import time
import statistics
import cinderx
import cinderx.jit as jit

jit.enable()
print(f"JIT enabled: {jit.is_enabled()}")

sys.path.insert(0, "/root/benchmarks")
from run_benchmark import bench_generators

# Warmup
for _ in range(3):
    bench_generators(1)

# Measure
times = []
for i in range(10):
    start = time.perf_counter()
    bench_generators(1)
    elapsed = time.perf_counter() - start
    times.append(elapsed)
    print(f"Run {i+1}: {elapsed:.6f}s")

avg = statistics.mean(times)
print(f"\nCinderX: {avg:.6f}s")
PY
```

### 7. 测试 CinderX + 优化

```bash
PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY=1 python3 << 'PY'
import sys
import time
import statistics
import os

print(f"Optimization enabled: PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY={os.environ.get('PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY')}")

import cinderx
import cinderx.jit as jit
jit.enable()

sys.path.insert(0, "/root/benchmarks")
from run_benchmark import bench_generators

# Warmup
for _ in range(3):
    bench_generators(1)

# Measure
times = []
for i in range(10):
    start = time.perf_counter()
    bench_generators(1)
    elapsed = time.perf_counter() - start
    times.append(elapsed)
    print(f"Run {i+1}: {elapsed:.6f}s")

avg = statistics.mean(times)
print(f"\nCinderX (optimized): {avg:.6f}s")
PY
```

### 8. 计算对比

```bash
python3 << 'PY'
# 输入上面三步得到的结果
baseline = 0.XX  # 从步骤 5 获取
cinderx = 0.XX   # 从步骤 6 获取
optimized = 0.XX # 从步骤 7 获取

speedup_cx = baseline / cinderx
speedup_opt = baseline / optimized
opt_benefit = cinderx / optimized

print(f"Baseline:            {baseline:.6f}s")
print(f"CinderX:             {cinderx:.6f}s")
print(f"CinderX (optimized): {optimized:.6f}s")
print()
print(f"Speedup (CinderX):   {speedup_cx:.4f}x ({(speedup_cx-1)*100:+.2f}%)")
print(f"Speedup (optimized): {speedup_opt:.4f}x ({(speedup_opt-1)*100:+.2f}%)")
print(f"Optimization benefit: {opt_benefit:.4f}x ({(opt_benefit-1)*100:+.2f}%)")
PY
```

## 预期结果

根据根因分析，预期在真实 ARM 硬件上：
- CinderX baseline: 性能接近 CPython
- CinderX optimized (generators): 约 +0.79% 提升

注意：Docker ARM64 模拟（QEMU）的性能数据不精确，仅用于功能验证。

## 清理

```bash
docker compose down
```

## 故障排除

### wheel 安装失败
确保使用 Python 3.14 编译的 wheel：
```bash
python3 --version  # 应该是 3.14.x
pip debug --verbose  # 检查兼容的 tag
```

### JIT 没有启用
```bash
python3 -c "import cinderx.jit as jit; print(jit.is_enabled())"
```

### 优化没有触发
检查环境变量和文件路径：
```bash
echo $PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY
python3 -c "
import sys
sys.path.insert(0, '/root/benchmarks')
from run_benchmark import Tree
print(f'qualname: {Tree.__iter__.__code__.co_qualname}')
print(f'filename: {Tree.__iter__.__code__.co_filename}')
"
```
