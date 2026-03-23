# CinderX 技术栈文档

本文基于以下文件梳理 CinderX 的技术栈与工程实践：`CMakeLists.txt`、`setup.py`、`pyproject.toml`、`README.md`。

## 1. 编程语言

### 1.1 主要语言
- **C/C++（核心运行时与编译器实现）**
  - `CMakeLists.txt` 中 `set(CMAKE_CXX_STANDARD 20)`，说明 C++ 代码按 **C++20** 标准编译。
  - `CMakeLists.txt` 通过 `file(GLOB_RECURSE ...)` 构建多个模块（如 `cinderx/Common/*.cpp`、`cinderx/Jit/*.cpp`、`cinderx/StaticPython/*.c`、`cinderx/Interpreter/*.c`）。
- **Python（构建编排、打包、用户 API）**
  - `setup.py` 负责 build/pgo/lto 逻辑、CMake 调用、wheel/sdist 打包。
  - `README.md` 展示了 Python 侧 JIT API（如 `cinderx.jit.auto()`、`compile_after_n_calls()`）。

### 1.2 语言分工建议（开发参考）
- 新增执行引擎/优化 pass：优先在 C/C++ 层（`cinderx/Jit`、`cinderx/Interpreter`）完成。
- 新增对外配置或易用接口：优先在 Python 层补充入口与封装（`cinderx/PythonLib`）。

## 2. 运行时与平台

### 2.1 Python 版本支持
- `pyproject.toml`：`requires-python = ">= 3.14.0, < 3.16"`。
- `README.md`：要求 **Python 3.14.3+**，并指出 3.14 是首个支持的 stock CPython 版本。
- `CMakeLists.txt` 与 `setup.py` 都会把当前解释器版本传入构建（`PY_VERSION`），并且对 `3.12/3.14/3.15` 有条件分支。

### 2.2 操作系统支持
- `README.md` 与 `pyproject.toml` classifier 均指向 **Linux** 为主支持平台。
- `README.md`：
  - Linux（x86_64）为主目标。
  - macOS 可构建/导入，但多数功能运行时关闭。
  - Windows 暂不支持。
- `CMakeLists.txt`：`if (${CMAKE_SYSTEM_NAME} MATCHES "Darwin")` 识别 macOS，且对 macOS 启用 `-undefined dynamic_lookup` 兼容选项。

### 2.3 CPU 架构与编译器
- `README.md`：明确 Linux **x86_64**。
- `setup.py`：
  - 编译器策略优先 GCC（要求 `MIN_GCC_VERSION = 13`），否则回退 Clang。
  - `README.md` 也给出推荐：GCC 13+ 或 Clang 18+。
- `setup.py` 中 `should_enable_adaptive_static_python()` / `should_enable_lightweight_frames()` 显示部分特性在 **ARM64/AArch64 + Python 3.14** 下默认开启。

## 3. 构建系统

### 3.1 构建总体链路（setuptools + CMake）
1. `pyproject.toml` 指定构建后端：`setuptools.build_meta`。
2. `setup.py` 定义 `CMakeExtension(name="_cinderx")`。
3. `BuildExt.run()` 识别 `CMakeExtension` 后调用 `_run_cmake()`：
   - 通过 `cmake -B <build_dir> <source_root>` 配置；
   - 再通过 `cmake --build` 编译。
4. `CMakeLists.txt` 将各子模块编译并链接为共享库 `_cinderx.so`。

这意味着：**Python 打包负责流程控制，CMake 负责原生代码编译与链接**。

### 3.2 CMake 工作原理（本项目语境）
- 在 `CMakeLists.txt` 中：
  - 设置编译标准与通用编译宏/告警参数；
  - 通过 `option(...)` 控制特性（如 `ENABLE_STATIC_PYTHON`、`ENABLE_INTERPRETER_LOOP`、`ENABLE_PARALLEL_GC`）；
  - `find_package(Python ... Development.Module REQUIRED)` 绑定当前 Python 头文件与模块链接信息；
  - 使用 `FetchContent` 拉取第三方依赖；
  - 将各目录源码编译为中间库（`common`、`interpreter`、`jit` 等），最终链接 `_cinderx.so`。

### 3.3 PGO/LTO 机制
- `setup.py` 通过环境变量控制：
  - `CINDERX_ENABLE_PGO=1`：触发三阶段 PGO（instrument → workload → optimize）；
  - `CINDERX_ENABLE_LTO=1`：向 CMake 传 `-DENABLE_LTO=ON`。
