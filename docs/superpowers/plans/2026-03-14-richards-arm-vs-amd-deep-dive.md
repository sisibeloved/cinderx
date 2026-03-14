# `richards` 基准的 Arm vs AMD 深入归因

## 目标

解释这样一类变化：

- 在 CPython 基准分支上，`richards` 的 Arm/AMD 性能比假设约为 `0.8`
- 切换到当前 `cinderx` 分支后，比值进一步恶化，例如下降到 `0.6`

这里要回答的不是“richards 为什么慢”，而是：

1. `richards` 本体在跑什么热路径
2. `CPython -> CinderX` 后，这些热路径发生了什么结构变化
3. 为什么这些新增成本在 Arm/AArch64 上的相对损失比 AMD/x86_64 更大

## 1. benchmark 本体到底在测什么

源码在：

- `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_richards/run_benchmark.py`

`richards` 的结构非常典型：

1. 创建多个 task 对象
2. 反复调度 `schedule()`
3. 在 task 之间转移 packet
4. 频繁追加链表 packet
5. 频繁调用极小的方法
6. 频繁读取和写入对象字段

核心不是算术，而是：

1. `Task.runTask()`
2. `Task.addPacket()`
3. `Task.qpkt()`
4. `Packet.append_to()`
5. `HandlerTask.fn()`
6. `WorkTask.fn()`
7. `schedule()`

## 2. richards 的字节码热点轮廓

我把 benchmark 源码去掉 `import pyperf` 后做了本地反汇编，看到的热点轮廓非常清楚：

### `Task.addPacket`

核心字节码是：

1. `LOAD_ATTR input`
2. `STORE_ATTR input`
3. `STORE_ATTR packet_pending`
4. `LOAD_ATTR priority`
5. `LOAD_METHOD append_to`
6. `CALL_METHOD`

### `Task.runTask`

核心字节码是：

1. `LOAD_METHOD isWaitingWithPacket`
2. `CALL_METHOD`
3. `LOAD_ATTR input`
4. `LOAD_ATTR link`
5. `STORE_ATTR input`
6. `LOAD_METHOD running / packetPending / fn`
7. `CALL_METHOD`

### `Task.qpkt`

核心字节码是：

1. `LOAD_METHOD findtcb`
2. `LOAD_ATTR ident`
3. `CALL_METHOD`
4. `LOAD_ATTR qpktCount`
5. `STORE_ATTR qpktCount`
6. `STORE_ATTR link`
7. `STORE_ATTR ident`
8. `LOAD_METHOD addPacket`
9. `CALL_METHOD`

### `HandlerTask.fn` / `WorkTask.fn` / `schedule`

也都表现为：

1. 大量 `LOAD_ATTR` / `STORE_ATTR`
2. 大量 `LOAD_METHOD` / `CALL_METHOD`
3. 少量比较、跳转和链表遍历
4. 极少真正的重计算

所以 `richards` 可以概括成：

> 一个以“小方法调用 + 小对象字段访问 + 链表 packet 传递 + 状态机调度”为核心的 benchmark。

这意味着它对“解释器 bookkeeping、调用分派、属性 guard、frame/tstate 访问”的变化极其敏感。

## 3. CPython 基准分支上的关键执行链

在 CPython 基准提交 `ebf955df7a89ed0c7968f79faec1de49f61ed7cb` 上，`richards` 的主要热路径依赖：

1. `LOAD_ATTR` 专项化
2. `LOAD_METHOD` / `CALL` 专项化
3. `STORE_ATTR`
4. 常规解释器 frame 进入/退出
5. CPython 的默认 adaptive opcode 机制

换句话说，CPython 在这个 benchmark 上的瓶颈主要是：

1. 方法分派
2. 属性读写
3. 调用开销

但这些都还处于“CPython 默认执行模型”的框架内。

## 4. CinderX 相对 CPython 的结构变化

`richards` 最关键的变化，不是 checked container，也不是 coroutine，而是解释器调度和调用相关的结构成本。

### 4.1 解释器引入了额外 bookkeeping

在：

- `/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/ceval_macros.h`
- `/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/interpreter.c`

CinderX 相比 CPython，多了以下热路径逻辑：

1. `adaptive_enabled` 被作为 tail-call interpreter 的额外参数在线程化传播
2. `CI_UPDATE_CALL_COUNT`
3. `CI_SET_ADAPTIVE_INTERPRETER_ENABLED_STATE`
4. `IS_PEP523_HOOKED`

