# Arm 与 AMD/x86_64 平台性能差异的根因分析

> 目标：回答“为什么同一份代码在 Arm 和 AMD/x86_64 上会跑出明显不同的性能”，并把结论落到源码与近机器码层面，而不是只停留在 benchmark 现象描述。

## 分析边界

这份分析只记录目前已经能被以下证据支撑的结论：
- 当前仓库源码中的显式平台分支
- JIT 后端针对 AArch64 / x86_64 的不同实现
- 本地编译器对代表性微模式生成的汇编

这份分析不做的事：
- 不把 macOS Arm 的性能数据当作 Linux Arm 结论
- 不凭空猜测某个 benchmark 的热点机器码
- 不把未验证的编译器行为当作定论

---

## 总结结论

当前仓库里，Arm 和 AMD/x86_64 跑同一份代码出现性能差异，不只是“编译器随机生成了不同机器码”，而是存在 5 类更根本的结构原因：

1. **AArch64 在 TLS / thread-state 访问上天然比 x86_64 多一步。**
2. **AArch64 在 JIT helper 调用上更频繁落入“先取地址，再间接跳转”的模式。**
3. **AArch64 地址模式和立即数约束更强，导致 frame / metadata 访存更依赖 scratch register 与额外地址解析。**
4. **AArch64 后端为了维护 JIT frame / generator frame，会发出更多显式的 load/store 序列。**
5. **当前仓库还在 Arm 上默认开启了更多 CinderX 特性，这让“平台差异”不只是 ISA 差异，也包含功能开关差异。**

这 5 条里，前 4 条是“同一逻辑如何被降低成不同机器码”的根本原因；第 5 条是“同一代码库实际走了不同功能路径”的根本原因。

---

## 1. TLS / thread-state 访问：Arm 必须先读 TPIDR_EL0

### 源码证据

