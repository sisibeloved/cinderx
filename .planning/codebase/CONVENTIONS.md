# CinderX C++ 开发规范（基于 `cinderx/Jit/`）

本文档根据以下代码实样归纳：

- `cinderx/Jit/pyjit.cpp`
- `cinderx/Jit/jit_rt.cpp`
- `cinderx/Jit/context.h`
- `cinderx/Jit/inline_cache.cpp`
- `cinderx/Common/ref.h`

---

## 1. C++ 代码风格

### 1.1 命名约定

- **类型名 / 类名**：`PascalCase`
  - 例：`DisableGilCheck`（`cinderx/Jit/pyjit.cpp`）
  - 例：`Context`、`CompilationKey`（`cinderx/Jit/context.h`）
- **函数名**：`camelCase`
  - 例：`hasRequiredFlags`、`isPreloaded`（`cinderx/Jit/pyjit.cpp`）
  - 例：`maybeCollectCacheStats`（`cinderx/Jit/inline_cache.cpp`）
- **常量名**：
  - 对外/显式常量常用 `kXxx`：`kUnhandledSubscriptSuppressThreshold`（`cinderx/Jit/pyjit.cpp`）
  - 局部语义常量也可用 `snake_case`：`required_code_flags`（`cinderx/Jit/pyjit.cpp`）
- **成员字段**：`snake_case_`（尾部下划线）
  - 例：`is_initialized_`、`name_to_cfunc_`（`cinderx/Jit/context.h`）
- **宏 / 编译开关**：全大写下划线
  - 例：`PY_VERSION_HEX`、`SHADOWCODE_SUPPORTED`、`JIT_DCHECK`

### 1.2 缩进与排版

- 使用 **2 空格缩进**（无 tab）。
- 左花括号与声明同一行，控制语句遵循 K&R 风格。
- 长参数列表换行时，后续参数与首参数对齐。
- 命名空间关闭时带注释：` } // namespace jit`

示例（`cinderx/Jit/pyjit.cpp`）：

```cpp
bool hasRequiredFlags(BorrowedRef<PyCodeObject> code) {
  return (code->co_flags & required_code_flags) == required_code_flags;
}
```

### 1.3 注释风格

- 以 `//` 为主；复杂行为先给“为什么”，再给“怎么做”。
- 关键约束注释紧贴逻辑，避免与代码分离。
- 版本差异注释与 `#if PY_VERSION_HEX ...` 同步维护。

示例（`cinderx/Jit/jit_rt.cpp`）：

```cpp
// One significant difference is we don't need to incref the args
// in the new array.
```

---

## 2. 错误处理模式

### 2.1 断言与不变量

- 使用 `JIT_CHECK` / `JIT_DCHECK` 捕获内部不变量，失败时输出格式化上下文。
- 用于“理论上不应失败”的分支，而非普通业务分支。

示例（`cinderx/Jit/inline_cache.cpp`）：

```cpp
JIT_CHECK(
    cinderx::getModuleState()->watcher_state.watchType(type) == 0,
    "Failed to watch type {} for attribute cache",
    type->tp_name);
```

### 2.2 Python C API 错误约定

- 失败返回 `nullptr`（对象）或 `0/-1`（状态码），由调用方继续传播。
- 每次 `Py*` 分配后立刻判空，避免延迟故障。
- 必要时使用 `_PyErr_Occurred(...)` 判断是否已有异常。

示例（`cinderx/Jit/jit_rt.cpp`）：

```cpp
kwdict = Ref<>::steal(PyDict_New());
if (kwdict == nullptr) {
  return 0;
}
```

### 2.3 降级/回退路径

- 快路径失败后回退到 CPython 常规路径，优先保证语义一致。

示例（`cinderx/Jit/jit_rt.cpp`）：

```cpp
if (JITRT_BindKeywordArgs(...)) {
  return JITRT_GET_REENTRY(func->vectorcall)(...);
}
return Ci_PyFunction_Vectorcall((PyObject*)func, args, nargsf, kwnames);
```

