# Arm 与 AMD 平台上 CPython 基准回退分析计划

> **面向代理执行者：** 必须使用 `superpowers:subagent-driven-development`（若支持子代理）或 `superpowers:executing-plans` 来执行本计划。步骤使用复选框 `- [ ]` 跟踪。

**目标：** 找出当前 `cinderx` 分支在所列 pyperformance benchmark 上落后于上游 CPython 的原因，重点判断差异是来自 Arm 特有性能回退、x86/AMD 特有性能提升，还是 x86 提升幅度明显高于 Arm。

**总体方法：** 这不是同一仓库历史上的普通 `git diff`，而是一项跨仓库、跨架构的性能取证工作。先把启动成本、解释器成本、JIT 成本分离，再把当前分支相对上游 CPython 的代码差异映射到 benchmark 热路径，最后判断每个 benchmark 的主要成因属于 Arm 特有回退、x86 特有 uplift，还是共享结构性差异。

**技术栈：** `git`、pyperformance、硬件计数器、CinderX 解释器/JIT 内部实现、基线 CPython 3.14 提交 `ebf955df7a89ed0c7968f79faec1de49f61ed7cb`

---

## 文件与代码区域映射

**主要对比目标**
- 检查：`/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/interpreter.c`
- 检查：`/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/ceval_macros.h`
- 检查：`/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/borrowed-ceval.c.template`
- 检查：`/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp`
- 检查：`/Users/luchen/Repo/cinderx/cinderx/Jit/lir/generator.cpp`
- 检查：`/Users/luchen/Repo/cinderx/cinderx/Jit/jit_rt.cpp`
- 检查：`/Users/luchen/Repo/cinderx/setup.py`
- 检查：`/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh`

**可复用的已有证据**
- 阅读：`/Users/luchen/Repo/cinderx/plans/2026-02-27-cinderx-vs-cpython-314-interpreter/deliverable.md`
- 阅读：`/Users/luchen/Repo/cinderx/docs/plans/2026-03-10-raytrace-cpython-vs-cinderx-jit-analysis.md`
- 阅读：`/Users/luchen/Repo/cinderx/plans/2026-03-12-float-accumulator-entry-promotion/findings.md`
- 阅读：`/Users/luchen/Repo/cinderx/plans/2026-03-12-generators-attr-decref/findings.md`
- 阅读：`/Users/luchen/Repo/cinderx/plans/2026-03-13-float-power-square-strength-reduction/findings.md`

**上游基线**
- 阅读：`/tmp/cpython-ebf955`
- 提交：`ebf955df7a89ed0c7968f79faec1de49f61ed7cb`

---

## 根因簇划分

1. **解释器热路径相对上游 CPython 的额外开销**
   - CinderX 特有的 `adaptive_enabled` 状态
   - `CI_UPDATE_CALL_COUNT` / `CI_SET_ADAPTIVE_INTERPRETER_ENABLED_STATE`
   - tail-call 解释器多传递一个状态参数
   - 自定义 PEP 523 与 awaitable 处理逻辑

2. **Arm 平台默认开启的特性**
   - `ENABLE_ADAPTIVE_STATIC_PYTHON`
   - `ENABLE_LIGHTWEIGHT_FRAMES`
   - 可能带来 Arm 专属 frame / dispatch / codegen 成本

3. **JIT 在 mixed numeric 场景下的特化失配**
   - 小 helper 上 exact-int guard 过激
   - mixed int/float 导致 deopt 风暴
   - 局部仍回退到 boxed / generic 路径

4. **generator / coroutine 运行时额外成本**
   - generator attr lowering 未完全覆盖
   - decref 展开
   - coroutine awaitable wrapper

5. **启动路径注入成本**
   - pyperformance worker `sitecustomize.py`
   - CinderX 自动导入 / JIT enable 路径

---

## 优先级顺序

### 任务 1：建立按架构与模式分层的测量矩阵

