# CinderX LTO/PGO 性能修复 - 需求文档

## 需求总览

本文档定义 CinderX JIT 编译器 LTO/PGO 性能修复项目的完整需求集合。所有需求按优先级排序，包含功能需求、性能需求和兼容性需求。

---

## 1. 功能需求

### FR-001: LTO 安全模式 [P0 - 必须]

**描述**: 实现 LTO 安全编译模式，保护 JIT 运行时函数免受过度优化

**验收标准**:
- [ ] 标记所有 `JITRT_*` 运行时辅助函数为 `__attribute__((noinline))`
- [ ] 确保 JIT 入口点函数地址在 LTO 后保持稳定
- [ ] 在 `jit_rt.h` 中添加 `JIT_RUNTIME_API` 宏统一标记
- [ ] 编译时检查：LTO 构建不内联关键运行时函数

**测试方法**:
```bash
# 构建后检查符号表
nm -C _cinderx.so | grep JITRT_ReCompileCached
# 预期: 符号存在且为 T (text 段)，非 I (内联)
```

---

### FR-002: PGO 工作负载更新 [P0 - 必须]

**描述**: 替换 PGO 训练工作负载，使用 JIT 密集型基准测试

**验收标准**:
- [ ] 修改 `setup.py` 中的 PGO 工作负载
- [ ] 使用 `pyperformance` 基准测试套件替代 CPython 测试套件
- [ ] 至少包含：richards, nbody, deltablue, regex_compile
- [ ] 训练时间控制在 5-10 分钟内

**当前代码**:
```python
# setup.py 第259-277行 - 需修改
workload_cmd = [
    sys.executable, "-c",
    """
import cinderx
import cinderx.jit
cinderx.jit.auto()

# 运行 JIT 密集型基准测试
import pyperformance
pyperformance.run_suite([
    'richards', 'nbody', 'deltablue', 
    'regex_compile', 'nqueens'
])
"""
]
```

---

### FR-003: 工具链完整性检查 [P0 - 必须]

**描述**: 在启用 LTO/PGO 前检查工具链完整性

**验收标准**:
- [ ] Clang LTO 检查 `llvm-ar` 和 `llvm-profdata`
- [ ] GCC LTO 检查 `gcc-ar` 和 `nm`
- [ ] 缺失工具时给出明确错误信息
- [ ] 提供降级选项：自动禁用 LTO 并继续构建

**错误信息示例**:
```
Error: LTO requires llvm-ar but it was not found.
Please install: apt-get install llvm-ar (Debian/Ubuntu)
                 dnf install llvm-static (Fedora)
Or disable LTO: CINDERX_ENABLE_LTO=0 python setup.py install
```

---

### FR-004: macOS 优雅降级 [P1 - 重要]

**描述**: macOS 平台自动禁用 LTO，提供清晰的文档说明

**验收标准**:
- [ ] `CMakeLists.txt` 检测 macOS 时自动设置 `ENABLE_LTO=OFF`
- [ ] 构建日志输出信息："LTO disabled on macOS (not supported)"
- [ ] 不中断构建流程，正常完成
- [ ] 文档说明 macOS 限制

---

### FR-005: 运行时 LTO 检测 API [P1 - 重要]

**描述**: 提供 API 查询当前构建是否启用 LTO

**验收标准**:
- [ ] Python API: `cinderx.is_lto_enabled()` 返回 bool
- [ ] C++ API: `jit::isLTOEnabled()` 返回 bool
- [ ] 在 `test_oss_quick.py` 中验证

---

### FR-006: LTO 回归测试套件 [P1 - 重要]

**描述**: 创建专门的 LTO 回归测试

**验收标准**:
- [ ] 测试 JIT 编译时间不劣化超过 5%
- [ ] 测试运行时辅助函数调用开销
- [ ] 测试代码大小变化（应减少或持平）
- [ ] CI 流程包含 LTO 构建测试

**测试文件**: `cinderx/PythonLib/test_cinderx/test_lto_regression.py`

---

## 2. 性能需求

### PR-001: 基准性能不劣化 [P0 - 必须]

**描述**: 修复后 LTO 构建的性能不劣于无 LTO 构建

**验收标准**:
```
Richards 基准测试:
- 无 LTO: baseline (0.0516s median)
- 有 LTO: ≤ baseline × 1.01 (允许 1% 测量误差)

N-body 基准测试:
- 无 LTO: baseline
- 有 LTO: ≤ baseline × 1.01

综合测试 (pyperformance 完整套件):
- 几何平均值劣化 ≤ 1%
```

**测试环境**: ARM64 Linux, Python 3.14.3

---

### PR-002: 目标性能提升 [P2 - 期望]

**描述**: 理想情况下 LTO 应带来性能提升

**目标**:
- Richards: +5%~10% 性能提升
- N-body: +3%~8% 性能提升
- 完整 pyperformance 套件: +3%~5% 几何平均提升

**注意**: 这是目标而非硬性要求。先确保不劣化，再追求提升。

---

### PR-003: 构建时间控制 [P1 - 重要]

**描述**: LTO 构建时间增加控制在合理范围内

