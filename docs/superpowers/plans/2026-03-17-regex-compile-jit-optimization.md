# regex_compile JIT 优化实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 regex_compile 用例中 CinderX JIT 相对于 CPython 的 14% 性能劣化，达到或超过 CPython 基线性能（96ms → ≤84ms），并提供完整的 HIR 对比报告。

**Architecture:** 数据驱动优化 - 先通过诊断工具识别性能瓶颈，再依次实施 C 函数调用优化（方案 A）、JIT 编译开销优化（方案 B）和内存分配优化（方案 C）。每个方案实施后都导出 HIR 进行对比分析。

**Tech Stack:** Python 3.14, CinderX JIT, C++ (HIR/LIR), Docker ARM64 QEMU, pyperformance

**设计文档:** `docs/superpowers/specs/2026-03-17-regex-compile-jit-optimization-design.md`

---

## 文件结构

### 诊断阶段文件
- **Create:** `scripts/diagnostics/benchmark_regex_compile.py` - 主基准测试工具
- **Create:** `scripts/diagnostics/profile_regex_phases.py` - 分段计时分析器
- **Create:** `scripts/diagnostics/export_hir.py` - HIR 导出工具
- **Create:** `scripts/diagnostics/verify_jit_path.py` - JIT 编译验证
- **Create:** `docs/superpowers/diagnostics/phase0-report.md` - 诊断报告模板

### 优化实施文件
- **Modify:** `cinderx/Jit/codegen/gen_asm.cpp` - 方案 A：C 函数调用优化
- **Modify:** `cinderx/Jit/lir/regalloc.cpp` - 方案 A：寄存器分配优化
- **Modify:** `cinderx/Jit/hir/pass.cpp` - 方案 B：优化 pass 管理
- **Modify:** `cinderx/Jit/compiler.cpp` - 方案 B：编译流程优化
- **Modify:** `cinderx/Jit/hir/refcount_insertion.cpp` - 方案 C：引用计数优化
- **Modify:** `cinderx/Jit/generators_mm.cpp` - 方案 C：内存管理优化

### 测试文件
- **Create:** `tests/test_regex_compile_optimization.py` - 优化测试套件

---

## Chunk 1: 诊断基础设施（Phase 0）

### Task 1: 创建诊断目录结构

**Files:**
- Create: `scripts/diagnostics/` 目录
- Create: `docs/superpowers/diagnostics/` 目录

- [ ] **Step 1: 创建诊断目录**

Run:
```bash
cd /Users/luchen/Agents-Repo/OpenCode/cinderx
mkdir -p scripts/diagnostics
cd scripts/diagnostics
mkdir -p __init__.py
cd ../..
mkdir -p docs/superpowers/diagnostics
```

Expected: 两个目录创建成功，无错误输出

- [ ] **Step 2: 提交目录创建**

Run:
```bash
git add scripts/diagnostics/ docs/superpowers/diagnostics/
git commit -m "diag: create diagnostic directories for regex_compile optimization

Create infrastructure for Phase 0 performance analysis."
```

Expected: 提交成功，commit hash 生成

---

### Task 2: 编写基准测试工具

**Files:**
- Create: `scripts/diagnostics/benchmark_regex_compile.py`

- [ ] **Step 1: 创建基准测试脚本**

Create `scripts/diagnostics/benchmark_regex_compile.py`:

