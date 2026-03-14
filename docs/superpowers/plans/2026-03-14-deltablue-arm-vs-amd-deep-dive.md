# `deltablue`：为什么 CinderX 的约束对象图更容易拉大 Arm 与 AMD 的差距

## 1. benchmark 本体在做什么

`bm_deltablue` 是典型的约束传播 benchmark。  
从源码和字节码看，热点主要在：

- `Planner.incremental_add()`
- `Planner.add_propagate()`
- `Plan.execute()`
- `Constraint.satisfy()`
- `Variable.add_constraint()`
- `ScaleConstraint.execute()`
- `EqualityConstraint.execute()`

它的形状和 `richards` 很像：

- 很多小对象
- 很多很短的方法
- 大量字段读写
- `append/pop` 这样的短容器操作
- 很少有足够长的纯数值内核去摊薄调度成本

## 2. CPython 基准分支的关键执行链

在基准 CPython 上，这个 benchmark 的主要成本是：

- 反复执行小方法
- 读写 `Variable` / `Constraint` / `Planner` 对象字段
- 在 `OrderedCollection(list)` 上做 `append` / `pop`
- 在约束传播循环里来回跳转

`Planner.add_propagate()` 是个很典型的热点：

- 建一个 `todo`
- 循环 `pop(0)`
- `output().mark` 检查
- `recalculate()`
- `add_constraints_consuming_to(...)`

每一步都不大，但串起来非常密。

## 3. 切到 CinderX 后，最相关的代码差异是什么

### 3.1 解释器 bookkeeping 会直接打在 benchmark 的主循环上

`deltablue` 和 `richards` 一样，属于 tiny-helper-heavy。  
所以：

- `CI_UPDATE_CALL_COUNT`
- `adaptive_enabled`
- `IS_PEP523_HOOKED`

这类逻辑很难被摊薄。

### 3.2 属性访问路径比基准 CPython 更重

`Constraint.satisfy()`、`ScaleConstraint.execute()`、`EqualityConstraint.execute()` 都是“读几个字段，算一点逻辑，再写回另一个字段”。

这意味着 CinderX 的 `LOAD_ATTR_INSTANCE_VALUE` 风格 guard 也会大量参与。  
对这种 benchmark 来说，attr guard 的固定成本比数值 op 本身更重要。

### 3.3 JIT 很难把它变成 `raytrace` 式 primitive-heavy 热循环

即使 `ScaleConstraint.execute()` 里有：

- `value * scale + offset`
- `(... - offset) / scale`

这类算术，它依然被大量对象字段访问包围。  
也就是说，JIT 的收益上限主要受对象模型和 attr/call glue 限制，而不是受单个乘加序列限制。

## 4. 静态机器码层面，为什么 Arm 更容易输得更多

### 4.1 attr guard 扩张模式对 `deltablue` 特别不友好

`ScaleConstraint.execute()` 和 `EqualityConstraint.execute()` 的算术部分都很短，周围却有很多：

- `self.v1.value`
- `self.scale.value`
- `self.offset.value`
- `self.v2.value`

这种“字段访问包裹少量算术”的形状，使得 attr guard 的成本主导得更明显。  
而我们已经确认，CinderX 风格 attr guard 在 AArch64 上会展开成更重的地址生成与加载链。

### 4.2 小方法 bookkeeping 的 AArch64 固定成本更高

像 `Variable.add_constraint()` 这种方法本体几乎就是：

- `self.constraints.append(constraint)`

再加上 `Planner.incremental_add()` 这种几十条字节码以内的调度函数，CinderX 的额外 bookkeeping 会比在 x86_64 上更明显地伤到 AArch64。

## 5. JIT 侧应该怎样理解

`deltablue` 即使在 JIT 下，也更像：

- “对象图传播”

而不是：

- “浮点内核”

所以它更可能出现这种情况：

- x86_64 还能从较紧凑的 helper/guard 里拿到一些收益
- AArch64 则因为 attr/call/frame glue 更重，收益被吃掉甚至倒挂

这和 `raytrace`/`float` 的根因簇不同。

## 6. 为什么 Arm/AMD 比值会从 CPython 到 CinderX 继续变差

最合理的因果链是：

1. `deltablue` 的热点本来就是大量小方法和对象字段访问；
2. CinderX 正是在这些点上引入了更多固定成本；
3. 这些固定成本在 AArch64 上更难压缩成紧凑机器码；
4. x86_64 对同样的变动相对更不敏感；
5. 因此从基准 CPython 切到 CinderX 后，Arm 的相对损失更大，平台比值继续下滑。

## 7. 结论

`deltablue` 应与 `richards`、`richards_super`、`go` 归为同一个解释器/对象模型簇。  
它的第一嫌疑不是某个数值 opcode，而是：

- 小方法入口成本
- attr guard 成本
- 对象图传播里的分支与字段流量

因此如果要解释平台比值为什么从 CPython 到 CinderX 进一步恶化，`deltablue` 的最强根因仍然是：

- CinderX 在对象模型热路径上新增的固定成本
- 这些成本在 Arm 上的放大幅度大于 AMD/x86_64