**验收标准**:
- LTO 构建时间 ≤ 无 LTO 构建时间 × 1.30 (30% 增加)
- PGO 三阶段总时间 ≤ 15 分钟（单个 benchmark worker）

**测量方法**:
```bash
time CINDERX_ENABLE_LTO=1 python setup.py install
```

---

### PR-004: 内存使用控制 [P2 - 期望]

**描述**: LTO 链接阶段内存占用不超限

**验收标准**:
- 峰值 RSS ≤ 8GB（ARM64/X86_64）
- 不触发 OOM killer

---

## 3. 兼容性需求

### CR-001: 编译器支持矩阵 [P0 - 必须]

**描述**: 明确支持的编译器和版本

| 编译器 | 版本 | LTO | PGO | 状态 |
|--------|------|-----|-----|------|
| GCC | 13+ | ✅ | ✅ | 主要目标 |
| GCC | 12 | ⚠️ | ⚠️ | 尽力支持 |
| Clang | 18+ | ✅ | ✅ | 主要目标 |
| Clang | 17 | ⚠️ | ⚠️ | 尽力支持 |
| MSVC | - | ❌ | ❌ | 不支持 |

**验收标准**:
- [ ] GCC 13 CI 测试通过
- [ ] Clang 18 CI 测试通过
- [ ] 文档明确说明支持的版本

---

### CR-002: 平台支持矩阵 [P0 - 必须]

**描述**: 明确支持的平台

| 平台 | 架构 | LTO | PGO | 状态 |
|------|------|-----|-----|------|
| Linux | x86_64 | ✅ | ✅ | 完全支持 |
| Linux | ARM64 | ✅ | ✅ | 主要目标 |
| macOS | x86_64 | ❌ | ❌ | 不支持 |
| macOS | ARM64 | ❌ | ❌ | 不支持 |
| Windows | - | ❌ | ❌ | 不支持 |

---

### CR-003: 向后兼容 [P0 - 必须]

**描述**: 无 LTO/PGO 的构建方式继续完全支持

**验收标准**:
- [ ] `CINDERX_ENABLE_LTO=0` 构建零回归
- [ ] `CINDERX_ENABLE_PGO=0` 构建零回归
- [ ] 不设置环境变量时行为不变（默认禁用）
- [ ] 所有现有测试继续通过

---

## 4. 文档需求

### DR-001: 构建文档更新 [P0 - 必须]

**描述**: 更新 README 和构建文档

**内容**:
- [ ] LTO/PGO 启用说明
- [ ] 工具链安装指南
- [ ] 已知问题列表
- [ ] 性能对比数据

**文档位置**: `README.md`, `docs/build.md`

---

### DR-002: 开发者文档 [P1 - 重要]

**描述**: 为 CinderX 开发者提供 LTO/PGO 内部机制说明

**内容**:
- [ ] JIT 运行时函数保护机制
- [ ] PGO 训练数据收集流程
- [ ] 调试 LTO 问题的技巧

**文档位置**: `docs/lto-pgo-internals.md`

---

### DR-003: API 文档 [P2 - 期望]

**描述**: 新增 API 的文档

**内容**:
- [ ] `cinderx.is_lto_enabled()` 用法
- [ ] `cinderx.is_pgo_enabled()` 用法

---

## 5. 需求优先级汇总

### P0 - 必须 (Must Have)
- FR-001: LTO 安全模式
- FR-002: PGO 工作负载更新
- FR-003: 工具链完整性检查
- PR-001: 基准性能不劣化
- CR-001: 编译器支持矩阵
- CR-002: 平台支持矩阵
- CR-003: 向后兼容
- DR-001: 构建文档更新

### P1 - 重要 (Should Have)
- FR-004: macOS 优雅降级
- FR-005: 运行时 LTO 检测 API
- FR-006: LTO 回归测试套件
- PR-003: 构建时间控制
- DR-002: 开发者文档

### P2 - 期望 (Nice to Have)
- PR-002: 目标性能提升
- PR-004: 内存使用控制
- DR-003: API 文档

---

## 6. 需求追踪

| 需求ID | 状态 | 负责人 | 预计完成 | 实际完成 |
|--------|------|--------|----------|----------|
| FR-001 | 📝 待办 | TBD | Phase 1 | - |
| FR-002 | 📝 待办 | TBD | Phase 1 | - |
| FR-003 | 📝 待办 | TBD | Phase 1 | - |
| FR-004 | 📝 待办 | TBD | Phase 1 | - |
| FR-005 | 📝 待办 | TBD | Phase 2 | - |
| FR-006 | 📝 待办 | TBD | Phase 2 | - |
| PR-001 | 📝 待办 | TBD | Phase 3 | - |
| ... | ... | ... | ... | ... |

**图例**:
- 📝 待办
- 🚧 进行中
- ✅ 完成
- ❌ 阻塞

---

## 7. 变更历史

| 日期 | 版本 | 变更 | 作者 |
|------|------|------|------|
| 2026-03-23 | 1.0 | 初始版本 | GSD |

---

*文档生成: GSD new-project*  
*模板版本: 1.0*