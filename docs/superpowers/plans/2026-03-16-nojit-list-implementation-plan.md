# NoJIT List Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有 JIT 白名单机制新增对称的 `nojitlist` 黑名单基础能力，并让 deny 优先于 allow。

**Architecture:** 复用现有 `jitlist` 的数据结构与解析逻辑，在 module state 中维护第二份 list，并在 `getCompilationEligibility()` 的资格判定前面插入 deny lookup。Python 层新增对称 API，测试先覆盖基础行为和优先级，不先做性能实验逻辑。

**Tech Stack:** C++ (`pyjit.cpp`, `jit_list.*`), Python API 包装 (`cinderx/PythonLib/cinderx/jit.py`), unittest

---

## Chunk 1: 底层存储与资格判定

### Task 1: 为 module state 添加 `no_jit_list`

**Files:**
- Modify: `/Users/luchen/Repo/cinderx/cinderx/ModuleState/module_state.h`
- Modify: `/Users/luchen/Repo/cinderx/cinderx/ModuleState/module_state.cpp`
- Reference: `/Users/luchen/Repo/cinderx/cinderx/Jit/jit_list.h`

- [ ] **Step 1: 写失败测试**

在 Python 层测试里准备一个“deny 命中时不应编译”的测试用例，先不实现底层逻辑。

- [ ] **Step 2: 跑测试确认先红**

Run: `PYTHONPYCACHEPREFIX=/tmp/codex-pycache PYTHONPATH=cinderx/PythonLib /tmp/cinderx314-local/bin/python -m unittest test_cinderx.test_nojitlist -v`

Expected: FAIL，因为 `read_nojit_list()` / deny 逻辑不存在。

- [ ] **Step 3: 最小实现**

在 module state 里新增：

```cpp
std::unique_ptr<jit::IJITList> no_jit_list;
```

只做状态接线，不先扩复杂行为。

- [ ] **Step 4: 跑测试**

同上，确认还是红，但错误从“字段缺失”推进到“接口未实现”。

- [ ] **Step 5: Commit**

暂不单独提交，等本 chunk 完整通过后再一起提交。

### Task 2: 在 eligibility 中插入 deny lookup

**Files:**
- Modify: `/Users/luchen/Repo/cinderx/cinderx/Jit/pyjit.cpp`
- Reference: `/Users/luchen/Repo/cinderx/cinderx/Jit/jit_list.cpp`

- [ ] **Step 1: 写失败测试**

测试覆盖：
- 只有 deny 命中时，`force_compile()` 后仍不编译
- allow + deny 同时命中时，以 deny 为准

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPYCACHEPREFIX=/tmp/codex-pycache PYTHONPATH=cinderx/PythonLib /tmp/cinderx314-local/bin/python -m unittest test_cinderx.test_nojitlist -v`

Expected: FAIL，当前 deny 不生效。

- [ ] **Step 3: 最小实现**

修改：
- `getCompilationEligibility(BorrowedRef<PyFunctionObject>)`
- `getCompilationEligibility(BorrowedRef<> module_name, BorrowedRef<PyCodeObject>)`

逻辑顺序改成：

1. 基础前置条件检查
2. `no_jit_list` 命中则 `Ineligible`
3. `jit_list` 命中则 `JitListEligible`
4. 否则走默认 `Eligible`

- [ ] **Step 4: 跑测试确认转绿**

同上。

- [ ] **Step 5: Commit**

暂不单独提交。

## Chunk 2: Python API

### Task 3: 新增 `read_nojit_list` / `append_nojit_list` / `get_nojit_list`

**Files:**
- Modify: `/Users/luchen/Repo/cinderx/cinderx/Jit/pyjit.cpp`
- Modify: `/Users/luchen/Repo/cinderx/cinderx/PythonLib/cinderx/jit.py`

- [ ] **Step 1: 写失败测试**

测试覆盖：
- `append_nojit_list("mod:qualname")`
- `read_nojit_list(path)`
- `get_nojit_list()` 返回结构与 `get_jit_list()` 对称

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONPYCACHEPREFIX=/tmp/codex-pycache PYTHONPATH=cinderx/PythonLib /tmp/cinderx314-local/bin/python -m unittest test_cinderx.test_nojitlist -v`

Expected: FAIL，因为 API 不存在。

- [ ] **Step 3: 最小实现**

新增底层函数：
- `ensureNoJitList()`
- `deleteNoJitList()`
- `append_nojit_list(...)`
- `read_nojit_list(...)`
- `get_nojit_list(...)`

Python 包装层同步导出。

- [ ] **Step 4: 跑测试确认转绿**

同上。

- [ ] **Step 5: Commit**

暂不单独提交。

## Chunk 3: 基础测试闭环

### Task 4: 新增 `test_nojitlist.py`

**Files:**
- Create: `/Users/luchen/Repo/cinderx/cinderx/PythonLib/test_cinderx/test_nojitlist.py`
- Reference: `/Users/luchen/Repo/cinderx/cinderx/PythonLib/test_cinderx/test_jitlist.py`
- Reference: `/Users/luchen/Repo/cinderx/cinderx/PythonLib/test_cinderx/test_jit_disable.py`

- [ ] **Step 1: 写测试**

至少覆盖：
- `append_nojit_list()` 基础解析
- `read_nojit_list()` 基础解析
- deny 命中时 `is_jit_compiled()` 为 `False`
- allow + deny 同时命中时 deny 优先
- nested code object deny 命中

- [ ] **Step 2: 跑测试确认先红**

Run: `PYTHONPYCACHEPREFIX=/tmp/codex-pycache PYTHONPATH=cinderx/PythonLib /tmp/cinderx314-local/bin/python -m unittest test_cinderx.test_nojitlist -v`

Expected: FAIL

- [ ] **Step 3: 补最小实现直到转绿**

只实现通过这些测试所需的最小逻辑，不提前做性能筛选能力。

- [ ] **Step 4: 跑相关回归测试**

Run:

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache PYTHONPATH=cinderx/PythonLib /tmp/cinderx314-local/bin/python -m unittest \
  test_cinderx.test_nojitlist \
  test_cinderx.test_jitlist \
  test_cinderx.test_jit_disable -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cinderx/Jit/pyjit.cpp \
        cinderx/PythonLib/cinderx/jit.py \
        cinderx/PythonLib/test_cinderx/test_nojitlist.py \
        cinderx/ModuleState/module_state.h \
        cinderx/ModuleState/module_state.cpp \
        docs/superpowers/specs/2026-03-16-nojit-list-design.md \
        docs/superpowers/plans/2026-03-16-nojit-list-implementation-plan.md
git commit -m "jit: add nojit list infrastructure"
```
