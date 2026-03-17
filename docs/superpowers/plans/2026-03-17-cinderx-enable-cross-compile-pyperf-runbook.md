# CinderX 启用、交叉编译与 PyPerformance 运行流程

> 目标：把这次实际使用过的 3 条流程固化下来：
> 1. 怎样在 CPython 环境里启用 CinderX / CinderX JIT
> 2. 怎样做 Arm / x86_64 交叉编译与反汇编分析
> 3. 怎样运行本地与远端的 pyperformance

---

## 1. 适用范围

这份 runbook 只记录本仓库里已经验证过、并且和当前实验流程一致的做法：

- 本地 macOS Arm 快速验证
- 远端 Linux Arm 正式构建与 pyperformance
- 使用 `gcc-15/g++-15` 的本地构建
- 使用 `aarch64-linux-gnu-gcc` / `x86_64-linux-gnu-gcc` 做静态机器码近似分析

这份文档不覆盖：

- 线上部署
- 非 Python 3.14 的完整兼容矩阵
- JIT runtime dump 的完整工作流

---

## 2. 环境约定

### 2.1 本地仓库

- CinderX 仓库：
  - `/Users/luchen/Repo/cinderx`
- pyperformance 仓库：
  - `/Users/luchen/Repo/pyperformance`
- CPython 基准仓库：
  - `/Users/luchen/Repo/cpython`

### 2.2 本地 Python / venv

这次本地 quick validation 使用的是：

- 本地 venv：
  - `/tmp/cinderx314-local`
- 解释器：
  - `/tmp/cinderx314-local/bin/python`

### 2.3 远端 Linux Arm

这次远端正式流程使用的是：

- 工作目录：
  - `/root/work/cinderx-main`
- incoming 目录：
  - `/root/work/incoming`
- Python 3.14：
  - `/opt/python-3.14/bin/python3.14`
- driver venv：
  - `/root/venv-cinderx314`

---

## 3. 在 CPython 环境里启用 CinderX

这里的“启用 CinderX”分成两层：

1. 让一个普通 CPython 解释器能够 `import cinderx`
2. 在这个解释器里显式启用 `cinderx.jit`

### 3.1 本地 macOS Arm：editable install

我们这次本地是直接把 CinderX 作为扩展安装进 CPython venv 里。

如果还没有 venv，先创建：

```bash
python3.14 -m venv /tmp/cinderx314-local
```

进入仓库并安装：

```bash
cd /Users/luchen/Repo/cinderx

ENABLE_STATIC_PYTHON=0 \
ENABLE_ADAPTIVE_STATIC_PYTHON=0 \
ENABLE_LIGHTWEIGHT_FRAMES=0 \
CC=gcc-15 \
CXX=g++-15 \
/tmp/cinderx314-local/bin/python -m pip install -e . --no-build-isolation
```

说明：

- 本地 macOS Arm quick validation 时，我们默认关掉：
  - `ENABLE_STATIC_PYTHON`
  - `ENABLE_ADAPTIVE_STATIC_PYTHON`
  - `ENABLE_LIGHTWEIGHT_FRAMES`
- 这是为了：
  - 避免本地 Darwin 路径掺入额外的 Static Python / lightweight frames 变量
  - 让本地 pyperformance 更专注于 JIT 方向筛选

### 3.2 本地最小 smoke：确认 CinderX 和 JIT 真正可用

最小 smoke 命令：

```bash
cd /Users/luchen/Repo/cinderx

PYTHONPATH=cinderx/PythonLib /tmp/cinderx314-local/bin/python - <<'PY'
import cinderx
import cinderx.jit as jit

assert cinderx.is_initialized()
jit.enable()

def f(n: int) -> int:
    s = 0
    for i in range(n):
        s += i
    return s

assert jit.force_compile(f)
assert jit.is_jit_compiled(f)
print("cinderx-ok", jit.get_compiled_size(f))
PY
```

如果要跑仓库里现成的 quick test：

```bash
cd /Users/luchen/Repo/cinderx

PYTHONPYCACHEPREFIX=/tmp/codex-pycache \
PYTHONPATH=cinderx/PythonLib \
/tmp/cinderx314-local/bin/python -m unittest \
  test_cinderx.test_oss_quick -v
```

### 3.3 自动启用方式：`sitecustomize.py`

仓库里最基础的自动加载入口是：

- [sitecustomize.py](/Users/luchen/Repo/cinderx/cinderx/PythonBin/sitecustomize.py)

它的内容很简单：

```python
import cinderx
```

也就是说，如果把这个文件放到启动路径上，解释器启动时就会先加载 CinderX。

### 3.4 远端 Linux Arm：wheel 安装 + smoke

远端正式流程不是本地 editable install，而是：

