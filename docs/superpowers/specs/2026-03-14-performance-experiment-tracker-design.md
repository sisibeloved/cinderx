# 性能实验提交跟踪表设计稿

## 1. 目标

这份跟踪表的目标不是简单记录 benchmark 数字，而是同时满足 4 个约束：

1. 每个性能实验提交都尽量只包含一个改动点，便于归因。
2. 每个提交都能追踪它面向的 benchmark、实验开关、测试环境和结果。
3. 每个提交都能同时回答两个问题：
   - 相对于前一个 CinderX 基线，它是否让 Arm 上的 CinderX 变快了？
   - 相对于基准 CPython，它是否让 Arm 上的 CinderX 更接近甚至超过目标性能？
4. 结果必须可回溯到具体 commit、具体命令和具体运行批次，避免“记得好像提升过”这种不可复现结论。

## 2. 记录粒度

主表采用“每个提交一行”的粒度。

原因：

- 这最适合“改动隔离”和“收益归因”。
- 当一个提交回退或被重写时，追踪成本最低。
- 便于和 `git log`、代码 review、Cherry-pick、回滚操作对齐。

但单个提交通常会对应多次 benchmark 运行，所以还需要配一个明细表。  
因此最终采用“双表结构”：

1. 提交主表
2. benchmark 结果明细表

## 3. 双表结构

### 3.1 提交主表

提交主表回答的是：

- 这个提交改了什么
- 为什么改
- 影响哪些 benchmark
- 跑过哪些实验
- 当前结论是什么

建议字段：

| 列名 | 含义 |
|---|---|
| `ID` | 人工递增编号，便于在讨论中引用 |
| `状态` | `planned` / `in_progress` / `measured` / `accepted` / `rejected` / `superseded` |
| `主题` | 一句话概括，例如 `Arm exact coroutine awaitable fast path` |
| `提交` | git commit hash |
| `父提交` | 用来确认比较基线 |
| `改动范围` | 关键文件或模块 |
| `实验开关` | 本次提交对应的 env flags |
| `目标 benchmark` | 预计受影响的 benchmark |
| `假设` | 这次提交为什么应该提升性能 |
| `macOS Arm 结果` | 快速筛选结论 |
| `Linux Arm 结果` | 正式结果结论 |
| `相对前一 CinderX 基线` | 以 speedup 表示 |
| `相对基准 CPython` | 以 speedup 表示 |
| `结论` | 保留、继续拆分、回滚、合并进下一提交 |
| `备注` | 例如 correctness 风险、波动异常、需要重跑 |

### 3.2 benchmark 结果明细表

明细表回答的是：

- 这个提交到底跑了什么
- 哪个平台
- 哪个 benchmark
- 基线时间和候选时间分别是多少
- speedup 具体是多少

建议字段：

| 列名 | 含义 |
|---|---|
| `Run ID` | 一次批量实验的唯一标识 |
| `提交 ID` | 对应主表的 `ID` |
| `提交` | git commit hash |
| `平台` | `macos-arm` / `linux-arm` |
| `对照对象` | `prev-cinderx` / `cpython-anchor` |
| `benchmark` | benchmark 名称 |
| `模式` | baseline、实验模式名 |
| `samples` | 采样次数 |
| `prewarm` | 预热次数 |
| `baseline median (s)` | 基线耗时 |
| `candidate median (s)` | 候选耗时 |
| `speedup` | `baseline / candidate` |
| `delta %` | `(speedup - 1) * 100%` |
| `命令` | 实际运行命令 |
| `备注` | deopt、crash、correctness 风险等 |

## 4. 核心口径

### 4.1 统一用时间反比表示收益

统一定义：

`speedup = baseline_time / candidate_time`

解释：

- `speedup > 1.0x` 表示候选提交更快
- `speedup = 1.0x` 表示无变化
- `speedup < 1.0x` 表示候选提交更慢

这样和你现在的表达方式一致。

### 4.2 必须同时保留两条比较线

每个值得保留的实验提交，至少要保留两条比较：

1. `相对前一 CinderX 基线`
2. `相对 CPython anchor`

原因：

- 第一条用来判断“这个提交本身是否有效”
- 第二条用来判断“我们离目标还差多远”

如果只保留第一条，会出现“提交 A 比提交 B 快，但整体仍远慢于 CPython”的假象。  
如果只保留第二条，又会难以定位是哪一个提交真正带来了收益。

## 5. 提交隔离原则

为了让表格真正可用，提交本身必须满足这些规则：

1. 一个提交只做一个主要性能假设。
2. 一个提交最多只挂一个主实验开关。
3. 如果需要叠加多个子开关，先分别提交，再做组合提交。
4. correctness 修复和性能优化尽量拆开。
5. 基础设施提交单独记录为 `infra`，不和性能提交混在一起。

推荐的提交类型：

- `infra`：跑通本地 benchmark、补驱动脚本、补 smoke test
- `perf-single`：单一性能改动
- `perf-combo`：组合验证提交
- `fix`：纠正前一个提交的 correctness 或测量问题

## 6. 推荐工作流

每个候选改动按下面流程进入主表：

1. 新建一条主表记录，状态为 `planned`
2. 写代码并单独提交
3. 在 macOS Arm 上跑快速实验
4. 更新主表中的 `macOS Arm 结果`
5. 只有方向正确时，才进入 Linux Arm 正式测试
6. 更新明细表中的正式数据
7. 根据结果把主表状态改成：
   - `accepted`
   - `rejected`
   - `superseded`

## 7. 为什么需要单独的基础设施行

像 `Enable local macOS Arm pyperformance JIT smoke path` 这样的提交，虽然不是性能优化本身，但它决定了后续实验是否能稳定复现。  
这类提交应该在主表里单列成 `infra`，并标记：

- 它不追求 speedup
- 它提供什么验证能力
- 它之后的哪些实验依赖它

否则后面回看历史时，会看不懂为什么某一批实验从这里开始才“可测”。

## 8. 最终产物

建议维护 1 份长期文件：

- `docs/superpowers/plans/2026-03-14-performance-experiment-commit-tracker.md`

这个文件中包含：

1. 使用约定
2. 提交主表
3. benchmark 明细表
4. 当前优先实验队列

这样后面无论是本地 macOS Arm 快速筛选，还是 Linux Arm 正式实验，都往同一份文件里追加即可。
