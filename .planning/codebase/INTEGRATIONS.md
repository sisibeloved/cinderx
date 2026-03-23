# CinderX 集成点文档

## 1) CPython C-API / Internal API 集成点

### 1.1 深度依赖 CPython 内部头文件（非稳定 ABI）
- **证据**：`cinderx/Jit/pyjit.cpp:8-15`、`12` 引入 `internal/pycore_ceval.h`、`internal/pycore_shadow_frame.h`、`internal/pycore_pystate.h`、`internal/pycore_interp_structs.h`。
- **证据**：`CMakeLists.txt:37` 编译标志包含 `-DPy_BUILD_CORE -DPy_BUILD_CORE_MODULE`；`CMakeLists.txt:176` 将 `Include/internal` 纳入 include path。
- **意义**：CinderX 并非仅使用稳定 C-API，而是与 CPython 运行时内部结构紧耦合，版本升级成本较高。

### 1.2 JIT 初始化与 Python 模块/解释器状态绑定
- **证据**：`cinderx/Jit/pyjit.cpp:3689` 通过 `_Ci_CreateBuiltinModule(&jit_module, "cinderjit")` 创建内建模块。
- **证据**：`cinderx/Jit/pyjit.cpp:3700-3703` 根据配置补丁 `sys.monitoring` 与 `sys.setprofile/settrace` 路径。
- **证据**：`cinderx/Jit/pyjit.cpp:3745-3772` finalize 时显式 deopt、释放 context 与 code allocator。
- **意义**：JIT 生命周期与解释器生命周期紧密耦合，初始化/反初始化顺序是关键稳定性点。

### 1.3 运行时行为钩子与兼容性折中
- **证据**：`cinderx/Jit/pyjit.cpp:1536-1539`、`1594`、`1619`（同文件）描述对 profiling/tracing 注册流程进行拦截以启停 JIT。
- **证据**：`cinderx/TestScripts/cinder_jit_ignore_tests.txt:122` 标注 JIT 不支持 `settrace()`/`setprofile()`。
- **意义**：为保持可调试性与性能，JIT 对 CPython 监控机制采用“动态禁用/恢复”策略，语义与纯解释器存在差异。

---

## 2) 外部工具集成（perf、GDB）

### 2.1 GDB 集成
- **证据**：`cinderx/Jit/pyjit.cpp:479-485` 提供 `jit-gdb-support` 开关；`488-495` 提供 `jit-gdb-write-elf`。
- **意义**：可在调试场景下生成更可读的 JIT 符号/ELF 信息，代价是额外开销与复杂配置。

### 2.2 perf / jitdump 集成
- **证据**：`cinderx/Jit/pyjit.cpp:745-748` 提供 `jit-perfmap`（`/tmp/perf-<pid>.map`）。
- **证据**：`cinderx/Jit/pyjit.cpp:752-757` 提供 `jit-perf-dumpdir` 输出 perf jitdump 目录。
- **意义**：支持 Linux 侧性能分析工具链，便于火焰图与热点归因。

---

## 3) 第三方库集成

### 3.1 CMake FetchContent 拉取依赖
- **证据**：
  - `CMakeLists.txt:183-189`：`asmjit`（JIT 后端）。
  - `CMakeLists.txt:193-199`：`fmt`（格式化/日志）。
  - `CMakeLists.txt:203-209`：`parallel-hashmap`。
  - `CMakeLists.txt:213-224`：`usdt`（探针相关头文件布局处理）。
  - `CMakeLists.txt:228-243`：优先本地 `ZLIB`，缺失时自动拉取 `zlib`。
- **意义**：构建流程在“本地已安装依赖”与“按需在线抓取依赖”之间自动切换。

### 3.2 Python 构建工具链
- **证据**：`pyproject.toml:1-3` 使用 `setuptools.build_meta`。
- **证据**：`setup.py:553-554` 在 `build_ext` 阶段调用 `cmake` 配置与构建。
- **意义**：Python 包发布入口是 setuptools，但底层原生扩展由 CMake 驱动。

---

## 4) 发布流程（PyPI、GitHub Actions）

### 4.1 自动化发布到 PyPI
- **证据**：`README.md:12` 说明“weekly basis”发布。
- **证据**：`.github/workflows/publish.yml:1` 工作流名即 `Publish to PyPI`；`:4-7` 每周定时；`:9-15` 支持手动触发与补丁版本输入。
- **证据**：`.github/workflows/publish.yml:35-43` 用 `cibuildwheel` 产出 wheel；`:63-71` 构建 sdist；`:92-93` 通过 `pypa/gh-action-pypi-publish` 发布。

### 4.2 CI 构建与验证
- **证据**：`.github/workflows/ci.yml:1-3` push/PR 触发。
- **证据**：`.github/workflows/ci.yml:12` 覆盖多个 3.14 小版本；`:30-45` 执行 build、安装、导入校验与 pytest。
- **意义**：发布前路径具备基础构建与运行验证闭环。

---

## 5) 构建时依赖获取

### 5.1 getdeps 流程（GitHub Actions）
- **证据**：`.github/workflows/getdeps-main-linux.yml:23` 使用 `build/fbcode_builder/getdeps.py query-paths`。
- **证据**：`:24-44` 按需 fetch `ninja/cmake/python-setuptools/autoconf/automake/libtool/python-main`。
- **证据**：`:45-156` 使用 cache restore/save 与 build；`:157-166` 构建、拷贝产物并测试 `cinderx-main`。
- **意义**：这是面向工程化/可复现构建的依赖准备管线，和 PyPI wheel 构建流程并行存在。

### 5.2 包构建参数化（PGO/LTO/平台能力）
- **证据**：`pyproject.toml:26-33` cibuildwheel 设定 Linux 目标与 PGO/LTO 环境变量。
- **证据**：`setup.py:211-217`、`218-373` 支持三阶段 PGO；`482-487` 支持 LTO 开关。
- **证据**：`setup.py:523-537`、`CMakeLists.txt:65-67` 按平台启用 ELF/symbolizer/usdt 等能力。
- **意义**：构建参数与平台特性强绑定，需在 CI/CD 中保持一致环境避免“本地可过、线上失败”。
