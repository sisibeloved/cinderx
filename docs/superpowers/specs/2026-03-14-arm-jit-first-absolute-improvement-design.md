# Arm JIT 优先绝对性能提升设计稿

> 面向目标：针对 `coroutines`、`comprehensions`、`richards`、`richards_super`、`go`、`deltablue`、`raytrace`、`nqueens`、`float`、`generators`、`python_startup`，优先提升 Arm 平台上当前 CinderX 分支相对于基准 CPython 分支的绝对性能；允许忽略甚至牺牲 x86_64 侧收益，但所有激进优化都必须先挂在显式实验开关后，再通过 macOS Arm 的 pyperformance 快速验证和 Linux Arm 的正式验证决定是否保留。

## 1. 目标变更

之前的主目标是“修复 Arm/AMD 平台比下降”。  
现在主目标改成：

1. 只优先追 Arm 上的 `CinderX vs CPython` 绝对提升；
2. 可以不关心 x86_64 是否同步变快；
3. 可以接受对 x86_64 无收益，甚至轻微回退；
4. 优先使用 JIT 侧更激进、更针对热点形状的优化；
5. 所有这类优化先用显式实验开关控制，不直接默认打开。

这意味着设计重点也要调整：

- 不再优先做“同时照顾 Arm 和 x86_64 的温和共享优化”
- 而是优先做“只要 Arm 热点会受益，就值得验证”的 JIT 激进专门化

## 2. 新的总体策略

采用三层策略：

### 2.1 JIT 优先层

优先修改：

- HIR builder
- simplify pass
- AArch64 codegen / lowering
- coroutine / generator runtime glue

只有当某个 benchmark 明显还长期停留在解释器，或者解释器成本主导时，才补解释器兜底。

### 2.2 Arm-only 实验层

所有激进优化都挂在显式开关后，例如：

- `PYTHONJITARMEXPERIMENT=1`
- `PYTHONJITARMCOROFAST=1`
- `PYTHONJITARMINSTANCEFAST=1`
- `PYTHONJITARMINSTANCEFASTSKIPVALID=1`
- `PYTHONJITARMNUMERICLEAF=1`
- `PYTHONJITARMGENFAST=1`

可以进一步允许：

- 在 `__aarch64__` / `arm64` 下存在更激进的默认候选行为
- 但在实验阶段仍要求通过开关显式启用

### 2.3 双阶段验证层

验证流程改为：

1. **macOS Arm 快速筛选**
   目的不是给最终数据，而是快速判断“方向是否有效”。
   重点看：
   - benchmark 是否明显回升
   - HIR 形状是否如预期变化
   - 是否出现明显功能回归或编译失败

2. **Linux Arm 正式确认**
   只有在 macOS Arm 上已经看到方向正确，才值得推到隔离 Linux Arm 环境做正式 benchmark。

## 3. 设计原则

### 3.1 不按 benchmark 名字硬编码

虽然目标是拉升 pyperformance，但仍然优先按“热点代码形状”做特化：

- exact coroutine awaitable
- exact instance-value attr
- tiny numeric leaf helper
- low-local generator resume / attr
- pure list/dict write

这样做的好处是：

- 容易归因
- 容易通过 HIR / LIR / 机器码验证
- 后续决定是否默认打开时也更容易评估风险

### 3.2 允许激进，但必须可回退

每个实验都要满足：

- 能用单独开关开/关
- 能通过 HIR 形状判断是否命中
- 出现回归时可以快速关闭，不影响主线行为

### 3.3 先改最可能影响 Arm 绝对性能的点

优先级不再按“平台比共享根因”排，而是按“Arm 上 CinderX 最有机会直接变快”排：

1. `coroutines`
2. `richards` / `go` / `deltablue`
3. `comprehensions`
4. `raytrace` / `float`
5. `generators`
6. `nqueens`
7. `python_startup`
8. `richards_super`

