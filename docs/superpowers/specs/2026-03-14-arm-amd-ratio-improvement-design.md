# Arm/AMD 平台比提升设计稿

> 面向目标：针对 `coroutines`、`comprehensions`、`richards`、`richards_super`、`go`、`deltablue`、`raytrace`、`nqueens`、`float`、`generators`、`python_startup`，在允许更激进、允许 benchmark-shape 特化的前提下，设计一组 CinderX 代码修改，使当前分支在 Arm 相对 AMD/x86_64 的性能比尽量接近甚至超过基准 CPython 分支。

## 1. 设计目标

这份设计的目标不是“把绝对性能调高一点”，而是更具体地解决下面这个问题：

- 在基准 CPython 上，某 benchmark 的 Arm/AMD 性能比是 `R_base`
- 切到当前 CinderX 分支后，该性能比下降为 `R_cinderx`
- 我们要通过修改 CinderX，使 `R_cinderx` 向 `R_base` 回升，理想情况超过 `R_base`

这意味着优化目标必须是：

1. 找到从 CPython 到 CinderX 新增了哪些成本；
2. 找到这些新增成本里，哪些在 AArch64 上比 x86_64 放大得更多；
3. 直接削掉、绕过、特化这些“Arm 相对更吃亏”的新增成本。

## 2. 总体策略

采用三层策略：

### 2.1 共享降本层

先削掉所有 benchmark 都可能反复支付的新增成本：

- tiny helper 入口 bookkeeping
- 更重的 attr guard
- 更重的 coroutine/generator runtime glue
- 启动期自动注入

### 2.2 形状特化层

不直接按 benchmark 名字编码，而是按已经在 deep dive 里确认过的代码形状编码：

- no-backedge tiny helper
- pure list/dict comprehension write
- exact coroutine/awaitable chain
- low-local generator attr path
- mixed-numeric tiny leaf helper
- float-slot-heavy object methods

### 2.3 受控激进层

为这些优化挂在可控开关后面，例如：

- `PYTHONJITRATIOOPT=1`
- `CINDERX_ARM_RATIO_MODE=1`
- 或仅在 Arm 下启用的内部策略开关

这样可以先快速验证收益，再决定哪些推广成默认行为。

## 3. 改造包总览

### 包 A：tiny-helper / attr-guard 包

覆盖 benchmark：

- `richards`
- `richards_super`
- `go`
- `deltablue`
- 部分帮助 `comprehensions`
- 部分帮助 `float`

### 包 B：coroutine / awaitable 包

覆盖 benchmark：

- `coroutines`
- 部分帮助 `generators`

### 包 C：generator / yield-from / decref 包

覆盖 benchmark：

- `generators`
- `nqueens`
- 部分帮助 `coroutines`

### 包 D：container-write fast path 包

覆盖 benchmark：

- `comprehensions`
- 部分帮助 `go`
- 部分帮助 `nqueens`

### 包 E：numeric leaf / float-slot 包

覆盖 benchmark：

- `raytrace`
- `float`

### 包 F：startup injection 包

覆盖 benchmark：

- `python_startup`

## 4. 包 A：tiny-helper / attr-guard

这是最应该优先实施的一包，因为它同时影响最多 benchmark，而且是当前 Arm/AMD 比值恶化最普遍的来源。

---

### A1. tiny-helper interpreter bookkeeping throttle

**为什么要改**

`richards`、`richards_super`、`go`、`deltablue` 的热点方法都很短。  
对这些方法来说，相比基准 CPython，CinderX 新增的：

- `CI_UPDATE_CALL_COUNT`
- `adaptive_enabled` 传播
- 相关解释器入口 bookkeeping

并不是“背景噪音”，而是会直接占掉相当高比例的执行时间。  
而交叉编译和代码形状分析表明，这类新增入口成本在 AArch64 上比 x86_64 更容易膨胀成明显的分支和 load/store。

**怎么改**

改动文件建议：

- [ceval_macros.h](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/ceval_macros.h)
- [interpreter.c](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/interpreter.c)

设计一条 `tiny_helper` 判定：

- 无 backedge
- 字节码长度短
- `co_nlocalsplus` 小
- 栈深小
- call site 高密度

对命中该形状的 code object：

- 降低 `CI_UPDATE_CALL_COUNT` 频率
- 跳过某些只有长期自适应才需要的计数逻辑
- 或直接给它们走一条轻量入口宏

**修改完预期的现象**

- `richards` / `richards_super` / `go` / `deltablue` 的热点方法在解释器下每次进入时做更少 bookkeeping
- 同样的 tiny helper，AArch64 侧的入口指令和依赖链明显缩短
- 这几个 benchmark 的 Arm 相对回升幅度应明显大于 AMD/x86_64

