# 第一轮差异点分析结论

> 目标：基于当前仓库代码，先把最值得在隔离 Linux Arm 环境中验证的差异点钉实，再决定一键脚本该采哪些最小数据。

## 结论总览

当前分支相对上游 CPython，最值得优先验证的不是零散 benchmark 个案，而是 4 条共享差异链：

1. 解释器热路径被额外状态与分支污染。
2. Arm 默认开启了更多 CinderX 特性。
3. JIT 在 mixed numeric 小 helper 上有过明确历史问题。
4. pyperformance worker 启动时会自动注入 CinderX。

这 4 条链分别对应第一轮最小执行集中的：
- `coroutines`
- `richards`
- `raytrace`
- `python_startup`

---

## 1. 解释器热路径额外状态与分支

### 关键代码点

- `adaptive_enabled` 被加入 tail-call 解释器函数参数：
  [ceval_macros.h](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/ceval_macros.h#L75)
- PEP 523 hook 判断变为 “非空且不等于 `Ci_EvalFrame`”：
  [ceval_macros.h](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/ceval_macros.h#L170)
- `ADVANCE_ADAPTIVE_COUNTER` 变成条件执行：
  [ceval_macros.h](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/ceval_macros.h#L283)
- 每次调用会触发 call-count / adaptive 状态更新：
  [ceval_macros.h](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/Includes/ceval_macros.h#L443)

### 为什么它可能是 Arm 敏感的

这组差异不会只增加单一算术成本，而是会增加：
- 热路径上的参数传播
- 条件分支数量
- code-extra 访问
- 每次调用时的状态查询

这类成本更容易在高调用密度 benchmark 中放大，也更容易表现成 branch / icache 压力，而不是单纯 instructions 增加。

### 最相关 benchmark

- `richards`
- `richards_super`
- `go`
- `deltablue`
- `coroutines`

### 第一轮应采数据

- `interp_feature_matrix.sh` 四组合
- 若条件允许，再补：
  - `cycles`
  - `branches`
  - `branch-misses`

---

## 2. Arm 默认特性开启本身就是差异源

### 关键代码点

- 3.14 上 Arm 默认开启 adaptive static python：
  [setup.py](/Users/luchen/Repo/cinderx/setup.py#L137)
- 3.14 上 Arm 默认开启 lightweight frames：
  [setup.py](/Users/luchen/Repo/cinderx/setup.py#L152)
- 实际构建时写入：
  [setup.py](/Users/luchen/Repo/cinderx/setup.py#L513)
  [setup.py](/Users/luchen/Repo/cinderx/setup.py#L529)

### 为什么这条链优先级很高

这意味着你看到的“Arm 相对 AMD 差异”不一定全是 codegen 水平差距，也可能是：
- Arm 默认多开了功能
- AMD 默认没开同样的功能
- 最终表现成 Arm-only slowdown

所以第一轮不能直接把 Arm 慢理解成“Arm 代码生成差”，必须先用 feature matrix 把这层拆掉。

### 最相关 benchmark

- `coroutines`
- `richards`
- `richards_super`
- `go`
- `deltablue`
- `comprehensions`
- `nqueens`

### 第一轮应采数据

- feature matrix 四组合：
  - `1,1`
  - `1,0`
  - `0,1`
  - `0,0`

如果 `0,0` 显著更快，第一结论就该偏向 Arm 默认特性成本，而不是 JIT 专项问题。

---

## 3. `coroutines` 不是普通解释器 benchmark

### 关键代码点

- `_PyEval_GetANext` 被替换为 CinderX 版本：
  [borrowed-ceval.c.template](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/borrowed-ceval.c.template#L107)
- `_PyEval_GetAwaitable` 被替换为 CinderX 版本：
  [borrowed-ceval.c.template](/Users/luchen/Repo/cinderx/cinderx/Interpreter/3.14/borrowed-ceval.c.template#L121)
- 这里使用了：
  - `JitCoro_GetAwaitableIter`
  - `JitGen_yf`

### 含义

`coroutines` 不能只归到“解释器调用开销”。
它还有一条独立差异链：
- awaitable 获取逻辑不同
- coroutine already-awaited 检查逻辑不同
- 可能与 lightweight frame / JIT coroutine runtime 交互

### 第一结论

`coroutines` 的第一轮验证必须同时回答两件事：
- 它是不是和 `richards` 一样，主要是解释器 bookkeeping 成本
- 还是说它有独立的 coroutine/awaitable 路径成本

### 第一轮应采数据

- `interp_feature_matrix.sh` on `coroutines`
- 若可行，再补 `PYTHONJITLIGHTWEIGHTFRAME=0/1`

---

## 4. `raytrace` 的高优先级差异点已经很明确

### 关键代码点

- specialized numeric opcode 对 int guard 的策略：
  [builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp#L2139)

这里当前分支的策略非常明确：
- exact-int guard 只保留给有 backedge 的 code object
- float exact guard 仍然保留

### 含义

这说明当前分支已经显式地承认并修过一类历史问题：
- 小 helper mixed numeric 代码被过度 exact-int 特化
- 导致 deopt storm
- `raytrace` 是这个问题的典型样本

所以第一轮不该重新从零猜测 `raytrace`，而是该快速验证：
- 当前分支是否仍然在 `all` 模式下表现更差
- `top_deopts` 是否仍集中在 mixed numeric helper
- `backedge` 是否比 `all` 更稳

### 第一轮应采数据

- `bench_pyperf_direct.py`：
  - `none`
  - `all`
  - 若需要则 `backedge`

重点只看：
- `median_wall_sec`
- `compiled_count`
- `total_deopt_count`
- `top_deopts`

---

## 5. `generators` 目前不是第一轮主角，但差异点已经清楚

### 关键代码点

- 当前代码仍保留 generator 的 low-local 例外：
  [builder.cpp](/Users/luchen/Repo/cinderx/cinderx/Jit/hir/builder.cpp#L2876)

这里非常关键：
- 普通函数 low-local threshold 默认是 10
- generator 如果带 `kCoFlagsAnyGenerator`，直接返回 0

这说明之前的修复点仍然存在：
- `Tree.__iter__` 这类低 locals generator 不应因为 locals 少而失去 instance-value lowering

### 含义

`generators` 第一轮不需要优先跑，因为这条差异链已经相对明确：
- attr lowering 已修
- 剩余风险主要是 decref 展开

所以它更适合第二轮，而不是第一轮最小执行集。

---

## 6. `python_startup` 的主要差异链几乎可以直接判定

### 关键代码点

- pyperformance venv 中会动态写入 `sitecustomize.py`：
  [remote_update_build_test.sh](/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh#L221)
- 启动时，如果不在 skip 场景，就会：
  - `import cinderx.jit`
  - 并在未禁用时 `jit.enable()`
  [remote_update_build_test.sh](/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh#L296)

### 含义

`python_startup` 很可能首先测到的是：
- worker startup 期间自动导入 CinderX
- 启动时执行额外判断
- 可能触发 JIT 初始化路径

它并不是一个适合先拿来讨论 steady-state 执行质量的 benchmark。

### 第一轮应采数据

- `python_startup`：
  - `autoload`
  - `noautoload`
- `-X importtime`

如果这两组已经给出明显差距，第一轮就可以直接定性为启动注入成本。

---

## 7. 第一轮最值得验证的因果链

### `coroutines`
- 优先验证：
  - Arm 默认特性
  - coroutine 自定义 awaitable 路径

### `richards`
- 优先验证：
  - 解释器 bookkeeping / adaptive / call-count 结构成本

### `raytrace`
- 优先验证：
  - mixed numeric helper 过编译 / deopt

### `python_startup`
- 优先验证：
  - `sitecustomize` 自动加载与 `import cinderx.jit`

---

## 8. 对一键脚本设计的直接影响

基于这轮差异点分析，一键脚本不应该一上来就覆盖全部 benchmark。

第一轮 bundle 脚本只需要 4 个子任务：

1. `coroutines` 解释器 feature matrix
2. `richards` 解释器 feature matrix
3. `raytrace` direct-run `none/all/backedge`
4. `python_startup` autoload/noautoload + importtime

这样就能先回答：
- 是否主要是 Arm 默认特性
- 是否主要是解释器结构开销
- 是否主要是 JIT mixed numeric
- 是否主要是启动注入成本

在这 4 个结论没出来之前，不值得在隔离环境里大范围盲跑全部 benchmark。

