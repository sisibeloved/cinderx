# `coroutines` 基准的 Arm vs AMD 深入归因

## 目标

回答一个非常具体的问题：

- 在 CPython 基准分支上，`coroutines` 的 Arm/AMD 性能比假设约为 `0.8`
- 切到当前 `cinderx` 分支后，性能比降到 `0.6`

这里要解释的不是“CinderX 慢”，而是：

1. `CPython -> CinderX` 之后，这个 benchmark 的热路径发生了什么变化
2. 这些变化在 Arm 和 AMD/x86_64 上各自会生成怎样的静态机器码或 JIT 代码形状
3. 为什么这些新增成本会让 Arm 的损失比 AMD 更大，从而把比值从 `0.8` 进一步拉低到 `0.6`

## 1. benchmark 本身到底在测什么

源码在：

- `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_coroutines/run_benchmark.py`

核心代码非常短：

```python
async def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return await fibonacci(n - 1) + await fibonacci(n - 2)

def bench_coroutines(loops: int) -> float:
    for _ in range(loops):
        coro = fibonacci(25)
        try:
            while True:
                coro.send(None)
        except StopIteration:
            pass
```

这意味着 `coroutines` 的热点不是 `asyncio` 调度器，而是纯协程机制本身：

1. 每次递归调用都会创建新的 coroutine 对象
2. 每个 `await fibonacci(...)` 都会走 `GET_AWAITABLE`
3. 每次 `send(None)` 都会触发 coroutine resume / suspend
4. 递归树非常深，协程对象创建与销毁总量巨大

因此这个 benchmark 最敏感的路径是：

1. `RETURN_GENERATOR -> _Py_MakeCoro`
2. `GET_AWAITABLE -> _PyEval_GetAwaitable -> _PyCoro_GetAwaitableIter`
3. `SEND / YIELD_VALUE / END_SEND`
4. coroutine object / frame / generator resume 相关 runtime

## 2. CPython 基准分支上的关键执行链

CPython 基准提交 `ebf955df7a89ed0c7968f79faec1de49f61ed7cb` 中，对应关键代码在：

- `/Users/luchen/Repo/cpython/Objects/genobject.c`
- `/Users/luchen/Repo/cpython/Python/ceval.c`
- `/Users/luchen/Repo/cpython/Python/generated_cases.c.h`

### 2.1 coroutine 创建

`RETURN_GENERATOR` 最终走到：

- `_Py_MakeCoro()`
- `make_gen(&PyCoro_Type, func)`

也就是每次递归调用 `fibonacci()`，都会新建一个 `PyCoroObject`。

### 2.2 awaitable 解析

`GET_AWAITABLE` 最终调用：

- `_PyEval_GetAwaitable(iterable, oparg)`
- `_PyCoro_GetAwaitableIter(iterable)`

CPython 版本的 `_PyEval_GetAwaitable()` 只有一条 coroutine 专项检查链：

1. 先 `_PyCoro_GetAwaitableIter()`
2. 如果返回的是 exact `PyCoro`
3. 再 `_PyGen_yf()` 判断它是否已经在 await 别的对象

这是一个相对紧凑的结构。

## 3. CinderX 相对 CPython 在 `coroutines` 上改了什么

这里不能只说“改了 awaitable helper”，而要明确地说热路径被怎样改写了。

### 3.1 解释器 helper 被替换

在：

- `/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/borrowed-ceval.c.template`
- `/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/ceval.h`

CPython 的：

- `_PyCoro_GetAwaitableIter`
- `_PyEval_GetAwaitable`

被替换为：

- `JitCoro_GetAwaitableIter`
- `Ci_PyEval_GetAwaitable`

关键差异不是“名字变了”，而是判断链变长了。

#### CPython 的逻辑

输入对象 `o`：

1. `PyCoro_CheckExact(o)`
2. `gen_is_coroutine(o)`
3. 否则再走 `tp_as_async->am_await`
4. 对返回值再做一次同类检查

#### CinderX 的逻辑

输入对象 `o`：

1. `JitCoro_CheckExact(o)`
2. `PyCoro_CheckExact(o)`
3. `jitgen_is_coroutine(o)`
4. 否则再走 `tp_as_async->am_await`
5. 对返回值再做一轮
   - `JitCoro_CheckExact(res)`
   - `PyCoro_CheckExact(res)`
   - `jitgen_is_coroutine(res)`

也就是说，CinderX 在 coroutine fast path 上显式引入了“同时兼容 CPython coroutine 与 JIT coroutine”的额外判定层。

### 3.2 “已经被 await”的检查范围更宽

CPython:

- exact `PyCoro_CheckExact(iter)` 时才 `_PyGen_yf()`

CinderX:

- `PyCoro_CheckExact(iter) || JitCoro_CheckExact(iter)` 时走 `JitGen_yf()`

这会把 Cinder coroutine type 也纳入额外检查路径。

### 3.3 JIT 没有把这些检查消掉，反而结构化进了 IR