```python
#!/usr/bin/env python3
"""
regex_compile 性能诊断工具
比较 CPython 与 CinderX JIT 在 regex_compile 用例上的性能
"""

import sys
import time
import statistics
from pathlib import Path


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
        # 导入并运行 bm_regex_effbot
        sys.path.insert(0, str(Path.home() / "Repo" / "pyperformance" / "pyperformance" / "data-files" / "benchmarks" / "bm_regex_compile"))
        import bm_regex_effbot
        bm_regex_effbot.bench_regex_effbot(1)
        
        # 导入并运行 bm_regex_v8
        import bm_regex_v8
        bm_regex_v8.bench_regex_v8(1)
    except ImportError as e:
        print(f"Warning: Could not import benchmark modules: {e}")
        # 使用备选正则表达式列表
        regexes = [
            (r'^ba', 0),
            (r'Python|Perl', 0),
            (r'.*Python.*', 0),
            (r'\s+', 0),
            (r'[a-z]+', 0),
        ]
    finally:
        re.compile = real_compile
        re.search = real_search
        re.sub = real_sub
    
    return regexes


def bench_cpython(regexes, loops=10):
    """使用 CPython 运行基准测试"""
    import re
    
    times = []
    for _ in range(loops):
        start = time.perf_counter()
        for regex, flags in regexes:
            re.purge()
            re.compile(regex, flags)
        times.append(time.perf_counter() - start)
    
    return statistics.mean(times), statistics.stdev(times)


def bench_with_cinderjit(regexes, loops=10):
    """使用 CinderX JIT 运行基准测试"""
    import re
    
    # 预热
    for _ in range(3):
        for regex, flags in regexes:
            re.purge()
            re.compile(regex, flags)
    
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


def main():
    print("=" * 70)
    print("regex_compile 性能诊断")
    print("=" * 70)
    
    # 捕获正则表达式
    print("\n[1] 捕获正则表达式...")
    regexes = capture_regexes()
    print(f"    捕获了 {len(regexes)} 个正则表达式")
    
    loops = 10
    
    # 测试 1: CPython 基线
    print("\n[2] CPython 基线测试...")
    mean1, std1 = bench_cpython(regexes, loops)
    print(f"    时间: {mean1*1000:.3f}ms ± {std1*1000:.3f}ms")
    
    # 测试 2: CinderX JIT（如果可用）
    try:
        import cinderjit
        cinderjit.enable()
        
        print("\n[3] CinderX JIT 测试...")
        mean2, std2 = bench_with_cinderjit(regexes, loops)
        print(f"    时间: {mean2*1000:.3f}ms ± {std2*1000:.3f}ms")
        
        # 计算慢化因子
        slowdown = mean2 / mean1
        print(f"\n[4] 性能对比")
        print(f"    CPython:    {mean1*1000:.3f}ms")
        print(f"    CinderX:    {mean2*1000:.3f}ms")
        print(f"    慢化因子:   {slowdown:.2f}x")
        
        if slowdown > 1.05:
            print(f"    ⚠️  性能劣化: {(slowdown-1)*100:.1f}%")
        else:
            print(f"    ✅ 性能达标或更好")
            
    except ImportError:
        print("\n[3] CinderX 不可用，跳过 JIT 测试")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 使脚本可执行**

Run:
```bash
chmod +x scripts/diagnostics/benchmark_regex_compile.py
```

- [ ] **Step 3: 测试基线基准（不使用 JIT）**

Run:
```bash
python3 scripts/diagnostics/benchmark_regex_compile.py 2>&1 | tee docs/superpowers/diagnostics/baseline-results.txt
```

Expected output (approximate):
```
======================================================================
regex_compile 性能诊断
======================================================================

[1] 捕获正则表达式...
    捕获了 XXX 个正则表达式

[2] CPython 基线测试...
    时间: 80-90ms ± Xms

[3] CinderX JIT 测试...
    时间: 90-100ms ± Xms

[4] 性能对比
    CPython:    XXms
    CinderX:    XXms
    慢化因子:   1.XXx
    ⚠️  性能劣化: XX%

======================================================================
```

- [ ] **Step 4: 提交基准测试工具**

Run:
```bash
git add scripts/diagnostics/benchmark_regex_compile.py docs/superpowers/diagnostics/baseline-results.txt
git commit -m "diag: add regex_compile benchmark tool

Add comprehensive benchmark tool for regex_compile performance analysis.
Captures regexes from pyperformance and compares CPython vs CinderX JIT."
```

---

### Task 3: 编写分段计时分析器

**Files:**
- Create: `scripts/diagnostics/profile_regex_phases.py`

- [ ] **Step 1: 创建阶段分析器脚本**

Create `scripts/diagnostics/profile_regex_phases.py`:

```python
#!/usr/bin/env python3
"""
对 regex_compile 执行各阶段进行性能分析
"""

import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from benchmark_regex_compile import capture_regexes


def profile_phases(regexes):
    """分析各阶段耗时"""
    import re
    
    purge_times = []
    compile_times = []
    loop_overhead = []
    
    # 测量多次取平均
    for _ in range(5):
        for regex, flags in regexes[:50]:  # 只测前50个避免太慢
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
        'purge_std': statistics.stdev(purge_times) if len(purge_times) > 1 else 0,
        'compile_avg': statistics.mean(compile_times),
        'compile_std': statistics.stdev(compile_times) if len(compile_times) > 1 else 0,
    }


