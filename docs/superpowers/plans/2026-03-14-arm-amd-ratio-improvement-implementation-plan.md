# Arm/AMD Ratio Improvement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实施一组以 Arm/AMD 平台比恢复为目标的 CinderX 优化，优先提升 `coroutines`、`comprehensions`、`richards`、`richards_super`、`go`、`deltablue`、`raytrace`、`nqueens`、`float`、`generators`、`python_startup` 在 Arm 上相对 AMD/x86_64 的表现。

**Architecture:** 以 6 个改造包分阶段推进：`startup injection`、`tiny-helper / attr-guard`、`container-write fast path`、`coroutine / awaitable`、`generator / yield-from / decref`、`numeric leaf / float-slot`。每个包先用开关落地，再用单元测试/HIR 测试和定向 benchmark 验证。优先做共享改动，再补 AArch64 特化与 benchmark-shape 特化。

**Tech Stack:** C++, C, CPython interpreter internals, CinderX JIT HIR/LIR/codegen, Python runtime tests, RuntimeTests HIR fixtures, pyperformance direct-run scripts

---

## 文件结构

### 需要修改的核心文件

- `cinderx/Interpreter/3.14/Includes/ceval_macros.h`
- `cinderx/Interpreter/3.14/interpreter.c`
- `cinderx/Interpreter/3.14/borrowed-ceval.c.template`
- `cinderx/Interpreter/3.14/cinder-bytecodes.c`
- `cinderx/Interpreter/3.14/Includes/generated_cases.c.h`
- `cinderx/Jit/hir/builder.cpp`
- `cinderx/Jit/hir/simplify.cpp`
- `cinderx/Jit/hir/refcount_insertion.cpp`
- `cinderx/Jit/lir/generator.cpp`
- `cinderx/Jit/codegen/arch.cpp`
- `cinderx/Jit/codegen/gen_asm.cpp`
- `cinderx/Jit/codegen/frame_asm.cpp`
- `cinderx/Jit/generators_core.cpp`
- `cinderx/StaticPython/checked_dict.c`
- `cinderx/StaticPython/checked_list.c`
- `cinderx/PythonLib/cinderx/jit.py`
- `cinderx/PythonBin/sitecustomize.py`
- `scripts/arm/remote_update_build_test.sh`

### 需要新增或修改的测试文件