---

## 3. Python C API 使用规范

### 3.1 统一使用 `Ref<>` / `BorrowedRef<>`

来源：`cinderx/Common/ref.h`

- **借用引用**：`BorrowedRef<T>`，仅表达“非拥有”。
- **拥有引用**：`Ref<T>`，析构自动 `Py_XDECREF`。
- 新引用来源必须显式选择：
  - `Ref<>::steal(...)`：偷取引用
  - `Ref<>::create(...)`：从 borrowed 创建新引用（内部 `INCREF`）

示例（`cinderx/RuntimeTests/fixtures.h`）：

```cpp
auto code = Ref<>::steal(Py_CompileString(src, filename, start));
if (code == nullptr) {
  THROW("Failed to compile code using the CPython compiler");
}
```

### 3.2 明确引用语义，避免裸指针所有权歧义

- 函数参数中，若会“偷取”引用，使用 `Ref<>`（并在调用处 `std::move`）。
- 仅观察对象时使用 `BorrowedRef<>`。

### 3.3 版本兼容分支必须显式包裹

- 统一通过 `PY_VERSION_HEX` 做编译期分支。
- 版本逻辑与注释同位，避免行为漂移。

示例（`cinderx/Jit/pyjit.cpp`）：

```cpp
#if PY_VERSION_HEX >= 0x030B0000
  return code->co_exceptiontable != nullptr &&
      PyBytes_CheckExact(code->co_exceptiontable) &&
      PyBytes_GET_SIZE(code->co_exceptiontable) > 0;
#else
  ...
#endif
```

---

## 4. 代码组织原则

### 4.1 头/实现分离与模块边界

- `*.h` 放声明、接口、轻量内联；`*.cpp` 放实现。
- 运行时 helper 在 `cinderx/Jit/jit_rt.h/.cpp`；上下文状态在 `cinderx/Jit/context.h/.cpp`。

### 4.2 命名空间层次

- 公共实现位于 `namespace jit`。
- 文件内私有工具放匿名命名空间 `namespace {}`，减少符号泄露。

示例（`cinderx/Jit/inline_cache.cpp`）：

```cpp
namespace jit {
namespace {
// file-local helpers
}
} // namespace jit
```

### 4.3 include 组织

- 先本文件头（self include），再内部依赖，再系统头。
- 版本相关 include 用 `#if PY_VERSION_HEX ...` 包裹。

### 4.4 可测试与可替换

- 关键行为通过独立 helper 暴露给 RuntimeTests（如 `JITRT_*` 系列），
  便于单测与跨版本行为验证。

---

## 5. 常见模式示例

### 模式 A：RAII 守卫

文件：`cinderx/Jit/pyjit.cpp`

```cpp
class DisableGilCheck {
 public:
  DisableGilCheck() : old_check_enabled_{_PyRuntime.gilstate.check_enabled} {
    _PyRuntime.gilstate.check_enabled = 0;
  }
  ~DisableGilCheck() {
    _PyRuntime.gilstate.check_enabled = old_check_enabled_;
  }
 private:
  int old_check_enabled_;
};
```

适用：临时修改全局/线程状态，确保异常路径可恢复。

### 模式 B：快速路径 + 慢路径

文件：`cinderx/Jit/inline_cache.cpp`

```cpp
if (!ensureValueOffset(name)) {
  return getAttrSlowPath(obj, name, dict);
}
return getAttrKnownOffset(obj, name);
```

适用：JIT/缓存场景先走低开销路径，失败后保证语义正确。

### 模式 C：错误传播而非吞错

文件：`cinderx/Jit/jit_rt.cpp`

```cpp
int cmp = PyObject_RichCompareBool(keyword, name, Py_EQ);
if (cmp > 0) {
  goto kw_found;
} else if (cmp < 0) {
  return 0;
}
```

适用：C API 返回值同时编码“结果 + 异常状态”时，必须完整分支处理。