- `CMakeLists.txt` 具体处理编译器参数：
  - Clang 与 GCC 分别设置不同 PGO/LTO flags；
  - LTO 在 Linux 才允许；
  - Clang PGO 需要 `llvm-profdata` 合并 profile。

## 4. 核心框架（IR / JIT / 代码生成）

### 4.1 IR 分层
- 从源码组织可见 JIT 子系统下存在清晰分层：
  - `cinderx/Jit/hir/`（高层 IR，优化与分析 pass）
  - `cinderx/Jit/lir/`（低层 IR，寄存器分配、重写、校验）
  - `cinderx/Jit/codegen/`（最终机器码生成）
- `CMakeLists.txt` 通过 `file(GLOB_RECURSE JIT_SOURCES ...)` 将 `cinderx/Jit/*.cpp/*.c` 全量纳入 `jit` 库。

### 4.2 JIT 编译管线（工程视角）
- `README.md` 的对外语义：
  - 追踪热点函数调用频次；
  - 将热点 Python 字节码 JIT 为本地机器码。
- 从目录结构可推断的内部路径：
  - 字节码/运行时信息进入 HIR；
  - 经 HIR 优化后下沉 LIR；
  - LIR 经寄存器分配与指令选择后进入 codegen；
  - 产出架构相关机器码（见 `cinderx/Jit/codegen/arch/x86_64.cpp`、`.../aarch64.cpp`）。

### 4.3 代码生成与运行时衔接
- `CMakeLists.txt` 中 `jit` 会与 `interpreter`、`asmjit::asmjit`、`fmt::fmt` 链接，说明 JIT 与解释器紧密协作。
- 最终 `_cinderx.so` 统一链接 `jit`、`interpreter`、`static-python`、`common` 等组件，Python 导入时一次性加载核心能力。

## 5. 依赖库

`CMakeLists.txt` 使用 `FetchContent`/`find_package` 管理三方依赖：

- **asmjit**：JIT 汇编生成基础设施。
- **fmt**：高性能格式化输出。
- **parallel-hashmap**：高性能哈希容器实现。
- **usdt**：USDT tracing 相关支持（Linux 观测能力）。
- **zlib**：优先系统包，找不到则自动拉取源码构建。

开发注意点：
- 依赖版本和 hash 在 `CMakeLists.txt` 固定，确保可复现构建；
- 供应链升级时应同步更新 URL_HASH，并在 Linux 主目标环境验证 ABI/性能回归。

## 6. 打包与发布（PyPI）

### 6.1 包管理与元数据
- `pyproject.toml` 定义 PEP 517 构建后端与项目元数据。
- `setup.py` 中：
  - `name="cinderx"`；
  - `version=compute_package_version()`；
  - `packages=find_packages(where="cinderx/PythonLib", ...)`。

### 6.2 版本号策略
- `setup.py::compute_package_version()` 使用 UTC 日期生成版本：`YYYY.MM.DD.PP`。
- 支持通过 `CINDERX_VERSION_PATCH` 覆盖当日 patch 序号。
- 从 sdist 安装时若存在 `PKG-INFO`，优先使用其 `Version`，确保与发布产物一致。

### 6.3 CI 构建矩阵与发布形态
- `pyproject.toml` 的 `tool.cibuildwheel`：
  - 构建目标：`cp314-manylinux_x86_64`、`cp314-musllinux_x86_64`；
  - 默认开启 `CINDERX_ENABLE_PGO=1` 与 `CINDERX_ENABLE_LTO=1`。
- 对外分发以 PyPI wheel 为主（`README.md` 指明可 `pip install cinderx`，且每周发布）。

### 6.4 典型发布流程（可操作）
1. 在 Linux x86_64 CI 环境触发 cibuildwheel。
2. 通过 `setup.py` 驱动 CMake 完成原生扩展编译。
3. 产出 manylinux/musllinux wheel 并执行基础导入与冒烟验证。
4. 上传至 PyPI，用户侧通过 `pip install cinderx` 获取。

---

## 附：开发者快速判断清单
- 想确认 Python 支持范围：先看 `pyproject.toml` 的 `requires-python`。
- 想确认平台/编译器约束：看 `README.md` Requirements + `setup.py` 编译器选择逻辑。
- 想调整构建优化：看 `setup.py` 的 `CINDERX_ENABLE_PGO/LTO` 与 `CMakeLists.txt` 的 `ENABLE_PGO_*`、`ENABLE_LTO`。
- 想追 JIT 管线：从 `cinderx/Jit/hir` → `cinderx/Jit/lir` → `cinderx/Jit/codegen` 阅读。
