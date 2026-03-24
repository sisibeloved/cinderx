# Phase 03B Docker LTO 集成总结

**日期**: 2026-03-24
**状态**: ✅ 完成
**分支**: bench-cur-7c361dce-opencode

---

## 🎯 目标

回滚 OpenCode 创建的独立 `docker/arm/` 框架，改为扩展现有的 `docker/cpython-baseline` 和 `docker/cinderx-test` 框架来支持 LTO 性能测试。

---

## ✅ 完成的工作

### 1. 回滚 OpenCode 的 Docker 改动

**删除的文件**:
- `docker/Dockerfile.arm`
- `docker/docker-compose.arm.yml`
- `docker/arm/scripts/build-lto.sh`
- `docker/arm/scripts/entrypoint.sh`
- `docker/arm/scripts/run-full-suite.sh`

**原因**: OpenCode 创建了全新的独立框架，没有复用现有的测试基础设施，导致代码重复和维护负担。

**提交**: `93641c50` - "revert: remove OpenCode's standalone docker/arm framework"

---

### 2. 扩展 docker/cpython-baseline 支持 LTO

#### 2.1 更新 Dockerfile

**添加的工具链**:
```dockerfile
# Install LLVM 19 for LTO/PGO support
RUN wget -qO /tmp/llvm.sh https://apt.llvm.org/llvm.sh \
    && chmod +x /tmp/llvm.sh \
    && /tmp/llvm.sh 19 \
    && rm -f /tmp/llvm.sh

# Create symlinks for LLVM tools
RUN ln -sf /usr/bin/llvm-ar-19 /usr/local/bin/llvm-ar \
    && ln -sf /usr/bin/llvm-profdata-19 /usr/local/bin/llvm-profdata \
    && ln -sf /usr/bin/llvm-ranlib-19 /usr/local/bin/llvm-ranlib \
    && ln -sf /usr/bin/llvm-nm-19 /usr/local/bin/llvm-nm
```

#### 2.2 新增脚本

**build-cinderx-lto.sh**:
- 支持配置化 LTO/PGO 构建（`ENABLE_LTO=1|0`, `ENABLE_PGO=1|0`）
- 自动检测已存在的 wheel
- 显示构建时间和 LTO 状态
- 单线程构建避免 ARM OOM

**test-lto-comparison.sh**:
- LTO vs non-LTO 自动对比测试
- 支持回归检测（阈值可配置，默认 1%）
- 生成 JSON 格式报告
- 集成现有 benchmark_harness.py

#### 2.3 新增文档

**README-LTO.md**:
- 快速开始指南
- 环境变量说明
- 性能目标和阈值
- 故障排查指南
- 与 cinderx-test 框架的集成说明

**提交**: `97842e22` - "feat(docker): add LTO support to cpython-baseline framework"

---

### 3. 扩展 docker/cinderx-test 支持 LTO

#### 3.1 新增脚本

**build-wheel-lto.sh**:
- 快速构建 LTO wheel（简化版）
- 支持 `ENABLE_LTO=1|0` 配置
- 显示构建结果和 wheel 路径

**test-lto-quick.sh**:
- 快速 LTO 性能测试（5 samples，快速反馈）
- 自动安装 CinderX
- 检测 LTO 状态
- 保存结果到 `/results/*.json`

#### 3.2 新增文档

**README-LTO.md**:
- 快速实验流程
- LTO vs non-LTO 对比方法
- 典型实验场景（基础性能、优化开关组合、构建时间）
- 与 cpython-baseline 的区别对比表
- 故障排查

**提交**: `05822c5b` - "feat(docker): add LTO support to cinderx-test framework"

---

## 📊 设计原则

### 复用现有基础设施

