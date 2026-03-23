# CinderX JIT 架构文档（中文）

## 1. 系统整体架构模式

CinderX 的 JIT 采用**分层编译器 + 运行时协作**模式：

- **入口层（调度与生命周期）**：`cinderx/Jit/pyjit.cpp`
  - 挂接/切换 `PyFunctionObject->vectorcall`
  - 根据调用热度触发编译（autojit）
  - 管理编译结果、降级策略、失败回退
- **中间表示层（HIR/LIR）**：`cinderx/Jit/hir/` + `cinderx/Jit/lir/`
  - HIR 负责语义表达和高层优化
  - LIR 负责接近机器的低层操作与寄存器/栈布局
- **后端代码生成层**：`cinderx/Jit/codegen/`
  - 将 LIR 映射到目标架构机器指令（AsmJit）
- **运行时支持层**：`cinderx/Jit/jit_rt.cpp`
  - 提供 JIT helper（`JITRT_*`）
  - 框架链接、调用约定桥接、Deopt/异常恢复

这一架构的核心特点是：

1. **编译与执行解耦**：`pyjit.cpp` 负责“何时编译”，`compiler.cpp` 负责“如何编译”。
2. **IR 分层**：高层优化与底层寄存器分配分离，降低复杂度。
3. **显式 runtime helper 边界**：难以内联或依赖 CPython 语义的路径，通过 `JITRT_*` 下沉到运行时。

---

## 2. HIR/LIR 双层 IR 设计

### 2.1 HIR（High-level IR）

关键路径：

- 构建入口：`cinderx/Jit/hir/builder.h` / `builder.cpp`
  - `jit::hir::buildHIR(const Preloader&)`
  - `jit::hir::HIRBuilder::buildHIR()`
- IR 核心：`cinderx/Jit/hir/hir.h`
- 优化 pass：`cinderx/Jit/hir/*.cpp`（如 `simplify.cpp`、`inliner.cpp`、`dead_code_elimination.cpp`）

HIR 的职责：

- 将 Python 字节码语义转换为可优化的 SSA/CFG 结构。
- 在高层做类型驱动、控制流、引用计数相关优化。
- 保留 deopt 信息，便于运行时恢复解释器执行。

来自源码注释（`cinderx/Jit/hir/builder.h`）可见，初始 HIR 是：

- 未优化
- 非 SSA
- 尚未插入 refcount 操作

后续 pass 才会完成 SSA、类型流和 refcount 插入。

### 2.2 LIR（Low-level IR）

关键路径：

- HIR→LIR lowering：`cinderx/Jit/lir/generator.cpp`
  - `jit::lir::LIRGenerator::TranslateFunction()`
- LIR 核心结构：`cinderx/Jit/lir/function.h`, `instruction.h`, `operand.h`
- 寄存器分配：`cinderx/Jit/lir/regalloc.h` / `regalloc.cpp`
- 后处理：`postalloc.*`, `postgen.*`, `dce.*`, `verify.*`

LIR 的职责：

- 把 HIR 语义“落地”为更贴近机器的指令和操作数模型。
- 显式处理物理寄存器、栈槽、调用约定、边界复制（phi/edge copy）。
- 为代码生成器提供可直接翻译的输入。

`regalloc.h` 明确说明采用 **Linear Scan on SSA** 思路，流程包括：

1. 基本块重排（RPO）
2. 活跃区间/使用点计算
3. 线性扫描分配
4. 回写重写 LIR

---

## 3. 编译管线流程（解析 → HIR → LIR → 机器码）

> 本项目“解析”主要指 Python 字节码解析与预加载（preload）语义准备，而非源码 AST 解析。

### 3.1 管线主干（`cinderx/Jit/compiler.cpp`）

`Compiler::Compile(const hir::Preloader&)` 的核心步骤：

```cpp
// cinderx/Jit/compiler.cpp
std::unique_ptr<hir::Function> irfunc(hir::buildHIR(preloader));
Compiler::runPasses(*irfunc, config);

auto ngen = ngen_factory_(irfunc.get());
entry = reinterpret_cast<vectorcallfunc>(ngen->getVectorcallEntry());
```

即：

1. `buildHIR(preloader)` 生成 HIR
2. `runPasses()` 运行 HIR 优化流水线
3. `NativeGenerator` 触发低层生成并拿到 native 入口

### 3.2 HIR pass 管线（`Compiler::runPasses`）

关键顺序（简化）：

1. `SSAify`（必须先执行）
2. `Simplify`/类型相关优化
3. 比较消除、Guard 移除、Phi 消除、可选 Inliner
4. CFG 清理、DCE
5. `RefcountInsertion`（语义正确性关键）
6. 若配置开启，输出 HIR stats

这体现了“先语义规范化，再做优化，最后补齐运行时语义（refcount）”的分层策略。

### 3.3 HIR→LIR（`cinderx/Jit/lir/generator.cpp`）

`LIRGenerator::TranslateFunction()` 做到：

