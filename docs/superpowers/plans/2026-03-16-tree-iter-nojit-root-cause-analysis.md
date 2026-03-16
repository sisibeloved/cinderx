# `Tree.__iter__` nojit 根因分析

## 目标

解释为什么在 `bm_generators` 里，对 `Tree.__iter__` 做函数级 `nojitlist` 之后：

- 主用例 `generators` 提升到 `1.1922x`
- 固定多用例集几何平均提升到 `1.0202x`

也就是：

- `Tree.__iter__` 的 JIT 版本，当前明显比解释器版本更差
- 而且这不是只对主用例有利的偶然现象

## benchmark 代码形状

源码：

- `/Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_generators/run_benchmark.py`

热点函数非常集中：

```python
def __iter__(self):
    if self.left:
        yield from self.left
    yield self.value
    if self.right:
        yield from self.right
```

这意味着 `Tree.__iter__` 的成本主要由 4 类操作组成：

1. `self.left/self.value/self.right` 字段读取
2. 两个 truthiness 分支：`if self.left` / `if self.right`
3. 两个 `yield from`
4. generator resume / suspend / refcount

## 已排除的方向

### 1. 不是 compile coverage 问题

`Tree.__iter__` 实际上已经会被编译。

之前 `bench_pyperf_direct.py` 里看不到它，是统计口径问题：

- `Tree.__iter__` 会在前一个候选函数依赖编译时被带上
- 等轮到它自己 `force_compile()` 时，返回值已经是 `False`
- 但 `jit.is_jit_compiled(Tree.__iter__) == True`

所以根因不在“没编译上”，而在“编译上了但不够快”。

### 2. 不是 attr lowering 没命中

真实 benchmark 模块里，`Tree.__iter__` 当前 HIR 摘要是：

- `compiled_size = 2736`
- `YieldValue = 1`
- `YieldFrom = 2`
- `LoadField = 20`
- `CheckField = 5`
- `LoadAttrCached = 0`
- `Decref = 10`
- `BatchDecref = 0`

这里最关键的是：

- `LoadAttrCached = 0`
- `LoadField/CheckField` 明显存在

这说明 generator 的字段访问已经走到了 field lowering，不是还卡在通用 attr helper。

### 3. 不是 `BatchDecref` 漏命中

`optimizeLongDecrefRuns()` 的阈值是连续 `Decref >= 4` 才会合并：

- `/Users/luchen/Repo/cinderx/cinderx/Jit/hir/refcount_insertion.cpp`

而 `Tree.__iter__` 的连续 decref run 只有：

- `[1, 1, 2, 1, 1, 3, 1]`

所以当前 `BatchDecref = 0` 不是漏优化，而是压根没达到阈值。

### 4. 不是简单的“`yield from` 一定比别的写法差”

对照实验里，把：

- `yield from self.left`

改成：

- `for x in self.left: yield x`

虽然让 `compiled_size` 下降了，但 wall time 反而更差。

所以这里不能把问题简化成“`yield from` lowering 太重，只要绕开就能更快”。

## 当前最像真的根因

## 根因 1：truthiness 路径比 `is not None` 版本更重

当前 `if self.left` 的 HIR 形状接近：

- `CheckField`
- `IsTruthy`
- `Decref`
- `CondBranch`

而显式写成 `if self.left is not None` 时，HIR 变成：

- `CheckField`
- `LoadConst(None)`
- `PrimitiveCompare`
- `CondBranch`

对照实验结果：

| 形状 | compiled_size | `IsTruthy` | `Decref` | 相对原始 truthy speedup |
|---|---:|---:|---:|---:|
| `if self.left` | `2736` | `2` | `10` | `1.0000x` |
| `if self.left is not None` | `2616` | `0` | `8` | `1.0079x` |

这说明：

- 当前 generator 里的 `Tree | None` truthiness 没有被收窄到更便宜的 `None` 比较
- 这会额外制造 `IsTruthy` 和关联的 refcount 成本
- 这条成本虽然不是全部，但是真实存在，而且已经被局部对照实验验证过

对应源码入口最值得看：

- `/Users/luchen/Repo/cinderx/cinderx/Jit/hir/simplify.cpp`
  - `simplifyIsTruthy()`

这里当前只会对：

- trusted 常量对象
- `bool`
- 有长度的对象
- `int`

