# 性能实验提交跟踪表

## 使用约定

### 口径

- `speedup = baseline_time / candidate_time`
- `speedup > 1.0x` 表示候选提交更快
- `speedup < 1.0x` 表示候选提交更慢
- `delta % = (speedup - 1) * 100%`

### 对照对象

- `prev-cinderx`：与前一个 CinderX 基线提交比较，用来判断“这次改动是否有效”
- `cpython-anchor`：与基准 CPython 分支比较，用来判断“距离目标还有多远”

### 状态

- `计划中`：已登记，尚未开始
- `进行中`：代码或实验正在进行
- `已测量`：已有数据，尚未下结论
- `已接受`：收益稳定，保留
- `已拒绝`：无收益或有明显副作用
- `已替代`：被后续提交替代

### 提交隔离规则

- 一个提交只承载一个主要性能假设
- correctness 修复和性能优化尽量拆开
- 跑通工具链或脚本的基础设施提交单独记为 `infra`

### 如何回填刚完成的提交

每次做完一个实验提交后，按下面流程把 commit 回填进这张表：

1. 先拿到刚提交的 commit ID
   运行：
   `git log --oneline -1`
2. 在“提交主表”里找到对应的计划项
   一般就是状态为“计划中”或“进行中”的那一行。
3. 把这一行的字段更新完整
   至少要回填：
   - `状态`
   - `提交`
   - `父提交`
   - `改动范围`
   - `实验开关`
   - `备注`
4. 如果这个提交已经开始跑 benchmark，再到“benchmark 结果明细表”里新增一行
   明细表必须写清楚：
   - 平台
   - benchmark
   - baseline 时间
   - candidate 时间
   - speedup
   - 实际命令
5. 如果这个提交替代了一个更老的实验项
   把老条目的状态改成“已替代”，并在备注里写明“被哪一个提交替代”。

推荐的最小回填模板如下：

| 操作 | 需要填写的内容 |
|---|---|
| 提交后立即回填 | `提交`、`父提交`、`状态=进行中` |
| 本地 macOS Arm 跑完后 | `macOS Arm 结果`、主表里的初步结论、明细表新增运行记录 |
| Linux Arm 正式跑完后 | `Linux Arm 结果`、`相对前一 CinderX 基线`、`相对基准 CPython`、最终结论 |

### 回填示例

下面用已经完成的基础设施提交 `5aa24f54` 演示一次完整回填流程。

#### 第一步：拿到刚提交的 commit ID

运行：

```bash
git log --oneline -1
```

示例输出：

```text
5aa24f54 Enable local macOS Arm pyperformance JIT smoke path
```

#### 第二步：把主表对应行从“计划中”改成已知状态

如果这是一个已经完成并验证过的基础设施提交，那么主表里这一行至少要写成：

| 编号 | 状态 | 类型 | 主题 | 提交 | 父提交 | 备注 |
|---|---|---|---|---|---|---|
| 001 | 已接受 | `infra` | 本地 macOS Arm pyperformance JIT smoke path | `5aa24f54` | `f551f1db` | 这是实验基础设施提交，不以 speedup 为目标 |

如果是新做完、但还没跑 benchmark 的性能提交，建议先写成：

| 编号 | 状态 | 提交 | 父提交 |
|---|---|---|---|
| 00X | 进行中 | `刚提交的 commit` | `它的父提交` |

#### 第三步：把本地 macOS Arm 结果补进主表

对 `5aa24f54` 这类基础设施提交，主表里的 `macOS Arm 结果` 可以这样写：

```text
import cinderx 成功，coroutines smoke 跑通，compiled_count=2
```

如果是性能提交，则建议写成一句结论，例如：

```text
richards 在 macOS Arm 上 speedup=1.0254x，方向正确，建议继续上 Linux Arm 验证
```

#### 第四步：在明细表里新增对应运行记录

`5aa24f54` 的 smoke 记录已经按下面这种形式写进表里：

| 运行编号 | 提交编号 | 提交 | 平台 | 对照对象 | 用例 | 模式 | samples | prewarm | candidate median (s) | 备注 |
|---|---:|---|---|---|---|---|---:|---:|---:|---|
| `mac-smoke-001` | 001 | `5aa24f54` | `macos-arm` | `prev-cinderx` | `coroutines` | `baseline` | 1 | 0 | `0.0257616250` | smoke only, `compiled_count=2` |

对普通性能提交，明细表里至少还要把 `baseline median (s)`、`candidate median (s)` 和 `speedup` 一起填上。

#### 第五步：Linux Arm 跑完后补齐最终结论

当 Linux Arm 正式结果回来后，再回主表补：

- `Linux Arm 结果`
- `相对前一 CinderX 基线`
- `相对基准 CPython`
- `结论`

这一步完成后，这个提交才算真正闭环。

---

## 提交主表