- 先分析可传播 copy
- 翻译所有可达 HIR block
- 建立 LIR CFG successor 边
- 后续由 regalloc 与 post-pass 收敛到可发射形态

同时在 lowering 中大量调用 runtime helper，例如：

```cpp
// cinderx/Jit/lir/generator.cpp（示例）
bbb.appendCallInstruction(instr->output(), JITRT_LoadGlobal, globals, builtins, name);
bbb.appendCallInstruction(dst, JITRT_GetMethod, base, name);
```

### 3.4 LIR→机器码（`cinderx/Jit/codegen/`）

核心组件：

- `codegen/autogen.h/.cpp`：`AutoTranslator` 按 opcode+operand pattern 选择翻译规则
- `codegen/arch.h` + `codegen/arch/*`：架构抽象（x86_64 / aarch64）
- `codegen/gen_asm.cpp`：deopt trampoline、frame/link、入口/出口模板等

机器码由 AsmJit builder 最终提交到 code allocator，形成可执行代码块并返回入口地址。

---

## 4. 运行时系统集成

运行时集成点分三类：

### 4.1 函数入口与调度（`pyjit.cpp`）

- `jitVectorcall()`：热度检查 + 触发编译
- `forcedJitVectorcall()`：忽略热度直接尝试编译
- 编译失败时恢复解释器入口（`setVectorcall(func, interp_entry)`）

示例（简化）：

```cpp
// cinderx/Jit/pyjit.cpp
auto result = compileFunction(func);
if (result == Result::OK) {
  return func->vectorcall(func_obj, stack, nargsf, kwnames);
}
setVectorcall(func, interp_entry);
return interp_entry(func_obj, stack, nargsf, kwnames);
```

### 4.2 Runtime Helper（`jit_rt.cpp`）

`jit_rt.cpp` 提供大量 `JITRT_*` helper：

- 调用桥接：`JITRT_Call*` / `JITRT_Vectorcall`
- 作用域和全局访问：`JITRT_LoadGlobal*`
- 类型转换与装箱拆箱：`JITRT_Box*`, `JITRT_Unbox*`, `JITRT_Cast*`
- 生成器与 frame 链接：`JITRT_AllocateAndLink*`, `JITRT_GenSend*`
- 容器、算术、比较等运行时语义

这使得 LIR 不必内联所有复杂 Python 语义，降低后端复杂度。

### 4.3 Deopt 与解释器恢复（`codegen/gen_asm.cpp` + `jit_rt.cpp`）

- machine code 侧在 guard 失败等场景跳转至 deopt trampoline
- 通过 `CodeRuntime` + `DeoptMetadata` 重建 frame/live value
- 再转回解释器继续执行

这保证了“激进优化 + 可回退”的正确性闭环。

---

## 5. 关键抽象与接口

### 5.1 编译器门面

- 文件：`cinderx/Jit/compiler.h`
- 类型：`jit::Compiler`
- 接口：
  - `Compile(BorrowedRef<PyFunctionObject>)`
  - `Compile(const hir::Preloader&)`
  - `runPasses(hir::Function&, PassConfig)`

### 5.2 HIR 抽象

- 文件：`cinderx/Jit/hir/hir.h`
- 核心对象：`Function`, `CFG`, `BasicBlock`, `Instr`
- 构建入口：`cinderx/Jit/hir/builder.h` 的 `buildHIR()`

### 5.3 LIR 抽象

- 文件：`cinderx/Jit/lir/function.h`, `instruction.h`, `operand.h`
- Lowering 入口：`cinderx/Jit/lir/generator.h` 的 `LIRGenerator`
- 寄存器分配：`cinderx/Jit/lir/regalloc.h` 的 `LinearScanAllocator`

### 5.4 代码生成抽象

- 文件：`cinderx/Jit/codegen/gen_asm.h`
- 核心类型：`jit::codegen::NativeGenerator`
- 关键接口：
  - `getVectorcallEntry()`
  - `getCodeBuffer()`
  - `codeRuntime()`

### 5.5 运行时抽象

- 文件：`cinderx/Jit/jit_rt.cpp`, `cinderx/Jit/code_runtime.h`
- 核心：`JITRT_*` helper + `CodeRuntime` + deopt 元数据

---

## 6. 一张图看清主路径

```text
PyFunction 调用
  -> cinderx/Jit/pyjit.cpp (jitVectorcall / compileFunction)
  -> cinderx/Jit/compiler.cpp
      -> cinderx/Jit/hir/builder.cpp (bytecode -> HIR)
      -> cinderx/Jit/hir/*.cpp (SSA + 优化 + refcount)
      -> cinderx/Jit/lir/generator.cpp (HIR -> LIR)
      -> cinderx/Jit/lir/regalloc.cpp + post*.cpp
      -> cinderx/Jit/codegen/autogen.cpp + gen_asm.cpp (LIR -> machine code)
  -> 安装 vectorcall native 入口
执行期
  -> 快路径 native 执行
  -> 慢路径/守卫失败: deopt trampoline + jit_rt.cpp helper -> 解释器恢复
```