**文件：**
- 阅读：`/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh`
- 阅读：`/Users/luchen/Repo/cinderx/scripts/arm/bench_pyperf_direct.py`
- 阅读：`/Users/luchen/Repo/cinderx/setup.py`
- 输出目录：`artifacts/<date>-arm-amd-regression-matrix/`

- [ ] **步骤 1：定义六个基础测量单元**

对每个 benchmark 记录：
- `cpython-arm`
- `cpython-amd`
- `cinderx-arm-interp`
- `cinderx-arm-jit`
- `cinderx-amd-interp`
- `cinderx-amd-jit`

- [ ] **步骤 2：统一环境变量与运行策略**

固定矩阵：
- 纯解释器模式：`PYTHONJITDISABLE=1`
- JIT 模式：两边使用同样 threshold / jitlist 策略
- 启动测试：分别在启用与禁用 CinderX 自动加载 `sitecustomize` 下运行

- [ ] **步骤 3：保存原始结果与汇总结果**

每个测量单元都保存：
- wall time 中位数
- warmup / sample 次数
- Python 版本与构建 flag
- 当前分支 head / 提交号
- `ENABLE_LIGHTWEIGHT_FRAMES` 与 `ENABLE_ADAPTIVE_STATIC_PYTHON` 的实际开启状态

- [ ] **步骤 4：计算三类派生对比**

对每个 benchmark 计算：
- 上游 CPython 内部的 Arm-vs-AMD
- CinderX 内部的 Arm-vs-AMD
- 同一架构下 CinderX-vs-CPython

- [ ] **步骤 5：建立归因分类规则**

把每个回退分为：
- Arm 特有 slowdown
- x86/AMD 特有 uplift
- 两边都退，但 x86 uplift 更大

### 任务 2：先验证共享根因簇，而不是先逐个 benchmark 深挖

**文件：**
- 阅读：`/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/interpreter.c`
- 阅读：`/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/ceval_macros.h`
- 阅读：`/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/borrowed-ceval.c.template`
- 阅读：`/Users/luchen/Repo/cinderx/plans/2026-02-27-cinderx-vs-cpython-314-interpreter/deliverable.md`

- [ ] **步骤 1：先用四个代表 benchmark 做首轮验证**

先跑：
- `coroutines`
- `richards`
- `raytrace`
- `python_startup`

原因：
- 分别覆盖 async/runtime、解释器高调用、JIT mixed numeric、启动成本

- [ ] **步骤 2：验证解释器根因簇**

对 `coroutines` 和 `richards`，至少比较：
- CinderX 纯解释器
- CinderX 纯解释器且关闭部分特性（若可构建 feature variant）
- 上游 CPython

重点看是否和以下代码差异一致：
- `adaptive_enabled`
- `CI_UPDATE_CALL_COUNT`
- `CI_SET_ADAPTIVE_INTERPRETER_ENABLED_STATE`
- PEP 523 hook 检查

- [ ] **步骤 3：验证 JIT numeric 根因簇**

对 `raytrace`，比较：
- 当前分支
- `PYTHONJITDISABLE=1`
- compile strategy 变体（若工具链支持）

检查：
- deopt 数量
- 编译函数数量
- HIR guard 形态
- generic `BinaryOp` 回退频率

- [ ] **步骤 4：验证启动根因簇**

对 `python_startup`，比较：
- 纯 CPython
- CinderX 且禁用 worker `sitecustomize`
- CinderX 且启用 worker `sitecustomize`

这一组用于把启动注入成本与 steady-state 执行成本分开。

### 任务 3：按 benchmark 优先级逐个建立“怀疑点 -> 验证点”映射

**文件：**
- 使用 benchmark 输出
- 仅对必要热点导出 HIR/LIR
- 将笔记保存到 `artifacts/<date>-arm-amd-regression-matrix/`

- [ ] **步骤 1：`coroutines`**