这类差异对 `richards` 特别敏感，因为 `richards` 不是“单个大函数慢慢跑”，而是：

1. 很多非常小的函数
2. 很多非常小的对象方法
3. 高频 frame 切换和返回

所以只要每次 frame 进入、每次小 helper 执行时多一点 bookkeeping，这些成本就会被大量放大。

### 4.2 仓库里已有 interpreter overhead 结论本来就把 richards 列成高优先级

已有文档：

- `/Users/luchen/Repo/cinderx/plans/2026-02-27-cinderx-vs-cpython-314-interpreter/deliverable.md`

已经明确把以下项列为 richards 类 workload 的高优先级成本：

1. `CI_UPDATE_CALL_COUNT`
2. `CI_SET_ADAPTIVE_INTERPRETER_ENABLED_STATE`
3. `if (adaptive_enabled)` 分支压力
4. `IS_PEP523_HOOKED`

这和 `richards` 源码的 call-heavy / attr-heavy 形状是高度一致的。

## 5. 静态机器码证据：为什么同类新增开销对 Arm 更伤

为了避免停留在“多了 call count”这种抽象描述，我做了两个最小探针：

1. 一个模拟 `addPacket()` 这种 tiny helper
2. 一个模拟 `LOAD_ATTR_INSTANCE_VALUE` 风格的属性 guard

### 5.1 `addPacket` 风格 tiny helper

探针对比：

1. `cpy_add_packet`
2. `cx_add_packet`

区别只是 `cx_add_packet` 在函数入口增加了：

```c
if (adaptive_enabled) {
    *call_count += 1;
}
```

也就是模拟 CinderX 在 richards 这类小 helper 周边附加的 bookkeeping 成本。

#### AArch64 形状

`cx_add_packet` 相比 `cpy_add_packet`，额外多了：

1. `cbz w3, ...`
2. `ldr x0, [x4]`
3. `add x0, x0, #1`
4. `str x0, [x4]`

也就是说，只加一个很小的计数逻辑，AArch64 就多出了一串显式的分支与 load/store。

#### x86_64 形状

x86_64 版本也会变长，但主要是：

1. `test %ecx,%ecx`
2. `je ...`
3. `addq $1,(%r8)`

它仍然是更紧凑的形状。

#### 对 richards 的意义

`richards` 最大的问题不是“某个单函数特别慢”，而是“这种 tiny helper 成千上万次被执行”。  
因此即使只是每次 helper 入口多 2-4 条指令，累积起来也会很大。

这正是 Arm/AMD 比值恶化的第一层原因：

- 两边都更慢
- 但 Arm 上每次 tiny helper 额外成本更高

### 5.2 属性 guard：`LOAD_ATTR_INSTANCE_VALUE` 风格

richards 中对象字段访问非常多，而 CinderX JIT 对 instance-value attr 会生成更重的 guard。

在：

- `/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp`

`LOAD_ATTR_INSTANCE_VALUE` 会在 type-version guard 之外，再做：

1. 读取 `tp_basicsize`
2. 计算 inline-values 的 `valid` 地址
3. 加载 `valid` 字节
4. 检查 `valid != 0`

我做的最小探针对比是：

1. `cpy_attr_guard`: 仅比较 `tp_version_tag == cached`
2. `cx_attr_guard`: `tp_version_tag == cached && valid != 0`

#### AArch64

`cx_attr_guard` 的形状是：

1. `ldr obj->ob_type`
2. `ldr tp->tp_basicsize`
3. `ldr tp->tp_version_tag`
4. `ldrb [obj + basicsize]`
5. `cmp valid, 0`
6. `ccmp version, cached`
7. `cset`

#### x86_64

x86_64 也会变复杂，但仍然更紧凑：

1. `mov obj->ob_type`
2. `mov tp->tp_basicsize`
3. `cmpb (%rdi,%rdx,1), 0`
4. `setne`
5. `cmp cached, version`
6. `sete`
7. `and`

#### 对 richards 的意义

`richards` 里字段访问密度非常高，例如：

1. `self.input`
2. `msg.link`
3. `self.priority`
4. `old.priority`
5. `pkt.ident`
6. `pkt.kind`
7. `work.datum`
8. `dev.link`
9. `h.work_in`
10. `h.device_in`

