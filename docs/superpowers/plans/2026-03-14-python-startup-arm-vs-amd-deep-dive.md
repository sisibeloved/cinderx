# `python_startup`：为什么这几乎不是“执行内核”问题，而是 CinderX 启动注入成本问题

## 1. benchmark 本体在做什么

`bm_python_startup` 非常直接：

- 默认：`python -c pass`
- `--no-site`：`python -S -c pass`
- `--exit`：`python -c "import os; os._exit(0)"`

所以它几乎不测 steady-state 执行。  
它测的是：

- 解释器进程启动
- `site` / `sitecustomize`
- import 初始化
- 扩展模块加载

## 2. 基准 CPython 分支上的执行链

在基准 CPython 上，`python -c pass` 的成本主要来自：

- 进程启动
- Python 初始化
- `site` 模块
- `-c` 命令执行与退出

这时 Arm/AMD 比值更多反映：

- 平台本身对初始化代码、动态链接和 import 的差异

## 3. 切到 CinderX 后，代码路径发生了什么变化

这里的差异不是推测，而是当前仓库脚本里明写了。

### 3.1 pyperformance worker venv 会写 `sitecustomize.py`

`scripts/arm/remote_update_build_test.sh` 会往 pyperformance venv 写入：

- 自动加载 CinderX 的 `sitecustomize.py`

脚本内容明确会在启动期执行：

- `import cinderx.jit as jit`
- 如果未禁用则 `jit.enable()`

这意味着 `python_startup` 在 CinderX 环境里并不是“跑一个空 Python”，而是“启动时先引入一套额外 runtime/JIT glue”。

### 3.2 `cinderx/PythonBin/sitecustomize.py` 也会导入 `cinderx`

仓库里的 `sitecustomize.py` 本身就是：

- `import cinderx`

因此启动路径天然带有额外 import 成本。

### 3.3 Arm 默认还会启用更多功能开关

`setup.py` 明确写着，3.14 的 Arm 默认开启：

- `ENABLE_ADAPTIVE_STATIC_PYTHON`
- `ENABLE_LIGHTWEIGHT_FRAMES`

所以这里的“平台差异”不仅是 ISA 差异，还有默认功能路径差异。

## 4. 静态机器码为什么不是这里的主视角

对 `python_startup` 来说，最关键的不是某个热点函数的几条汇编，而是：

- import 链长度
- 扩展模块初始化
- 动态链接器工作量
- 运行时全局初始化

也就是说，它更像：

- “启动路径是否多了一整段工作”

而不像：

- “某个热点循环在 Arm 上生成了更差机器码”

所以这个 benchmark 不应该用和 `raytrace` 一样的分析框架去看。

## 5. JIT 侧如何理解

`python_startup` 的 JIT 问题不是“JIT 编译了哪段热点”，而是：

- 启动时是否导入了 JIT
- JIT 模块初始化做了哪些事情

从脚本看，pyperformance venv 的启动路径会：

- import `cinderx.jit`
- 在允许时调用 `jit.enable()`

因此这个 benchmark 的劣化，首先是“JIT 被自动注入到 startup path 里”，不是“JIT 运行时优化了哪些函数”。

## 6. 为什么 Arm/AMD 比值会从基准 CPython 切到 CinderX 后继续恶化

最合理的解释链是：

1. 基准 CPython 的 `python -c pass` 基本只量启动本身；
2. 切到 CinderX 后，benchmark startup path 被额外注入了 `sitecustomize -> import cinderx(.jit) -> jit.enable()`；
3. Arm 默认又开启了更多 CinderX 功能开关；
4. 这些新增成本和 steady-state 算法无关，而是纯启动固定成本；
5. 固定启动成本在 Arm 上的相对负担更高，因此平台比值会继续变差。

## 7. 结论

`python_startup` 必须单列，不应该和其他 benchmark 共用根因。  
它的最强解释不是：

- x86 有某个更好的执行优化

而是：

- CinderX 把启动路径本身改重了
- 且 Arm 默认特性开启更多

因此如果平台比值从基准 CPython 到 CinderX 明显恶化，`python_startup` 几乎可以直接判为：

- 启动注入成本
- import/JIT 初始化成本
- Arm 默认功能路径更重