主要怀疑点：
- `borrowed-ceval.c.template` 里的 awaitable / coroutine 自定义路径
- JIT coroutine wrapper / runtime
- Arm 上 lightweight frames 的额外交互

验证重点：
- await / send / resume 热路径计数
- 若可行，比较 `PYTHONJITLIGHTWEIGHTFRAME=0/1`
- 确认是否替换了 stock `_PyCoro_GetAwaitableIter`

- [ ] **步骤 2：`comprehensions`**

主要怀疑点：
- `LIST_APPEND` / `MAP_ADD` 包装路径
- 解释器 adaptive 分支
- ext-op / static-python 对紧凑容器构建循环的扰动

验证重点：
- list-comp 与 dict-comp 是否表现不同
- 与 append/update 类微基准的相关性
- Arm 上 branch / icache 是否更敏感

- [ ] **步骤 3：`richards`**

主要怀疑点：
- frame 切换
- 调用计数 / adaptive 记账
- 解释器分支密度

验证重点：
- `cycles`
- `branches`
- `branch-misses`
- `icache`

- [ ] **步骤 4：`richards_super`**

主要怀疑点：
- 与 `richards` 相同
- 外加方法分派 / 属性访问 / `super()` 行为

验证重点：
- 方法调用形态
- attr load/store 频率
- 是否触发 CinderX 特化 attr 路径上的不匹配

- [ ] **步骤 5：`go`**

主要怀疑点：
- 对象方法分派
- global/type guard 策略
- 高调用密度解释器开销

验证重点：
- 与 mutable global guard 相关 findings 对照
- 观察是否有小 helper 被过度编译

- [ ] **步骤 6：`deltablue`**

主要怀疑点：
- 方法分派 + 属性访问 + 约束对象图更新成本
- 解释器开销大于纯数值吞吐

验证重点：
- attr-heavy helper 热点
- guard/deopt 数量
- 容器变更密度

- [ ] **步骤 7：`raytrace`**

主要怀疑点：
- 剩余 mixed numeric leaf method 问题
- Arm codegen 仍落后于 AMD 的 float/math helper

验证重点：
- 确认当前分支是否已避开旧的 exact-int guard storm
- 比较 Arm/AMD 的 compiled size 与 deopt count
- 仅检查最热少数 helper

- [ ] **步骤 8：`nqueens`**

主要怀疑点：
- 递归 / 分支 / 整数搜索
- 解释器开销
- JIT 回报有限

验证重点：
- 解释器与 JIT 模式的收益差
- Arm 上 branch miss 敏感性
- 是否存在小 helper overcompile

- [ ] **步骤 9：`float`**

主要怀疑点：
- 仍有 float 形状未被 accumulator promotion 或 `**2` rewrite 覆盖
- Arm codegen 在 float 快路径上仍有差距

验证重点：
- 区分 `float` benchmark 内部的子形状
- 只 dump 最慢热点方法
- 确认出现 `DoubleBinaryOp`，避免 generic `BinaryOp<Power>`

- [ ] **步骤 10：`generators`**

主要怀疑点：
- 剩余 generator decref 开销
- benchmark 的真实形状不完全落入 low-local attr-lowering 例外

验证重点：
- `LoadAttrCached`
- `LoadField`
- `Decref`
- `BatchDecref`

- [ ] **步骤 11：`python_startup`**

主要怀疑点：
- CinderX import + worker `sitecustomize`
- 启动时的 feature probing

验证重点：
- import timing
- 若可行使用 `-X importtime`
- 对比禁用 autoload 的 worker 环境

### 任务 4：把代码差异映射回上游 CPython 基线

**文件：**
- 阅读：`/tmp/cpython-ebf955`
- 阅读：`/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/*`
- 阅读：`/Users/luchen/Repo/cinderx/cinderx/Jit/*`

- [ ] **步骤 1：为每个 benchmark 填一张差异表**

字段：
- 热子系统
- CinderX 独有代码差异
- 为什么它可能是架构敏感的
- 当前置信度

