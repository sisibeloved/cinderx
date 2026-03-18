# regex_compile JIT 优化设计文档

**日期**: 2026-03-17
**状态**: 草稿
**作者**: Claude Code
**目标用例**: pyperformance regex_compile

## 1. 问题陈述

### 当前情况

在 ARM 服务器上测试 pyperformance 用例时，发现 **regex_compile** 用例存在性能劣化：

| 环境 | 性能 | 备注 |
|------|------|------|
| CPython JIT | ~84ms | 基线 |
| CinderX JIT | ~96ms | 慢约 14% |

**劣化因子**: 1.14x（CinderX 比 CPython 慢 14%）

### 用例分析

regex_compile 用例主要测试正则表达式编译性能：

```python
def bench_regex_compile(loops, regexes):
    for _ in range(loops):
        for regex, flags in regexes:
            re.purge()           # 清除缓存
            re.compile(regex, flags)  # 强制重新编译
```

**关键特征**：
1. 主要是 C 函数调用密集型（`re.purge()`, `re.compile()`）
2. 循环结构简单，但执行次数多
3. 涉及频繁的内存分配（正则表达式对象）

### 劣化原因假设

基于代码分析，可能的性能瓶颈包括：

1. **C 函数调用开销**（方案 A）：
   - JIT 编译代码调用 C 函数时的边界开销
   - 寄存器保存/恢复过多
   - 参数传递效率低

2. **JIT 编译开销**（方案 B）：
   - HIR/LIR 编译流程中的瓶颈
   - 过度优化导致的编译时间开销

3. **内存分配模式**（方案 C）：
   - JIT 编译代码的内存分配策略不佳
   - 额外的 GC 压力

## 2. 优化目标

### 主要目标

消除 14% 性能劣化，将 CinderX JIT 的 regex_compile 性能提升到至少 CPython 基线水平。

### 量化目标

| 指标 | 当前 | 目标 |
|------|------|------|
| CPython 基线（ARM） | ~84ms | N/A |
| CinderX JIT（ARM） | ~96ms | **≤84ms** |
| 劣化因子 | 1.14x | **≤1.0x** |

### 约束条件

1. **不影响其他用例**：其他 pyperformance 用例性能不能回退 >2%
2. **通过现有测试**：所有 CinderX 测试套件必须通过
3. **ARM Docker 验证**：必须在 ARM Docker 容器中验证优化效果
4. **HIR 对比报告**：必须提供优化前后的 HIR 对比

## 3. 诊断阶段（Phase 0）

### 3.1 诊断基础设施

**创建诊断脚本**：

```python
# scripts/diagnostics/benchmark_regex_compile.py
#!/usr/bin/env python3
"""
regex_compile 性能诊断工具
比较 CPython 与 CinderX JIT 在 regex_compile 用例上的性能
"""

import sys
import time
import statistics
from pathlib import Path

# 添加 pyperformance 路径
sys.path.insert(0, str(Path.home() / "Repo" / "pyperformance"))

def capture_regexes():
    """捕获 regex_compile 用例中使用的正则表达式"""
    import re
    regexes = []
    
    real_compile = re.compile
    real_search = re.search
    real_sub = re.sub
    
    def capture_compile(regex, flags=0):
        regexes.append((regex, flags))
        return real_compile(regex, flags)
    
    def capture_search(regex, target, flags=0):
        regexes.append((regex, flags))
        return real_search(regex, target, flags)
    
    def capture_sub(regex, *args):
        regexes.append((regex, 0))
        return real_sub(regex, *args)
    
    re.compile = capture_compile
    re.search = capture_search
    re.sub = capture_sub
    
    try:
        from pyperformance.data-files.benchmarks.bm_regex_compile import bm_regex_effbot
        bm_regex_effbot.bench_regex_effbot(1)
        from pyperformance.data-files.benchmarks.bm_regex_compile import bm_regex_v8
        bm_regex_v8.bench_regex_v8(1)
    finally:
        re.compile = real_compile
        re.search = real_search
        re.sub = real_sub
    
    return regexes

def bench_with_cinderjit(regexes, loops=10):
    """使用 CinderX JIT 运行基准测试"""
    import re
    
    times = []
    for _ in range(loops):
        start = time.perf_counter()
        for regex, flags in regexes:
            re.purge()
            re.compile(regex, flags)
        times.append(time.perf_counter() - start)
    
    return statistics.mean(times), statistics.stdev(times)

def verify_jit_compilation(func):
    """验证函数是否被 JIT 编译"""
    try:
        import cinderjit
        cinderjit.force_compile(func)
        is_compiled = cinderjit.is_jit_compiled(func)
        size = cinderjit.get_compiled_size(func) if is_compiled else 0
        return is_compiled, size
    except ImportError:
        return False, 0
```

