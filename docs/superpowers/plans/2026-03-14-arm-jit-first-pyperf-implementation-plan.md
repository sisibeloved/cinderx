# Arm JIT First PyPerformance Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通 macOS Arm 上的 pyperformance 快速验证流程，并基于 TDD 实现第一批 Arm JIT 实验开关与定向 benchmark 验证。

**Architecture:** 先建立本地 pyperformance 驱动层，把 CinderX 解释器、pyperformance 仓库和实验开关串起来，确保能在 macOS Arm 上稳定运行指定 benchmark。然后按 TDD 逐个实现 Arm JIT 实验开关，先做 coroutine 与 instance-value 两组最有价值的实验，再补 numeric leaf 的快速验证。

**Tech Stack:** CPython/CinderX runtime, pyperformance, Python unittest/pytest, C++ JIT HIR/codegen, shell scripts

---

## File Map

- Modify: `scripts/arm/bench_pyperf_direct.py`
  - 复用现有 direct-run 基础，必要时扩展成本地 pyperformance 快速验证的通用驱动
- Create: `scripts/arm/run_local_pyperf_matrix.py`
  - macOS Arm 本地快速验证入口，负责调用 pyperformance benchmark 与实验开关矩阵
- Modify: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
  - 新增 Arm JIT 实验开关的失败测试与形状验证
- Modify: `cinderx/Jit/hir/builder.cpp`
  - 加入第一批 Arm JIT 实验开关
- Modify: `cinderx/Interpreter/3.14/ceval.h`
  - coroutine 解释器兜底快路径
- Modify: `cinderx/Interpreter/3.14/interpreter.c`
  - 实验开关解析与解释器侧配套逻辑
- Modify: `cinderx/Interpreter/3.14/Includes/generated_cases.c.h`
  - exact instance-value 相关解释器快路径

## Chunk 1: 打通 macOS Arm pyperformance 快速验证

### Task 1: 建立本地 pyperformance 驱动脚本

**Files:**
- Create: `scripts/arm/run_local_pyperf_matrix.py`
- Modify: `scripts/arm/bench_pyperf_direct.py`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，验证本地 pyperformance 参数组装**

在 `cinderx/PythonLib/test_cinderx/test_arm_runtime.py` 新增一个纯 Python 测试，断言本地驱动能：
- 接收 `pyperformance` 仓库路径
- 接收 benchmark 名
- 接收实验环境变量
- 组装出稳定的 benchmark 模块路径和运行命令

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k local_pyperf_driver -v
```

Expected:
- FAIL，提示缺少驱动函数或命令组装逻辑

- [ ] **Step 3: 写最小实现**

实现 `scripts/arm/run_local_pyperf_matrix.py`：
- 接收 `--pyperformance-root`
- 接收 `--benchmark`
- 接收 `--mode` / `--env`
- 支持输出最终执行命令
- 优先复用 `bench_pyperf_direct.py`

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k local_pyperf_driver -v
```

Expected:
- PASS

- [ ] **Step 5: 跑 smoke，确认本地可调用**

Run:
```bash
python3 scripts/arm/run_local_pyperf_matrix.py --help
```

Expected:
- 正常输出帮助信息

### Task 2: 让本地驱动先打通 `coroutines`

**Files:**
- Modify: `scripts/arm/run_local_pyperf_matrix.py`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，锁定 `coroutines` benchmark 解析**

测试要求：
- 能从 `/Users/luchen/Repo/pyperformance` 解析 `bm_coroutines/run_benchmark.py`
- 能给 direct runner 传入正确的 `bench_func`

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k local_pyperf_coroutines -v
```

Expected:
- FAIL

- [ ] **Step 3: 写最小实现**

为首批 benchmark 建立显式映射：
- `coroutines`
- `richards`
- `go`
- `deltablue`
- `comprehensions`
- `raytrace`
- `float`

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k local_pyperf_coroutines -v
```

Expected:
- PASS

- [ ] **Step 5: 本机 smoke 跑一次 `coroutines`**

Run:
```bash
python3 scripts/arm/run_local_pyperf_matrix.py --pyperformance-root /Users/luchen/Repo/pyperformance --benchmark coroutines --mode baseline
```

Expected:
- 至少能启动并输出一次可解析结果

## Chunk 2: Arm Coroutine JIT 实验

### Task 3: 把 exact coroutine fast path 挂到显式实验开关

**Files:**
- Modify: `cinderx/Jit/hir/builder.cpp`
- Modify: `cinderx/Interpreter/3.14/ceval.h`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，验证不开开关时仍走旧形状**

测试要求：
- 关闭 `PYTHONJITARMCOROFAST`
- exact coroutine 形状下 `CallCFunc` 数量回到旧水平

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k exact_coroutine_gate -v
```

Expected:
- FAIL

- [ ] **Step 3: 写最小实现**

实现：
- 仅当 `PYTHONJITARMCOROFAST=1` 时启用 exact coroutine 短路
- 不开开关时保持现有行为

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k exact_coroutine -v
```

Expected:
- PASS

- [ ] **Step 5: 用本地 pyperformance 跑 `coroutines` A/B**

