# CinderX LTO Quick Experiments

本文档说明如何在 `docker/cinderx-test` 框架中进行快速的 LTO 性能实验。

## 快速开始

### 1. 构建 LTO wheel

```bash
cd /path/to/cinderx

# 构建 LTO wheel
ENABLE_LTO=1 ./docker/cinderx-test/scripts/build-wheel-lto.sh

# 或者构建非 LTO baseline
ENABLE_LTO=0 ./docker/cinderx-test/scripts/build-wheel-lto.sh
```

### 2. 启动实验容器

```bash
cd docker/cinderx-test

# 启动容器
docker compose -p lto-exp up -d

# 进入容器
docker compose -p lto-exp exec cinderx-arm64 bash
```

### 3. 运行快速 LTO 测试

在容器内：

```bash
# 准备环境
BENCHMARK=generators /scripts/setup.sh

# 运行 LTO 测试
BENCHMARK=generators SAMPLES=5 /scripts/test-lto-quick.sh
```

结果保存在 `/results/generators-lto-quick.json`。

## 对比 LTO vs non-LTO

### 方法 1: 分别构建和测试

```bash
# 1. 构建 LTO wheel
ENABLE_LTO=1 ./docker/cinderx-test/scripts/build-wheel-lto.sh

# 2. 启动容器并测试
cd docker/cinderx-test
docker compose -p lto-exp up -d
docker compose -p lto-exp exec cinderx-arm64 bash -c \
  'BENCHMARK=generators SAMPLES=5 /scripts/test-lto-quick.sh'

# 3. 保存结果
cp results/generators-lto-quick.json results/generators-lto.json

# 4. 构建 non-LTO wheel
ENABLE_LTO=0 ./docker/cinderx-test/scripts/build-wheel-lto.sh

# 5. 重启容器并测试
docker compose -p lto-exp down
docker compose -p lto-exp up -d
docker compose -p lto-exp exec cinderx-arm64 bash -c \
  'BENCHMARK=generators SAMPLES=5 /scripts/test-lto-quick.sh'

# 6. 对比结果
python3 -c "
import json
with open('results/generators-lto.json') as f: lto = json.load(f)
with open('results/generators-lto-quick.json') as f: baseline = json.load(f)
delta = ((lto['average'] / baseline['average']) - 1) * 100
print(f'LTO: {lto[\"average\"]:.6f}s')
print(f'Baseline: {baseline[\"average\"]:.6f}s')
print(f'Delta: {delta:+.2f}%')
"
```

### 方法 2: 使用配置文件

创建配置文件 `configs/generators/lto.env`:

```bash
# LTO optimization config
PYTHONJIT_ARM_INLINE_THRESHOLD=100
PYTHONJIT_ARM_SPECULATION=1
```

运行测试：

```bash
docker compose -p lto-exp exec cinderx-arm64 bash -c \
  'BENCHMARK=generators OPT_ENV_FILE=/scripts/configs/generators/lto.env SAMPLES=5 /scripts/test-benchmark.sh'
```

## 环境变量

- `ENABLE_LTO=1|0` - 启用/禁用 LTO（构建时）
- `BENCHMARK=<name>` - benchmark 名称
- `SAMPLES=<n>` - 采样次数（默认：5，快速实验用较少次数）
- `WARMUP=<n>` - 预热次数（默认：1）

## 典型实验流程

### 实验 1: 验证 LTO 基础性能

```bash
# 1. 构建 LTO wheel
ENABLE_LTO=1 ./docker/cinderx-test/scripts/build-wheel-lto.sh

# 2. 启动容器
cd docker/cinderx-test
docker compose -p lto-exp up -d

# 3. 测试多个 benchmark
for bench in generators mdp deltablue; do
  echo "Testing $bench..."
  docker compose -p lto-exp exec cinderx-arm64 bash -c \
    "BENCHMARK=$bench SAMPLES=5 /scripts/test-lto-quick.sh"
done
```

### 实验 2: LTO + 优化开关组合

```bash
# 创建实验配置
cat > configs/generators/lto-aggressive.env << 'EOF'
PYTHONJIT_ARM_INLINE_THRESHOLD=150
PYTHONJIT_ARM_SPECULATION=1
PYTHONJIT_ARM_OPT_LEVEL=3
EOF

# 运行测试
docker compose -p lto-exp exec cinderx-arm64 bash -c \
  'BENCHMARK=generators \
   OPT_ENV_FILE=/scripts/configs/generators/lto-aggressive.env \
   SAMPLES=10 \
   /scripts/test-benchmark.sh'
```

### 实验 3: 构建时间测量

```bash
# 测量 LTO 构建时间
time ENABLE_LTO=1 ./docker/cinderx-test/scripts/build-wheel-lto.sh

# 测量 non-LTO 构建时间
time ENABLE_LTO=0 ./docker/cinderx-test/scripts/build-wheel-lto.sh
```

## 与 cpython-baseline 的区别

| 特性 | cinderx-test | cpython-baseline |
|------|--------------|------------------|
| 用途 | 快速实验、原型验证 | 正式对照测试 |
| 采样次数 | 5-10（快速反馈） | 10-20（高精度） |
| 结果保存 | `/results/*.json` | `/results/benchmark/config/` |
| 配置系统 | 支持 | 支持 |
| CI 集成 | 不推荐 | 推荐 |

## 故障排查

### wheel 安装失败

**问题**：`pip install` 报错

**解决**：Python 3.14 的 pip 可能有问题，手动安装：

```bash
python3 -c "
import sys
import zipfile
import shutil
whl = '/dist/cinderx-*-linux_aarch64.whl'
with zipfile.ZipFile(whl) as z:
    z.extractall(sys.prefix)
"
```

### JIT 未启用

**问题**：`jit.is_enabled()` 返回 False

**检查**：

```bash
python3 -c "
import cinderx
import cinderx.jit as jit
print(f'Initialized: {cinderx.is_initialized()}')
print(f'JIT: {jit.is_enabled()}')
jit.enable()
print(f'JIT after enable: {jit.is_enabled()}')
"
```

## 下一步

- 如果实验结果良好，使用 `docker/cpython-baseline` 进行正式测试
- 调整优化开关，找到最佳配置
- 将稳定的配置迁移到 `cpython-baseline/configs/`
