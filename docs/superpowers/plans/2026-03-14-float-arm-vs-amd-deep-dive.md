# `float`：为什么它的主因在 JIT 浮点专门化，但剩余平台差距仍会被对象路径放大

## 1. benchmark 本体在做什么

`bm_float` 的热点非常清晰：

- `Point.__init__()`：`sin/cos` 和字段初始化
- `Point.normalize()`：三次平方、两次加法、一次 `sqrt`、三次除法
- `Point.maximize()`：三组字段比较与写回
- `maximize(points)`：遍历点数组调用 `Point.maximize()`
- `benchmark()`：创建 `Point` 列表，再做 normalize，再做 maximize

它是一个“浮点-heavy + `__slots__` 对象字段读写”的 benchmark。

## 2. 基准 CPython 分支的关键执行链

在基准 CPython 上，平台比值由两类路径共同决定：

- 浮点运算本身
- `Point.x/y/z` 这类 slot 字段访问

因此它和 `raytrace` 不完全一样。  
`raytrace` 更偏 tiny helper mixed numeric；`float` 则是：

- 更连续的浮点路径
- 但仍被对象字段访问包围

## 3. 切到 CinderX 后，已知的关键差异

### 3.1 历史主因之一：float accumulator / entry promotion

已有 findings 已确认：

- float 累加器入口如果保留错误的混合类型形状，会导致第一轮就 deopt
- 修复后可以显著减少 deopt 并带来明显加速

### 3.2 历史主因之二：`x ** 2` 没有及时变成乘法

已有 findings 也确认：

- 对 `x ** 2` 做窄化 strength reduction，可以把热路径从 generic `BinaryOp<Power>` 变成 float 乘法

虽然当前 benchmark 源码里直接是 `x * x`，但相关结论说明当前分支已经在积极修正“浮点路径没有被充分 primitive 化”的问题。

### 3.3 仍然存在对象字段访问路径

即使浮点算术已经做了专门化，`Point.normalize()` 和 `Point.maximize()` 周围仍有大量：

- `self.x`
- `self.y`
- `self.z`
- `other.x`
- `other.y`
- `other.z`

这些都会触发 slot/attr 相关访问成本。

## 4. 静态机器码层面，为什么 Arm 的剩余损失更容易被对象路径放大

### 4.1 纯浮点算术并不是唯一成本

如果整个 benchmark 是单个长 `double` 循环，那平台比值会更多取决于浮点 codegen。  
但 `float` 并不是这样，它被很多对象字段访问包住了。

### 4.2 `LOAD_ATTR_INSTANCE_VALUE` 风格 guard 在 AArch64 上仍然更重

`Point.maximize()` 的三组比较和 `Point.normalize()` 的字段读写，都说明这个 benchmark 仍然高度依赖对象字段。  
因此我们在 `richards/comprehensions` 里确认过的 attr guard 扩张模式，依然会影响这里的 Arm/AMD 比值。

也就是说：

- 浮点专门化修复的是“最糟的 JIT 退化”
- 剩余的架构差距则更多来自对象字段路径

## 5. JIT 侧该怎样理解

`float` 是当前列表里最像“理想 JIT 浮点 benchmark”的之一。  
当前分支已有的两项修复说明：

- CinderX 之前确实在热 float 路径上丢失了该有的 specialization
- 当前分支已经补了一部分

所以它和 `raytrace` 类似，也不能简单当作“未知问题”。  
更准确的说法是：

- 历史上它有明确的 JIT 根因；
- 当前分支已修复其中两项关键问题；
- 如果仍有平台比值恶化，剩余解释更多落在 attr/object glue 上。

## 6. 为什么平台比值会从 CPython 切到 CinderX 后继续恶化

最合理的解释链是：

1. `float` 既有浮点热路径，也有大量对象字段访问；
2. CinderX 在历史上对 float JIT specialization 不够理想，导致 Arm/AMD 比值可能明显恶化；
3. 当前分支已经修掉一部分最明显问题；
4. 但即使浮点算术路径改善，AArch64 上对象字段 guard / 地址生成仍比 x86_64 更吃亏；
5. 因此从 CPython 到 CinderX 后，平台比值仍可能比基准分支更差，只是主因已从“严重 JIT 误专门化”转向“剩余对象路径成本”。

## 7. 结论

`float` 应该放在 JIT 数值组，但要和 `raytrace` 区分开：

- `raytrace` 更偏 tiny mixed-numeric leaf helper
- `float` 更偏连续浮点路径 + slot 字段访问

所以它的解释应该分两层：

1. 历史大劣化来自 float JIT specialization 不足；
2. 当前剩余平台差距则更多由对象字段访问在 AArch64 上的较高固定成本解释。

