# Arm 与 AMD 回退分析：差异点到一键脚本的映射设计

> **面向代理执行者：** 必须使用 `superpowers:subagent-driven-development`（若支持子代理）或 `superpowers:executing-plans` 来执行本计划。步骤使用复选框 `- [ ]` 跟踪。

**目标：** 先把当前仓库相对上游 CPython 的关键差异点枚举清楚，再把每个差异点映射成“在隔离 Linux Arm 环境里一次性采什么数据”，最后据此生成一键脚本。

**适用约束：**
- 最终性能结论只能来自隔离的 Linux Arm 环境
- 本地 macOS Arm 只能用于穿刺、缩小复现、验证 dump 路径、提前检查脚本逻辑
- 远端环境网络隔离，因此脚本必须尽量一次执行收集完足够多的数据

---

## 第一部分：关键差异点清单

### 任务 1：解释器路径差异点

**代码区域：**
- `/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/interpreter.c`
- `/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/ceval_macros.h`
- `/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/borrowed-ceval.c.template`

- [ ] **差异点 1：延迟 adaptive 启用**

代码信号：
- `Ci_DelayAdaptiveCode`
- `Ci_AdaptiveThreshold`
- `is_adaptive_enabled()`

需要采集的数据：
- 纯解释器 benchmark 中 feature 开关 4 组合结果
- 是否存在明显的 Arm-only feature 敏感性

适用 benchmark：
- `coroutines`
- `richards`
- `richards_super`
- `go`
- `deltablue`
- `comprehensions`
- `nqueens`

- [ ] **差异点 2：每次调用的 call-count / adaptive bookkeeping**

代码信号：
- `CI_UPDATE_CALL_COUNT`
- `CI_SET_ADAPTIVE_INTERPRETER_ENABLED_STATE`
- `adaptive_enabled` 在 tail-call 参数中传播

需要采集的数据：
- 纯解释器模式下 feature matrix
- 若可能，加 `cycles` / `branches` / `branch-misses`

适用 benchmark：
- `richards`
- `richards_super`
- `go`
- `deltablue`
- `coroutines`

- [ ] **差异点 3：自定义 coroutine / awaitable 路径**

代码信号：
- `JitCoro_GetAwaitableIter`
- `JitGen_yf`
- 自定义 `_PyEval_GetAwaitable` / `_PyEval_GetANext`

需要采集的数据：
- `coroutines` 的纯解释器结果
- 若可行，`PYTHONJITLIGHTWEIGHTFRAME=0/1`
- async 热路径上的额外错误或 deopt 指标

适用 benchmark：
- `coroutines`

- [ ] **差异点 4：容器构建 opcode 包装路径**

代码信号：
- `LIST_APPEND`
- `MAP_ADD`
- checked list / checked dict 路径

需要采集的数据：
- `comprehensions` 的纯解释器结果
- 与 feature combo 的关系
- 如有需要再补 branch / icache

适用 benchmark：
- `comprehensions`

### 任务 2：Arm 默认特性差异点

**代码区域：**
- `/Users/luchen/Repo/cinderx/setup.py`

- [ ] **差异点 5：Arm 默认开启 adaptive static python**

代码信号：
- `should_enable_adaptive_static_python()`

需要采集的数据：
- feature matrix 中 `adaptive_static_python` 0/1 的影响

适用 benchmark：
- 所有解释器敏感 benchmark

- [ ] **差异点 6：Arm 默认开启 lightweight frames**

代码信号：
- `should_enable_lightweight_frames()`

需要采集的数据：
- feature matrix 中 `lightweight_frames` 0/1 的影响
- 对 `coroutines` 的单独敏感性

适用 benchmark：
- `coroutines`
- `richards`
- `richards_super`
- `go`
- `deltablue`

### 任务 3：JIT 数值路径差异点

**代码区域：**
- `/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp`
- `/Users/luchen/Repo/cinderx/cinderx/Jit/hir/float_accumulator_promotion.cpp`
- `/Users/luchen/Repo/cinderx/cinderx/Jit/hir/float_compare_elimination.cpp`

- [ ] **差异点 7：无 backedge 小 helper 的 exact-int guard 策略**

代码信号：
- `codeHasBackedge(code_)`
- specialized int guards 只对有 backedge 的 code object 保留

需要采集的数据：
- `raytrace` direct-run `none/all/backedge`
- `compiled_count`
- `total_deopt_count`
- `top_deopts`

适用 benchmark：
- `raytrace`
- 可能扩展到 `nqueens`

- [ ] **差异点 8：float accumulator 与 `**2` 路径**

代码信号：
- float accumulator promotion
- `FloatBinaryOp<Power>` 对 `x ** 2` 的识别

需要采集的数据：
- `float` direct-run 或缩小复现
- HIR 中 `DoubleBinaryOp`
- 是否仍出现 generic `BinaryOp<Power>`

适用 benchmark：
- `float`
- 部分 `raytrace`