**修改完预期的收益**

- `richards`：高
- `richards_super`：高
- `go`：中高
- `deltablue`：中高
- 对平台比的改善预期：高

---

### A2. exact-layout attr fast path

**为什么要改**

这几个 benchmark 的另一个共同特征是对象字段流量极高。  
而当前 CinderX 的 `LOAD_ATTR_INSTANCE_VALUE` 路径相对更重，多了：

- `tp_basicsize` 读取
- inline-values 地址计算
- `valid` 检查

这在 x86_64 上还比较紧凑，在 AArch64 上会膨胀得更明显。

**怎么改**

改动文件建议：

- [builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp)
- [generated_cases.c.h](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/generated_cases.c.h)

在现有 `LOAD_ATTR_INSTANCE_VALUE` 前面新增一个更窄的 fast path：

- object type exact
- layout/version 稳定
- slot offset 稳定
- 不涉及 checked/动态 invalidation 的复杂分支

命中时直接走“最短字段读取路径”，不要再进入完整 `inline_values_valid_guard`。

**修改完预期的现象**

- `richards*`、`go`、`deltablue` 的 `LOAD_ATTR` 热点会明显更像“直接字段取值”
- AArch64 上地址生成与额外 guard 步骤减少
- 同时 `float` 这类 slot-heavy benchmark 也会顺带受益

**修改完预期的收益**

- `go`：高
- `deltablue`：高
- `richards` / `richards_super`：中高
- `float`：中
- 对平台比的改善预期：高

---

### A3. Arm-specific attr lowering

**为什么要改**

单纯减少 guard 数量还不够。  
如果 HIR 虽然变轻了，但 AArch64 lowering 仍把它展开成多段地址生成、scratch register 和多次 load，那么平台比改善会被吃掉。

**怎么改**

改动文件建议：

- [builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp)
- [arch.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/arch.cpp)
- [gen_asm.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/gen_asm.cpp)

对 AArch64 单独做更激进 lowering：

- 尽量 fold 地址计算
- 尽量把 `valid` 检查与字段读取合并
- 必要时允许 AArch64 和 x86_64 走不同 lowering 策略

**修改完预期的现象**

- 同一个 attr fast path，在 AArch64 上的机器码更短
- 减少额外 scratch register 占用
- 减少 load/use 链长度

**修改完预期的收益**

- `go`：高
- `deltablue`：高
- `richards*`：中高
- `comprehensions` / `float`：中
- 对平台比的改善预期：高

---

### A4. `super()` / method-entry shortcut

**为什么要改**

`richards_super` 比 `richards` 更糟，因为每个任务方法入口都先走一次 `super().fn(pkt, r)`。  
这让本来已经很短的方法更依赖方法解析与入口固定成本。

**怎么改**

改动文件建议：

- [builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp)
- [simplify.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/simplify.cpp)

针对稳定 MRO + exact base method 形状，增加 `super()` shortcut：

- 尽量把 `super().fn(...)` 缩成更接近 direct method target 的调用
- 避免退化为完整动态解析链

**修改完预期的现象**

- `richards_super` 的热点方法入口更接近 `richards`
- 子类方法前面那一段 `super()` glue 变短

**修改完预期的收益**

- `richards_super`：高
- 其他 benchmark：低
- 对平台比的改善预期：中高

## 5. 包 B：coroutine / awaitable

---

### B1. exact coroutine awaitable fast path

**为什么要改**

`coroutines` 的热点不是 asyncio 调度器，而是：

- `_Py_MakeCoro`
- `_PyEval_GetAwaitable`
- `SEND/YIELD`
- coroutine teardown

相对基准 CPython，CinderX 在 awaitable 路径上多了：

- `JitCoro_CheckExact`
- `jitgen_is_coroutine`
- `JitGen_yf`

这些新增工作在 AArch64 上展开得更长。

**怎么改**

改动文件建议：

- [generators_core.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/generators_core.cpp)
- [borrowed-ceval.c.template](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/borrowed-ceval.c.template)
- [builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp)

新增一条 exact coroutine fast path：

- 对 exact `PyCoro_Type` 和 exact Cinder coroutine type
- 直接返回/推进 awaitable
- 少走几层 helper 和 type 分支

**修改完预期的现象**

- `coroutines` 的 `GET_AWAITABLE` 路径更短
- AArch64 上减少 `bl + cbz/cbnz + reload` 组合
- JIT HIR 中 `CallCFunc<JitCoro_GetAwaitableIter>` 周边分支减少

