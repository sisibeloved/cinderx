# Arm vs AMD 平台比值恶化的最终综合

## 1. 先看总图：不是一个原因，而是四个根因簇

把这批 benchmark 全部串起来后，可以把“为什么从基准 CPython 切到 CinderX 后，Arm/AMD 比值会进一步变差”总结成四个根因簇。

### 簇 A：解释器 bookkeeping / 小方法入口 / attr guard

代表 benchmark：

- `richards`
- `richards_super`
- `go`
- `deltablue`

共同特征：

- 很多很短的方法
- 大量对象字段读写
- 很少有长数值循环摊薄固定成本

对这些 benchmark，最关键的不是单个 opcode，而是：

- `CI_UPDATE_CALL_COUNT`
- `adaptive_enabled`
- `IS_PEP523_HOOKED`
- `LOAD_ATTR_INSTANCE_VALUE` 风格 guard

这组差异在 AArch64 上更容易展开成更长的分支、地址生成和 load/store 链，因此比值更容易从例如 `0.8` 继续掉到 `0.6` 一类的水平。

### 簇 B：coroutine / generator runtime

代表 benchmark：

- `coroutines`
- `generators`
- `nqueens`

共同特征：

- 高频 resume/suspend
- generator/coroutine frame 管理
- `yield` / `yield from` / awaitable 路径

对这些 benchmark，关键不是普通算术，而是：

- `JitCoro_GetAwaitableIter`
- `Ci_PyEval_GetAwaitable`
- `JitGen_yf`
- generator attr lowering
- decref / batch decref
- AArch64 的 frame metadata/store 形状

这类路径在 AArch64 上比 x86_64 更重，因此从 CPython 切到 CinderX 时，Arm 的相对损失更容易更大。

### 簇 C：JIT 数值专门化 / helper-heavy 机器码形状

代表 benchmark：

- `raytrace`
- `float`

共同特征：

- 数值路径热
- 但仍然由很多小 helper 或对象字段访问包围

`raytrace` 的历史主因最明确：

- overcompile
- mixed numeric leaf helper
- exact guard 过窄
- deopt storm

`float` 的历史主因也很明确：

- float accumulator / entry promotion
- float fast path specialization 不足

这类 benchmark 在当前分支里已经有部分修复，因此现在更准确的说法是：

- 历史上它们确实强烈拉低过平台比值；
- 当前分支已经缓解一部分；
- 剩余平台差距则更多来自 helper call lowering、attr/object glue 在 AArch64 上更重。

### 簇 D：启动注入成本

代表 benchmark：

- `python_startup`

它和其他 benchmark 根本不是一类问题。  
主因不是热循环，而是：

- `sitecustomize`
- `import cinderx`
- `import cinderx.jit`
- `jit.enable()`
- Arm 默认功能开关更多

所以它几乎可以直接判为“CinderX 启动路径改重了”。

## 2. 每个 benchmark 的最终定位

### `coroutines`

主因：

- 自定义 awaitable/coroutine helper 链
- AArch64 上更重的 coroutine runtime 和 frame glue

### `comprehensions`

主因：

- checked container helper 路径
- attr guard 更重
- AArch64 上 helper/guard 展开更明显

### `richards`

主因：

- tiny helper bookkeeping
- 高频属性访问
- AArch64 对固定入口成本更敏感

### `richards_super`

主因：

- `richards` 的全部问题
- 再加 `super().fn(...)` 让方法入口进一步碎片化

### `go`

主因：

- 对象图遍历
- 高频 attr/method traffic
- AArch64 上 attr guard 与短 helper 成本更难摊薄

### `deltablue`

主因：

- 约束对象图传播
- 小方法调度
- attr/object glue 在 AArch64 上更重

### `raytrace`

主因：

- 历史上是 overcompile + mixed numeric leaf helper + deopt storm
- 当前分支已有缓解，剩余差距更多看 helper-heavy 机器码形状

### `nqueens`

主因：

- generator + 容器构造 + 小整数控制流
- generator runtime / frame glue 在 AArch64 上更重

### `float`

主因：

- 历史上是 JIT float specialization 不足
- 当前分支已修部分根因
- 剩余差距更多来自 slot/attr 路径

### `generators`

主因：

- generator attr lowering
- `yield from` / resume
- 剩余 decref 压力

### `python_startup`

主因：

- `sitecustomize` 自动注入
- `import cinderx(.jit)`
- Arm 默认功能路径更重

## 3. 最终排序：谁最像“把平台比值从 0.8 拉到 0.6”的强候选

如果按“对平台比值恶化的解释力”排序，当前最合理的顺序是：

1. `coroutines`
2. `richards`
3. `richards_super`
4. `go`
5. `deltablue`
6. `comprehensions`
7. `python_startup`
8. `generators`
9. `nqueens`
10. `raytrace`
11. `float`

这里把 `raytrace` 和 `float` 放后，不是因为它们不重要，而是因为当前分支已经有较明确的专项修复痕迹；而前面的 benchmark 仍然更像“当前分支上最可能继续伤到 Arm/AMD 比值”的未完全收敛根因。

## 4. 一句话结论

这批 benchmark 的共同结论不是“Arm 就是比 AMD 慢”，而是：

- CinderX 相比基准 CPython，引入了额外的解释器/JIT/runtime 固定成本；
- 这些新增成本恰好集中在 AArch64 更吃亏的代码形状上：
  - 短 helper
  - 重 attr guard
  - generator/coroutine frame glue
  - helper-heavy JIT call shape
  - startup import/init

因此从基准 CPython 切到 CinderX 后，Arm 的相对损失会比 AMD/x86_64 更大，平台比值就会继续恶化。

