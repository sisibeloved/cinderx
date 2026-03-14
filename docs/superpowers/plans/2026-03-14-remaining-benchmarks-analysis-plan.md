# Remaining Benchmarks Analysis Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to carry out this analysis plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按和 `coroutines`、`comprehensions` 相同的深度，把剩余 pyperformance benchmark 的 Arm vs AMD 比值恶化原因逐个分析完，并沉淀为可复用的根因文档。

**Architecture:** 先按共享根因簇分组，再按 benchmark 逐个做 single-benchmark deep dive。每个 deep dive 都必须串起 benchmark 源码、CPython 基准路径、CinderX 差异、静态机器码差异、JIT 代码形状差异，以及“为什么比值从基线进一步恶化”的因果链。

**Tech Stack:** `pyperformance` 源码、`~/Repo/cpython` 基准提交 `ebf955df7a89ed0c7968f79faec1de49f61ed7cb`、`cinderx` 当前分支源码、`aarch64-linux-gnu-gcc 15.2.0`、`x86_64-linux-gnu-gcc 15.2.0`、GNU `objdump`

---

## 文件结构

### 已有文档

- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-coroutines-arm-vs-amd-deep-dive.md`
- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-comprehensions-arm-vs-amd-deep-dive.md`
- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-arm-vs-amd-root-cause-analysis.md`

### 计划新增文档

- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-richards-arm-vs-amd-deep-dive.md`
- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-richards-super-arm-vs-amd-deep-dive.md`
- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-go-arm-vs-amd-deep-dive.md`
- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-deltablue-arm-vs-amd-deep-dive.md`
- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-raytrace-arm-vs-amd-deep-dive.md`
- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-nqueens-arm-vs-amd-deep-dive.md`
- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-float-arm-vs-amd-deep-dive.md`
- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-generators-arm-vs-amd-deep-dive.md`
- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-python-startup-arm-vs-amd-deep-dive.md`
- `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-final-benchmark-synthesis.md`

### 持续更新的工作记忆

- `/Users/luchen/Repo/cinderx/task_plan.md`
- `/Users/luchen/Repo/cinderx/findings.md`
- `/Users/luchen/Repo/cinderx/progress.md`

## 分组策略

### 第一组：解释器调度 / 调用密集型

- `richards`
- `richards_super`
- `go`
- `deltablue`

**核心假设：**

- `CI_UPDATE_CALL_COUNT`
- `adaptive_enabled`
- `IS_PEP523_HOOKED`
- 解释器 tail-call 参数传播
- Arm 默认 `ENABLE_LIGHTWEIGHT_FRAMES`
- 调用密集型小函数 / 方法 / 属性访问组合

### 第二组：JIT 数值 / 小 helper / mixed numeric

- `raytrace`
- `float`
- `nqueens`

**核心假设：**

- mixed numeric guard 策略
- 小 helper 过编译
- Arm/x86_64 helper 调用 lowering 差异
- AArch64 地址模式和寄存器压力
- 递归 / 回溯中的分支与对象开销

### 第三组：generator / coroutine 邻近机制

- `generators`

**核心假设：**

- generator attr lowering
- `Decref` / `BatchDecref`
- resume / suspend 形状
- AArch64 generator frame 路径

### 第四组：启动 / 注入 / 环境路径

- `python_startup`

**核心假设：**

- `sitecustomize.py`
- `import cinderx.jit`
- autoload 路径
- 启动期 CinderX glue code

## Chunk 1: 解释器调度组

### Task 1: `richards`

**Files:**
- Read: `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_richards/run_benchmark.py`
- Read: `/Users/luchen/Repo/cpython/Python/generated_cases.c.h`
- Read: `/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/generated_cases.c.h`
- Read: `/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/ceval_macros.h`
- Create: `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-richards-arm-vs-amd-deep-dive.md`

- [ ] 定位 benchmark 源码，确认热循环和对象模型特征
- [ ] 映射 CPython 的解释器热点 opcode、调用路径和属性访问路径
- [ ] 映射 CinderX 的对应解释器差异
- [ ] 为 call-count / adaptive / lightweight frame 相关微模式构建交叉汇编探针
- [ ] 将静态机器码差异与 benchmark 比值恶化联系起来
- [ ] 写出中文 deep dive 文档

### Task 2: `richards_super`

**Files:**
- Read: `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_richards_super/run_benchmark.py`
- Read: `/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp`
- Create: `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-richards-super-arm-vs-amd-deep-dive.md`

- [ ] 确认 `super`、方法分派、属性访问在 benchmark 中的精确使用形状
- [ ] 对比 CPython 与 CinderX 在 `LOAD_ATTR` / `LOAD_METHOD` / `CALL_METHOD` 上的差异
- [ ] 为方法分派和 super 路径构建交叉汇编探针
- [ ] 写出中文 deep dive 文档

### Task 3: `go`

**Files:**
- Read: `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_go/run_benchmark.py`
- Create: `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-go-arm-vs-amd-deep-dive.md`

- [ ] 确认 benchmark 是调度/方法调用/容器访问中的哪一类组合
- [ ] 映射解释器与 JIT 的主差异点
- [ ] 提炼最能代表平台差异的 helper/guard 探针
- [ ] 写出中文 deep dive 文档

