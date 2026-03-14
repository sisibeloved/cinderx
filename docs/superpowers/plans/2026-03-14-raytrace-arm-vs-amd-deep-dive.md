# `raytrace`：为什么这个 benchmark 的平台比值变化首先要从“过编译 + mixed numeric”理解

## 1. benchmark 本体在做什么

`bm_raytrace` 的热点主要在：

- `Vector.dot()`
- `Vector.scale()`
- `Point.__sub__()`
- `Sphere.intersectionTime()`
- `Scene.rayColour()`
- `firstIntersection()`

它和 `richards` / `go` 最大的不同是：

- 有明显的数值 leaf helper
- helper 很小，但调用次数极多
- 类型流里混着 `int` 和 `float`

这使它非常依赖 JIT 对 mixed numeric leaf helper 的处理策略。

## 2. 基准 CPython 与 CinderX 的关键差异

已有专项分析已经把这条链路钉得很清楚：

- CinderX 曾经会编译很多 `raytrace` 小 helper
- 这些 helper 的类型流不是纯 float，而是混合 `int/float`
- CinderX 对它们做过窄 specialization，会引发大量 `GuardType` 失败和 deopt
- CPython 自带 JIT 则只编译少数真正有 backedge 的热区

这不是“Arm 天生不适合 raytrace”，而是：

- CinderX 相对基准 CPython 引入了一种对该 benchmark 不友好的 JIT 策略

## 3. 当前分支已经有哪些修复

当前仓库并不是完全没有处理这个问题。  
已有 findings 表明当前分支已经收窄策略：

- 对 specialized numeric opcodes，只在有 backedge 的 code object 上保留 exact-int guard
- 对无 backedge 的 tiny leaf helper，避免保留那类 exact-int guard

这一点正是为了消除 `raytrace` 风格的 mixed numeric deopt storm。

因此，`raytrace` 在当前分支里的定位和 `coroutines`、`richards` 不一样：

- 它的历史主因已经比较明确
- 当前分支还要看的是“剩余差距是否仍然受平台代码形状影响”

## 4. 静态机器码层面，为什么 Arm 会更容易被 helper-heavy JIT 形状放大

在 `raytrace` 上，最重要的静态差异不在解释器，而在 helper 调用与地址模式。

### 4.1 helper call lowering

我们已经确认：

- x86_64 的 helper 调用更容易变成紧凑的 `call`
- AArch64 更常见的是“准备目标地址 + `blr`”的形状

对于 `Vector.dot()`、`Vector.scale()`、`Point.__sub__()` 这种“小而频繁”的 helper，这种差异会被反复支付。

### 4.2 AArch64 的地址模式更不利于碎 helper

`raytrace` 的 helper 经常需要：

- 读对象字段
- 做少量算术
- 立刻再调用别的 helper

在 AArch64 上，额外的地址生成和寄存器压力更容易把这种路径拉长。  
所以即使 mixed numeric 主问题已经缓解，Arm 仍可能比 x86_64 更容易为“helper 很碎”付代价。

## 5. JIT 侧为什么这是最典型的 benchmark

`raytrace` 是当前列表里最典型的 JIT benchmark。  
它的关键不是解释器 bookkeeping，而是：

- 编译范围是否过宽
- numeric guard 是否过窄
- leaf helper 是否发生大规模 deopt

已有结论已经说明：

1. CinderX 会比 CPython JIT 编译更多函数；
2. mixed numeric leaf helper 曾出现巨大 guard failure；
3. 收窄 exact-int guard 后，`raytrace` 可以显著好转。

这说明平台比值的变化来自两层：

- 第一层：CinderX 的 JIT 策略把 benchmark 变成了“容易出错的 mixed numeric helper 风格”
- 第二层：AArch64 对这种 helper-heavy 代码形状更敏感

## 6. 为什么 Arm/AMD 比值会从基准 CPython 进一步恶化

如果观察到基准 CPython 上平台比值尚可，而切到 CinderX 后明显变差，那么 `raytrace` 的因果链最可能是：

1. CinderX 把更多 tiny numeric helper 拉进编译范围；
2. 这些 helper 的真实类型流是 mixed numeric，不是理想化纯 float；
3. 过窄 guard 让它们在运行中频繁 deopt；
4. 即使不 deopt，AArch64 对 helper call / 地址生成 / scratch register 的成本也更高；
5. 因此从 CPython 到 CinderX，Arm 的相对损失会比 AMD/x86_64 更大。

## 7. 当前分支应怎样理解这个 benchmark

当前分支已经有针对 `raytrace` 的修复痕迹，因此它不是“完全未知”的高危点。  
更准确的理解应该是：

- 历史上它确实是平台比值恶化的强根因；
- 当前分支已经缓解了最糟的 mixed numeric deopt storm；
- 如果现在仍有平台比值恶化，剩余解释更可能是：
  - helper call lowering 的架构差异
  - residual attr/object glue
  - x86_64 在 helper-heavy 数值代码上的剩余结构优势

## 8. 结论

`raytrace` 不应与 `richards/go/deltablue` 混在一起。  
它的核心不是解释器，而是：

- JIT 编译范围
- mixed numeric specialization 策略
- helper-heavy 机器码形状在 AArch64 上更吃亏

因此如果平台比值从 CPython 到 CinderX 进一步恶化，`raytrace` 的最强解释依然是：

- CinderX 把 benchmark 变成了更依赖 tiny JIT helper 质量的 workload
- 而 AArch64 在这类 workload 上的结构性损失大于 AMD/x86_64