这里把 `richards_super` 放后，不是因为它不重要，而是因为 `super()` shortcut 的语义风险比前几项高，适合在前面的 JIT 激进包打稳之后再做。

## 4. 实验包总览

### 包 A：Arm Coroutine / Awaitable Fast Path

覆盖 benchmark：

- `coroutines`
- 部分帮助 `generators`

### 包 B：Arm Instance-Value Aggressive Fast Path

覆盖 benchmark：

- `comprehensions`
- `richards`
- `go`
- `deltablue`
- 部分帮助 `float`

### 包 C：Arm Tiny Numeric Leaf Fast Path

覆盖 benchmark：

- `raytrace`
- `float`
- 部分帮助 `nqueens`

### 包 D：Arm Generator Resume / Attr / Decref Fast Path

覆盖 benchmark：

- `generators`
- 部分帮助 `coroutines`
- 部分帮助 `nqueens`

### 包 E：Arm Startup / Autoload Policy

覆盖 benchmark：

- `python_startup`

## 5. 包 A：Arm Coroutine / Awaitable Fast Path

### A1. exact coroutine awaitable 短路

**为什么要改**

`coroutines` 的热点并不是通用 awaitable 协议，而是非常窄的 exact coroutine 形状。  
当前 CinderX 仍然把这条形状放进通用链里：

- `JitCoro_GetAwaitableIter`
- coroutine type check
- `JitGen_yf`
- already-awaited 检查

这在 Arm 上的 helper / branch 成本偏高。

**怎么改**

优先修改：

- [cinderx/Jit/hir/builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp)
- [cinderx/Interpreter/3.14/ceval.h](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/ceval.h)

实验开关建议：

- `PYTHONJITARMCOROFAST=1`

命中条件：

- exact `PyCoro_Type`
- exact Cinder coroutine type

命中后直接：

- `Py_NewRef` / `Incref`
- 仅保留 already-awaited 检查
- 跳过通用 awaitable helper

**预期现象**

- `GET_AWAITABLE` 周边的 HIR `CallCFunc` 数量下降
- exact coroutine 形状的控制流图更短
- macOS Arm 上 `coroutines` 应该能直接看到方向性提升

**预期收益**

- `coroutines`：高
- `generators`：低到中

### A2. coroutine resume metadata shortcut

**为什么要改**

即使 awaitable 入口变短，resume / suspend 本身在 Arm 上仍可能更重。  
对 pyperformance 的 coroutine benchmark 来说，resume 链是持续付费项。

**怎么改**

优先修改：

- [cinderx/Jit/codegen/gen_asm.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/gen_asm.cpp)
- [cinderx/Jit/codegen/arch.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/arch.cpp)

实验开关建议：

- `PYTHONJITARMCORORESUMEFAST=1`

方向：

- 合并 metadata 访问
- 压缩 AArch64 上的地址生成
- 尽量减少 scratch register 和重复 load/store

**预期现象**

- `coroutines` compiled size 有下降趋势
- AArch64 disassembly / annotation 更短
- `coroutines` 再获得第二段 uplift

**预期收益**

- `coroutines`：中高

## 6. 包 B：Arm Instance-Value Aggressive Fast Path

### B1. low-local instance-value 放开

**为什么要改**

`richards`、`go`、`deltablue` 里大量热点方法都很小。  
如果 instance-value lowering 对 low-local 形状过于保守，就会把最该优化的 Arm 热路径留在 `LoadAttrCached` 上。

**怎么改**

优先修改：

- [cinderx/Jit/hir/builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp)

实验开关建议：

- `PYTHONJITARMINSTANCEFAST=1`

命中后：

- 将 low-local method 也允许走 instance-value lowering

**预期现象**

- `LoadAttrCached` / `StoreAttrCached` 下降
- `LoadField` / `StoreField` 上升

**预期收益**

- `richards`：中高
- `go`：高
- `deltablue`：高
- `comprehensions`：中