| 编号 | 状态 | 类型 | 主题 | 提交 | 父提交 | 改动范围 | 实验开关 | 目标用例 | 假设 | macOS Arm 结果 | Linux Arm 结果 | 相对前一 CinderX 基线 | 相对基准 CPython | 结论 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|---|---:|---:|---|---|
| 001 | 已接受 | `infra` | 本地 macOS Arm pyperformance JIT smoke path | `5aa24f54` | `f551f1db` | `setup.py`, `cinderx/StaticPython/vtable_defs.c`, `cinderx/Jit/*`, `scripts/arm/*` | 无 | `coroutines` smoke、本地 JIT 可用性 | 修复 Darwin `_PyVTable_thunk_native` 符号链和 JIT code allocator 后，本地 macOS Arm 可以稳定跑 JIT smoke benchmark | `import cinderx` 成功，`coroutines` smoke 跑通，`compiled_count=2` | 待补 | N/A | N/A | 保留 | 这是实验基础设施提交，不以 speedup 为目标 |
| 002 | 已拒绝 | `perf-single` | Arm exact coroutine awaitable fast path | 待定 | `5aa24f54` | `cinderx/Jit/hir/builder.cpp`, `cinderx/Interpreter/3.14/ceval.h` | `PYTHONJITARMCOROFAST=1` | `coroutines`、部分 `generators` | exact coroutine 形状应绕过通用 awaitable helper，缩短 Arm 上 helper/branch 链 | 本地筛选为负收益，实验代码已撤回 | 待补 | N/A | 待补 | 不保留 | 当前本地 `coroutines` 为 `0.4037x`，不值得继续 |
| 003 | 计划中 | `perf-single` | Arm instance-value aggressive fast path | 待定 | `5aa24f54` | `cinderx/Jit/hir/builder.cpp` | `PYTHONJITARMINSTANCEFAST=1` | `richards`、`go`、`deltablue`、`comprehensions` | low-local exact instance-value 形状应更多落到 field access，而不是 cached attr helper | 待跑 | 待跑 | 待补 | 待补 | 待定 | 可先和 skip-valid 分开测 |
| 004 | 计划中 | `perf-single` | Arm instance-value skip-valid fast path | 待定 | `5aa24f54` | `cinderx/Jit/hir/builder.cpp`, interpreter attr fast path | `PYTHONJITARMINSTANCEFASTSKIPVALID=1` | `richards`、`go`、`deltablue` | 跳过 inline-values valid guard 可降低 Arm 上额外 guard 和地址生成成本 | 待跑 | 待跑 | 待补 | 待补 | 待定 | 需要重点盯 correctness |
| 005 | 计划中 | `perf-single` | Arm tiny numeric leaf fast path | 待定 | `5aa24f54` | `cinderx/Jit/hir/builder.cpp`, numeric lowering | `PYTHONJITARMNUMERICLEAF=1` | `raytrace`、`float`、部分 `nqueens` | tiny numeric leaf 上减少 mixed-numeric guard 和 helper glue，Arm 收益应大于 x86 | 待跑 | 待跑 | 待补 | 待补 | 待定 | 优先看 `raytrace` |
| 006 | 计划中 | `fix` | comprehensions correctness fix | 待定 | `5aa24f54` | 待定 | 无 | `comprehensions` | 先修复当前 `TypeError: 'int' object is not an iterator`，恢复可测状态 | 待跑 | 待跑 | N/A | N/A | 待定 | 这是 correctness gate，不应和性能提交混合 |
| 007 | 已拒绝 | `perf-single` | Raytrace float guard relax | 待定 | `5aa24f54` | `cinderx/Jit/hir/builder.cpp`, `cinderx/Jit/config.h`, `cinderx/Jit/pyjit.cpp` | `PYTHONJITARMRAYTRACEFLOATGUARDRELAX=1` | `raytrace` | 放宽 `Vector.dot/Vector.scale` 的 tiny float guard，期望在 Arm 上减少 numeric leaf 成本 | 单开对 `raytrace` 有过正向信号，但跨 10 个 benchmark 的 geomean 为 `0.9505x` | 待补 | `0.9505x` | 待补 | 不保留 | `comprehensions` / `deltablue` / `nqueens` 回退明显 |
| 008 | 进行中 | `perf-single` | Raytrace colourAt relax attr guards | 待定 | `5aa24f54` | `cinderx/Jit/hir/builder.cpp`, `cinderx/Jit/config.h`, `cinderx/Jit/pyjit.cpp` | `PYTHONJITARMRAYTRACECOLOURATRELAXATTRGUARDS=1` | `raytrace` | 避免 `SimpleSurface.colourAt` 的 specialized instance-value path 在非目标形状上反复 deopt | 单开 geomean 为 `0.9995x`，最接近可提交线 | 待补 | `0.9995x` | 待补 | 继续优化 | 当前是最接近 `>1.0` gate 的实验开关 |
| 009 | 已拒绝 | `perf-combo` | Raytrace float+colourAt 组合开关 | 待定 | `5aa24f54` | `cinderx/Jit/hir/builder.cpp`, `cinderx/Jit/config.h`, `cinderx/Jit/pyjit.cpp` | `PYTHONJITARMRAYTRACEFLOATGUARDRELAX=1` + `PYTHONJITARMRAYTRACECOLOURATRELAXATTRGUARDS=1` | `raytrace` | 组合后应同时压 numeric leaf 和 `colourAt` 成本 | `raytrace` 可到 `1.0250x`，但跨 10 个 benchmark 的 geomean 为 `0.9693x` | 待补 | `0.9693x` | 待补 | 不保留 | 组合收益无法覆盖其它用例回退 |
| 010 | 进行中 | `analysis` | Arm generator resume / attr / decref fast path | 待定 | `5aa24f54` | 待定 | 待定 | `generators` | 当前生成器热点可能根本没进入 compiled set，应先确认编译覆盖率与 resume 链路 | 本地基线显示 `compiled_count=3`，缺少 `Tree.__iter__`；zero-deopt | 待补 | N/A | 待补 | 分析中 | 先解释为什么 `Tree.__iter__` 未进入 compiled qualnames |

