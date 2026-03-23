# CinderX 测试规范与流程（基于 `cinderx/RuntimeTests/` 与 CI）

本文档基于以下实际文件整理：

- `cinderx/RuntimeTests/main.cpp`
- `cinderx/RuntimeTests/fixtures.h`
- `cinderx/RuntimeTests/testutil.h`
- `cinderx/RuntimeTests/hir_test.cpp`
- `cinderx/RuntimeTests/sanity_test.cpp`
- `cinderx/RuntimeTests/README.rst`
- `.github/workflows/ci.yml`
- `.github/workflows/getdeps-main-linux.yml`
- `.github/workflows/getdeps-3_14-linux.yml`

---

## 1. 测试框架

### 1.1 C++ 测试：GoogleTest（gtest）

- 入口：`cinderx/RuntimeTests/main.cpp`
- 常见形式：
  - `TEST(...)`：纯算法/结构测试（不依赖 Python 解释器）
  - `TEST_F(..., ...)`：基于 fixture 的运行时测试

示例（`cinderx/RuntimeTests/hir_test.cpp`）：

```cpp
TEST(BasicBlockTest, CanAppendInstrs) {
  Environment env;
  BasicBlock block;
  auto v0 = env.AllocateRegister();
  block.append<LoadConst>(v0, TNoneType);
  block.append<Return>(v0);
  ASSERT_TRUE(block.GetTerminator()->IsReturn());
}
```

### 1.2 Runtime fixture：`RuntimeTest`

- 定义：`cinderx/RuntimeTests/fixtures.h`
- `SetUp()` 中执行：
  - `Py_Initialize()`
  - 安装 CinderX frame evaluator
  - 初始化 globals / 编译器环境
- `TearDown()` 中执行：
  - `Py_FinalizeEx()`
  - 校验 JIT 与模块状态回收

示例（`cinderx/RuntimeTests/sanity_test.cpp`）：

```cpp
class SanityTest : public RuntimeTest {};

TEST_F(SanityTest, CanUsePrivateAPIs) {
  auto g = Ref<>::steal(PyLong_FromLong(100));
  ASSERT_NE(g.get(), nullptr);
  ASSERT_TRUE(PyLong_CheckExact(g.get()));
  ASSERT_EQ(PyLong_AsInt(g.get()), 100);
}
```

---

## 2. 测试目录结构

目录：`cinderx/RuntimeTests/`

- `main.cpp`：测试主程序 + HIR 文本测试动态注册
- `fixtures.h/.cpp`：`RuntimeTest` 基础 fixture 与 Python 运行时生命周期管理
- `testutil.h/.cpp`：HIR 文本测试读取、环境变量/XArgs 辅助函数
- `*_test.cpp`：C++ 测试实现（如 `hir_test.cpp`、`jit_context_test.cpp`）
- `hir_tests/*.txt`：HIR 文本驱动测试数据（按 pass/版本分段）

HIR 文本测试样例：`cinderx/RuntimeTests/hir_tests/simplify_test.txt`

- 包含 `--- Test Suite Name ---`、`--- Passes ---`、`--- Input ---`、`--- Expected 3.14 ---` 等段。
- 在 `main.cpp` 通过 `register_test("simplify_test.txt")` 类似流程注册。

---

## 3. 单元测试 vs 集成测试（在本仓库中的划分）

### 3.1 单元测试（偏内部结构与算法）

特征：

- 主要验证 IR/CFG/LIR 数据结构与转换正确性。
- 不一定需要完整 Python 解释器生命周期。
- 常见在 `hir_test.cpp`、`dataflow_test.cpp`、`bitvector_test.cpp`。

示例：`TEST(CFGIterTest, VisitsAllBranches)`（`cinderx/RuntimeTests/hir_test.cpp`）。

### 3.2 集成测试（解释器 + JIT + C API 联动）

特征：

- 基于 `RuntimeTest` fixture。
- 涉及 Python 代码编译执行、JIT 初始化/收尾、模块状态。
- 常见在 `pyjit_test.cpp`、`deopt_test.cpp`、`jit_context_test.cpp`。

示例：`TEST_F(RuntimeTest, ReadingFromCodeRuntimeReadsCode)`（`cinderx/RuntimeTests/pyjit_test.cpp`）。

---

## 4. CI/CD 流程（GitHub Actions）

### 4.1 主 CI：`.github/workflows/ci.yml`

触发：`push` / `pull_request`

关键作业：

1. `run_tests`
   - Python 版本矩阵：`3.14.0` ~ `3.14.3`
   - `uv build --wheel`
   - `uv pip install dist/*.whl`
   - 运行：

     ```bash
     uv run pytest cinderx/PythonLib/test_cinderx/test*.py
     ```

2. `build_wheels`
   - `cibuildwheel` 构建 wheel

3. `build_sdist`
   - `python -m build --sdist`

### 4.2 getdeps 构建与测试流水线

文件：

- `.github/workflows/getdeps-main-linux.yml`
- `.github/workflows/getdeps-3_14-linux.yml`

关键点：

- 使用 `build/fbcode_builder/getdeps.py` 统一拉取依赖、构建、缓存。
- 最后执行项目级测试：

```bash
python3 build/fbcode_builder/getdeps.py test --src-dir=. cinderx-main --project-install-prefix cinderx-main:/usr/local
python3 build/fbcode_builder/getdeps.py test --src-dir=. cinderx-3_14 --project-install-prefix cinderx-3_14:/usr/local
```

这两条命令代表 CI 中完整构建产物上的测试验证入口。

---

## 5. 如何运行测试（开发者视角）

> 说明：仓库同时存在 Python 测试与 C++ RuntimeTests。下面命令均来自现有 CI 或 RuntimeTests 文档语境。

### 5.1 运行 Python 层回归测试（与 CI 对齐）

```bash
uv venv --python 3.14.3
uv build --wheel --python 3.14.3
uv pip install dist/*.whl
uv pip install pytest
uv run pytest cinderx/PythonLib/test_cinderx/test*.py
```

来源：`.github/workflows/ci.yml`

### 5.2 运行 getdeps 测试（与 Linux getdeps CI 对齐）

```bash
python3 build/fbcode_builder/getdeps.py build --src-dir=. cinderx-3_14 --project-install-prefix cinderx-3_14:/usr/local
python3 build/fbcode_builder/getdeps.py test --src-dir=. cinderx-3_14 --project-install-prefix cinderx-3_14:/usr/local
```

来源：`.github/workflows/getdeps-3_14-linux.yml`

### 5.3 编写新的 RuntimeTests

遵循 `cinderx/RuntimeTests/README.rst`：

1. 新建 `*_test.cpp`
2. 若测试涉及 C API，继承 `RuntimeTest`
3. HIR 场景可新增 `hir_tests/*.txt`，并在 `main.cpp` 注册

最小示例：

```cpp
class MyPythonTest : public RuntimeTest {};

TEST_F(MyPythonTest, TestFoo) {
  // arrange / act / assert
}
```

---

## 6. 提交前测试建议（实践）

1. 先跑受影响最小集合（对应模块 test 文件）。
2. 对 JIT/HIR 相关改动，补跑对应 `RuntimeTests/*_test.cpp` + 相关 `hir_tests/*.txt`。
3. 提交前至少跑一轮与 CI 等价的 Python 测试命令（见 5.1）。
4. 若改动涉及构建系统或低层依赖，跑 getdeps 测试入口（见 5.2）。