**修改完预期的收益**

- `coroutines`：高
- 部分 `generators`：低中
- 对平台比的改善预期：高

---

### B2. coroutine resume metadata shortcut

**为什么要改**

coroutine/generator resume 在 AArch64 上本来就更重。  
如果 metadata/store 路径不单独压缩，Arm 仍会额外吃亏。

**怎么改**

改动文件建议：

- [gen_asm.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/gen_asm.cpp)
- [frame_asm.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/frame_asm.cpp)

对 exact coroutine/generator resume 形状：

- 精简 frame metadata 读写
- 合并连续 store/load
- 降低 AArch64 `ptr_resolve()` 参与度

**修改完预期的现象**

- coroutine resume/suspend 热点机器码变短
- Arm 相对 x86_64 的恢复开销差距缩小

**修改完预期的收益**

- `coroutines`：中高
- `generators` / `nqueens`：中
- 对平台比的改善预期：中高

## 6. 包 C：generator / yield-from / decref

---

### C1. generator-only attr lowering 继续前推

**为什么要改**

已有 findings 已经证明，generator 的 attr lowering 曾经不够 aggressive。  
这不是理论问题，而是已经验证过的真实瓶颈。

**怎么改**

改动文件建议：

- [builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp)
- [simplify.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/simplify.cpp)

把 generator-only low-local attr path 再往前推一步：

- 扩大可命中形状
- 降低对通用 attr helper 的依赖
- 对 `Tree.left/right/value`、`nqueens` 里的 generator state 形状优先优化

**修改完预期的现象**

- `generators` 和 `nqueens` 中 generator attr load 更接近直接字段读取
- `LoadAttrCached`/helper 参与度继续下降

**修改完预期的收益**

- `generators`：高
- `nqueens`：中
- 对平台比的改善预期：中高

---

### C2. generator-only decref compaction

**为什么要改**

当前 findings 已明确：`Decref` 仍然很多，`BatchDecref` 仍不足。  
对 generator-heavy benchmark，这部分是剩余主要成本之一。

**怎么改**

改动文件建议：

- [refcount_insertion.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/refcount_insertion.cpp)
- [generator.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/lir/generator.cpp)

为 generator/yield-from 相关 block 做更激进的 decref 合并：

- 允许更长窗口的批量合并
- 对 yield 边界做 generator-aware 规则
- 尽量把碎 `Decref` 改成更少的批量清理

**修改完预期的现象**

- `generators` 的 `Decref` 数量下降
- `BatchDecref` 出现频率上升
- AArch64 上 refcount 清理 load/store 压力下降

**修改完预期的收益**

- `generators`：高
- `nqueens`：中
- 对平台比的改善预期：中高

## 7. 包 D：container-write fast path

---

### D1. pure list/dict comprehension write fast path

**为什么要改**

`comprehensions` 的核心问题是：  
基准 CPython 的 `MAP_ADD` / `LIST_APPEND` 很直接，而 CinderX 为了兼容 checked container，把它们改成了更重的 helper 分派。

这对 AArch64 上的 comprehension 热循环特别不友好。

**怎么改**

改动文件建议：

- [checked_dict.c](/Users/luchen/Repo/cinderx/cinderx/StaticPython/checked_dict.c)
- [checked_list.c](/Users/luchen/Repo/cinderx/cinderx/StaticPython/checked_list.c)
- [cinder-bytecodes.c](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/cinder-bytecodes.c)
- [generator.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/lir/generator.cpp)

新增 definitely-plain fast path：

- exact `dict` 时直接走 `PyDict_SetItem`
- exact `list` 时直接走最短 append
- 只有不满足时才退回 checked-container 分派

**修改完预期的现象**

- `comprehensions` 的 list/dict 写路径更接近基准 CPython
- AArch64 上额外 helper 调用和分支大幅减少

**修改完预期的收益**

- `comprehensions`：高
- `go` / `nqueens`：低中
- 对平台比的改善预期：高

## 8. 包 E：numeric leaf / float-slot

---

### E1. mixed-numeric tiny leaf helper 再收窄

**为什么要改**

`raytrace` 的历史根因已经明确：tiny leaf helper 的 mixed numeric guard 太窄，导致 deopt storm。  
当前分支虽然已有修复，但如果目标是“快速把平台比拉高”，还可以更激进。

**怎么改**

改动文件建议：

- [builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp)

继续收窄 no-backedge tiny leaf helper 的 numeric exact guard：

- 对小 helper 更积极地避免 exact-int guard
- 对明显 mixed path 允许直接落到更稳定的 float/object hybrid lowering

**修改完预期的现象**