### 3.2 诊断检查点

**检查点 1：基准性能对比**

```bash
# 在 Docker ARM64 中运行
python3 scripts/diagnostics/benchmark_regex_compile.py
```

输出示例：
```
=== regex_compile 性能诊断 ===

[1] CPython 基线
    时间: 84.5ms ± 2.1ms

[2] CinderX JIT
    时间: 96.3ms ± 2.8ms
    慢化: 1.14x

[3] JIT 编译验证
    bench_regex_compile 已编译: True
    代码大小: 2048 bytes
```

**检查点 2：HIR 导出与分析**

```python
# 导出 HIR 用于分析
import cinderjit
import os

os.environ['PYTHONJITLOG'] = '1'
os.environ['PYTHONJITHIRDUMP'] = '1'

# 运行基准测试以触发 JIT 编译
cinderjit.enable()
# ... 运行测试
```

**检查点 3：分段计时**

```python
def profile_phases(regexes):
    """分析各阶段耗时"""
    import re
    
    purge_times = []
    compile_times = []
    loop_overhead_times = []
    
    for regex, flags in regexes:
        # 测量 re.purge()
        t0 = time.perf_counter()
        re.purge()
        t1 = time.perf_counter()
        purge_times.append(t1 - t0)
        
        # 测量 re.compile()
        t0 = time.perf_counter()
        re.compile(regex, flags)
        t1 = time.perf_counter()
        compile_times.append(t1 - t0)
    
    return {
        'purge_avg': statistics.mean(purge_times),
        'compile_avg': statistics.mean(compile_times),
    }
```

**检查点 4：Docker ARM64 验证**

```bash
# 在 cpython-baseline 容器中
docker-compose -f docker/cpython-baseline/docker-compose.yml up -d
docker exec -it cpython-baseline-test /bin/bash

# 运行诊断
python3 /scripts/benchmark_regex_compile.py
```

**诊断报告输出**：
- 性能瓶颈识别报告
- JIT 编译状态确认
- 各阶段耗时分布
- HIR 代码片段（优化前）

## 4. 优化策略

### 4.1 方案 A：优化 C 函数调用路径

**适用场景**：诊断发现 JIT 编译代码调用 C 函数存在明显开销

**优化策略**：

1. **优化调用约定**：
   - 减少寄存器保存/恢复
   - 使用更高效的参数传递方式
   - 减少栈帧操作

2. **实现位置**：
   - `cinderx/Jit/codegen/gen_asm.cpp` - 代码生成
   - `cinderx/Jit/lir/regalloc.cpp` - 寄存器分配
   - `cinderx/Jit/hir/builder.cpp` - HIR 构建

3. **HIR 对比示例**：

优化前：
```
# 调用 re.compile 前的 HIR
[BeginInlinedFunction]
[LoadGlobal] re.compile
[LoadConst] regex_pattern
[LoadConst] flags
# 保存大量寄存器
[SaveRegisters]
[CallCFunction] re.compile
[RestoreRegisters]
```

优化后：
```
# 优化后的 HIR
[BeginInlinedFunction]
[LoadGlobal] re.compile
[LoadConst] regex_pattern  
[LoadConst] flags
# 最小寄存器保存
[SaveMinimalRegisters]
[CallCFunctionFastPath] re.compile
# 延迟恢复或按需恢复
[RestoreRegistersLazy]
```

**预期改进**：5-15%

### 4.2 方案 B：优化 JIT 编译开销

**适用场景**：诊断发现 JIT 编译过程本身引入过多开销

**优化策略**：

1. **简化优化 Pass**：
   - 识别 regex_compile 用例不需要的重度优化
   - 为简单循环提供快速编译路径

2. **实现位置**：
   - `cinderx/Jit/hir/pass.cpp` - 优化 pass 管理
   - `cinderx/Jit/compiler.cpp` - 编译器主流程

3. **HIR 对比示例**：

优化前（完整优化）：
```
# 经过所有优化 pass 的 HIR
[Function]
  [Block 1]
    [PhiElimination]
    [CopyPropagation]
    [DeadCodeElimination]
    ...
    [Loop optimization]
    [Inlining]
    [Final HIR]
```

优化后（快速路径）：
```
# 针对简单循环的快速编译路径
[Function]
  [Block 1]
    [MinimalOptimization]
    # 跳过不适用于此模式的复杂优化
    [FastPathHIR]
```

**预期改进**：10-20%

### 4.3 方案 C：优化内存分配模式

**适用场景**：诊断发现内存分配和 GC 是瓶颈

**优化策略**：

1. **优化堆栈分配**：
   - 减少临时对象分配
   - 优化循环内对象的栈分配