Run:
```bash
python3 scripts/arm/run_local_pyperf_matrix.py --pyperformance-root /Users/luchen/Repo/pyperformance --benchmark coroutines --mode baseline
python3 scripts/arm/run_local_pyperf_matrix.py --pyperformance-root /Users/luchen/Repo/pyperformance --benchmark coroutines --mode arm_coro_fast
```

Expected:
- `arm_coro_fast` 至少方向性优于 baseline，或给出可解释的失败信息

## Chunk 3: Arm Instance-Value JIT 实验

### Task 4: 把 low-local instance-value 放开改成显式实验开关

**Files:**
- Modify: `cinderx/Jit/hir/builder.cpp`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，验证不开开关时 low-local 不触发激进路径**

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k instance_value_gate -v
```

Expected:
- FAIL

- [ ] **Step 3: 写最小实现**

实现：
- `PYTHONJITARMINSTANCEFAST=1` 才把 low-local 形状放开

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k low_local_instance_value -v
```

Expected:
- PASS

- [ ] **Step 5: 本地 pyperformance 跑 `richards` / `go` / `deltablue`**

Run:
```bash
python3 scripts/arm/run_local_pyperf_matrix.py --pyperformance-root /Users/luchen/Repo/pyperformance --benchmark richards --mode arm_instance_fast
python3 scripts/arm/run_local_pyperf_matrix.py --pyperformance-root /Users/luchen/Repo/pyperformance --benchmark go --mode arm_instance_fast
python3 scripts/arm/run_local_pyperf_matrix.py --pyperformance-root /Users/luchen/Repo/pyperformance --benchmark deltablue --mode arm_instance_fast
```

Expected:
- 至少有 1-2 个 benchmark 出现方向性提升

### Task 5: 把 skip valid guard 改成 Arm JIT 实验开关

**Files:**
- Modify: `cinderx/Jit/hir/builder.cpp`
- Modify: `cinderx/Interpreter/3.14/interpreter.c`
- Modify: `cinderx/Interpreter/3.14/Includes/generated_cases.c.h`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，验证不开开关时 HIR 仍包含 valid guard 痕迹**

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k skip_valid_guard_gate -v
```

Expected:
- FAIL

- [ ] **Step 3: 写最小实现**

实现：
- `PYTHONJITARMINSTANCEFASTSKIPVALID=1` 控制 JIT
- `PYTHONCINDERXINSTANCEVALUESKIPVALID=1` 控制解释器

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k skip_valid_guard -v
```

Expected:
- PASS

- [ ] **Step 5: 本地 pyperformance 跑 `go` / `deltablue` / `comprehensions`**

Run:
```bash
python3 scripts/arm/run_local_pyperf_matrix.py --pyperformance-root /Users/luchen/Repo/pyperformance --benchmark go --mode arm_instance_skip_valid
python3 scripts/arm/run_local_pyperf_matrix.py --pyperformance-root /Users/luchen/Repo/pyperformance --benchmark deltablue --mode arm_instance_skip_valid
python3 scripts/arm/run_local_pyperf_matrix.py --pyperformance-root /Users/luchen/Repo/pyperformance --benchmark comprehensions --mode arm_instance_skip_valid
```

Expected:
- 至少方向性优于 baseline，或产出可归因日志

## Chunk 4: Arm Numeric Leaf 快速实验

### Task 6: 为 numeric leaf 实验开关预留本地 pyperformance 验证入口

**Files:**
- Modify: `scripts/arm/run_local_pyperf_matrix.py`
- Modify: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，验证 `raytrace` / `float` 模式选择**

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k local_pyperf_numeric_modes -v
```

Expected:
- FAIL

- [ ] **Step 3: 写最小实现**

在本地驱动中增加：
- `arm_numeric_leaf`
- `arm_all_experiments`

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k local_pyperf_numeric_modes -v
```

Expected:
- PASS

- [ ] **Step 5: 本地 smoke 跑 `raytrace` / `float`**

Run:
```bash
python3 scripts/arm/run_local_pyperf_matrix.py --pyperformance-root /Users/luchen/Repo/pyperformance --benchmark raytrace --mode arm_numeric_leaf
python3 scripts/arm/run_local_pyperf_matrix.py --pyperformance-root /Users/luchen/Repo/pyperformance --benchmark float --mode arm_numeric_leaf
```

Expected:
- 正常启动并给出结果

## Chunk 5: 汇总与交接

### Task 7: 汇总 macOS Arm 快速验证结果

**Files:**
- Create: `docs/superpowers/plans/2026-03-14-arm-jit-first-macos-pyperf-findings.md`

- [ ] **Step 1: 记录 baseline 与实验模式结果**

- [ ] **Step 2: 标注哪些实验值得推到 Linux Arm**

- [ ] **Step 3: 列出剩余未做的 JIT 实验**

- [ ] **Step 4: 运行最终最小验证**

Run:
```bash
PYTHONPATH=cinderx/PythonLib python3 -m unittest test_cinderx.test_startup -v
PYTHONPYCACHEPREFIX=/tmp/codex-pycache python3 -m py_compile cinderx/PythonLib/test_cinderx/test_arm_runtime.py scripts/arm/run_local_pyperf_matrix.py
```

Expected:
- PASS

- [ ] **Step 5: 准备推送到 Linux Arm 环境**

输出：
- 推荐开启的实验开关
- 推荐优先复测的 benchmark