做更强的收窄；并没有把“nullable object field 的 truthiness”识别成 `x is not None` 形状。

## 根因 2：generator resume / `yield from` 路径在 AArch64 上固定成本偏高

`Tree.__iter__` 不是普通函数，它每次遍历都会大量经过：

- suspend
- resume
- `yield from`
- generator frame linkage

对应的 AArch64 resume 入口在：

- `/Users/luchen/Repo/cinderx/cinderx/Jit/codegen/gen_asm.cpp`

关键路径包括：

- 从 generator 里取 `gi_jit_data`
- 写回 `linkAddress`
- 写回 `returnAddress`
- 保存原始 frame pointer
- 读取并清空 `yieldPoint`
- 再跳到 `resume target`

这条路径在 AArch64 上明显是多段 `ldr/str + ptr_resolve + br` 链。即使没有 deopt，它也会为每次 resume 带来一笔不可忽略的固定成本。

`Tree.__iter__` 恰好是：

- 递归 generator
- 两处 `yield from`
- 遍历整棵大树

所以它会把这种 resume 固定成本反复放大。

换句话说：

- JIT 对普通算术/字段访问能赚回来的东西
- 在 `Tree.__iter__` 这里，很可能被 generator resume 本身吃掉了

## 根因 3：JIT 已经把 attr 降低了，但“代码更低层”不等于“整体更快”

`Tree.__iter__` 的一个重要反直觉点是：

- 把 `left/right` 提前缓存到局部变量后
- `LoadField/CheckField/Decref` 都减少了
- `compiled_size` 也下降了

但 wall time 反而更差。

这说明这个函数不是单纯受“字段读取次数”支配，而是受更高层的 generator 执行结构支配：

- 代码大小
- suspend/resume 边界
- truthiness lowering
- `yield from` 状态切换

所以 `Tree.__iter__` 被 `nojit` 后更快，并不是因为解释器的字段访问更优，而更像是：

- 解释器路径避免了 JIT generator runtime 的一整层固定成本
- 而当前 JIT 在这个函数身上，并没有足够多的数值或对象访问收益去抵消这层成本

## 当前最可信的因果链

`Tree.__iter__` 当前更像是下面这条组合问题：

1. 字段访问已经被 JIT 优化了，但收益有限
2. truthiness 仍然走了偏重的 `IsTruthy` 路径
3. 两个 `yield from` 让 generator resume/suspend 成本被反复放大
4. `Decref = 10` 说明 refcount 压力仍然不低
5. 最终 JIT 节省下来的 attr 成本，不足以覆盖 generator runtime 的固定开销

这也解释了为什么函数级禁 JIT 反而会显著变快：

- 解释器版本没有 JIT generator 这套额外 machinery
- 而这个 benchmark 又刚好是 generator machinery 占主导的形状

## 下一步最值得做的实验

### 1. `IsTruthy -> is not None` 专项实验

目标：

- 只对“来自稳定 object field、且 value shape 是 `T | None`”的 truthiness
- 在 JIT 里收成 `PrimitiveCompare(None)` 形状

预期：

- `Tree.__iter__` 的 `IsTruthy` 从 `2 -> 0`
- `Decref` 再下降一点
- `compiled_size` 继续低于当前 `2616`

这是当前最接近“可精确命中根因”的 JIT 优化方向。

### 2. generator resume 固定成本拆分实验

目标：

- 区分“字段访问优化收益”与“generator runtime 固定成本”

做法：

- 继续保留 `Tree.__iter__` 的 field lowering
- 但在同形状 toy benchmark 上减少 `yield from` 层级或 resume 次数
- 看 wall time 是否立刻改善

如果改善明显，就能进一步坐实：

- 真正的问题更偏 generator runtime
- 而不是单个 HIR opcode 数量

## 当前结论

`Tree.__iter__` 被 `nojit` 后明显更快，不是因为它没有被编译，也不是因为 attr lowering 失效，而是因为：

- 当前 JIT 在这个函数上只拿到了有限的字段访问收益
- 却仍然承担了 truthiness、`yield from`、resume/suspend、refcount 这些 generator 特有固定成本

所以这条函数当前是一个非常典型的：

- **“JIT 已介入，但收益结构与成本结构不匹配”**

的案例。