JIT frame 代码加载 `PyThreadState` 的实现：
[frame_asm.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/frame_asm.cpp#L160)

- x86_64：
  - 直接用 `fs:` 段寄存器读取 TLS 槽位
- AArch64：
  - 先 `mrs ..., TPIDR_EL0`
  - 再 `ldr` 从 thread pointer 基址取目标槽位

### 近机器码证据

本地编译器对微模式的汇编结果：

- x86_64 Linux 风格 TLS 读取：
```asm
movq    %fs:(%rdi), %rax
retq
```

- arm64：
```asm
mrs     x8, TPIDR_EL0
ldr     x0, [x8, x0]
ret
```

### 含义

对需要频繁接触 `PyThreadState` 的路径，Arm 至少天然多出：
- 一次系统寄存器读取
- 一次额外的 base+offset 解引用

这类成本会被哪些 benchmark 放大：
- `coroutines`
- `richards`
- `richards_super`
- `go`
- `deltablue`

原因是它们都更容易频繁触发：
- frame linkage
- state update
- helper 调用

---

## 2. JIT helper 调用：x86_64 更容易直接 call，AArch64 更常见间接 br/blr

### 源码证据

JIT helper 调用生成逻辑：
[gen_asm_utils.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/gen_asm_utils.cpp#L56)

- x86_64：
  - `env.as->call(func);`
- AArch64：
  - hot section 中优先走 literal pool：
    - `ldr reg_scratch_br, [literal]`
    - `blr reg_scratch_br`
  - cold section 或超范围场景：
    - `mov reg_scratch_br, func`
    - `blr reg_scratch_br`

另外，AArch64 还专门维护一套 call target literal pool / shared stub：
[gen_asm.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/gen_asm.cpp#L3044)

### 近机器码证据

本地编译器对“间接调用”微模式的汇编：

- x86_64：
```asm
movq    %rdi, %rax
movq    %rsi, %rdi
jmpq    *%rax
```

- arm64：
```asm
mov     x2, x0
mov     x0, x1
br      x2
```

这只是最简单的函数指针跳转。当前仓库里的 AArch64 JIT helper 调用比这更重，因为还要先解决 helper 地址来源：
- literal pool
- scratch register
- `blr`

### 含义

对 helper-heavy 的 JIT 路径，AArch64 比 x86_64 更容易多出：
- 目标地址装载
- scratch register 占用
- 间接调用本身

这对哪些 benchmark 最敏感：
- `raytrace`
- `generators`
- `coroutines`
- 任何 helper 很碎、函数很多的 JIT 热路径

---

## 3. AArch64 地址模式受限，frame / metadata 访问要靠 `ptr_resolve`

### 源码证据

AArch64 专门引入了：
- `ptr_offset()`
- `ptr_resolve()`

见：
[arch.h](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/arch.h#L120)

而 x86_64 没有对应的“地址解析 helper”，因为大量访存都能直接编码成：
- `rbp + 立即数偏移`
- `base + index + disp`

### 代码层表现

在 AArch64 的 `frame_asm.cpp` 中，大量 frame 字段初始化都长这样：
- `ldr scratch, [base + off]`
- `str scratch, ptr_resolve(...)`
- 反复占用 `x12/x13/x16`

典型位置：
[frame_asm.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/frame_asm.cpp#L671)

而 x86_64 对应位置往往就是直接：
- `mov [rbp + disp], reg`
- `lea scratch, [rbp + disp]`

典型位置：
[frame_asm.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/frame_asm.cpp#L560)

### 含义

这不是“小语法差异”，而是会真正影响机器码质量的根因：
- AArch64 需要更多 scratch register
- 指令序列更长
- 依赖链更深
- 对调度与寄存器分配更不友好

这会优先影响：
- frame-heavy 路径
- generator resume / yield 路径
- coroutine / async 路径
- 调用密度高的小函数

---

## 4. Generator / frame linkage：AArch64 显式 load/store 更重

### 源码证据

生成器 resume 入口：
[gen_asm.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/gen_asm.cpp#L2439)

从这里可以直接看到：

- x86_64：
  - `rbp` 可直接作为 frame pointer
  - 多数状态搬运是 `mov` + `ptr`
  - 最后 `jmp [yield_point + offset]`

- AArch64：
  - `x29`/`fp` 作为 frame pointer
  - `gi_jit_data`、`yield_point`、`returnAddress` 等都需要显式 `ldr/str`
  - 大偏移地址往往经 `ptr_resolve()`

### 另一处佐证

普通 generator frame 的链接：
[frame_asm.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/frame_asm.cpp#L183)

这里 AArch64 版本需要：
- 准备 `x1/x2/x3/x4`
- `emitCall(...)`
- 结果从 `x0/x1` 回传
- 再把 `fp` 切换到 generator data

x86_64 版本虽然也要做同样的语义工作，但地址准备与访存编码明显更短。

### 含义

如果 benchmark 的热点本来就围绕：
- generator
- coroutine
- yield / resume
- lightweight frame

那么 AArch64 更长的状态搬运链，很可能直接变成平台级性能差距。

最相关 benchmark：
- `coroutines`
- `generators`

---

## 5. RegisterPreserver：两边都保存寄存器，但实现成本并不对称

### 源码证据

寄存器保护逻辑：
[register_preserver.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/register_preserver.cpp#L1)

可以看到：

- x86_64：
  - GP 常用 `push/pop`
  - XMM 用 `movdqu` 到栈
  - 仅在奇数个寄存器时额外 `push rax` 对齐

- AArch64：
  - 需要先按寄存器类型分组
  - 再决定 `stp/ldp` 还是 `str/ldr`
  - 仍要显式围绕 `sp` 做 pre/post increment

### 含义

这不是说 Arm 一定更慢，而是说：
- AArch64 的保存/恢复序列更依赖“成对寄存器是否刚好可配对”
- 一旦不能很好配对，就会退化成更多单独 `str/ldr`
- 和上面的 scratch register 压力叠加后，容易让 helper-heavy / frame-heavy 路径继续变差

这类问题更像“后端代码质量差异”，不是 Python 语义差异。

---

## 6. Arm 平台不是只换了 ISA，还默认打开了更多功能

### 源码证据

[setup.py](/Users/luchen/Repo/cinderx/setup.py#L137)
[setup.py](/Users/luchen/Repo/cinderx/setup.py#L152)
[setup.py](/Users/luchen/Repo/cinderx/setup.py#L513)
[setup.py](/Users/luchen/Repo/cinderx/setup.py#L529)

当前 3.14 OSS 构建里：
- Arm 默认开启 `ENABLE_ADAPTIVE_STATIC_PYTHON`
- Arm 默认开启 `ENABLE_LIGHTWEIGHT_FRAMES`
- x86_64 默认并不走同样的开关组合

### 含义

所以“同一份代码”在两个平台上，其实未必走的是同一条功能路径。

这会导致两类差异混在一起：

1. **真正的 ISA / 机器码差异**
   - TLS 读取方式
   - helper 调用方式
   - addressing mode 约束

2. **平台功能开关差异**
   - Arm 默认多走 adaptive static python
   - Arm 默认多走 lightweight frame

如果不先拆开这两层，就很容易把“Arm 默认开了更多东西”的成本误判成“Arm 编译器/机器码更差”。

---

## 7. 对 benchmark 的直接影响判断

### `coroutines`

最可能同时叠加 4 层差异：
- 自定义 awaitable/coroutine 路径
- TLS / tstate 访问
- frame / generator linkage
- Arm 默认 lightweight frames

所以它是最该优先验证“平台根因”的 benchmark。

### `richards`

更偏解释器 bookkeeping 与 frame/state 更新链。
这里不一定需要先看复杂 JIT codegen，但非常适合验证：
- Arm 默认特性
- 解释器额外状态与分支

### `raytrace`

最典型的 JIT 后端差异样本：
- helper 调用很多
- mixed numeric 小函数很多
- 一旦 AArch64 后端更依赖间接 call / scratch reg / longer sequences，就容易把差距放大

### `python_startup`

主要不是 ISA 级机器码问题，而是功能路径差异：
- pyperformance worker 启动时自动写 `sitecustomize.py`
- 自动 `import cinderx.jit`

所以它更像“启动注入成本”，不是“Arm 指令不如 x86 指令”。

---

## 8. 当前最可信的根因优先级

1. **Arm 默认功能开关不同**
   - 这是最容易被忽略、但最可能直接改变结论的根因。

2. **AArch64 的 helper 调用方式更重**
   - x86_64 直接 `call`
   - AArch64 常常要 literal pool / scratch / `blr`

3. **AArch64 的 TLS / thread-state 读取更重**
   - `mrs TPIDR_EL0` + `ldr`

4. **AArch64 的 frame / metadata 访存更依赖地址解析**
   - `ptr_resolve()`
   - scratch register 压力

5. **generator / coroutine resume 入口在 AArch64 上更长**
   - 对 async / generator benchmark 影响尤其直接

---

## 9. 对后续一键脚本的要求

基于这份根因分析，一键脚本不应该只是“把 benchmark 跑一遍”，而应显式回答以下问题：

1. Arm 默认开关关掉后，差距是否明显缩小？
2. `raytrace` 在 `none/all/backedge` 下，是否是 `all` 模式最差？
3. `python_startup` 的 autoload/noautoload 差距有多大？
4. `coroutines` 是否比 `richards` 对 lightweight frames 更敏感？

只有先把这几个问题答清楚，后面再去追更细的机器码级热点才有价值。