### B2. 跳过 instance-value valid guard

**为什么要改**

在 Arm 上，`tp_basicsize` + `valid` 检查这一段经常比字段访问本身更贵。  
如果对象形状在 benchmark 中高度稳定，那么这层 guard 是很有可能“付出很多、实际很少触发”的。

**怎么改**

优先修改：

- [cinderx/Jit/hir/builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp)
- [cinderx/Interpreter/3.14/Includes/generated_cases.c.h](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/generated_cases.c.h)
- [cinderx/Interpreter/3.14/interpreter.c](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/interpreter.c)

实验开关建议：

- `PYTHONJITARMINSTANCEFASTSKIPVALID=1`

命中条件：

- exact stable layout
- benchmark 形状明确是单态对象流

命中后：

- 直接跳过 `inline_values.valid` guard
- 允许更接近“直接字段读取”的 HIR / interpreter fast path

**预期现象**

- HIR 文本中 `tp_basicsize` / `inline_values.valid` 相关痕迹消失
- `go` / `deltablue` / `richards` 类 benchmark 在 Arm 上有更明显 uplift

**预期收益**

- `go`：高
- `deltablue`：高
- `richards`：中高
- `comprehensions`：中

### B3. AArch64 lowering 特化

**为什么要改**

HIR 变短并不自动等于 Arm 机器码就变短。  
如果 lowering 仍然展开出额外地址计算，收益会被吃掉。

**怎么改**

优先修改：

- [cinderx/Jit/codegen/arch.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/arch.cpp)
- [cinderx/Jit/codegen/gen_asm.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/gen_asm.cpp)

实验开关建议：

- `PYTHONJITARMINSTANCELOWERING=1`

方向：

- fold 地址计算
- 减少 scratch
- 合并 valid / field load 相关序列

**预期收益**

- `go`：高
- `deltablue`：高
- `richards`：中高

## 7. 包 C：Arm Tiny Numeric Leaf Fast Path

### C1. mixed-numeric tiny leaf 去 helper 化

**为什么要改**

`raytrace` 和 `float` 的核心问题不是“没有优化”，而是 tiny numeric leaf helper 太碎，helper call / guard / deopt 太多。  
Arm 对这种碎 helper 的胶水成本更敏感。

**怎么改**

优先修改：

- [cinderx/Jit/hir/builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp)
- 数值相关 simplify / pass 文件

实验开关建议：

- `PYTHONJITARMNUMERICLEAF=1`

方向：

- 对 no-backedge tiny numeric helper 放宽 guard
- 降低 mixed int/float 的过度专门化
- 尽量把 helper call 改成更直接的 lowering

**预期收益**

- `raytrace`：高
- `float`：高
- `nqueens`：中

### C2. float-slot-heavy object method 强化

**为什么要改**

`float` 类 benchmark 往往会反复读写 float slot，Arm 上这类 load/use 链容易长。

**怎么改**

实验开关建议：

- `PYTHONJITARMFLOATSLOT=1`

方向：

- hoist float slot load
- 更激进的 float-only lowering
- 避免退回 object helper

**预期收益**

- `float`：高
- `raytrace`：中

## 8. 包 D：Arm Generator Resume / Attr / Decref Fast Path

### D1. low-local generator attr 专项

**为什么要改**

`generators` 和部分 `nqueens` / `coroutines` 路径里，generator helper 很小，但 attr 很频繁。  
这和 `richards` 一类 tiny helper 很像，只是更偏 generator runtime。

**怎么改**

实验开关建议：

- `PYTHONJITARMGENFAST=1`

方向：

- generator low-local attr 尽量走 field lowering
- 避免 generic attr cache

### D2. generator decref / resume 收缩

**为什么要改**

Arm 上 generator 的 resume + decref glue 很容易膨胀成多段基本块。

**怎么改**

方向：

- 收缩 decref lowering
- 合并 generator resume metadata path

