# CinderX LTO/PGO 性能修复 - 路线图

## 路线图概览

本项目分为 3 个阶段，按顺序执行：

| 阶段 | 名称 | 目标 | 预计时长 | 依赖 |
|------|------|------|----------|------|
| **Phase 1** | 基础修复 | 使 LTO 构建可用 | 1-2 周 | 无 |
| **Phase 2** | 功能完善 | 完整功能支持 | 1-2 周 | Phase 1 |
| **Phase 3** | 性能优化 | 达到性能目标 | 2-3 周 | Phase 2 |

---

## Phase 1: 基础修复 (Foundation)

**目标**: 修复 LTO 构建失败，确保 JIT 运行时函数安全

**成功标准**:
- LTO 构建在 ARM64/X86_64 Linux 上 100% 成功
- 运行时辅助函数不被 LTO 内联
- 基础功能测试通过

### Phase 1 Plans

**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md — JIT Runtime Function Protection (mark JITRT_* functions noinline)
- [x] 01-02-PLAN.md — Build System Improvements (PGO workload, toolchain checks, macOS graceful degradation)
- [x] 01-03-PLAN.md — Integration Testing (LTO regression test suite)

### Phase 1 任务分解

#### Task 1.1: 标记 JIT 运行时函数 [P0]

**描述**: 在 `jit_rt.h` 中标记所有 `JITRT_*` 函数为 noinline

**具体工作**:
```cpp
// cinderx/Jit/jit_rt.h
#define JIT_RUNTIME_API \
    __attribute__((noinline, visibility("default")))

JIT_RUNTIME_API
PyObject* JITRT_ReCompileCached(...);

JIT_RUNTIME_API
PyObject* JITRT_CallMethod(...);

// ... 其他 JITRT_* 函数
```

**验收标准**:
- [ ] 所有 `JITRT_*` 函数标记完成
- [ ] 编译通过
- [ ] 符号表检查：函数未被内联

**预计时间**: 2-3 天

---

#### Task 1.2: 更新 PGO 工作负载 [P0]

**描述**: 修改 `setup.py` 使用 JIT 密集型基准测试

**具体工作**:
```python
# setup.py 第258-277行
def get_pgo_workload():
    return [
        sys.executable, "-c",
        """
import cinderx
import cinderx.jit
cinderx.jit.auto()

# 使用 pyperformance 替代 CPython 测试套件
import pyperformance
pyperformance.run_suite([
    'richards', 'nbody', 'deltablue',
    'regex_compile', 'nqueens'
])
"""
    ]
```

**验收标准**:
- [ ] PGO 训练使用新的工作负载
- [ ] 训练时间控制在 10 分钟内
- [ ] 生成的 profile 数据有效

**预计时间**: 1-2 天

---

#### Task 1.3: 工具链完整性检查 [P0]

**描述**: 添加 LTO/PGO 工具链预检查

**具体工作**:
```python
# setup.py 新增函数
def check_lto_toolchain():
    cc, _ = get_compiler()
    if "clang" in cc:
        required = ['llvm-ar', 'llvm-profdata']
    else:
        required = ['gcc-ar', 'nm']
    
    for tool in required:
        if not shutil.which(tool):
            raise RuntimeError(
                f"LTO requires {tool} but it was not found.\n"
                f"Please install or disable LTO: "
                f"CINDERX_ENABLE_LTO=0"
            )
```

**验收标准**:
- [ ] Clang LTO 检查 `llvm-ar` 和 `llvm-profdata`
- [ ] GCC LTO 检查 `gcc-ar` 和 `nm`
- [ ] 缺失工具时给出清晰的错误信息

**预计时间**: 1-2 天

---

#### Task 1.4: macOS 优雅降级 [P1]

**描述**: macOS 自动禁用 LTO

**具体工作**:
```cmake
# CMakeLists.txt 第81-86行
if(ENABLE_LTO)
  if(MACOS)
    message(STATUS "LTO: Disabled on macOS (not supported)")
    set(ENABLE_LTO OFF)
  else()
    # ... 现有 LTO 逻辑
  endif()
endif()
```

**验收标准**:
- [ ] macOS 构建自动禁用 LTO
- [ ] 构建成功完成
- [ ] 日志输出降级信息

**预计时间**: 1 天

---

#### Task 1.5: Phase 1 集成测试

**测试内容**:
```bash
# 测试 1: LTO 构建
CINDERX_ENABLE_LTO=1 python setup.py install

# 测试 2: 运行时检查
python -c "import cinderx; print('OK')"

# 测试 3: 符号表检查
nm -C _cinderx.so | grep JITRT_ReCompileCached

# 测试 4: 基础功能测试
python -m pytest cinderx/PythonLib/test_cinderx/test_oss_quick.py -v
```

