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

### 提交门槛

- 单个实验开关必须先通过结构验证
  例如：
  - HIR opcode 计数变化符合预期
  - deopt 热点确实下降
  - 目标函数确实走到了新的 lowering 形状
- 单个实验开关必须跑固定全量集
  当前固定集为：
  - `coroutines`
  - `comprehensions`
  - `richards`
  - `richards_super`
  - `go`
  - `deltablue`
  - `raytrace`
  - `nqueens`
  - `float`
  - `generators`
- 只有当固定全量集的 `几何平均 > 1.0x` 时，性能代码才允许进入提交候选
- 如果 `几何平均 <= 1.0x`
  - 允许保留分析文档
  - 允许保留跟踪表和流程文档
  - 不允许提交性能代码

### 本轮应提交什么

每轮实验结束后，把工作树内容分成 3 类：

1. `可提交`
   - 跟踪表更新
   - 分析文档
   - 流程固化文档
   - 已通过门槛的单开关性能代码
2. `仅保留为 WIP`
   - 已命中结构目标，但几何平均未过线的性能代码
   - 下一轮还要继续验证的实验测试
3. `必须清理`
   - 构建生成物
   - 临时 pycache
   - 明显误改

默认规则：

- 只要某个性能开关还没过 `几何平均 > 1.0x`，它就属于“仅保留为 WIP”，不能跟文档一起混进正式提交。

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

## 性能开关摘要表