在：

- `/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp`

`emitGetAwaitable()` 会显式生成：

1. `CallCFunc<JitCoro_GetAwaitableIter>`
2. coroutine type 分支
   - exact `cinderx coroType`
   - exact `PyCoro_Type`
3. `CallCFunc<JitGen_yf>`
4. `RaiseStatic("coroutine is being awaited already")`

因此对于 `coroutines` 这种 benchmark，JIT 并不是把 await 路径“简化成一个紧凑 fast path”，而是把 Cinder coroutine 兼容逻辑显式保留在编译后代码形状里。

## 4. 静态机器码证据：为什么同样的新增逻辑对 Arm 更伤

为了避免只停留在源码层，我把 CPython/CinderX 的 awaitable helper 结构抽成了最小探针，并用：

- `aarch64-linux-gnu-gcc 15.2.0`
- `x86_64-linux-gnu-gcc 15.2.0`

交叉编译成目标文件后反汇编。

探针函数对应四类逻辑：

1. `cpy_coro_get_awaitable_iter`
2. `cx_coro_get_awaitable_iter`
3. `cpy_eval_get_awaitable`
4. `cx_eval_get_awaitable`

### 4.1 `*_coro_get_awaitable_iter`：CinderX 版比 CPython 版多出来什么

在两个平台上，CinderX 版都比 CPython 版明显更长，因为它额外增加了：

1. `JitCoro_CheckExact(o)`
2. `jitgen_is_coroutine(o)`
3. `JitCoro_CheckExact(res)`
4. `jitgen_is_coroutine(res)`

#### AArch64 观察

`cpy_coro_get_awaitable_iter` 的主干大致是：

- `bl PyCoro_CheckExact`
- `bl gen_is_coroutine`
- `blr am_await`
- `bl PyCoro_CheckExact`
- `bl gen_is_coroutine`
- `bl PyIter_Check`

`cx_coro_get_awaitable_iter` 则扩成：

- `bl JitCoro_CheckExact`
- `bl PyCoro_CheckExact`
- `bl jitgen_is_coroutine`
- `blr am_await`
- `bl JitCoro_CheckExact`
- `bl PyCoro_CheckExact`
- `bl jitgen_is_coroutine`
- `bl PyIter_Check`

这里的关键不是“多了两个 if”，而是：

1. 每个新增类型判断基本都变成一条独立 `bl`
2. 每次判断后都接 `cbz/cbnz`
3. 参数寄存器会被反复重装
4. 返回值经常要从栈槽或寄存器重新取回

所以在 AArch64 上，helper 变长不仅是指令数变多，更是关键路径深度和分支数都增加。

#### x86_64 观察

x86_64 也同样变长，但每次新增判断通常表现为：

- `call *GOT(...)`
- `test %eax,%eax`
- `je/jne`

而且对象字段访问更多能直接落在短小的 base+disp 形式上。

结论是：

- 两边都会因为 CinderX helper 变复杂而变慢
- 但 AArch64 上，这种“多一层 exact-type 兼容”的成本放大更明显

这正是“平台性能比进一步下滑”的第一层原因。

### 4.2 `*_eval_get_awaitable`：CinderX 再加一层 exact-type + `JitGen_yf`

`cpy_eval_get_awaitable`：

1. 调 `cpy_coro_get_awaitable_iter`
2. `PyCoro_CheckExact(iter)`
3. `_PyGen_yf(iter)`

`cx_eval_get_awaitable`：

1. 调 `cx_coro_get_awaitable_iter`
2. `PyCoro_CheckExact(iter)`
3. 如果不是，再 `JitCoro_CheckExact(iter)`
4. `JitGen_yf(iter)`

在 AArch64 探针里，`cx_eval_get_awaitable` 比 CPython 多出了一整条：

- `bl JitCoro_CheckExact`
- 再次装载 `iter`
- `bl JitGen_yf`

而 x86_64 虽然也多了这段，但指令序列更紧。

因此，单是 `await` 入口这一个 helper，CinderX 就让 Arm 比 x86_64 多承担了更高比例的“额外控制流成本”。

## 5. JIT 路径：为什么 `coroutines` 在 CinderX 上不只是解释器 helper 变重

如果这个 benchmark 只跑解释器，那么上面的 helper 扩张已经足够解释一部分比值变化；但用户要求还要看 JIT。

这里要注意一个关键点：

- `coroutines` 并不是传统数值循环型 benchmark
- 它的热路径是 coroutine object / frame / resume machinery

而这正好是 CinderX JIT 在不同 ISA 上差异最明显的一块。

### 5.1 `RETURN_GENERATOR` 在 JIT 中不是普通返回，而是 `InitialYield`

在：

- `/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp`

`RETURN_GENERATOR` 会被 lowering 成 `InitialYield`，不是普通的 `RETURN_VALUE`。

这意味着每个递归 `fibonacci()` 调用，JIT 都要走 generator/coroutine 专用的 frame 与 resume 机制。

