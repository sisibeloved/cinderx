# `nqueens`：为什么这个 benchmark 更像“生成器/容器/控制流”问题，而不是纯整数算术问题

## 1. benchmark 本体在做什么

`bm_nqueens` 不是位运算或数值 DP，而是：

- 用纯 Python 实现 `permutations()`
- 在 `n_queens()` 里枚举所有排列
- 用两个 `set(...)` 检查对角线冲突
- 通过 generator `yield` 产生解

字节码特征很明确：

- `permutations()` 本身就是 generator
- 内部反复做 list slice、tuple 构造、索引交换、`yield tuple(...)`
- `n_queens()` 再包一层 generator
- 里面还有两个生成器表达式去构造 `set`

所以它的真实形状是：

- generator 恢复/挂起
- tuple/list/set 构造
- 小整数控制流

而不是“一个长整数循环”。

## 2. 基准 CPython 分支的关键执行链

在基准 CPython 上，热点主要是：

- `permutations()` 的 generator 状态推进
- `tuple(pool[i] for i in indices[:r])`
- `set(vec[i] + i for i in cols)`
- `set(vec[i] - i for i in cols)`
- 大量索引、切片、交换和 `yield`

这说明平台比值更多受下面几类成本影响：

- generator frame/resume
- 容器构造
- 小整数控制流
- 分支与引用计数

## 3. 切到 CinderX 后，哪些差异最关键

### 3.1 generator/runtime 路径比基准 CPython 更重

`nqueens` 不是 coroutine，但它高度依赖 generator。  
而 CinderX 在 generator 相关路径上引入了自己的 runtime / JIT 体系，这意味着：

- resume/suspend glue
- frame metadata
- deopt / yield-from 相关 runtime

都可能和基准 CPython 不同。

### 3.2 解释器 bookkeeping 仍然会打在很多小 helper 上

`permutations()` 和 `n_queens()` 都有很密的循环，但循环体非常碎。  
因此 `adaptive_enabled` / call-count 之类额外成本仍然可能伤到这个 benchmark。

### 3.3 容器构造不会自动变成“便宜的数值循环”

这个 benchmark 中真正热的是：

- tuple/set/list 结构操作
- generator 切换

不是那种 JIT 很容易全程 primitive 化的浮点/整数算术。

## 4. 静态机器码层面，为什么 Arm 更容易在这里吃亏

### 4.1 generator resume 路径在 AArch64 上更重

已有 AArch64 backend 分析已经说明：

- generator/coroutine resume 需要较多 frame metadata 读写
- AArch64 更依赖 `ptr_resolve()`、显式 `ldr/str`
- x86_64 往往能用更短的 base+disp 访问

`nqueens` 正好会非常高频地命中 generator 恢复与挂起。

### 4.2 引用计数和短生命周期对象很多

这个 benchmark 会产生大量：

- tuple
- set
- generator frame
- 切片对象 / 中间列表状态

这些对象的生命周期很短。  
短生命周期对象越多，AArch64 上额外的 load/store 和 frame glue 就越容易被放大。

## 5. JIT 侧该如何理解

`nqueens` 不是最理想的 JIT 数值 benchmark。  
它更可能出现：

- JIT 只能覆盖部分循环/辅助函数
- 真正主导时间的仍然是 generator 和容器路径

所以它更像：

- `generators` + `comprehensions` 的混合体

而不像：

- `float`
- `raytrace`

这意味着平台比值的变化更可能来自：

- generator runtime 在 AArch64 上更重
- 容器/引用计数固定成本更重

## 6. 为什么平台比值会从 CPython 切到 CinderX 后继续恶化

最合理的解释链是：

1. `nqueens` 的热路径主要是 generator + 容器 + 小整数控制流；
2. CinderX 的 generator/runtime 路径相对基准 CPython 更复杂；
3. AArch64 的 generator resume/frame metadata/store 形状更重；
4. benchmark 又会高频产生短生命周期对象，固定成本更难摊薄；
5. 因此从基准 CPython 切到 CinderX 后，Arm 的相对损失会大于 AMD/x86_64。

## 7. 结论

`nqueens` 不应该先按“整数 benchmark”去看。  
更准确的归类是：

- generator-heavy
- 容器构造-heavy
- 控制流-heavy

所以如果平台比值在 CinderX 上明显变差，最优先怀疑的不是整数 ALU，而是：

- generator runtime / frame glue
- 容器和对象生命周期成本
- AArch64 对这类碎路径的结构性放大