---

## Benchmark 结果明细表

| 运行编号 | 提交编号 | 提交 | 平台 | 对照对象 | 用例 | 模式 | samples | prewarm | baseline median (s) | candidate median (s) | speedup | delta % | 命令 | 备注 |
|---|---:|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| `mac-smoke-001` | 001 | `5aa24f54` | `macos-arm` | `prev-cinderx` | `coroutines` | `baseline` | 1 | 0 | N/A | `0.0257616250` | N/A | N/A | `scripts/arm/run_local_pyperf_matrix.py --benchmark coroutines --mode baseline --samples 1 --prewarm-runs 0` | smoke only, `compiled_count=2` |
| `mac-exp-001` | 002 | 待定 | `macos-arm` | `prev-cinderx` | `coroutines` | `baseline -> arm_coro_fast` | 5 | 2 | `0.06438825` | `0.06620771` | `0.9725x` | `-2.75%` | 本地 quick experiment | 当前这轮未复现收益 |
| `mac-exp-002` | 002 | 待定 | `macos-arm` | `prev-cinderx` | `coroutines` | `baseline -> arm_all_experiments` | 5 | 2 | `0.06438825` | `0.06479429` | `0.9937x` | `-0.63%` | 本地 quick experiment | 基本持平偏慢 |
| `mac-exp-003` | 004 | 待定 | `macos-arm` | `prev-cinderx` | `richards` | `baseline -> arm_instance_skip_valid` | 5 | 2 | `0.02804500` | `0.02788358` | `1.0058x` | `+0.58%` | 本地 quick experiment | 有微弱正向信号 |
| `mac-exp-004` | 003/004/005 组合 | 待定 | `macos-arm` | `prev-cinderx` | `richards` | `baseline -> arm_all_experiments` | 5 | 2 | `0.02804500` | `0.02734913` | `1.0254x` | `+2.54%` | 本地 quick experiment | 说明这组开关值得继续拆分 |
| `mac-exp-005` | 007 | 待定 | `macos-arm` | `prev-cinderx` | `raytrace` | `baseline -> PYTHONJITARMRAYTRACEFLOATGUARDRELAX=1` | 10 | 3 | 见该组明细 | 见该组明细 | `0.9505x` | `-4.95%` | 顺序测 10 个 benchmark，取几何平均 | 单开不满足提交 gate |
| `mac-exp-006` | 008 | 待定 | `macos-arm` | `prev-cinderx` | `raytrace` | `baseline -> PYTHONJITARMRAYTRACECOLOURATRELAXATTRGUARDS=1` | 10 | 3 | 见该组明细 | 见该组明细 | `0.9995x` | `-0.05%` | 顺序测 10 个 benchmark，取几何平均 | 最接近提交线 |
| `mac-exp-007` | 009 | 待定 | `macos-arm` | `prev-cinderx` | `raytrace` | `baseline -> float_guard_relax + colourAt_relax_attr_guards` | 10 | 3 | 见该组明细 | 见该组明细 | `0.9693x` | `-3.07%` | 顺序测 10 个 benchmark，取几何平均 | 组合不可提交 |
| `mac-exp-008` | 010 | 待定 | `macos-arm` | `prev-cinderx` | `generators` | `baseline` | 5 | 1 | N/A | `0.10902658` | N/A | N/A | `bench_pyperf_direct.py --module-path .../bm_generators/run_benchmark.py --bench-func bench_generators --bench-args-json '[1]'` | `compiled_count=3`，compiled qualnames 不含 `Tree.__iter__` |

---

## 当前优先实验队列

| 优先级 | 提交编号 | 主题 | 下一步 |
|---|---:|---|---|
| P0 | 006 | `comprehensions` correctness fix | 先恢复 benchmark 可测状态 |
| P1 | 003 | Arm instance-value aggressive fast path | 把 `richards` 的收益来源拆细 |
| P1 | 004 | Arm instance-value skip-valid fast path | 继续验证 `richards/go/deltablue` |
| P2 | 008 | Raytrace colourAt relax attr guards | 继续收窄副作用，把 geomean 从 `0.9995x` 推过 `1.0` |
| P2 | 010 | Arm generator resume / attr / decref fast path | 先解释 `Tree.__iter__` 未被编译的原因，再决定是 compile coverage 问题还是 generator runtime 问题 |