### Task 4: `deltablue`

**Files:**
- Read: `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_deltablue/run_benchmark.py`
- Create: `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-deltablue-arm-vs-amd-deep-dive.md`

- [ ] 明确约束对象图上的热点：属性、方法、容器、排序还是小函数调度
- [ ] 选择最合适的解释器/JIT 差异点去证明平台比值恶化
- [ ] 写出中文 deep dive 文档

## Chunk 2: JIT 数值组

### Task 5: `raytrace`

**Files:**
- Read: `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_raytrace/run_benchmark.py`
- Read: `/Users/luchen/Repo/cinderx/docs/plans/2026-03-10-raytrace-cpython-vs-cinderx-jit-analysis.md`
- Create: `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-raytrace-arm-vs-amd-deep-dive.md`

- [ ] 用 benchmark 源码重新锚定热点 helper，而不是只依赖旧 findings
- [ ] 确认当前分支上 mixed numeric 修复后剩余的 Arm/x86_64 差异
- [ ] 为 helper call lowering 和小 helper 代码形状补静态汇编证据
- [ ] 写出中文 deep dive 文档

### Task 6: `nqueens`

**Files:**
- Read: `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_nqueens/run_benchmark.py`
- Create: `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-nqueens-arm-vs-amd-deep-dive.md`

- [ ] 确认 benchmark 更像递归/回溯/整数/容器中的哪种组合
- [ ] 定位最可能的解释器或 JIT 热路径
- [ ] 写出中文 deep dive 文档

### Task 7: `float`

**Files:**
- Read: `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_float/run_benchmark.py`
- Read: `/Users/luchen/Repo/cinderx/plans/2026-03-12-float-accumulator-entry-promotion/findings.md`
- Read: `/Users/luchen/Repo/cinderx/plans/2026-03-13-float-power-square-strength-reduction/findings.md`
- Create: `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-float-arm-vs-amd-deep-dive.md`

- [ ] 将已修复点和 benchmark 当前形状重新对齐
- [ ] 区分“已修过但平台差异仍在”和“仍未覆盖”的部分
- [ ] 写出中文 deep dive 文档

## Chunk 3: generator / startup 组

### Task 8: `generators`

**Files:**
- Read: `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_generators/run_benchmark.py`
- Read: `/Users/luchen/Repo/cinderx/plans/2026-03-12-generators-attr-decref/findings.md`
- Create: `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-generators-arm-vs-amd-deep-dive.md`

- [ ] 用 benchmark 源码确认 generator attr/decref 路径是否真是主因
- [ ] 补上 AArch64 resume/frame 相关静态/JIT 证据
- [ ] 写出中文 deep dive 文档

### Task 9: `python_startup`

**Files:**
- Read: `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_python_startup/run_benchmark.py`
- Read: `/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh`
- Read: `/Users/luchen/Repo/cinderx/cinderx/PythonBin/sitecustomize.py`
- Create: `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-python-startup-arm-vs-amd-deep-dive.md`

- [ ] 明确 benchmark 测的是真正 startup 还是 startup + autoload glue
- [ ] 把 `sitecustomize` / `import cinderx.jit` / Arm 默认特性串成证据链
- [ ] 写出中文 deep dive 文档

## Chunk 4: 总结归并

### Task 10: 全量综合

**Files:**
- Modify: `/Users/luchen/Repo/cinderx/findings.md`
- Modify: `/Users/luchen/Repo/cinderx/progress.md`
- Create: `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-final-benchmark-synthesis.md`

- [ ] 把全部 benchmark 的根因按共享簇重排
- [ ] 归纳“解释器热路径类”“容器/属性类”“JIT helper 类”“generator/coroutine 类”“startup 类”
- [ ] 明确哪些结论是源码+机器码级证据，哪些仍是高概率推断
- [ ] 给出后续一键脚本最值得优先验证的最小点集

## 执行顺序

推荐顺序：

1. `richards`
2. `richards_super`
3. `go`
4. `deltablue`
5. `raytrace`
6. `nqueens`
7. `float`
8. `generators`
9. `python_startup`
10. 综合归并

这样排序的原因是：

1. 先把“解释器调度/调用密集”这一大簇打透
2. 再回到 JIT 数值类
3. 最后收 generator 与 startup

## 每个 deep dive 的固定交付模板

每个 benchmark 都必须包含以下部分：

1. benchmark 本体到底在测什么
2. CPython 基准分支上的关键执行链
3. CinderX 相对 CPython 的结构变化
4. 静态机器码证据
5. JIT 代码形状证据
6. 为什么平台比值会进一步恶化
7. 当前归因结论
8. 后续最值得验证的点

## 风险与边界

- 这里的机器码证据统一基于 `gcc 15.2.0`，不是目标机 `gcc 12.3.1`
- 因此“机器码层结论”应表述为：
  - 说明代码形状趋势
  - 用来支持平台差异方向
  - 不伪装成目标机最终产物
- 对于 asmjit 运行时生成代码，真正可信的仍然是源码层 arch split 与 JIT lowering 形状

Plan complete and saved to `/Users/luchen/Repo/cinderx/docs/superpowers/plans/2026-03-14-remaining-benchmarks-analysis-plan.md`. Ready to execute?