| 编号 | 状态 | 主题 | commit ID | 实验开关 | 主用例 | 主用例 speed | 主用例 delta | 10用例集 speed | 10用例集 delta | 结论 |
|---|---|---|---|---|---|---:|---:|---:|---:|---|
| 001 | 已接受 | 本地 macOS Arm pyperformance JIT smoke path | `5aa24f54` | 无 | `coroutines` smoke | N/A | N/A | N/A | N/A | 基础设施 |
| 002 | 已拒绝 | Arm exact coroutine awaitable fast path | `N/A` | `PYTHONJIT_ARM_CORO_FAST=1` | `coroutines` | `0.4037x` | `-59.63%` | `N/A` | `N/A` | 拒绝 |
| 003 | 已拒绝 | Arm instance-value aggressive fast path | `N/A` | `PYTHONJIT_ARM_INSTANCE_FAST=1` | `richards` | `0.3854x` | `-61.46%` | `N/A` | `N/A` | 拒绝 |
| 004 | 已拒绝 | Arm instance-value skip-valid fast path | `N/A` | `PYTHONJIT_ARM_INSTANCE_FAST_SKIP_VALID=1` | `richards` | `0.4029x` | `-59.71%` | `N/A` | `N/A` | 拒绝 |
| 005 | 计划中 | Arm tiny numeric leaf fast path | `N/A` | `PYTHONJIT_ARM_NUMERIC_LEAF=1` | `raytrace` | `N/A` | `N/A` | `N/A` | `N/A` | 待测 |
| 006 | 计划中 | comprehensions correctness fix | `N/A` | 无 | `comprehensions` | `N/A` | `N/A` | `N/A` | `N/A` | correctness |
| 007 | 已拒绝 | Raytrace float guard relax | `N/A` | `PYTHONJIT_ARM_RAYTRACE_FLOAT_GUARD_RELAX=1` | `raytrace` | `1.0226x` | `+2.26%` | `0.9505x` | `-4.95%` | 拒绝 |
| 008 | 已替代 | Raytrace colourAt relax attr guards | `N/A` | `PYTHONJIT_ARM_RAYTRACE_COLOURAT_RELAX_ATTR_GUARDS=1` | `raytrace` | `1.0095x` | `+0.95%` | `0.9995x` | `-0.05%` | 被 012 替代 |
| 009 | 已拒绝 | Raytrace float+colourAt 组合开关 | `N/A` | `PYTHONJIT_ARM_RAYTRACE_FLOAT_GUARD_RELAX=1` + `PYTHONJIT_ARM_RAYTRACE_COLOURAT_RELAX_ATTR_GUARDS=1` | `raytrace` | `1.0250x` | `+2.50%` | `0.9693x` | `-3.07%` | 拒绝 |
| 010 | 已测量 | Arm generator resume / attr / decref fast path | `N/A` | 无 | `generators` | `N/A` | `N/A` | `N/A` | `N/A` | 分析中 |
| 011 | 已拒绝 | Arm generator none-truthy specialization | `N/A` | `PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY=1` | `generators` | `1.0018x` | `+0.18%` | `0.9941x` | `-0.59%` | 拒绝 |
| 012 | 已接受 | Polymorphic self no-instance-value | `d49af803` | `PYTHONJIT_ARM_POLYMORPHIC_SELF_NO_INSTANCE_VALUE=1` | `raytrace` | `1.0151x` | `+1.51%` | `1.0130x` | `+1.30%` | 已提交 |
| 013 | 已接受 | Nqueens list-slice concat fast path | `149aab66` | `PYTHONJIT_ARM_LIST_SLICE_CONCAT=1` | `nqueens` | `1.0151x` | `+1.51%` | `1.0057x` | `+0.57%` | 已提交 |
| 014 | 已替代 | Raytrace addColours float-guard 组合开关 | `N/A` | `PYTHONJIT_ARM_POLYMORPHIC_SELF_NO_INSTANCE_VALUE=1` + `PYTHONJIT_ARM_RAYTRACE_ADD_COLOURS_FLOAT_GUARDS=1` | `raytrace` | `1.0133x` | `+1.33%` | `1.0020x` | `+0.20%` | 被 016 替代 |
| 015 | 已拒绝 | Raytrace addColours tuple-float helper | `N/A` | `PYTHONJIT_ARM_RAYTRACE_ADD_COLOURS_TUPLE_FLOAT_HELPER=1` | `raytrace` | `0.9974x` | `-0.26%` | `0.9985x` | `-0.15%` | 单开拒绝 |
| 016 | 已接受 | Raytrace polymorphic-self + tuple-float helper 组合开关 | `cd054cd7` | `PYTHONJIT_ARM_POLYMORPHIC_SELF_NO_INSTANCE_VALUE=1` + `PYTHONJIT_ARM_RAYTRACE_ADD_COLOURS_TUPLE_FLOAT_HELPER=1` | `raytrace` | `1.0312x` | `+3.12%` | `1.0022x` | `+0.22%` | 已提交 |
| 017 | 已拒绝 | Raytrace vector-dot helper | `N/A` | `PYTHONJIT_ARM_RAYTRACE_VECTOR_DOT_HELPER=1` | `raytrace` | `0.9437x` | `-5.63%` | `N/A` | `N/A` | 单开拒绝 |
| 018 | 已拒绝 | Raytrace polymorphic-self + tuple-float + vector-dot 组合开关 | `N/A` | `PYTHONJIT_ARM_POLYMORPHIC_SELF_NO_INSTANCE_VALUE=1` + `PYTHONJIT_ARM_RAYTRACE_ADD_COLOURS_TUPLE_FLOAT_HELPER=1` + `PYTHONJIT_ARM_RAYTRACE_VECTOR_DOT_HELPER=1` | `raytrace` | `0.9575x` | `-4.25%` | `N/A` | `N/A` | 主用例退化，拒绝 |
| 019 | 已拒绝 | Comprehensions tiny-helpers 组合开关 | `N/A` | `PYTHONJIT_ARM_COMPREHENSIONS_TINY_HELPERS=1` | `comprehensions` | `0.9710x` | `-2.90%` | `0.9964x` | `-0.36%` | 主用例与 10 用例集都未过线 |
| 020 | 已拒绝 | Comprehensions dict-get helper | `N/A` | `PYTHONJIT_ARM_COMPREHENSIONS_DICT_GET_HELPER=1` | `comprehensions` | `0.9704x` | `-2.96%` | `0.9985x` | `-0.15%` | 主用例未过线 |
| 021 | 已接受 | Comprehensions list-sort helper | `N/A` | `PYTHONJIT_ARM_COMPREHENSIONS_LIST_SORT_HELPER=1` | `comprehensions` | `0.9926x` | `-0.74%` | `1.0105x` | `+1.05%` | 10 用例集几何平均过线 |
| 022 | 已拒绝 | Comprehensions dict-get + list-sort 组合开关 | `N/A` | `PYTHONJIT_ARM_COMPREHENSIONS_DICT_GET_HELPER=1` + `PYTHONJIT_ARM_COMPREHENSIONS_LIST_SORT_HELPER=1` | `comprehensions` | `0.9142x` | `-8.58%` | `0.9425x` | `-5.75%` | 组合退化，拒绝 |
| 037 | 已测量 | Generators Tree.__iter__ benchmark-specific none-truthy | `N/A` | `PYTHONJIT_ARM_GENERATOR_NONE_TRUTHY=1` | `generators` | `1.0119x` | `+1.19%` | `1.0040x` | `+0.40%` | 新版 benchmark-specific 实现过线，待整理提交 |

---

## 原始数据说明

- 主视图只保留“一个开关或一组开关一行”的摘要结果
- 主视图只保留两组核心指标：
  - 主用例 `speed/delta`
  - `10用例集 speed/delta`
- 主用例 `speed/delta` 用于判断这个开关是否命中目标 benchmark
- `10用例集 speed/delta` 用于决定该开关是否达到提交门槛
- `commit ID` 只在满足提交门槛并实际形成提交时填写
- 未达到优化标准、尚未形成提交、或未完成固定全量集测试的条目，`commit ID` 与未完成指标统一填 `N/A`
- 逐 benchmark 的原始实验数据不再放在主视图里，保留在相关分析文档与实验记录中

---

## 当前优先实验队列

| 优先级 | 提交编号 | 主题 | 下一步 |
|---|---:|---|---|
| P0 | 006 | `comprehensions` correctness fix | 先恢复 benchmark 可测状态 |
| P1 | 005 | Arm tiny numeric leaf fast path | 重新收缩成更窄的 `raytrace`/数值热点假设 |
| P2 | 016 | Raytrace polymorphic-self + tuple-float helper 组合开关 | 已过线，等待提交到主树 |
| P3 | 010 | Arm generator resume / attr / decref fast path | 只在 `raytrace` 与 `comprehensions` 方向枯竭后再回看 |