- [ ] **步骤 2：标记证据强度**

证据标签：
- `已有本地 findings 已确认`
- `当前代码阅读已确认`
- `需要新的 benchmark 验证`

- [ ] **步骤 3：区分结构性差异与当前分支特有问题**

要分清：
- CinderX-vs-CPython 的长期结构成本
- 当前分支已经在修复中的点
- 仍未解释清楚的剩余差距

### 任务 5：用硬件计数器与 dump 做最终验证

**文件：**
- 输出目录：`artifacts/<date>-arm-amd-regression-matrix/`

- [ ] **步骤 1：解释器型 benchmark**

采集：
- `cycles`
- `instructions`
- `branches`
- `branch-misses`
- 若可得则加 `icache` misses

- [ ] **步骤 2：JIT 型 benchmark**

采集：
- deopt 数量
- 编译函数数量
- 编译后代码尺寸
- 热方法 HIR/LIR dump

- [ ] **步骤 3：启动型 benchmark**

采集：
- import timing
- 总启动时间
- benchmark body 开始前的成本

### 任务 6：最终报告结构

**文件：**
- 生成：`artifacts/<date>-arm-amd-regression-matrix/report.md`

- [ ] **步骤 1：写总览**

说明：
- 哪些回退主要是解释器路径
- 哪些主要是 JIT 路径
- 哪些主要是启动路径

- [ ] **步骤 2：写优先级发现**

按顺序：
1. `coroutines`
2. `comprehensions`
3. `richards`
4. `richards_super`
5. `go`
6. `deltablue`
7. `raytrace`
8. `nqueens`
9. `float`
10. `generators`
11. `python_startup`

- [ ] **步骤 3：每个 benchmark 固定记录以下字段**

模板：
- 回退类别
- 主要根因簇
- 具体应检查的代码区域
- 下一步实验
- 达到“足够确认”的退出条件

---

## 当前假设快照

- `coroutines`：最高概率是 CinderX 自定义 awaitable/coroutine 路径与 Arm-only lightweight frames 共同导致。
- `comprehensions`：最高概率是解释器容器操作成本，而不是 JIT numeric codegen。
- `richards` / `richards_super` / `go` / `deltablue`：最高概率是共享的解释器 dispatch / call bookkeeping 额外成本，并在 Arm 上被 branch 与 icache 压力放大。
- `raytrace`：当前 mixed-numeric guard 策略应该已经修掉主要灾难点，因此剩余差距更像是 Arm codegen 质量或 benchmark 形状覆盖不足。
- `nqueens`：更像递归/分支型解释器成本，JIT 收益未必明显。
- `float`：已有部分修复，需要定位是否还有未覆盖的 float 子形状。
- `generators`：attr-lowering 已经改善，但 decref 开销仍然可疑。
- `python_startup`：大概率主要是 CinderX 自动加载与启动注入成本，不是 steady-state Python 核心执行吞吐。

## 验证命令

- [ ] **步骤 1：确认分支与基线**

运行：
```bash
git -C /Users/luchen/Repo/cinderx rev-parse HEAD
git -C /Users/luchen/Repo/cpython rev-parse ebf955df7a89ed0c7968f79faec1de49f61ed7cb
```

- [ ] **步骤 2：再次确认 Arm 默认特性**

运行：
```bash
python3 - <<'PY'
from setup import should_enable_adaptive_static_python, should_enable_lightweight_frames
print("adaptive_arm", should_enable_adaptive_static_python("3.14", False, "arm64"))
print("lwf_arm", should_enable_lightweight_frames("3.14", False, "arm64"))
print("adaptive_x86", should_enable_adaptive_static_python("3.14", False, "x86_64"))
print("lwf_x86", should_enable_lightweight_frames("3.14", False, "x86_64"))
PY
```

- [ ] **步骤 3：准备证据目录**

运行：
```bash
mkdir -p artifacts/2026-03-14-arm-amd-regression-matrix
```