2. **实现位置**：
   - `cinderx/Jit/hir/refcount_insertion.cpp` - 引用计数优化
   - `cinderx/Jit/generators_mm.cpp` - 内存管理

3. **HIR 对比示例**：

优化前：
```
# 每次循环都分配临时对象
[Loop]
  [Allocate] temp_object_1
  [Allocate] temp_object_2
  [CallCFunction] re.compile
  [Decref] temp_object_1
  [Decref] temp_object_2
```

优化后：
```
# 循环外预分配或复用对象
[AllocateOnce] temp_object_pool
[Loop]
  [Reuse] temp_object_1 from pool
  [Reuse] temp_object_2 from pool
  [CallCFunction] re.compile
  # 延迟释放或批量释放
```

**预期改进**：5-10%

## 5. HIR 对比报告要求

每个优化方案实施后，必须提供以下 HIR 对比：

### 5.1 HIR 导出方法

```bash
# 启用 HIR 导出
export PYTHONJITHIRDUMP=1
export PYTHONJITLOG=1

# 运行测试
python3 scripts/diagnostics/benchmark_regex_compile.py 2>&1 | tee hir_dump.txt
```

### 5.2 HIR 对比内容

对于每个关键函数（如 `bench_regex_compile`），报告必须包含：

1. **优化前 HIR**：
   - 完整的 HIR 代码
   - 关键指令序列
   - 控制流图

2. **优化后 HIR**：
   - 优化后的 HIR 代码
   - 改进的指令序列
   - 优化点标注

3. **差异分析**：
   - 指令数量对比
   - 内存访问次数对比
   - C 函数调用开销对比

示例格式：

```markdown
## HIR 对比：bench_regex_compile

### 优化前
```
Function bench_regex_compile:
  Block 1:
    LoadGlobal re.compile
    LoadLocal regexes
    ... (完整 HIR)
```

### 优化后  
```
Function bench_regex_compile:
  Block 1:
    LoadGlobal re.compile [optimized]
    LoadLocal regexes
    ... (优化后的 HIR)
```

### 关键差异
- 指令数: 45 → 38 (-15%)
- C 函数调用开销: 12 cycles → 8 cycles (-33%)
- 寄存器保存: 8 → 4 (-50%)
```

## 6. 验证和测试

### 6.1 单元测试

**新测试文件**：`test_regex_compile_perf.py`

```python
class TestRegexCompileOptimization:
    def test_bench_function_compiled(self):
        """验证 bench_regex_compile 被 JIT 编译"""
        import cinderjit
        # 强制编译
        cinderjit.force_compile(bench_regex_compile)
        assert cinderjit.is_jit_compiled(bench_regex_compile)
    
    def test_no_deoptimization(self):
        """验证运行时没有频繁反优化"""
        # 运行多次，检查反优化计数
        pass
    
    def test_correctness(self):
        """验证优化后结果正确"""
        regexes = capture_regexes()
        result_cpython = bench_cpython(regexes)
        result_jit = bench_with_cinderjit(regexes)
        assert result_cpython == result_jit
    
    def test_performance_regression(self):
        """验证性能至少匹配 CPython"""
        # 运行 15 次，取中位数
        # assert median_time <= CPython_baseline * 1.05
```

### 6.2 回归测试

**必须通过的现有测试**：
- `test_jit.py` - 所有 JIT 基础测试
- `test_cinderx.py` - CinderX 综合测试
- `test_re.py` - Python 正则表达式测试

**性能回归检查**：
- 在 ARM Docker 中运行完整 pyperformance
- 对比优化前后的所有 benchmark
- 确认没有 benchmark 回退 >2%

### 6.3 ARM Docker 验证流程

```bash
# 1. 构建 CinderX wheel
cd /Users/luchen/Agents-Repo/OpenCode/cinderx
python3 setup.py bdist_wheel

# 2. 启动测试容器
docker-compose -f docker/cinderx-test/docker-compose.yml up -d

# 3. 安装新版本
docker exec cinderx-arm64-test pip install /dist/cinderx-*.whl --force-reinstall

# 4. 正确性验证
docker exec cinderx-arm64-test python3 -c "
import sys
sys.path.insert(0, '/root/benchmarks')
from run_benchmark import bench_regex_compile, capture_regexes
import cinderjit
cinderjit.enable()
regexes = capture_regexes()
result = bench_regex_compile(1, regexes)
print('正确性 OK')
"

# 5. 性能验证
docker exec cinderx-arm64-test python3 << 'PY'
import sys, statistics
sys.path.insert(0, '/root/benchmarks')
from run_benchmark import bench_regex_compile, capture_regexes
import cinderjit
cinderjit.enable()

regexes = capture_regexes()

# 预热
for _ in range(5):
    bench_regex_compile(1, regexes)

# 测量
times = []
for _ in range(15):
    times.append(bench_regex_compile(1, regexes))

print(f'CinderX JIT: {statistics.mean(times)*1000:.3f}ms ± {statistics.stdev(times)*1000:.3f}ms')
print(f'目标: ≤84ms')
PY
```