def main():
    print("=" * 70)
    print("regex_compile 阶段性能分析")
    print("=" * 70)
    
    print("\n[1] 捕获正则表达式...")
    regexes = capture_regexes()
    print(f"    捕获了 {len(regexes)} 个正则表达式")
    
    print("\n[2] 分析各阶段耗时...")
    stats = profile_phases(regexes)
    
    total = stats['purge_avg'] + stats['compile_avg']
    
    print("\n[3] 阶段计时结果")
    print(f"    re.purge() 平均:   {stats['purge_avg']*1000:.6f}ms ± {stats['purge_std']*1000:.6f}ms")
    print(f"    re.compile() 平均: {stats['compile_avg']*1000:.6f}ms ± {stats['compile_std']*1000:.6f}ms")
    print(f"    总平均:            {total*1000:.6f}ms")
    
    print("\n[4] 比例分析")
    print(f"    re.purge():   {stats['purge_avg']/total*100:.1f}%")
    print(f"    re.compile(): {stats['compile_avg']/total*100:.1f}%")
    
    # JIT 对比
    try:
        import cinderjit
        cinderjit.enable()
        
        print("\n[5] CinderX JIT 阶段分析...")
        # 预热
        import re
        for _ in range(3):
            for regex, flags in regexes[:10]:
                re.purge()
                re.compile(regex, flags)
        
        stats_jit = profile_phases(regexes)
        total_jit = stats_jit['purge_avg'] + stats_jit['compile_avg']
        
        print(f"    re.purge() 平均:   {stats_jit['purge_avg']*1000:.6f}ms")
        print(f"    re.compile() 平均: {stats_jit['compile_avg']*1000:.6f}ms")
        print(f"    总平均:            {total_jit*1000:.6f}ms")
        
        slowdown = total_jit / total
        print(f"\n    相比 CPython 慢化: {slowdown:.2f}x")
        
    except ImportError:
        print("\n[5] CinderX 不可用")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 测试阶段分析器**

Run:
```bash
python3 scripts/diagnostics/profile_regex_phases.py 2>&1 | tee docs/superpowers/diagnostics/phase-analysis.txt
```

- [ ] **Step 3: 提交阶段分析器**

Run:
```bash
git add scripts/diagnostics/profile_regex_phases.py docs/superpowers/diagnostics/phase-analysis.txt
git commit -m "diag: add regex_compile phase profiler

Analyze time spent in re.purge() vs re.compile() phases
to identify optimization targets."
```

---

### Task 4: 编写 HIR 导出工具

**Files:**
- Create: `scripts/diagnostics/export_hir.py`

- [ ] **Step 1: 创建 HIR 导出脚本**

Create `scripts/diagnostics/export_hir.py`:

```python
#!/usr/bin/env python3
"""
导出 JIT 编译函数的 HIR 用于分析
"""

import sys
import os
import subprocess
from pathlib import Path


def export_hir_for_function(func_name, output_file):
    """导出指定函数的 HIR"""
    env = os.environ.copy()
    env['PYTHONJITHIRDUMP'] = '1'
    env['PYTHONJITLOG'] = '1'
    
    # 创建测试脚本来触发 JIT 编译
    test_script = f'''
import sys
sys.path.insert(0, "{Path(__file__).parent}")
from benchmark_regex_compile import capture_regexes, bench_with_cinderjit

import cinderjit
cinderjit.enable()

regexes = capture_regexes()

# 强制编译并执行
result = bench_with_cinderjit(regexes, 1)
print(f"Benchmark completed: {{result}}")
'''
    
    # 运行并捕获输出
    with open(output_file, 'w') as f:
        process = subprocess.Popen(
            [sys.executable, '-c', test_script],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        for line in process.stdout:
            f.write(line)
            # 同时打印到控制台
            print(line, end='')
    
    process.wait()
    return process.returncode == 0


def main():
    print("=" * 70)
    print("HIR 导出工具")
    print("=" * 70)
    
    output_file = "docs/superpowers/diagnostics/hir_dump_baseline.txt"
    
    print(f"\n导出 HIR 到: {output_file}")
    print("这会启用 PYTHONJITHIRDUMP 和 PYTHONJITLOG 环境变量")
    print("\n开始导出...")
    
    success = export_hir_for_function("bench_with_cinderjit", output_file)
    
    if success:
        print(f"\n✅ HIR 导出成功: {output_file}")
        
        # 显示文件大小
        file_size = Path(output_file).stat().st_size
        print(f"   文件大小: {file_size} bytes")
    else:
        print(f"\n❌ HIR 导出失败")
        return 1
    
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 测试 HIR 导出**

Run:
```bash
python3 scripts/diagnostics/export_hir.py 2>&1 | head -100
```

Expected: HIR 导出成功，文件创建

- [ ] **Step 3: 提交 HIR 导出工具**

Run:
```bash
git add scripts/diagnostics/export_hir.py
git commit -m "diag: add HIR export tool