### 5.2 generator resume 入口在 AArch64 上比 x86_64 长得多

在：

- `/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/gen_asm.cpp`

x86_64 版 resume 入口主要是：

1. `mov gen->gi_jit_data`
2. `mov [rbp+disp]` / `mov scratch`
3. `jmp [scratch+resume_target_offset]`

AArch64 版则大量使用：

1. `ldr(... ptr_resolve(...))`
2. `str(... ptr_resolve(...))`
3. 再 `ldr resume_target`
4. `br reg`

也就是说，resume 入口的每个“从 generator footer 取字段 / 写字段”的动作，在 AArch64 上都更像一串小序列，而不是 x86_64 常见的一条内存操作。

对于 `coroutines` 这种递归 await benchmark，这个差异会被放大，因为：

1. coroutine 创建非常多
2. resume / suspend 非常频繁
3. 每次递归层级转换都要碰 generator/coro frame 元数据

### 5.3 TLS / `PyThreadState` 访问会反复出现在 coroutine-heavy JIT 路径

在：

- `/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/frame_asm.cpp`

x86_64:

- 可以 `mov reg, %fs:offset`

AArch64:

- `mrs TPIDR_EL0`
- 再 `ldr [tpidr_el0 + offset]`

如果一个 benchmark 是数值密集型，这类成本可能被计算吞掉；但 `coroutines` 主要是对象/状态机/控制流，这种“每次取 thread state 更重一点”的差异更容易浮到前台。

## 6. 为什么是“比值从 0.8 变 0.6”，而不是简单两边一起降

现在可以把因果链收束成一句更精确的话：

> `coroutines` 从 CPython 切到 CinderX 后，热路径新增的不是纯算术，而是 coroutine 类型兼容、awaitable helper 扩张、generator/coroutine resume 机制和 frame 元数据操作。这类新增工作在 x86_64 上也会变慢，但在 Arm/AArch64 上会因为更长的 helper 调用链、更重的 TLS 访问、更受限的地址模式和更多 `ptr_resolve()` 产生更高的相对损失，所以 Arm/AMD 的相对比值进一步恶化。

也就是：

1. **CPython 基准分支的 0.8**
   - 两边都在跑相对精简的 CPython coroutine helper
   - Arm 已经比 AMD 慢，但差距还没有被 CinderX 特有路径放大到极致

2. **切到 CinderX 后的 0.6**
   - 解释器路径新增了 JIT coroutine-aware helper
   - JIT 路径保留了 coroutine 专项检查而不是完全消除
   - Arm 在这些新增路径上的单位成本更高
   - 所以新增成本更多地“压”在 Arm 上，而不是平均分布到两个平台

换句话说：

- 不是“Arm 原来就慢，所以现在还是慢”
- 而是“CinderX 新增的工作类型，恰好是 Arm 相对更吃亏的那类工作”

## 7. 对 `coroutines` 的当前归因结论

按证据强度排序，`coroutines` 的 Arm/AMD 比值恶化最可能来自这 4 层叠加：

1. **解释器 helper 扩张**
   - `JitCoro_GetAwaitableIter`
   - `Ci_PyEval_GetAwaitable`
   - exact type 检查链更长

2. **JIT await lowering 保留了 coroutine-aware 结构**
   - `CallCFunc<JitCoro_GetAwaitableIter>`
   - `CondBranchCheckType`
   - `CallCFunc<JitGen_yf>`
   - `RaiseStatic`

3. **AArch64 generator/coroutine resume codegen 更重**
   - `ptr_resolve()`
   - `ldr/str` 序列更多
   - indirect branch 前的准备更长

4. **AArch64 thread state / frame metadata 访问更贵**
   - `TPIDR_EL0` 路径
   - 限制更强的 addressing mode

## 8. 下一步最值得验证的点

如果后续要把这份静态归因再推进到“最小验证脚本”，`coroutines` 最值得先验证的是：

1. 关闭 JIT，仅保留解释器，比较 `coroutines`
   - 如果比值已经明显恶化，说明 helper 扩张本身就是主因之一

2. 在 CinderX 上关闭 lightweight frames
   - 看 `coroutines` 比值是否回升

3. 对 `JitCoro_GetAwaitableIter` / `Ci_PyEval_GetAwaitable` 做更细的样本插桩
   - 统计调用频率与失败/慢路径比例

4. 导出 `coroutines` 的 JIT HIR/LIR
   - 确认 `GET_AWAITABLE` 和 `InitialYield` 相关 block 数量与 guard 数量

## 一句话结论

`coroutines` 的平台比值从 `0.8` 掉到 `0.6`，核心不是“Arm 泛泛地比 x86 慢”，而是：

**CinderX 把这个 benchmark 的热路径从 CPython 的相对精简 coroutine helper，改成了更重的 coroutine-aware helper + JIT coroutine runtime，而这些新增工作在 AArch64 上会被放大得比 x86_64 更厉害。**