**预计时间**: 2-3 天

---

## Phase 2: 功能完善 (Features)

**目标**: 添加运行时检测、回归测试、完善文档

**成功标准**:
- 提供 LTO 状态查询 API
- LTO 回归测试套件就绪
- 构建文档更新完成

### Phase 2 Plans

**Plans:** 2 plans

Plans:
- [ ] 02-01-PLAN.md — LTO Detection API (cinderx.is_lto_enabled())
- [ ] 02-02-PLAN.md — Build Documentation Update (README.md, docs/build.md)

### Phase 2 任务分解

#### Task 2.1: LTO 状态检测 API [P1]

**描述**: 提供 API 查询当前构建是否启用 LTO

**具体工作**:
```cpp
// cinderx/Jit/lto_compat.h
namespace jit {
bool isLTOEnabled();
}

// cinderx/_cinderx-lib.cpp
PyObject* is_lto_enabled(PyObject* self) {
    return PyBool_FromLong(jit::isLTOEnabled());
}
```

```python
# cinderx/PythonLib/cinderx/__init__.py
def is_lto_enabled():
    try:
        from _cinderx import is_lto_enabled
        return is_lto_enabled()
    except ImportError:
        return False
```

**验收标准**:
- [ ] C++ API 可用
- [ ] Python API 可用
- [ ] 测试覆盖

**预计时间**: 2-3 天

---

#### Task 2.2: LTO 回归测试套件 [P1] ✅

**状态**: 已在 Phase 1 完成 (Plan 01-03)

**文件**: `cinderx/PythonLib/test_cinderx/test_lto_regression.py`

**包含测试**:
- `TestLTOSymbolIntegrity` - 验证 JITRT 符号未被内联
- `TestLTOBasicFunctionality` - 验证基本功能
- `TestLTOPerformanceBaseline` - 性能基线测试

---

---

#### Task 2.3: 构建文档更新 [P0]

**描述**: 更新 README 和构建文档

**具体工作**:
```markdown
# README.md 新增章节

## LTO/PGO 支持

### 启用 LTO（推荐 Linux）

```bash
CINDERX_ENABLE_LTO=1 python setup.py install
```

**要求**:
- GCC 13+ 或 Clang 18+
- Linux x86_64 或 ARM64
- 工具链: llvm-ar (Clang) 或 gcc-ar (GCC)

**注意**: macOS 不支持 LTO

### 启用 PGO

```bash
CINDERX_ENABLE_PGO=1 python setup.py install
```

PGO 三阶段流程:
1. 编译插桩版本
2. 运行基准测试收集 profile
3. 使用 profile 优化重新编译
```

**验收标准**:
- [ ] README 更新 LTO/PGO 说明
- [ ] 工具链安装指南
- [ ] 已知问题列表
- [ ] 性能对比数据

**预计时间**: 2-3 天

---

## Phase 3: 性能优化 (Optimization)

**目标**: 达到性能提升目标，验证无回归

**成功标准**:
- Richards 基准提升 +5%~10%
- 无性能劣化
- CI/CD 完整集成

### Phase 3 任务分解

#### Task 3.1: 性能基准测试 [P0]

**描述**: 建立 LTO vs 无 LTO 的性能对比基线

**具体工作**:
```bash
# scripts/bench/compare_lto_impact.py
#!/usr/bin/env python3
"""对比 LTO 和无 LTO 构建的性能差异"""

import subprocess
import json
import statistics

def run_benchmark(build_type, benchmark):
    """运行单个基准测试"""
    results = []
    for _ in range(5):
        result = subprocess.run(
            ['python', '-m', 'pyperformance', 'run', 
             '-b', benchmark, '--fast'],
            capture_output=True, text=True
        )
        # 解析结果
        results.append(parse_time(result.stdout))
    return {
        'mean': statistics.mean(results),
        'median': statistics.median(results),
        'stdev': statistics.stdev(results) if len(results) > 1 else 0
    }

# 对比无 LTO 和 LTO 构建
baseline = run_benchmark('no-lto', 'richards')
lto = run_benchmark('lto', 'richards')

print(f"Baseline: {baseline['mean']:.4f}s")
print(f"LTO: {lto['mean']:.4f}s")
print(f"Delta: {(lto['mean'] - baseline['mean']) / baseline['mean'] * 100:.2f}%")
```

**验收标准**:
- [ ] 自动化性能对比脚本
- [ ] 多轮次测试（n=5）
- [ ] 统计显著性检验
- [ ] CI 集成

**预计时间**: 3-5 天

---

