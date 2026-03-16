# NoJIT List 设计稿

## 目标

在现有 `jitlist` 白名单机制旁边新增一套对称的 `nojitlist` 黑名单机制，用于显式禁止指定函数或代码对象进入 JIT。

本轮目标不是立刻默认关闭 JIT，而是为性能实验提供一个稳定、可组合、可回退的禁用层，重点支持以下 benchmark：

- `generators`
- `coroutines`
- `comprehensions`
- `richards`
- `richards_super`
- `go`
- `deltablue`
- `nqueens`
- `raytrace`

## 设计原则

### 1. 语义复用 `jitlist`

`nojitlist` 复用 `jitlist` 的匹配格式和匹配逻辑：

- `module:qualname`
- `name@file:line`
- wildcard 行为与现有 `allow_jit_list_wildcards` 保持一致

这样可以最大限度复用已有实现和实验工具，不引入新的配置语言。

### 2. 独立存储，不污染现有白名单

不修改现有 `jitlist` 文件语义，不引入 `!entry` 这种反义语法。

新增：

- `NoJITList`
- `no_jit_list` module state
- 对应 Python API

这样 allow / deny 的语义边界更清楚，也方便实验时分别组合。

### 3. deny 优先于 allow

编译资格判断顺序调整为：

1. 先查 `nojitlist`
2. 命中则直接 `Ineligible`
3. 未命中再查 `jitlist`
4. 再走现有 eligibility 逻辑

这样即使某个函数已经在 `jitlist` 里，也可以被 `nojitlist` 明确压掉。

## API 设计

在现有 `cinderx.jit` API 旁新增：

- `append_nojit_list(entry: str) -> None`
- `read_nojit_list(path: str) -> None`
- `get_nojit_list() -> tuple[...] | None`

行为对齐：

- `append_nojit_list()`：追加单条 entry
- `read_nojit_list()`：读取整个文件
- `get_nojit_list()`：导出当前 deny 集合，格式尽量与 `get_jit_list()` 对称

不在这一轮新增复杂的删除、覆盖、优先级切换 API。

## C++ 实现落点

### 1. 数据结构

复用 `jit_list` 设计，新建一套：

- `cinderx/Jit/jit_list.h`
  - 新增 `NoJITList` 类型，或直接复用 `JITList` 接口实例化第二份状态
- `cinderx/Jit/jit_list.cpp`
  - 复用现有 parse / lookup 逻辑

### 2. ModuleState

在 module state 中新增：

- `std::unique_ptr<IJITList> no_jit_list`

要求：

- 生命周期与 `jit_list` 对齐
- 初始化和销毁逻辑明确

### 3. eligibility 判定

修改：

- `cinderx/Jit/pyjit.cpp`

核心变更：

- `getCompilationEligibility(BorrowedRef<PyFunctionObject>)`
- `getCompilationEligibility(BorrowedRef<> module_name, BorrowedRef<PyCodeObject>)`

判定顺序改为：

1. 基础前置条件不满足，直接 `Ineligible`
2. 如果 `no_jit_list` 命中，返回 `Ineligible`
3. 如果 `jit_list` 命中，返回 `JitListEligible`
4. 否则返回现有默认 eligibility

## Python 层 API 落点

修改：

- `cinderx/Jit/pyjit.cpp`
- `cinderx/PythonLib/cinderx/jit.py`

要求：

- 新 API 命名与 `jitlist` 对称
- 文档字符串清晰说明 deny 优先级更高
- 保持已有接口兼容，不影响现有脚本

## 实验粒度

### 1. 模块级禁用

例子：

- `bm_generators:*`
- `bm_raytrace:*`

用途：

- 快速验证“整个 benchmark 模块禁 JIT”是否能显著追回劣化

### 2. 函数级禁用

例子：

- `bm_raytrace:SimpleSurface.colourAt`
- `bm_generators:Tree.__iter__`
- `bm_go:UCTNode.best_child`

用途：

- 在模块级禁用有效后，进一步缩窄到真正拖后腿的热点函数

## 实验流程

### Phase 1: 基础能力验证

先只验证功能：

- `nojitlist` 能正确阻止 `force_compile`
- `is_jit_compiled` 在 deny 命中时保持 `False`
- `jitlist` 和 `nojitlist` 同时命中时，以 deny 为准

### Phase 2: 模块级性能筛选

对目标 benchmark，先跑模块级 deny：

- `generators`
- `coroutines`
- `comprehensions`
- `richards`
- `richards_super`
- `go`
- `deltablue`
- `nqueens`
- `raytrace`

记录：

- 主用例 `speed/delta`
- 固定 10 用例集几何平均

### Phase 3: 函数级收缩

只对模块级有明显正收益的 benchmark，继续做函数级 deny。

目标：

- 找到比“整模块禁 JIT”更细、而且几何平均更好的组合

## 成功标准

### 功能成功

- deny 命中后不再 JIT 编译目标函数/代码对象
- allow/deny 同时存在时，deny 优先
- 不影响未命中的函数正常编译

### 性能成功

按现有实验门槛：

- 单个 `nojitlist` 实验对象一行入表
- 主用例收益可见
- 固定 10 用例集几何平均 `> 1.0x` 才进入提交候选

## 风险

### 1. 模块级禁用过粗

整模块禁 JIT 可能追回某个主用例，但拖累其他 benchmark。

应对：

- 模块级只作为筛选手段
- 后续尽量收缩到函数级

### 2. nested code object 匹配不完整

某些 benchmark 的热点可能不是顶层函数，而是 nested code object。

应对：

- 复用现有 `lookupCode()` 路径
- 测试覆盖 nested function / code object deny

### 3. 与已有 jitlist 交互复杂

allow/deny 共存后，可能出现实验脚本误配。

应对：

- 明确 deny 优先
- 在 Python API 文档和测试中显式覆盖该规则

## 推荐实现顺序

1. 新增 `no_jit_list` 存储与 lookup
2. 新增 Python API
3. 接入 eligibility 优先级
4. 写基础功能测试
5. 跑模块级 deny 性能筛选
6. 再做函数级 deny 收缩