1. 构建 wheel
2. 安装进 driver venv
3. 安装进 pyperformance venv
4. 通过 smoke 验证 JIT 真正生效

仓库里这条标准流程已经固化在：

- [remote_update_build_test.sh](/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh)

典型调用：

```bash
INCOMING_DIR=/root/work/incoming \
WORKDIR=/root/work/cinderx-main \
PYTHON=/opt/python-3.14/bin/python3.14 \
DRIVER_VENV=/root/venv-cinderx314 \
BENCH=richards \
AUTOJIT=50 \
PARALLEL=1 \
SKIP_PYPERF=0 \
RECREATE_PYPERF_VENV=1 \
/root/work/incoming/remote_update_build_test.sh
```

这个脚本会：

1. 解压同步过来的源码包
2. 构建 wheel
3. 安装到 `/root/venv-cinderx314`
4. 创建 / 复用 pyperformance venv
5. 往 pyperformance venv 写入 `sitecustomize.py`
6. 跑 smoke 与 pyperformance gate

### 3.5 远端 smoke：如何确认不是“JIT 开关开了但其实没编译”

`remote_update_build_test.sh` 里已经内置了一段比较可靠的 smoke：

1. 先让函数解释执行一段时间，确认 interpreted call count 增长
2. 再 `force_compile()`
3. 再重复运行，确认 interpreted call count 不再增长

关键日志特征是：

```text
jit-effective-ok compiled_size ...
```

这比只看 `jit.enable()` 更可靠，因为它验证的是：

- 代码真的被编译了
- 编译后的代码真的被执行了

---

## 4. 交叉编译与反汇编

这部分的目标不是生成最终 JIT runtime 机器码，而是做“源码到目标 ISA 的近机器码分析”。

### 4.1 我们实际用过的工具

- `aarch64-linux-gnu-gcc 15.2.0`
- `x86_64-linux-gnu-gcc 15.2.0`
- `aarch64-linux-gnu-objdump`
- `x86_64-linux-gnu-objdump`

这套工具链在这轮分析里主要用于：

- 把最小 C/C++ 探针编成目标文件
- 再反汇编观察：
  - TLS 访问
  - helper 调用
  - attr/container helper 分派
  - generator / coroutine 相关局部代码形状

### 4.2 典型命令模板

假设有一个最小探针 `probe.c`：

```bash
aarch64-linux-gnu-gcc -O3 -c probe.c -o probe.aarch64.o
aarch64-linux-gnu-objdump -dr probe.aarch64.o > probe.aarch64.objdump.txt

x86_64-linux-gnu-gcc -O3 -c probe.c -o probe.x86_64.o
x86_64-linux-gnu-objdump -dr probe.x86_64.o > probe.x86_64.objdump.txt
```

如果探针是 C++：

```bash
aarch64-linux-gnu-g++ -O3 -c probe.cpp -o probe.aarch64.o
aarch64-linux-gnu-objdump -dr probe.aarch64.o > probe.aarch64.objdump.txt

x86_64-linux-gnu-g++ -O3 -c probe.cpp -o probe.x86_64.o
x86_64-linux-gnu-objdump -dr probe.x86_64.o > probe.x86_64.objdump.txt
```

### 4.3 这一流程适合分析什么

适合：

- `PyThreadState` / TLS 访问
- `PyDict_Check` / `Ci_CheckedDict_Check` 这类 helper 分派链
- `JitCoro_GetAwaitableIter` 这类额外 coroutine helper
- `LOAD_ATTR_INSTANCE_VALUE` 对应的地址生成与 guard 形状

不适合：

- 直接代表最终 JIT runtime 机器码
- 直接替代远端 Linux Arm 上的真实 perf / disassembly

### 4.4 这次分析里的使用方式

我们这轮 deep dive 里，交叉编译主要是为了回答：

- “同一份新增逻辑，为什么在 Arm 上更伤？”
- “AArch64 比 x86_64 多出来的调用、分支、load/store 到底长什么样？”

所以交叉编译的定位是：

- 机器码近似证据
- 不是最终运行时真值

---

## 5. 运行 pyperformance

这部分分成两条：

1. 本地 macOS Arm quick validation
2. 远端 Linux Arm 正式跑数

## 5.1 本地 quick validation：`bench_pyperf_direct.py`

最底层的本地 direct runner 是：

- [bench_pyperf_direct.py](/Users/luchen/Repo/cinderx/scripts/arm/bench_pyperf_direct.py)

它的特点：

- 直接加载某个 pyperformance benchmark 模块
- 显式指定 benchmark 函数
- 允许指定：
  - `compile-strategy`
  - `compile-names`
  - `prewarm-runs`
  - `samples`
  - `specialized-opcodes`

典型命令：