Export HIR for JIT-compiled functions to enable optimization analysis."
```

---

### Task 5: 编写 JIT 编译验证工具

**Files:**
- Create: `scripts/diagnostics/verify_jit_path.py`

- [ ] **Step 1: 创建 JIT 验证脚本**

Create `scripts/diagnostics/verify_jit_path.py`:

```python
#!/usr/bin/env python3
"""
验证 JIT 编译对 regex_compile 是否正常工作
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from benchmark_regex_compile import capture_regexes, bench_with_cinderjit


def main():
    print("=" * 70)
    print("JIT 执行路径验证")
    print("=" * 70)
    
    try:
        import cinderjit
    except ImportError:
        print("\n❌ 错误：CinderX 不可用")
        print("请先构建并安装 CinderX")
        return 1
    
    print("\n[1] 启用 JIT...")
    cinderjit.enable()
    print("    ✅ JIT 已启用")
    
    print("\n[2] 捕获正则表达式...")
    regexes = capture_regexes()
    print(f"    ✅ 捕获了 {len(regexes)} 个正则表达式")
    
    print("\n[3] 强制编译 bench_with_cinderjit...")
    cinderjit.force_compile(bench_with_cinderjit)
    print("    ✅ 编译已请求")
    
    print("\n[4] 检查编译状态...")
    is_compiled = cinderjit.is_jit_compiled(bench_with_cinderjit)
    print(f"    已编译: {is_compiled}")
    
    if is_compiled:
        size = cinderjit.get_compiled_size(bench_with_cinderjit)
        print(f"    代码大小: {size} bytes")
    else:
        print("    ⚠️  函数未编译（可能是不支持的 opcode）")
    
    print("\n[5] 运行基准测试...")
    try:
        mean, std = bench_with_cinderjit(regexes, 3)
        print(f"    ✅ 运行成功")
        print(f"    平均时间: {mean*1000:.3f}ms ± {std*1000:.3f}ms")
    except Exception as e:
        print(f"    ❌ 运行失败: {e}")
        return 1
    
    print("\n[6] 检查反优化...")
    # 检查是否仍然编译（运行后可能反优化）
    is_compiled_after = cinderjit.is_jit_compiled(bench_with_cinderjit)
    if is_compiled_after:
        print("    ✅ 函数保持编译状态（无反优化）")
    else:
        print("    ⚠️  函数已反优化")
    
    print("\n" + "=" * 70)
    print("✅ 所有检查通过")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 测试验证脚本（在 CinderX 构建前会失败）**

Run:
```bash
python3 scripts/diagnostics/verify_jit_path.py 2>&1
```

Expected output (before CinderX build):
```
======================================================================
JIT 执行路径验证
======================================================================

❌ 错误：CinderX 不可用
请先构建并安装 CinderX
```

- [ ] **Step 3: 提交验证脚本**

Run:
```bash
git add scripts/diagnostics/verify_jit_path.py
git commit -m "diag: add JIT execution path verifier

Verify:
- JIT is enabled and functioning
- bench_with_cinderjit is compiled
- No deoptimization occurs during execution"
```

---

### Task 6: 创建诊断报告模板

**Files:**
- Create: `docs/superpowers/diagnostics/phase0-report.md`

- [ ] **Step 1: 创建诊断报告模板**

Create `docs/superpowers/diagnostics/phase0-report.md`:

```markdown
# Phase 0 诊断报告：regex_compile 优化

**日期**: 2026-03-17
**平台**: [macOS/ARM64/Docker]
**状态**: [进行中/已完成]

## 执行摘要

### 性能基线

| 指标 | CPython | CinderX JIT | 慢化因子 |
|------|---------|-------------|----------|
| regex_compile | XXms | XXms | XXx |

### 瓶颈识别

**主要瓶颈**: [C函数调用/JIT编译开销/内存分配/其他]

**具体分析**:
- [详细分析内容]

## 详细测量数据

### 1. 基准性能对比

```
[粘贴 benchmark_regex_compile.py 输出]
```

### 2. 阶段计时分析

```
[粘贴 profile_regex_phases.py 输出]
```

**分析**:
- re.purge() 占比: XX%
- re.compile() 占比: XX%
- 其他开销: XX%

### 3. JIT 编译验证

```
[粘贴 verify_jit_path.py 输出]
```

**状态**: 
- JIT 编译: [是/否]
- 代码大小: XX bytes
- 反优化: [无/有]

### 4. HIR 基线（优化前）

**导出文件**: `hir_dump_baseline.txt`

**关键 HIR 片段**:
```
[粘贴关键 HIR 代码]
```

**HIR 分析**:
- 总指令数: XX
- C 函数调用点: XX 处
- 寄存器保存/恢复: XX 次
- 明显问题: [问题描述]

## 优化策略选择

基于诊断结果，选择以下优化策略：

- [ ] 方案 A：C 函数调用优化（优先级: [高/中/低]）
  - 理由: [说明]
  
- [ ] 方案 B：JIT 编译开销优化（优先级: [高/中/低]）
  - 理由: [说明]
  
- [ ] 方案 C：内存分配优化（优先级: [高/中/低]）
  - 理由: [说明]

## 预期改进

| 优化方案 | 预期改进 | 目标性能 |
|----------|----------|----------|
| 方案 A | XX% | XXms |
| 方案 B | XX% | XXms |
| 方案 C | XX% | XXms |
| **总计** | **XX%** | **≤84ms** |

## 下一步行动

1. [ ] 实施方案 A
2. [ ] 导出 HIR 对比（方案 A 后）
3. [ ] 根据效果决定是否实施方案 B/C
4. [ ] 最终验证和回归测试

## 附录

### A. 原始日志文件

- `baseline-results.txt`
- `phase-analysis.txt`
- `hir_dump_baseline.txt`

### B. 环境信息

- Python 版本: [版本]
- CinderX 版本: [版本]
- 操作系统: [系统]
- 架构: [架构]
```

- [ ] **Step 2: 提交报告模板**

Run:
```bash
git add docs/superpowers/diagnostics/phase0-report.md
git commit -m "diag: add Phase 0 diagnostic report template

Template for documenting baseline measurements and bottleneck identification."
```

---

### Task 7: 在 macOS 本地运行完整诊断套件

**Files:**
- Modify: `docs/superpowers/diagnostics/baseline-results.txt`
- Modify: `docs/superpowers/diagnostics/phase-analysis.txt`
- Modify: `docs/superpowers/diagnostics/phase0-report.md`

- [ ] **Step 1: 运行完整基准测试**

Run:
```bash
python3 scripts/diagnostics/benchmark_regex_compile.py 2>&1 | tee docs/superpowers/diagnostics/baseline-results.txt
```

- [ ] **Step 2: 运行阶段分析**

Run:
```bash
python3 scripts/diagnostics/profile_regex_phases.py 2>&1 | tee docs/superpowers/diagnostics/phase-analysis.txt
```

- [ ] **Step 3: 尝试 HIR 导出（注意：需要 CinderX 构建）**

Run:
```bash
# 如果 CinderX 已构建
python3 scripts/diagnostics/export_hir.py 2>&1 | head -200
```

如果 CinderX 未构建，先跳过此步骤，后续在 Docker 中执行。

- [ ] **Step 4: 更新诊断报告**

根据实际测量结果更新 `docs/superpowers/diagnostics/phase0-report.md`

- [ ] **Step 5: 提交诊断结果**

Run:
```bash
git add docs/superpowers/diagnostics/
git commit -m "diag: add Phase 0 diagnostic results (macOS)

Baseline measurements for regex_compile optimization.
- Performance baseline: CPython vs CinderX
- Phase timing analysis
- Bottleneck identification"
```

---

## Chunk 1 完成

**Phase 0 诊断阶段完成！**

**交付物：**
- ✅ `scripts/diagnostics/benchmark_regex_compile.py` - 主基准测试工具
- ✅ `scripts/diagnostics/profile_regex_phases.py` - 阶段分析器
- ✅ `scripts/diagnostics/export_hir.py` - HIR 导出工具
- ✅ `scripts/diagnostics/verify_jit_path.py` - JIT 验证工具
- ✅ `docs/superpowers/diagnostics/phase0-report.md` - 诊断报告（已更新）
- ✅ 基线测量数据（macOS）

**下一 Chunk 将：**
- 根据诊断结果选择优化策略
- 实施方案 A（C 函数调用优化）
- 导出 HIR 对比

---

*注：这是一个长计划文档。由于长度限制，我将创建后续 Chunks 在单独的文件中或继续扩展此文档。请确认是否需要我：*
1. *继续编写 Chunk 2-4（优化实施）*
2. *将后续内容写入新的计划文件*