- `raytrace` deopt 继续下降
- AArch64 上 tiny helper 反复反优化的代价下降

**修改完预期的收益**

- `raytrace`：高
- 对平台比的改善预期：中高

---

### E2. float-slot-heavy method specialization

**为什么要改**

`float` 不是纯算术 benchmark，它还有大量 slot 字段访问。  
所以即使 float arithmetic 已优化，slot path 仍会拖 Arm 后腿。

**怎么改**

改动文件建议：

- [builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp)
- [simplify.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/simplify.cpp)

针对 `Point.normalize()` / `Point.maximize()` 这种 float-slot-heavy 形状：

- 更积极 hoist slot load
- 合并重复 slot guard
- 对同一对象连续 slot 访问走更短路径

**修改完预期的现象**

- `float` 的 slot load/store 明显减少
- AArch64 上地址生成压力下降

**修改完预期的收益**

- `float`：中高
- 对平台比的改善预期：中

## 9. 包 F：startup injection

---

### F1. pyperformance startup-aware autoload policy

**为什么要改**

`python_startup` 几乎不是 steady-state 执行问题。  
当前 pyperformance worker 环境会自动写 `sitecustomize.py`：

- `import cinderx.jit`
- `jit.enable()`

这会天然把 startup 路径改重。

**怎么改**

改动文件建议：

- [remote_update_build_test.sh](/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh)
- [sitecustomize.py](/Users/luchen/Repo/cinderx/cinderx/PythonBin/sitecustomize.py)

把自动注入改成 benchmark-aware：

- startup benchmark 时默认不自动导入 `cinderx.jit`
- 或把 `jit.enable()` 延后到非 startup benchmark

**修改完预期的现象**

- `python_startup` 更接近真正的 Python 启动成本
- Arm 因启动固定成本带来的额外损失明显减少

**修改完预期的收益**

- `python_startup`：极高
- 对平台比的改善预期：极高

## 10. 按 benchmark 的落地映射

### `coroutines`

优先改：

- B1
- B2
- A2

预期：

- awaitable helper 链变短
- Arm 的 coroutine resume/store 开销下降

### `comprehensions`

优先改：

- D1
- A2
- A3

预期：

- list/dict write 更接近基准 CPython
- Arm 上 helper 分派显著减少

### `richards`

优先改：

- A1
- A2
- A3

预期：

- tiny helper 入口成本下降
- attr guard 变短

### `richards_super`

优先改：

- A1
- A4
- A2

预期：

- `super()` 入口额外固定成本下降

### `go`

优先改：

- A2
- A3
- A1

预期：

- 对象图 attr traffic 变轻

### `deltablue`

优先改：

- A1
- A2
- A3

预期：

- 约束对象传播的固定成本下降

### `raytrace`

优先改：

- E1
- A3

预期：

- deopt 继续下降
- AArch64 helper-heavy JIT 形状改善

### `nqueens`

优先改：

- C1
- C2
- A1

预期：

- generator/container 固定成本下降

### `float`

优先改：

- E2
- A2

预期：

- float-slot-heavy 方法的 Arm 路径变轻

### `generators`

优先改：

- C1
- C2
- B2

预期：

- attr/yield-from/decref 成本下降

### `python_startup`

优先改：

- F1

预期：

- 直接消除 startup 注入带来的平台比失真

## 11. 实施顺序建议

如果目标是最快把平台比拉回来，我建议按下面顺序做：

1. F1：先修 `python_startup`
2. A1 + A2：先打 `richards`、`richards_super`、`go`、`deltablue`
3. D1：打 `comprehensions`
4. B1：打 `coroutines`
5. C1 + C2：打 `generators`、`nqueens`
6. E1 + E2：继续压 `raytrace`、`float`
7. A3 + B2：最后做 AArch64 backend 收尾压榨

## 12. 最终预期

如果这套设计按优先级逐步落地，预期会出现三类结果：

1. `python_startup` 这类 benchmark 会最快接近甚至优于基准 CPython 的平台比；
2. `richards`、`richards_super`、`go`、`deltablue`、`comprehensions` 这类对象/解释器型 benchmark，会因为固定成本削减而出现最明显的 Arm 相对回升；
3. `coroutines`、`generators`、`nqueens`、`raytrace`、`float` 则会依赖更专项的 runtime/JIT 特化，回升会更分阶段，但同样有机会把平台比拉近甚至超过基准 CPython。

一句话总结：

这套设计不是要把 CinderX 变成“两个平台都一样快”，而是要把从基准 CPython 到 CinderX 新增的、且在 AArch64 上被放大的那部分成本，一块一块削掉或绕开。

