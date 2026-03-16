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

## 实验摘要表

| 编号 | 状态 | 主题 | commit ID | 实验开关 | 主用例 | 主用例 speedup | 主用例 delta | 10用例集几何平均 | 10用例集 delta | 结论 | 备注 |
|---|---|---|---|---|---|---:|---:|---:|---:|---|---|
| 001 | 已接受 | 本地 macOS Arm pyperformance JIT smoke path | `5aa24f54` | 无 | `coroutines` smoke | N/A | N/A | N/A | N/A | 保留 | 基础设施提交，不以性能收益为目标 |
| 002 | 已拒绝 | Arm exact coroutine awaitable fast path | `N/A` | `PYTHONJITARMCOROFAST=1` | `coroutines` | `0.4037x` | `-59.63%` | `N/A` | `N/A` | 不保留 | 主用例已明显负收益，未进入固定全量集 gate |
| 003 | 计划中 | Arm instance-value aggressive fast path | `N/A` | `PYTHONJITARMINSTANCEFAST=1` | `richards` | `N/A` | `N/A` | `N/A` | `N/A` | 待测 | 单开关结果未收敛 |
| 004 | 计划中 | Arm instance-value skip-valid fast path | `N/A` | `PYTHONJITARMINSTANCEFASTSKIPVALID=1` | `richards` | `N/A` | `N/A` | `N/A` | `N/A` | 待测 | 与 003 分开看 |
| 005 | 计划中 | Arm tiny numeric leaf fast path | `N/A` | `PYTHONJITARMNUMERICLEAF=1` | `raytrace` | `N/A` | `N/A` | `N/A` | `N/A` | 待测 | 优先看 `raytrace` |
| 006 | 计划中 | comprehensions correctness fix | `N/A` | 无 | `comprehensions` | `N/A` | `N/A` | `N/A` | `N/A` | 待测 | correctness gate，不是性能提交 |
| 007 | 已拒绝 | Raytrace float guard relax | `N/A` | `PYTHONJITARMRAYTRACEFLOATGUARDRELAX=1` | `raytrace` | `N/A` | `N/A` | `0.9505x` | `-4.95%` | 不保留 | 几何平均未过线 |
| 008 | 进行中 | Raytrace colourAt relax attr guards | `N/A` | `PYTHONJITARMRAYTRACECOLOURATRELAXATTRGUARDS=1` | `raytrace` | `N/A` | `N/A` | `0.9995x` | `-0.05%` | 继续优化 | 最接近提交线 |
| 009 | 已拒绝 | Raytrace float+colourAt 组合开关 | `N/A` | `PYTHONJITARMRAYTRACEFLOATGUARDRELAX=1` + `PYTHONJITARMRAYTRACECOLOURATRELAXATTRGUARDS=1` | `raytrace` | `1.0250x` | `+2.50%` | `0.9693x` | `-3.07%` | 不保留 | 主用例有收益，但整体回退明显 |
| 010 | 已测量 | Arm generator resume / attr / decref fast path | `N/A` | 无 | `generators` | `N/A` | `N/A` | `N/A` | `N/A` | 保留分析结论 | 分析项，不是性能开关 |
| 011 | 已拒绝 | Arm generator none-truthy specialization | `N/A` | `PYTHONJITARMGENERATORNONETRUTHY=1` | `generators` | `1.0018x` | `+0.18%` | `0.9941x` | `-0.59%` | 不保留性能代码 | 结构命中，但整体未过线 |

---

## 原始数据说明

- 主视图只保留“一个开关或一组开关一行”的摘要结果
- 主用例 `speedup/delta` 用于判断这个开关是否命中目标 benchmark
- `10用例集几何平均/delta` 用于决定该开关是否达到提交门槛
- 未达到优化标准或未完成固定全量集测试的条目，统一填 `N/A`
- 逐 benchmark 的原始实验数据不再放在主视图里，保留在相关分析文档与实验记录中

---

## 当前优先实验队列

| 优先级 | 提交编号 | 主题 | 下一步 |
|---|---:|---|---|
| P0 | 006 | `comprehensions` correctness fix | 先恢复 benchmark 可测状态 |
| P1 | 003 | Arm instance-value aggressive fast path | 把 `richards` 的收益来源拆细 |
| P1 | 004 | Arm instance-value skip-valid fast path | 继续验证 `richards/go/deltablue` |
| P2 | 008 | Raytrace colourAt relax attr guards | 继续收窄副作用，把 geomean 从 `0.9995x` 推过 `1.0` |
| P3 | 010 | Arm generator resume / attr / decref fast path | 分析已收束；只有在 `richards` / `raytrace` 方向枯竭后才回来看是否还有新假设 |
