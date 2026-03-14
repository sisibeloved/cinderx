# `richards_super`：为什么 CinderX 更容易把 Arm/AMD 比值继续往下拉

## 1. benchmark 本体在做什么

`bm_richards_super` 本质上还是 Richards 调度器，只是在任务方法里额外引入了 `super().fn(pkt, r)`。  
从 benchmark 源码和字节码看，热点仍然集中在：

- `schedule()`
- `Task.runTask()`
- `Task.qpkt()`
- `Task.addPacket()`
- `HandlerTask.fn()`
- `WorkTask.fn()`
- `DeviceTask.fn()`
- `IdleTask.fn()`

和 `richards` 一样，它不是数值 benchmark，而是“很多很短的小方法 + 大量 `LOAD_ATTR` / `STORE_ATTR` / `LOAD_METHOD` / `CALL_METHOD` + 链表/任务状态切换”。

和 `richards` 的关键区别是：`HandlerTask.fn()`、`WorkTask.fn()`、`DeviceTask.fn()`、`IdleTask.fn()` 都在入口先执行一次 `super().fn(pkt, r)`，因此每次任务调度都会多一层 `super()` 解析和基类方法调用。

## 2. CPython 基准分支的关键执行链

在基准 CPython 上，这个 benchmark 的关键成本仍然是：

- 解释器调度小方法
- 对象字段读写
- 方法调用和返回
- 调度器循环中的条件分支

也就是说，Arm/AMD 比值主要由“小 helper 调用成本 + 属性访问成本 + 分支密度”决定。

## 3. 切到 CinderX 后，代码路径发生了什么变化

相对基准 CPython，CinderX 在这类 benchmark 上叠加了两层额外工作：

### 3.1 解释器热路径额外 bookkeeping

已有解释器差异包括：

- `adaptive_enabled` 额外状态传播
- `CI_UPDATE_CALL_COUNT`
- `CI_SET_ADAPTIVE_INTERPRETER_ENABLED_STATE`
- `IS_PEP523_HOOKED`

这类逻辑在“大函数/重计算”里可能被摊薄，但在 `richards_super` 这种小 helper 洪流里非常敏感，因为每个任务方法本身就很短。

### 3.2 `super()` 让方法入口更像“helper 里的 helper”

`super().fn(pkt, r)` 会把原本已经很短的方法再拆成：

1. 解析 `super`
2. 找到基类 `fn`
3. 执行基类 `Task.fn`
4. 回到子类继续做状态机逻辑

这让 benchmark 更依赖“方法入口 bookkeeping 是否便宜”，而这恰好是 CinderX 相对 CPython 改动最多的一层。

## 4. 静态机器码层面，为什么 Arm 更容易吃亏

这里最关键的不是“`super()` 本身有某个 x86 特化”，而是它把 benchmark 更强地推向了我们已经在 `richards` 里确认过的那类代码形状：

- 很短的方法
- 高频方法入口
- 高频属性 guard
- 高频条件分支

对这类路径，我们已经有两类交叉编译证据：

### 4.1 tiny-helper bookkeeping 探针

在 `richards` 的 reduced probe 里，只是往一个很短的 helper 入口加上类似：

- `if (adaptive_enabled) *call_count += 1`

这样的 CinderX 风格 bookkeeping，AArch64 就会比 x86_64 更明显地扩成：

- 更多显式分支
- 更多 load/store
- 更长的依赖链

也就是说，CinderX 新增的“方法入口成本”在 Arm 上放大得更厉害。

### 4.2 `LOAD_ATTR_INSTANCE_VALUE` 风格 guard 探针

在属性访问探针里，CinderX 风格 guard 相比朴素 type-version guard 还会再做：

- `tp_basicsize` 读取
- 额外地址生成
- `valid` 字节检查

x86_64 这类地址生成更紧凑；AArch64 通常需要更多显式地址计算和加载。

`richards_super` 因为每个任务方法都更短，`super()` 又增加了一层调用入口，所以这些固定成本更难被摊薄。

## 5. JIT 侧为什么也不一定能把差距补回来

`richards_super` 的问题不在大块算术，而在：

- 小方法太多
- 对象状态切换太多
- attr/method traffic 太多
- `super()` 让调用形状更碎

这类代码即使被 JIT 编译，收益也更依赖：

- 属性 guard 是否轻
- 调用/返回 glue 是否轻
- frame / thread state 访问是否轻

而这些点在 AArch64 上都比 x86_64 更容易变重。  
因此 CinderX 不是“在两个平台上都等比例变慢”，而是更容易出现：

- x86_64 还能维持较紧凑的 helper/guard 形状
- AArch64 的新增 bookkeeping 和 attr/call glue 更快溢出成明显成本

## 6. 为什么 Arm/AMD 比值会从基准 CPython 进一步恶化

如果在基准 CPython 上：

- Arm/AMD 比值约为 `0.8`

切到 CinderX 后掉到更低，例如：

- `0.6`

那么 `richards_super` 最合理的解释链是：

1. benchmark 仍然主要由 tiny helper、属性访问和调度组成；
2. `super().fn(...)` 让每次任务方法入口都比 `richards` 更碎、更依赖调用 glue；
3. CinderX 在这些入口叠加了额外 interpreter bookkeeping；
4. CinderX 的 attr/call guard 形状比基准 CPython 更重；
5. 这些新增固定成本在 x86_64 上虽然也存在，但在 AArch64 上展开得更长；
6. 因此从 CPython 切到 CinderX 后，Arm 的相对损失会大于 AMD/x86_64。

## 7. 结论

`richards_super` 应该和 `richards` 放在同一个高优先级簇里，但根因比 `richards` 更集中：

- `richards` 更偏“调度 + attr + tiny helper”
- `richards_super` 则是在此基础上再叠加“`super()` 把方法入口进一步碎片化”

所以它比 `richards` 更像一个“放大 CinderX 方法入口固定成本”的 benchmark。  
如果平台比值在 CinderX 上明显比基准 CPython 更差，最优先怀疑的仍然是：

- 解释器 bookkeeping
- 属性 guard 变重
- `super()` 带来的额外方法分派层次