```bash
cd /Users/luchen/Repo/cinderx

/tmp/cinderx314-local/bin/python scripts/arm/bench_pyperf_direct.py \
  --module-path /Users/luchen/Repo/pyperformance/pyperformance/data-files/benchmarks/bm_generators/run_benchmark.py \
  --bench-func bench_generators \
  --bench-args-json "[1]" \
  --samples 3 \
  --prewarm-runs 1 \
  --compile-strategy all \
  --specialized-opcodes
```

输出会是一个 JSON，里面包括：

- `compiled_count`
- `compiled_qualnames`
- `median_wall_sec`
- `total_deopt_count`
- `top_deopts`

### 5.2 本地 quick validation：`run_local_pyperf_matrix.py`

在 direct runner 上面，我们又包了一层：

- [run_local_pyperf_matrix.py](/Users/luchen/Repo/cinderx/scripts/arm/run_local_pyperf_matrix.py)

它负责：

- 把 benchmark 名映射到 pyperformance 模块路径
- 注入实验开关环境变量
- 默认关掉本地 Darwin 上不需要的 Static Python 相关特性

本地 baseline 典型命令：

```bash
cd /Users/luchen/Repo/cinderx

/tmp/cinderx314-local/bin/python scripts/arm/run_local_pyperf_matrix.py \
  --pyperformance-root /Users/luchen/Repo/pyperformance \
  --benchmark coroutines \
  --mode baseline \
  --python /tmp/cinderx314-local/bin/python \
  --samples 1 \
  --prewarm-runs 0
```

它内部会默认注入：

```text
ENABLE_STATIC_PYTHON=0
ENABLE_ADAPTIVE_STATIC_PYTHON=0
ENABLE_LIGHTWEIGHT_FRAMES=0
```

这也是我们本地 quick validation 的标准口径。

### 5.3 远端 Linux Arm：标准 pyperformance 流程

远端正式跑数主要走：

- [remote_update_build_test.sh](/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh)

它会做两层 venv：

1. driver venv
   - `/root/venv-cinderx314`
2. pyperformance benchmark venv
   - 通过 `python -m pyperformance venv create/recreate` 创建

其中关键步骤是：

```bash
PYTHONJIT=0 python -m pyperformance venv create
PYTHONJIT=0 python -m pyperformance venv show
```

然后把 wheel 装进 pyperformance venv，并写入 `sitecustomize.py`，让 benchmark 子进程自动加载：

- `import cinderx.jit as jit`
- `jit.enable()`

### 5.4 远端 pyperformance 直跑

如果不走大脚本，也可以在远端 driver venv 里手工跑：

```bash
. /root/venv-cinderx314/bin/activate
python -m pyperformance run --debug-single-value -b richards -o /root/work/arm-sync/richards.json
```

如果要做 `python_startup` 的 autoload / no-autoload 对照，就需要手工切 pyperformance venv 里的 `sitecustomize.py`。

### 5.5 常见坑

#### 1. pyperformance venv 不是 driver venv

这轮已经反复踩过一次，必须分清：

- `/root/venv-cinderx314`
- `/root/work/cinderx-main/venv/...`

如果装错地方，会出现：

- 你以为更新了 `_cinderx.so`
- 实际 benchmark 还在跑旧版本

#### 2. 本地 macOS Arm 数据只用于方向筛选

本地 quick validation 的定位是：

- 快速判断某个实验开关值不值得继续

不应用来直接代表：

- Linux Arm 正式性能结论

#### 3. `sitecustomize.py` 会改变 benchmark 启动路径

远端 pyperformance venv 写入的 `sitecustomize.py` 会自动：

- `import cinderx.jit`
- `jit.enable()`

所以像 `python_startup` 这样的 benchmark，必须显式区分：

- autoload
- no-autoload

#### 4. 交叉编译不是最终 runtime 机器码

`aarch64-linux-gnu-gcc` / `x86_64-linux-gnu-gcc` 这条线的价值是：

- 做 Arm vs x86_64 的静态代码形状比较

不是：

- 代替目标机上的真实 JIT 机器码采样

---

## 6. 推荐的最小工作流

如果从零开始复现这次流程，建议顺序是：

1. 本地用 `gcc-15/g++-15` 做 editable install
2. 本地跑 `test_oss_quick`
3. 本地跑 `bench_pyperf_direct.py`
4. 本地跑 `run_local_pyperf_matrix.py`
5. 需要近机器码分析时，用交叉编译 + `objdump`
6. 正式性能数据统一走远端 `remote_update_build_test.sh`

这样能把：

- 构建问题
- JIT 可用性问题
- 本地 benchmark 驱动问题
- 远端 pyperformance 问题

拆成清晰的 4 层，而不是一开始就把所有变量混在一起。