- `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- `cinderx/PythonLib/test_cinderx/test_jit_generators.py`
- `cinderx/PythonLib/test_cinderx/test_jit_async_generators.py`
- `cinderx/RuntimeTests/hir_tests/*.txt`

### 需要复用的验证脚本

- `scripts/arm/bench_pyperf_direct.py`
- `scripts/arm/interp_feature_matrix.sh`
- `scripts/arm/remote_update_build_test.sh`

## Chunk 1: Startup Injection

### Task 1: 让 `python_startup` 不再量到 CinderX 自动注入成本

**Files:**
- Modify: `scripts/arm/remote_update_build_test.sh`
- Modify: `cinderx/PythonBin/sitecustomize.py`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，覆盖 startup-aware autoload policy**

在 `test_arm_runtime.py` 新增一个最小测试：

- 模拟 pyperformance worker 场景
- 断言 startup benchmark 命令形状下不会自动 `import cinderx.jit` / `jit.enable()`
- 非 startup benchmark 仍保持原行为

- [ ] **Step 2: 运行测试确认当前失败**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k startup -v
```

Expected:
- 失败，表现为当前策略仍会在 startup 路径自动加载 JIT

- [ ] **Step 3: 在 worker `sitecustomize` 里加入 benchmark-aware 判定**

实现方向：
- 识别 `python_startup` / `-c pass` / `-S -c pass` / `os._exit(0)` 这类 startup benchmark 形状
- startup benchmark 默认不加载 `cinderx.jit`
- 保留一个显式环境变量覆盖开关

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k startup -v
```

Expected:
- PASS

- [ ] **Step 5: 跑定向 benchmark 验证**

Run:
```bash
python3 scripts/arm/bench_pyperf_direct.py --benchmark python_startup --strategy none --samples 5
```

Expected:
- `python_startup` 明显回升
- `python_startup_no_site` / `python_startup_exit` 差异更接近“纯启动路径”

## Chunk 2: Tiny-Helper Interpreter Bookkeeping

### Task 2: 为 no-backedge tiny helper 降低解释器入口 bookkeeping

**Files:**
- Modify: `cinderx/Interpreter/3.14/Includes/ceval_macros.h`
- Modify: `cinderx/Interpreter/3.14/interpreter.c`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，验证 tiny helper 形状可以被识别和轻量处理**

新增测试脚本形状：
- 一个无 backedge、短字节码、小 locals 的方法
- 热循环外部反复调用它
- 断言启用 ratio mode 后，解释器统计或 debug trace 显示轻量入口被命中

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k tiny_helper -v
```

Expected:
- FAIL

- [ ] **Step 3: 实现 `tiny_helper` 判定与轻量入口路径**

实现方向：
- 依据 `co_nlocalsplus`、字节码长度、是否无 backedge、栈深等定义 tiny helper
- 在 `CI_UPDATE_CALL_COUNT` / adaptive bookkeeping 处对命中形状走轻量逻辑
- 用环境变量或 JIT 开关保护

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k tiny_helper -v
```

Expected:
- PASS

- [ ] **Step 5: 跑 `richards` / `richards_super` / `go` / `deltablue` 的解释器验证**

Run:
```bash
scripts/arm/interp_feature_matrix.sh richards
scripts/arm/interp_feature_matrix.sh richards_super
scripts/arm/interp_feature_matrix.sh go
scripts/arm/interp_feature_matrix.sh deltablue
```

Expected:
- 关闭/打开该优化时，Arm 相对 uplift 大于 AMD/x86_64

## Chunk 3: Exact-Layout Attr Fast Path

### Task 3: 为 exact stable layout 加最短 attr fast path

**Files:**
- Modify: `cinderx/Jit/hir/builder.cpp`
- Modify: `cinderx/Interpreter/3.14/Includes/generated_cases.c.h`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Test: `cinderx/RuntimeTests/hir_tests/hir_builder_static_test.txt`

- [ ] **Step 1: 写失败测试，验证 exact stable-layout attr 能走新 fast path**

测试形状：
- exact user class / slot-like field load
- 连续多次 `obj.x` / `obj.y`
- 断言 final HIR 或 runtime stats 显示不再走完整 `inline_values_valid_guard` 路径

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k attr_fast_path -v
```

Expected:
- FAIL

- [ ] **Step 3: 在 builder / interpreter 中增加更窄的 attr fast path**

实现方向：
- exact type
- stable version
- stable slot offset
- 无 checked/invalidity 复杂分支

- [ ] **Step 4: 更新 HIR fixture**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k attr_fast_path -v
```

Expected:
- PASS

- [ ] **Step 5: 跑 `go` / `deltablue` / `richards` / `float` 定向验证**

Run:
```bash
python3 scripts/arm/bench_pyperf_direct.py --benchmark go --strategy all --samples 5
python3 scripts/arm/bench_pyperf_direct.py --benchmark deltablue --strategy all --samples 5
python3 scripts/arm/bench_pyperf_direct.py --benchmark richards --strategy all --samples 5
python3 scripts/arm/bench_pyperf_direct.py --benchmark float --strategy all --samples 5
```

Expected:
- Arm uplift 大于 AMD/x86_64 uplift

## Chunk 4: AArch64-Specific Attr Lowering

### Task 4: 压缩 AArch64 上的 attr lowering 机器码形状

**Files:**
- Modify: `cinderx/Jit/codegen/arch.cpp`
- Modify: `cinderx/Jit/codegen/gen_asm.cpp`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Test: `cinderx/RuntimeTests/backend_test.cpp`

- [ ] **Step 1: 写失败测试，锁定 AArch64 attr fast path 的 lowering 形状**

测试内容：
- exact-layout attr fast path 在 Arm 下的 opcode / stats / HIR-LIR 形状
- 断言减少 scratch / helper / extra address-gen 片段

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k arm_attr_lowering -v
```

Expected:
- FAIL

- [ ] **Step 3: 实现 AArch64 专用 lowering**

实现方向：
- 尽量 fold 地址
- 合并 `valid` 检查与读取
- 减少 scratch register 与中间 materialization

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k arm_attr_lowering -v
```

Expected:
- PASS

- [ ] **Step 5: 重新验证 `go` / `deltablue`**

Expected:
- Arm/AMD 比值继续向上移动

## Chunk 5: `super()` Shortcut for `richards_super`

### Task 5: 为稳定 `super().fn(...)` 形状加入 shortcut

**Files:**
- Modify: `cinderx/Jit/hir/builder.cpp`
- Modify: `cinderx/Jit/hir/simplify.cpp`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，覆盖稳定 MRO 下的 `super()` 调用形状**

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k super_shortcut -v
```

- [ ] **Step 3: 实现 `super()` shortcut**

实现方向：
- 稳定 MRO + exact base method target
- 避免完整动态分派链

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k super_shortcut -v
```

- [ ] **Step 5: 跑 `richards_super` 直测**

Expected:
- `richards_super` 比 `richards` 的额外损失显著缩小

## Chunk 6: Container Write Fast Path

### Task 6: 为 pure list/dict comprehension 写入绕过 checked-container 分派

**Files:**
- Modify: `cinderx/StaticPython/checked_dict.c`
- Modify: `cinderx/StaticPython/checked_list.c`
- Modify: `cinderx/Interpreter/3.14/cinder-bytecodes.c`
- Modify: `cinderx/Jit/lir/generator.cpp`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，锁定 plain list/dict comprehension 形状**

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k comprehension_fast_path -v
```

- [ ] **Step 3: 增加 definitely-plain list/dict fast path**

实现方向：
- exact `list` 直走最短 append
- exact `dict` 直走 `PyDict_SetItem`
- 其他情况再退回 checked-container

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k comprehension_fast_path -v
```

- [ ] **Step 5: 跑 `comprehensions` 定向验证**

Expected:
- Arm uplift 明显

## Chunk 7: Coroutine / Awaitable Fast Path

### Task 7: 为 exact coroutine / awaitable 加最短 helper 链

**Files:**
- Modify: `cinderx/Jit/generators_core.cpp`
- Modify: `cinderx/Interpreter/3.14/borrowed-ceval.c.template`
- Modify: `cinderx/Jit/hir/builder.cpp`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- Test: `cinderx/RuntimeTests/hir_tests/hir_builder_static_test.txt`

- [ ] **Step 1: 写失败测试，覆盖 exact coroutine awaitable 形状**

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k awaitable_fast_path -v
```

- [ ] **Step 3: 实现 exact coroutine / awaitable fast path**

实现方向：
- exact `PyCoro_Type`
- exact Cinder coroutine type
- 缩短 `JitCoro_GetAwaitableIter` / `Ci_PyEval_GetAwaitable` 链

- [ ] **Step 4: 更新 HIR fixture 并跑测试**

Run:
```bash
python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -k awaitable_fast_path -v
```

- [ ] **Step 5: 跑 `coroutines` 定向验证**

Expected:
- `coroutines` 比值显著回升

## Chunk 8: Generator Attr / Decref

### Task 8: 扩大 generator-only attr lowering 覆盖面

**Files:**
- Modify: `cinderx/Jit/hir/builder.cpp`
- Modify: `cinderx/Jit/hir/simplify.cpp`
- Test: `cinderx/PythonLib/test_cinderx/test_jit_generators.py`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，覆盖 low-local generator attr 形状**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 扩大 generator attr lowering**
- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: 验证 `generators` / `nqueens`**

### Task 9: 为 generator/yield-from 做更激进的 decref compaction

**Files:**
- Modify: `cinderx/Jit/hir/refcount_insertion.cpp`
- Modify: `cinderx/Jit/lir/generator.cpp`
- Test: `cinderx/PythonLib/test_cinderx/test_jit_generators.py`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，锁定 `Decref` / `BatchDecref` 目标形状**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 实现 generator-only decref compaction**
- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: 验证 `generators` / `nqueens`**

## Chunk 9: Numeric Leaf / Float-Slot

### Task 10: 继续收窄 mixed-numeric tiny leaf helper guard

**Files:**
- Modify: `cinderx/Jit/hir/builder.cpp`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，覆盖 `raytrace`-style mixed numeric helper**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 收窄 no-backedge tiny leaf exact-guard 策略**
- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: 验证 `raytrace`**

### Task 11: 为 float-slot-heavy 方法做更激进的 slot specialization

**Files:**
- Modify: `cinderx/Jit/hir/builder.cpp`
- Modify: `cinderx/Jit/hir/simplify.cpp`
- Test: `cinderx/PythonLib/test_cinderx/test_arm_runtime.py`

- [ ] **Step 1: 写失败测试，覆盖 `Point.normalize()` / `Point.maximize()` 形状**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 实现连续 slot load hoist / guard merge**
- [ ] **Step 4: 跑测试确认通过**
- [ ] **Step 5: 验证 `float`**

## 验证矩阵

### 本地验证

- `python3 -m pytest cinderx/PythonLib/test_cinderx/test_arm_runtime.py -v`
- `python3 -m pytest cinderx/PythonLib/test_cinderx/test_jit_generators.py -v`
- `python3 -m pytest cinderx/PythonLib/test_cinderx/test_jit_async_generators.py -v`

### HIR / RuntimeTests

- `python3 cinderx/PythonLib/test_cinderx/test_arm_runtime.py`
- `buck2 test //cinderx/RuntimeTests:runtime_tests` 或仓库既有 RuntimeTests 入口

### 定向 benchmark 验证顺序

1. `python_startup`
2. `richards`
3. `richards_super`
4. `go`
5. `deltablue`
6. `comprehensions`
7. `coroutines`
8. `generators`
9. `nqueens`
10. `raytrace`
11. `float`

## 风险与回退

- 所有激进优化都先挂在显式开关后面，建议统一由一个 ratio-optimization 总开关控制。
- 如果某个 benchmark 提升但其他回归，可单独关闭对应子开关，不阻塞整体推进。
- 先收敛解释器/容器/startup 这类共享收益最大的包，再推进更复杂的 backend/JIT AArch64 特化。

## 执行建议

- 第一阶段只做 `Task 1`、`Task 2`、`Task 3`、`Task 6`。  
  这是最快能看到平台比改善的一组。
- 第二阶段做 `Task 7`、`Task 8`、`Task 9`。  
  主要拉 `coroutines`、`generators`、`nqueens`。
- 第三阶段做 `Task 4`、`Task 5`、`Task 10`、`Task 11`。  
  这是 AArch64 精修和数值路径收尾。