**预期收益**

- `generators`：高
- `coroutines`：中
- `nqueens`：中

## 9. 包 E：Arm Startup / Autoload Policy

### E1. startup benchmark 明确避开 JIT 注入

**为什么要改**

`python_startup` 不是 steady-state JIT benchmark。  
它更像“你有没有在启动时多做一堆事”的测试。

**怎么改**

继续沿用并加强：

- startup shape 不自动 import / enable jit
- 把 startup benchmark 从 JIT 实验中隔离出去

**预期收益**

- `python_startup`：高

## 10. macOS Arm 快速验证策略

macOS Arm 不作为最终性能结论来源，但可以作为非常高价值的方向筛选器。

### 10.1 验证目标

在 macOS Arm 上，只回答三件事：

1. 激进开关打开后，benchmark 是否明显向正确方向移动
2. HIR / LIR / disassembly 是否出现预期形状变化
3. 是否引入明显功能回归或编译失败

### 10.2 首批验证 benchmark

优先只跑：

- `coroutines`
- `richards`
- `go`
- `deltablue`
- `comprehensions`
- `raytrace`
- `float`

暂时不把 `python_startup` 混进同一轮 JIT 验证里。

### 10.3 首批开关组合

建议先做单开关 A/B：

1. `PYTHONJITARMCOROFAST=1`
2. `PYTHONJITARMINSTANCEFAST=1`
3. `PYTHONJITARMINSTANCEFAST=1` + `PYTHONJITARMINSTANCEFASTSKIPVALID=1`
4. `PYTHONJITARMNUMERICLEAF=1`
5. `PYTHONJITARMGENFAST=1`

然后再做组合验证：

1. coroutine 组
2. attr 组
3. numeric 组
4. all-in JIT Arm experiments

### 10.4 快速判定标准

如果某开关满足下面条件，就值得推到 Linux Arm：

- macOS Arm benchmark 有稳定提升趋势
- HIR 形状变化与设计一致
- 没有明显 correctness 问题

如果 macOS Arm 上完全无收益，就不必优先推到 Linux Arm。

## 11. 推荐实施顺序

### 第一波

1. `A1 exact coroutine awaitable`
2. `B1 low-local instance-value`
3. `B2 skip valid guard`
4. `C1 tiny numeric leaf`

这四项最值得先打，因为：

- 对应 benchmark 最集中
- HIR 变化最好验证
- 最有机会在 macOS Arm 上快速看到 uplift

### 第二波

1. `A2 coroutine resume metadata`
2. `B3 AArch64 attr lowering`
3. `D1 generator attr`
4. `D2 generator decref / resume`

### 第三波

1. `richards_super` 的 `super()` shortcut
2. 更激进的 Arm-only 默认候选行为

## 12. 风险与控制

### 12.1 正确性风险

跳过 valid guard、缩短 coroutine helper 链、收紧 numeric guard 都存在正确性风险。  
所以必须：

- 全部挂实验开关
- 先有形状测试
- 再做 pyperformance 快速验证

### 12.2 误判风险

macOS Arm 和 Linux Arm 不完全等价。  
所以 macOS Arm 只用于筛选方向，不用于下最终结论。

### 12.3 组合污染风险

多个激进开关一起开时，收益和回归可能互相掩盖。  
因此验证时必须先单开关，再做组合。

## 13. 最终建议

新的目标下，最值得坚持的不是“尽量温和”，而是“尽量可实验、可归因、可回退”。

因此推荐路线是：

1. 明确转向 `Arm-only + JIT-first`
2. 先把激进优化做成实验开关
3. 先用 macOS Arm 跑 pyperformance 做方向筛选
4. 只把已经在 macOS Arm 上显著有效的实验推到 Linux Arm 正式验证

这条路线最符合当前目标：  
快速找到哪些 JIT 形状特化，真的能把 Arm 上的 CinderX 拉到更接近甚至超过基准 CPython。