| 组件 | 复用内容 |
|------|----------|
| Dockerfile | 基于 python:3.14-slim，添加 LLVM 工具 |
| Scripts | 复用 benchmark_harness.py |
| Configs | 复用 configs/*.env 配置系统 |
| Results | 统一的 JSON 格式 |

### 两个框架的职责划分

| 特性 | cpython-baseline | cinderx-test |
|------|------------------|--------------|
| **用途** | 正式对照测试 | 快速实验验证 |
| **采样次数** | 10-20（高精度） | 5-10（快速反馈） |
| **结果目录** | `/results/benchmark/config/` | `/results/*.json` |
| **CI 集成** | ✅ 推荐 | ❌ 不推荐 |
| **构建** | 完整 wheel 构建 | 快速 wheel 构建 |
| **测试** | 全面对比测试 | 快速验证测试 |

---

## 🚀 使用示例

### cpython-baseline（正式测试）

```bash
# 1. 构建 LTO wheel
cd /path/to/cinderx
ENABLE_LTO=1 ./docker/cpython-baseline/scripts/build-cinderx-lto.sh

# 2. 启动容器
cd docker/cpython-baseline
docker compose build  # 首次或 Dockerfile 更新后
docker compose -p lto-test up -d

# 3. 运行对比测试
docker compose -p lto-test exec cpython-baseline bash -c \
  'BENCHMARK=generators SAMPLES=10 WARMUP=3 THRESHOLD_PCT=1.0 /scripts/test-lto-comparison.sh'

# 4. 查看结果
docker compose -p lto-test exec cpython-baseline cat /results/lto-comparison.json
```

### cinderx-test（快速实验）

```bash
# 1. 构建 LTO wheel
cd /path/to/cinderx
ENABLE_LTO=1 ./docker/cinderx-test/scripts/build-wheel-lto.sh

# 2. 启动容器
cd docker/cinderx-test
docker compose -p lto-exp up -d

# 3. 准备环境
docker compose -p lto-exp exec cinderx-arm64 bash -c \
  'BENCHMARK=generators /scripts/setup.sh'

# 4. 运行快速测试
docker compose -p lto-exp exec cinderx-arm64 bash -c \
  'BENCHMARK=generators SAMPLES=5 /scripts/test-lto-quick.sh'
```

---

## 📈 性能目标

| 指标 | 目标 | 阈值 | 优先级 |
|------|------|------|--------|
| 运行时性能 | +5% ~ +10% | ≥ -1%（无退化） | **必须** |
| 构建时间 | < 30% 增加 | ≤ 30% | **必须** |
| 内存使用 | < 10% 增加 | ≤ 8GB peak | 可选 |

---

## 🔄 下一步行动

### 立即行动（优先级：高）

1. **验证基础功能**
   ```bash
   # 测试 Dockerfile 构建
   cd docker/cpython-baseline
   docker compose build

   # 测试 wheel 构建
   ENABLE_LTO=1 ./scripts/build-cinderx-lto.sh
   ```

2. **运行基准测试**
   ```bash
   # 使用 cpython-baseline 运行完整对比
   BENCHMARK=generators SAMPLES=10 /scripts/test-lto-comparison.sh
   ```

3. **收集性能数据**
   - 运行 5 个 JIT-intensive benchmark
   - 对比 LTO vs non-LTO
   - 验证无性能退化

### 中期改进（优先级：中）

1. **CI/CD 集成**（Phase 03B-02）
   - 参考 `.planning/phases/03-validation/03B-02-PLAN.md`
   - 添加 GitHub Actions workflow
   - 自动化回归检测

2. **扩展 benchmark 覆盖**
   - 添加更多 JIT-intensive benchmark
   - 测试不同的 LTO 配置
   - 生成性能报告

3. **文档完善**
   - 更新 docs/performance.md
   - 添加故障排查案例
   - 记录最佳实践

### 长期优化（优先级：低）

1. **性能调优**
   - 分析 LTO 生成的代码
   - 识别优化机会
   - 调整编译器标志

2. **PGO 集成**
   - 添加 PGO 构建
   - 收集 profile 数据
   - 对比 LTO vs PGO vs LTO+PGO

---

## 🎓 经验教训

### 1. 复用优于重建

**问题**: OpenCode 创建了全新的独立框架

**教训**: 应该先充分理解现有架构，评估扩展的可能性，而不是立即创建新的框架

**结果**: 通过扩展现有框架，我们：
- 减少了代码重复
- 保持了架构一致性
- 降低了维护成本
- 加速了开发进度

### 2. 明确职责划分

**问题**: 两个框架的职责不清

**教训**: 明确定义每个组件的职责和适用场景

**结果**:
- cpython-baseline: 正式测试（高精度、CI 集成）
- cinderx-test: 快速实验（快速反馈、原型验证）

### 3. 文档先行

**问题**: OpenCode 的实现缺少使用文档

**教训**: 在编写代码之前，先定义清晰的使用场景和 API

**结果**: 每个新脚本都配备了详细的 README，包括：
- 快速开始指南
- 环境变量说明
- 故障排查
- 使用示例

---

## 📝 文件清单

### 回滚的文件（5 个）

```
docker/Dockerfile.arm
docker/docker-compose.arm.yml
docker/arm/scripts/build-lto.sh
docker/arm/scripts/entrypoint.sh
docker/arm/scripts/run-full-suite.sh
```

### 新增的文件（6 个）

```
docker/cpython-baseline/
├── README-LTO.md                        # LTO 测试指南
└── scripts/
    ├── build-cinderx-lto.sh            # LTO wheel 构建
    └── test-lto-comparison.sh          # LTO 对比测试

docker/cinderx-test/
├── README-LTO.md                        # 快速实验指南
└── scripts/
    ├── build-wheel-lto.sh              # 快速 LTO 构建
    └── test-lto-quick.sh               # 快速 LTO 测试
```

### 修改的文件（1 个）

```
docker/cpython-baseline/
└── Dockerfile                           # 添加 LLVM 工具链
```

---

## 🏆 成功标准

- [x] 回滚 OpenCode 的独立 docker/arm 框架
- [x] 扩展 docker/cpython-baseline 支持 LTO
- [x] 扩展 docker/cinderx-test 支持 LTO
- [x] 复用现有的 benchmark_harness.py
- [x] 提供完整的使用文档
- [x] 保持与现有框架的一致性
- [ ] **下一步**: 验证实际测试运行
- [ ] **下一步**: 收集性能数据
- [ ] **下一步**: 集成到 CI/CD（Phase 03B-02）

---

**总结**: 通过扩展现有的测试框架，我们成功实现了 LTO 性能测试的基础设施，避免了代码重复，保持了架构一致性，并为后续的 CI/CD 集成和性能优化奠定了坚实基础。

**下一步**: 运行实际测试验证 LTO 性能，调整优化配置，然后进入 Phase 03B-02（CI/CD 集成）。
