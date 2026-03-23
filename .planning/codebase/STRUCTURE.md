# CinderX 代码结构文档（中文）

## 1. 目录结构总览

仓库根目录（节选，按本次分析关注点）：

```text
/Users/luchen/Agents-Repo/OpenCode/cinderx/
├── cinderx/                 # C/C++ 与 Python 运行时核心代码
│   ├── Jit/                 # JIT 编译器与运行时
│   │   ├── hir/             # 高层 IR 与优化 pass
│   │   ├── lir/             # 低层 IR、寄存器分配、后处理
│   │   ├── codegen/         # 后端机器码生成（AsmJit）
│   │   ├── pyjit.cpp        # JIT 主入口/调度
│   │   └── jit_rt.cpp       # JIT 运行时 helper
│   └── PythonLib/test_cinderx/  # 主要 Python 测试集合
├── tests/                   # 根级测试（安装/集成脚本类）
├── CMakeLists.txt           # CMake 构建入口（实验性）
├── build/                   # 构建目录（当前有 fbcode_builder/）
└── artifacts/               # 基准/实验产物目录（deepcopy、richards 等）
```

---

## 2. 核心代码位置（JIT / HIR / LIR / 运行时）

### 2.1 JIT 主入口与编译调度

- `cinderx/Jit/pyjit.cpp`
  - 热度触发编译、vectorcall 切换、失败回退
  - 关键函数示例：`jitVectorcall()`, `forcedJitVectorcall()`, `compileFunction()`

示例片段：

```cpp
// cinderx/Jit/pyjit.cpp
auto result = compileFunction(func);
if (result == Result::OK) {
  return func->vectorcall(func_obj, stack, nargsf, kwnames);
}
```

### 2.2 HIR（高层 IR）

- 目录：`cinderx/Jit/hir/`
- 关键文件：
  - `builder.h/.cpp`：字节码到 HIR 的 lowering
  - `hir.h`：IR 核心对象（Function/Instr/CFG）
  - `ssa.cpp`, `simplify.cpp`, `inliner.cpp`, `dead_code_elimination.cpp` 等：优化 pass

### 2.3 LIR（低层 IR）

- 目录：`cinderx/Jit/lir/`
- 关键文件：
  - `generator.h/.cpp`：HIR→LIR
  - `instruction.h`, `operand.h`, `function.h`：LIR 数据结构
  - `regalloc.h/.cpp`：线性扫描寄存器分配
  - `postalloc.cpp`, `postgen.cpp`, `verify.cpp`, `dce.cpp`：后处理与校验

### 2.4 代码生成后端

- 目录：`cinderx/Jit/codegen/`
- 关键文件：
  - `gen_asm.h/.cpp`：入口/出口、trampoline、frame 管理
  - `autogen.h/.cpp`：opcode+pattern 驱动的指令翻译规则
  - `arch.h` + `arch/x86_64.*`, `arch/aarch64.*`：目标架构抽象

### 2.5 JIT 运行时

- 文件：`cinderx/Jit/jit_rt.cpp`
- 职责：调用桥接、类型转换、frame 链接、生成器支持、容器/算术 helper、异常/deopt 协助。

典型 helper 命名形态：

- `JITRT_Call*`
- `JITRT_LoadGlobal*`
- `JITRT_Box*` / `JITRT_Unbox*`
- `JITRT_GenSend*`

---

## 3. 测试代码组织

### 3.1 Python 测试主目录

- `cinderx/PythonLib/test_cinderx/`
  - 例如：
    - `test_cinderx/test_cinderjit.py`
    - `test_cinderx/test_jit_generators.py`
    - `test_cinderx/test_jit_preload.py`
    - `test_cinderx/test_jit_attr_cache.py`

### 3.2 根目录 tests

- `tests/`
  - 偏安装与场景验证，如：
    - `tests/test_setup_adaptive_static_python.py`
    - `tests/test_cinderx_lightweight_frames_api.py`

### 3.3 脚本化测试

- `cinderx/TestScripts/`
  - 如 `test_multithreaded_compile.sh`, `test_hir_stats.sh`, `test_builds.sh`

### 3.4 运行时测试辅助

- `cinderx/RuntimeTests/testutil.cpp`
- `cinderx/RuntimeTests/testutil.h`

---

## 4. 构建产物位置

### 4.1 CMake 定义的关键产物

从 `CMakeLists.txt` 可见：

- 目标模块名：`_cinderx.so`
  - 配置位置：
    - `set_target_properties(${PROJECT_NAME} PROPERTIES OUTPUT_NAME "_cinderx.so")`
- 生成头目录：`${CMAKE_BINARY_DIR}/generated`
  - 在 CMake 中定义为 `GENERATED_HEADER_DIR`
- JIT 相关库：`jit`（由 `cinderx/Jit/*.cpp|*.c` 汇总）

### 4.2 仓库中的常见构建/产物目录

- `build/fbcode_builder/`：当前仓库可见构建目录
- `artifacts/deepcopy/`, `artifacts/richards/`：基准/实验产物目录

> 注意：实际二进制落盘位置依赖本地构建方式（CMake、setuptools、CI pipeline）。

---

## 5. 命名约定（按当前代码库实践）

### 5.1 文件命名

- C/C++ 文件普遍使用 `snake_case`：
  - `jit_rt.cpp`, `compile_function.h`, `dead_code_elimination.cpp`
- 架构子目录按目标架构命名：
  - `codegen/arch/x86_64.cpp`, `codegen/arch/aarch64.cpp`

### 5.2 类型与函数命名

- 类/结构体：`PascalCase`
  - `Compiler`, `HIRBuilder`, `LIRGenerator`, `NativeGenerator`
- 普通函数：`camelCase`
  - `buildHIR`, `runPasses`, `TranslateFunction`
- 运行时 helper：`JITRT_*` 前缀
  - `JITRT_LoadGlobal`, `JITRT_Vectorcall`

### 5.3 pass 与模块命名

- HIR pass 文件通常反映优化动作：
  - `simplify.cpp`, `guard_removal.cpp`, `phi_elimination.cpp`
- LIR 后处理类似：
  - `postalloc.cpp`, `postgen.cpp`, `verify.cpp`

---

## 6. 快速定位建议（实用）

1. **看编译主流程**：先读 `cinderx/Jit/compiler.cpp`
2. **看入口策略**：再读 `cinderx/Jit/pyjit.cpp`
3. **看语义下沉点**：查 `cinderx/Jit/lir/generator.cpp` 中 `JITRT_*` 调用
4. **看运行时 helper 实现**：定位到 `cinderx/Jit/jit_rt.cpp`
5. **看架构差异**：阅读 `cinderx/Jit/codegen/arch/`