#### Task 3.2: 性能调优迭代 [P2]

**描述**: 根据基准测试结果进行调优

**可能的方向**:
1. **LTO 分区**: 将 JIT 运行时函数放入独立 section
2. **链接器脚本**: 自定义代码布局优化缓存局部性
3. **PGO 训练优化**: 调整训练工作负载组合

**验收标准**:
- [ ] Richards 达到 +5% 提升或劣化 < 1%
- [ ] 完整 pyperformance 套件无回归
- [ ] 构建时间增加 < 30%

**预计时间**: 5-10 天（迭代过程）

---

#### Task 3.3: CI/CD 集成 [P1]

**描述**: 将 LTO/PGO 构建加入 CI 流程

**具体工作**:
```yaml
# .github/workflows/ci.yml 新增 job
lto-build:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v3
    
    - name: Install dependencies
      run: |
        sudo apt-get install -y llvm-ar llvm-profdata
    
    - name: Build with LTO
      run: |
        CINDERX_ENABLE_LTO=1 python setup.py install
    
    - name: Run LTO regression tests
      run: |
        python -m pytest cinderx/PythonLib/test_cinderx/test_lto_regression.py -v
    
    - name: Performance check
      run: |
        python scripts/bench/compare_lto_impact.py --quick
```

**验收标准**:
- [ ] GitHub Actions LTO 构建 job
- [ ] 性能回归检查
- [ ] 构建产物保存

**预计时间**: 2-3 天

---

## 里程碑与检查点

### Milestone 1: Phase 1 完成

**日期**: 预计项目开始后 1-2 周

**检查清单**:
- [ ] Task 1.1: JIT 运行时函数标记
- [ ] Task 1.2: PGO 工作负载更新
- [ ] Task 1.3: 工具链检查
- [ ] Task 1.4: macOS 降级
- [ ] Task 1.5: 集成测试通过

**进入 Phase 2 条件**: 所有 P0 任务完成，LTO 构建稳定

---

### Milestone 2: Phase 2 完成

**日期**: 预计项目开始后 3-4 周

**检查清单**:
- [ ] Task 2.1: LTO 状态 API
- [ ] Task 2.2: 回归测试套件
- [ ] Task 2.3: 文档更新

**进入 Phase 3 条件**: 功能完整，测试覆盖充分

---

### Milestone 3: Phase 3 完成

**日期**: 预计项目开始后 5-7 周

**检查清单**:
- [ ] Task 3.1: 性能基准测试
- [ ] Task 3.2: 性能调优（如需要）
- [ ] Task 3.3: CI/CD 集成

**项目完成条件**: 性能目标达成或劣化控制在 1% 以内

---

## 资源需求

### 人力资源

| 角色 | 阶段 1 | 阶段 2 | 阶段 3 |
|------|--------|--------|--------|
| C++ 工程师 | 1 FTE | 0.5 FTE | 0.5 FTE |
| Python 工程师 | 0.5 FTE | 0.5 FTE | 0.5 FTE |
| 性能工程师 | - | - | 1 FTE |

### 硬件资源

- **ARM64 Linux 服务器**: 用于性能测试（至少 1 台）
- **X86_64 Linux 服务器**: 用于 CI/CD 验证
- **构建时间预算**: 每个 commit 约 30 分钟（LTO 构建）

### 工具链

- GCC 13+ 或 Clang 18+
- llvm-ar, llvm-profdata (Clang)
- pyperformance 基准测试套件
- GitHub Actions CI/CD

---

## 风险缓解

| 风险 | 阶段 | 缓解措施 |
|------|------|---------|
| LTO 引入难以调试的崩溃 | 1-3 | 分阶段启用、充分测试、保留回退 |
| 性能提升不达预期 | 3 | 先确保不劣化，再追求提升 |
| ARM 服务器不可用 | 3 | 使用 X86_64 作为替代测试环境 |
| 工具链版本差异 | 1 | 文档明确支持的版本矩阵 |

---

## 附录

### A. 参考文档

- [LTO/PGO 性能劣化分析报告](./LTO_PGO_PERFORMANCE_ANALYSIS.md)
- [需求文档](./REQUIREMENTS.md)
- [代码库技术文档](./codebase/)

### B. 术语表

- **LTO**: Link-Time Optimization，链接时优化
- **PGO**: Profile-Guided Optimization，性能引导优化
- **JIT**: Just-In-Time，即时编译
- **HIR**: High-level Intermediate Representation，高层中间表示
- **LIR**: Low-level Intermediate Representation，低层中间表示

---

*路线图版本: 1.0*  
*创建日期: 2026-03-23*  
*最后更新: 2026-03-23*