因此就算只有一部分 attr 走到更重的 guard，累积影响也会很明显。

## 6. JIT 侧：为什么 richards 也会被放大

如果 `richards` 只受解释器影响，那我们可以把问题缩成 bookkeeping；但它还会受到 JIT 的 call/attr lowering 形状影响。

### 6.1 JIT 会显式生成 `LoadMethod` / `CallMethod`

在：

- `/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp`

`LOAD_METHOD` 会走：

- `emitLoadMethod(...)`

`CALL_METHOD` 会走：

- `tc.emit<CallMethod>(...)`

也就是说 richards 里那些极小的方法调用，在 JIT 里并不是被“神奇消掉”，而是成为明确的 method load 和 method call 节点。

### 6.2 call 本身未必是最坏点，guard 和小 helper 才是

我还做了一个 `call_method_probe`，它在两边都基本只是 tail jump 到 `PyObject_VectorcallMethod`。  
这说明 richards 的平台差异并不主要来自“单次方法调用本身的 ISA 差异”，而更可能来自：

1. 调用前后的 attr guard
2. 小 helper 外围的 interpreter bookkeeping
3. 频繁的小对象字段访问

这一点很重要，因为它让我们把根因从“泛泛的 CALL 慢”收窄成更具体的结构。

## 7. 为什么 richards 的平台比值会从 `0.8` 恶化到 `0.6`

现在可以把因果链收束成一句更精确的话：

> `richards` 在 CPython 上已经是 Arm 相对偏吃亏的 call-heavy benchmark；切到 CinderX 后，额外引入的工作主要是解释器 bookkeeping 和更重的 attr guard，而这两类新增成本都更容易在 AArch64 上被放大，所以 Arm/AMD 比值继续恶化。

展开来说：

### 在 CPython 基准分支上

两边都主要在承受：

1. 小方法调用
2. 小对象属性访问
3. 链表 packet 处理

Arm 已经不如 AMD/x86_64，但还主要是“默认执行模型”的平台差异。

### 切到 CinderX 后

又叠加了：

1. `CI_UPDATE_CALL_COUNT`
2. `adaptive_enabled` 分支
3. `IS_PEP523_HOOKED`
4. 更重的 attr guard

这些新增工作恰好是：

1. 高频
2. 碎片化
3. 调度密集
4. 很难被单个大计算吞掉

而 AArch64 对这类“多一点分支、多一点 load/store、多一点地址生成”的额外成本更敏感。

所以最后的结果不是“两个平台都慢一点”，而是：

- Arm 的额外损失更大
- 于是相对比值进一步下降

## 8. 当前对 richards 的归因结论

按证据强度排序，`richards` 的平台比值恶化最可能来自这 4 层叠加：

1. **解释器 bookkeeping 热路径**
   - `CI_UPDATE_CALL_COUNT`
   - `CI_SET_ADAPTIVE_INTERPRETER_ENABLED_STATE`
   - `adaptive_enabled`
   - `IS_PEP523_HOOKED`

2. **tiny helper 对额外开销极其敏感**
   - `addPacket`
   - `runTask`
   - `qpkt`
   - `append_to`

3. **attr-heavy 对象模型**
   - packet / task / handler / worker 字段访问极多

4. **JIT 下 attr guard 更重**
   - `LOAD_ATTR_INSTANCE_VALUE`
   - `LOAD_ATTR_SLOT`
   - method load + method call 前后的 guard 成本

## 9. 后续最值得验证的点

如果后面要把 richards 再推进到一键验证脚本，最值得优先验证的是：

1. 关闭 JIT，仅跑解释器 richards
   - 看平台比值是否已经明显恶化

2. 屏蔽 `CI_UPDATE_CALL_COUNT` / adaptive bookkeeping
   - 看 richards 是否立即回升

3. 检查 richards 热函数是否大量走 `LOAD_ATTR_INSTANCE_VALUE`
   - 如果是，这条 guard 链就非常值得单独针对

4. 在 Arm 上关闭 lightweight frames
   - 看 richards 的调度密集路径是否更敏感

## 一句话结论

`richards` 的平台比值恶化，核心不是“算法本身更偏向 x86”，而是：

**CinderX 给这个 call-heavy / attr-heavy / tiny-helper-heavy benchmark 叠加了额外的解释器 bookkeeping 和更重的属性 guard，而这些新增工作在 AArch64 上的相对成本上升比 x86_64 更明显。**