### 任务 4：generator 路径差异点

**代码区域：**
- `/Users/luchen/Repo/cinderx/cinderx/Jit/lir/generator.cpp`
- `/Users/luchen/Repo/cinderx/cinderx/Jit/jit_rt.cpp`
- `/Users/luchen/Repo/cinderx/plans/2026-03-12-generators-attr-decref/findings.md`

- [ ] **差异点 9：generator attr lowering 与 decref 展开**

代码信号：
- low-local generator attr lowering
- generator-only decref lowering

需要采集的数据：
- `generators` direct-run
- `LoadAttrCached`
- `LoadField`
- `Decref`
- `BatchDecref`

适用 benchmark：
- `generators`

### 任务 5：启动路径差异点

**代码区域：**
- `/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh`
- `/Users/luchen/Repo/cinderx/cinderx/PythonBin/sitecustomize.py`

- [ ] **差异点 10：worker `sitecustomize` 自动导入 CinderX**

代码信号：
- pyperformance venv 内动态写入 `sitecustomize.py`
- 启动即导入 `cinderx.jit`

需要采集的数据：
- `python_startup` 的 `autoload` / `noautoload`
- `-X importtime`

适用 benchmark：
- `python_startup`

---

## 第二部分：一键脚本分层设计

### 任务 6：脚本职责拆分

- [ ] **脚本 A：解释器 feature 矩阵脚本**

职责：
- 接收一个 benchmark 名称
- 自动构建 4 个 feature combo
- 输出 `summary.json` 与 `results.tsv`

优先复用：
- `scripts/arm/interp_feature_matrix.sh`

覆盖差异点：
- 1, 2, 5, 6

- [ ] **脚本 B：JIT direct-run 采样脚本**

职责：
- 接收 benchmark 模块路径与入口
- 自动跑 `none/all/backedge`
- 汇总 `median_wall_sec`、`compiled_count`、`deopt`、`top_deopts`

优先复用：
- `scripts/arm/bench_pyperf_direct.py`

覆盖差异点：
- 7, 8, 9

- [ ] **脚本 C：startup 隔离脚本**

职责：
- 自动备份并切换 `sitecustomize.py`
- 跑 `python_startup` 的 `autoload/noautoload`
- 追加 `-X importtime`

建议新建：
- `scripts/arm/python_startup_matrix.sh`

覆盖差异点：
- 10

- [ ] **脚本 D：首轮最小执行集总控脚本**

职责：
- 顺序执行：
  - `coroutines` feature matrix
  - `richards` feature matrix
  - `raytrace` direct-run
  - `python_startup` startup matrix
- 统一保存到一个 `run_id` 目录
- 生成一页总览 `summary.md`

建议新建：
- `scripts/arm/first_pass_regression_bundle.sh`

---

## 第三部分：一键脚本的输入输出规范

### 任务 7：统一脚本接口

- [ ] **统一输入**

每个脚本都应支持：
- `RUN_ID`
- `OUT_ROOT`
- `DRIVER_VENV`
- `WORKDIR`
- `CPYTHON_PY`

- [ ] **统一输出**

每个脚本至少输出：
- `summary.json`
- `results.tsv` 或等价 JSON
- stdout / stderr 日志
- 关键配置快照

- [ ] **统一目录结构**

建议：
```text
<OUT_ROOT>/<run_id>/
  coroutines/
  richards/
  raytrace/
  python_startup/
  summary.md
```

---

## 第四部分：本地 macOS Arm 的用途边界

### 任务 8：明确本地穿刺用途

- [ ] **允许在 macOS Arm 上做的事**

- 验证脚本参数与输出格式
- 缩小 benchmark 模块入口
- 验证 `bench_pyperf_direct.py` 的调用方式
- 预先生成 dump / 检查日志格式

- [ ] **禁止把 macOS Arm 数据当作什么**

- 不能作为 Arm Linux 最终性能结论
- 不能与 AMD 正式做性能比值
- 不能用来替代隔离环境中的 feature matrix 结果

---

## 第五部分：生成脚本前的最后检查

### 任务 9：只有完成这些映射后才开始写脚本

- [ ] 已确认首轮只覆盖 4 个 benchmark
- [ ] 已确认每个 benchmark 对应的主要差异点
- [ ] 已确认每个差异点需要采哪些最小数据
- [ ] 已确认哪些脚本可以复用，哪些需要新建
- [ ] 已确认 macOS Arm 只用于脚本与路径预演

---

## 建议的下一步

1. 先按本文件确认差异点到数据项的映射是否需要调整。
2. 然后优先新建两个脚本：
   - `scripts/arm/python_startup_matrix.sh`
   - `scripts/arm/first_pass_regression_bundle.sh`
3. 复用现有两个脚本而不是重写：
   - `scripts/arm/interp_feature_matrix.sh`
   - `scripts/arm/bench_pyperf_direct.py`