## 7. 实施路线图

### Phase 0：诊断（1-2 天）
- [ ] 创建诊断基础设施（benchmark_regex_compile.py）
- [ ] 在 macOS 本地验证 JIT 执行路径
- [ ] 导出并分析 HIR（优化前）
- [ ] 在 Docker ARM64 中复现性能劣化
- [ ] **交付物**：诊断报告 + HIR 基线

### Phase 1：快速优化（2-3 天）
- [ ] 实施方案 A（C 函数调用优化）
- [ ] 导出并对比 HIR（方案 A 优化后）
- [ ] 实施方案 C（内存分配优化，轻量级部分）
- [ ] 单元测试验证
- [ ] Docker ARM64 性能验证
- [ ] **Go/No-Go 决策点**：如果改进 ≥50%，进入 Phase 3；否则进入 Phase 2

### Phase 2：深度优化（3-5 天，条件执行）
- [ ] 实施方案 B（JIT 编译开销优化）
- [ ] 导出并对比 HIR（方案 B 优化后）
- [ ] 完整 C 内存分配优化（方案 C 深度部分）
- [ ] 完整正确性测试
- [ ] Docker ARM64 性能验证

### Phase 3：集成和验证（1-2 天）
- [ ] 运行完整 CinderX 测试套件
- [ ] 在 Docker ARM64 中运行完整 pyperformance
- [ ] 确认其他 benchmark 无回退
- [ ] 生成最终 HIR 对比报告
- [ ] 代码审查
- [ ] 文档更新

**总预计时间**：4-10 天（取决于是否需要 Phase 2）

## 8. HIR 对比报告模板

最终报告必须包含以下 HIR 对比章节：

```markdown
# HIR 对比报告：regex_compile 优化

## 1. 基线 HIR（优化前）

### bench_regex_compile 函数
```
[完整的 HIR 代码]
```

### 关键指标
- 总指令数: XX
- C 函数调用点: XX 处
- 寄存器保存/恢复: XX 次
- 内存访问: XX 次

## 2. 方案 A 优化后 HIR

### 优化点 1：C 函数调用路径
```
[优化后的 HIR 代码]
```

### 改进指标
- 指令数: XX → XX (-X%)
- 调用开销: XX cycles → XX cycles (-X%)

## 3. 方案 B 优化后 HIR

### 优化点 2：JIT 编译开销
```
[优化后的 HIR 代码]
```

## 4. 方案 C 优化后 HIR

### 优化点 3：内存分配
```
[优化后的 HIR 代码]
```

## 5. 最终对比总结

| 指标 | 优化前 | 优化后 | 改进 |
|------|--------|--------|------|
| 指令数 | XX | XX | -X% |
| 执行时间 | 96ms | 84ms | -12.5% |
| ... | ... | ... | ... |
```

## 9. 风险和缓解措施

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 诊断发现不明确的瓶颈 | 中 | 延期 | 多角度分析（perf、HIR dump、手动插桩） |
| Phase 1 优化不足 | 中 | 需要更多时间 | Go/No-Go 机制，及时切换到 Phase 2 |
| 优化导致其他用例回退 | 低 | 阻塞发布 | 回滚机制 + 完整回归测试 |
| ARM Docker 和真实硬件表现不同 | 低 | 误判 | 预留真实硬件验证时间 |

## 10. 成功标准

优化将被视为成功，如果：

1. **性能**：CinderX JIT 在 regex_compile 用例上在 ARM Docker 中 ≤ 84ms（至少匹配 CPython 基线）
2. **HIR 对比**：提供完整的优化前后 HIR 对比报告
3. **正确性**：所有现有 CinderX 测试通过
4. **无回退**：没有其他 pyperformance benchmark 回退 >2%
5. **可维护性**：代码变更经过良好文档化和审查

## 11. 未来工作

如果此优化成功，潜在的后续工作包括：

1. **泛化**：将优化扩展到其他 C 函数调用密集型的用例
2. **主动优化**：添加启发式方法自动检测和优化此类模式
3. **文档**：记录编写 JIT 友好的正则表达式代码的最佳实践
4. **监控**：向 CI/CD 管道添加性能回归测试

---

**设计批准**: [待用户确认]

**下一步**: 用户批准后，使用 writing-plans 技能创建详细实施计划
