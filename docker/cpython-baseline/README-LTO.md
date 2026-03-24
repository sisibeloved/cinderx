# CinderX LTO Performance Testing

本文档说明如何使用现有的 `docker/cpython-baseline` 和 `docker/cinderx-test` 框架进行 LTO 性能测试。

## 概述

Link-Time Optimization (LTO) 可以显著提升 CinderX 的运行时性能（目标：5-10% 提升），但会增加构建时间（限制：< 30%）。

## 快速开始

### 1. 构建 LTO wheel（在宿主机）

```bash
cd /path/to/cinderx

# 构建 LTO wheel
ENABLE_LTO=1 ./docker/cpython-baseline/scripts/build-cinderx-lto.sh

# 构建非 LTO baseline（用于对比）
ENABLE_LTO=0 ./docker/cpython-baseline/scripts/build-cinderx-lto.sh
```

构建完成后，wheel 文件会保存在 `dist/cinderx-*-linux_aarch64.whl`。

### 2. 启动测试容器

```bash
cd docker/cpython-baseline

# 构建镜像（首次或 Dockerfile 更新后）
docker compose build

# 启动容器
docker compose -p lto-test up -d
```

### 3. 运行 LTO 性能对比测试

```bash
# 进入容器
docker compose -p lto-test exec cpython-baseline bash

# 在容器内运行测试
BENCHMARK=generators SAMPLES=10 WARMUP=3 /scripts/test-lto-comparison.sh
```

### 4. 查看结果

测试结果保存在 `/results/lto-comparison.json`：

```json
{
  "baseline_avg": 0.050000,
  "lto_avg": 0.047500,
  "delta_pct": -5.0,
  "threshold_pct": 1.0,
  "passed": true,
  "status": "PASS (improvement: 5.00%)"
}
```

## 性能目标

| 指标 | 目标 | 阈值 | 要求 |
|------|------|------|------|
| 运行时性能 | +5% ~ +10% 提升 | ≥ -1%（无退化） | **必须** |
| 构建时间 | < 30% 增加 | ≤ 30% | **必须** |

## 测试流程

### 单次基准测试

测试单个 benchmark：

```bash
docker compose -p lto-test exec cpython-baseline bash -c \
  'BENCHMARK=generators SAMPLES=10 WARMUP=3 /scripts/test-lto-comparison.sh'
```

### 多个 benchmark 测试

批量测试多个 benchmark：

```bash
for bench in generators mdp deltablue nbody regex_compile; do
  echo "Testing $bench..."
  docker compose -p lto-test exec cpython-baseline bash -c \
    "BENCHMARK=$bench SAMPLES=10 WARMUP=3 /scripts/test-lto-comparison.sh"
done
```

### 构建时间对比

测量 LTO vs non-LTO 的构建时间：

```bash
# Baseline 构建
time ENABLE_LTO=0 ./docker/cpython-baseline/scripts/build-cinderx-lto.sh

# LTO 构建
time ENABLE_LTO=1 ./docker/cpython-baseline/scripts/build-cinderx-lto.sh
```

## 环境变量

### 构建相关

- `ENABLE_LTO=1|0` - 启用/禁用 LTO（默认：1）
- `ENABLE_PGO=1|0` - 启用/禁用 PGO（默认：0）

### 测试相关

- `BENCHMARK=<name>` - 要测试的 benchmark 名称（默认：generators）
- `SAMPLES=<n>` - 采样次数（默认：10）
- `WARMUP=<n>` - 预热次数（默认：3）
- `THRESHOLD_PCT=<n>` - 回归检测阈值百分比（默认：1.0）

## 故障排查

### LTO 构建失败

**问题**：`llvm-ar: command not found`

**解决**：确保 Dockerfile 中安装了 LLVM 工具：

```bash
# 在容器内检查
which llvm-ar
llvm-ar --version
```

### 性能退化检测

**问题**：测试报告性能退化 > 1%

**调试步骤**：

1. 增加采样次数以减少噪声：`SAMPLES=20`
2. 检查系统负载：确保容器有足够资源
3. 验证 LTO 是否真正启用：查看构建日志

```bash
# 在容器内检查 LTO 状态
python3 -c "
import cinderx
import cinderx.jit as jit
jit.enable()
print(f'JIT enabled: {jit.is_enabled()}')
if hasattr(cinderx, 'is_lto_enabled'):
    print(f'LTO enabled: {cinderx.is_lto_enabled()}')
"
```

### Benchmark 不存在

**问题**：`ERROR: benchmark 'xxx' not found`

**解决**：检查 `benchmark_harness.py` 中的 benchmark 列表，或添加新的 benchmark 定义。

## 与现有框架集成

### docker/cpython-baseline

`docker/cpython-baseline` 用于正式对照测试：
- Stock CPython JIT vs CinderX JIT
- LTO vs non-LTO 性能对比
- 生成正式的性能报告

### docker/cinderx-test

`docker/cinderx-test` 用于快速实验：
- 频繁切换优化开关
- 快速验证单个优化
- 原型测试

两个框架共享：
- 相同的 benchmark harness (`benchmark_harness.py`)
- 相同的配置系统 (`configs/*.env`)
- 相同的结果格式

## 下一步

1. 运行完整的 benchmark 套件
2. 分析性能数据，识别优化机会
3. 调整 LTO 配置以平衡构建时间和运行时性能
4. 将 LTO 测试集成到 CI/CD（Phase 03B-02）

## 参考资料

- [LTO/PGO 性能分析](../../../.planning/LTO_PGO_PERFORMANCE_ANALYSIS.md)
- [性能文档](../../../docs/performance.md)
- [项目路线图](../../../.planning/ROADMAP.md)
