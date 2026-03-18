# HIR 分析报告：regex_compile 优化

**日期**: 2026-03-18
**来源**: macOS Debug 构建导出
**函数**: `bench_regex_compile`

## HIR 概览

```
fun __main__:bench_regex_compile {
  代码大小: 1624 bytes
  基本块: 14 个 (bb 0-14)
  编译时间: 11908µs
}
```

## 关键发现

### 1. 控制流结构

**基本块分布**:
- **bb 0**: 入口，初始化
- **bb 5**: 加载 `regexes` 全局变量，开始迭代
- **bb 13**: 主循环头（Loop header）
- **bb 1**: 迭代器 Next 调用
- **bb 2, 9, 10, 11**: 类型检查分支
- **bb 8**: 解包元组/列表
- **bb 3, 4**: `re.purge()` 和 `re.compile()` 调用
- **bb 7**: **Deopt 点**（反优化）
- **bb 4**: 返回

### 2. 守卫检查（Guards）

```hir
v34:MortalListExact[list:0x103739240] = GuardIs<0x103739240> v33 {
  Descr 'LOAD_GLOBAL: regexes'
  ...
}
```

**分析**:
- `GuardIs` 检查 `regexes` 变量是否指向特定列表对象
- 如果失败，会触发反优化
- 这是为了优化全局变量访问

### 3. 类型检查链

```hir
bb 2 {
  CondBranchCheckType<11, 9, TupleExact> v45
}

bb 11 {
  v47:CInt64[32] = LoadConst<CInt64[32]>
  v48:CPtr = LoadFieldAddress v45 v47
  Branch<8>
}

bb 9 {
  CondBranchCheckType<10, 7, ListExact> v45
}

bb 10 {
  v49:CPtr = LoadField<ob_item@24, CPtr, borrowed> v45
  Branch<8>
}
```

**分析**:
- 检查迭代器返回的是 `TupleExact` 还是 `ListExact`
- 如果不是这两种类型，跳转到 **bb 7 (Deopt)**
- 这解释了 Docker 测试中大量的反优化

### 4. 反优化点（Deopt）

```hir
bb 7 {
  Deopt {
    Descr 'UNPACK_SEQUENCE'
    GuiltyReg v45
    LiveValues<4> o:v35 o:v39 o:v40 o:v45
    FrameState {
      CurInstrOffset 18
      Locals<2> v39 v40
      Stack<2> v35 v45
    }
  }
}
```

**分析**:
- **位置**: UNPACK_SEQUENCE 指令
- **原因**: 类型检查失败（既不是 Tuple 也不是 List）
- **影响**: 代码回退到解释器执行
- **与 Docker 数据关联**: 这对应 `SubPattern.__getitem__` 等函数的 UnhandledException

### 5. 关键函数调用

#### re.purge()
```hir
v70:Object = LoadModuleAttrCached<2; "purge"> v69 {
  LiveValues<3> ...
  FrameState {...}
}
v79:Object = VectorCall<0> v70 {
  LiveValues<3> ...
  FrameState {...}
}
Decref v79
```

#### re.compile()
```hir
v81:Object = LoadModuleAttrCached<3; "compile"> v70 {
  LiveValues<4> ...
  FrameState {...}
}
v82:Object = VectorCall<2> v81 v58 v56 {
  LiveValues<4> ...
  FrameState {...}
}
Decref v81
Decref v82
```

**分析**:
- 使用 `LoadModuleAttrCached` 缓存属性访问
- `VectorCall` 调用 C 函数
- 调用后需要 `Decref` 减少引用计数

### 6. 引用计数操作

**统计**:
- `Incref`: 2 次（保护迭代变量）
- `Decref`: 5 次（释放临时对象）
- `XDecref`: 2 次（释放可能为 NULL 的变量）

**模式**:
- 每次 `VectorCall` 后都有 `Decref`
- 返回前清理局部变量

## 优化建议

### 方案 1: 减少 Deopt（高优先级）

**问题**: bb 7 的 Deopt 频繁触发

**原因**: `CondBranchCheckType` 对 `TupleExact` 和 `ListExact` 的检查过于严格

**优化策略**:
1. **放宽类型检查**: 如果不是性能关键路径，可以延迟类型检查
2. **添加更多类型支持**: 支持更多序列类型（如生成器）
3. **优化 HIR 生成**: 在 `cinderx/Jit/hir/builder.cpp` 中修改 `UNPACK_SEQUENCE` 的处理

**预期改进**: 减少 50% 反优化 → 性能提升 10-15%

### 方案 2: 优化 GuardIs（中优先级）

**问题**: `GuardIs` 检查全局变量 `regexes`

**优化策略**:
1. **全局变量缓存优化**: 如果 `regexes` 不变，可以跳过检查
2. **版本号机制**: 使用版本号替代直接比较

**实现位置**: `cinderx/Jit/hir/slot_version_guard_elimination.cpp`

**预期改进**: 5-10%

### 方案 3: 启用 HIR Inliner（中优先级）

**当前状态**: HIR Inliner 禁用（从之前的测试确认）

**优化策略**:
1. 启用 `cinderjit.enable_hir_inliner()`
2. 内联 `re.purge()` 和 `re.compile()` 的调用准备代码

**预期改进**: 5-10%

### 方案 4: 优化 VectorCall 开销（低优先级）

**观察**: `VectorCall` 后需要多次 `Decref`

**优化策略**:
1. **批量 Decref**: 合并相邻的 Decref
2. **延迟 Decref**: 使用延迟引用计数

**实现位置**: `cinderx/Jit/hir/refcount_insertion.cpp`

**预期改进**: 3-5%

## 实施路线图

### Phase 1: 快速验证（1-2 天）

1. **启用 HIR Inliner**
   ```python
   import cinderx.jit as jit
   jit.enable_hir_inliner()
   ```
   - 测试性能变化
   - 记录优化效果

2. **收集更多 HIR 样本**
   - 导出热点函数的 HIR
   - 分析 Deopt 模式

### Phase 2: 核心优化（3-5 天）

1. **减少 UNPACK_SEQUENCE 的 Deopt**
   - 修改 `cinderx/Jit/hir/builder.cpp`
   - 放宽类型检查条件
   - Docker 中验证效果

2. **优化 GuardIs**
   - 修改守卫检查生成逻辑
   - 添加版本号机制

### Phase 3: 验证和调优（2-3 天）

1. **Docker 完整测试**
   - CPython JIT: 80.3ms 基线
   - 优化后 CinderX JIT
   - 目标: 达到或超过基线

2. **HIR 对比报告**
   - 优化前 vs 优化后 HIR
   - Deopt 次数对比
   - 性能数据对比

## 预期效果

| 优化方案 | 预期改进 | 累计改进 |
|---------|---------|---------|
| 启用 HIR Inliner | 5-10% | 5-10% |
| 减少 Deopt | 10-15% | 15-25% |
| 优化 GuardIs | 5-10% | 20-35% |
| 其他微调 | 3-5% | 23-40% |

**目标**: 消除 17.6% 劣化，达到或超过 CPython JIT 性能

## 附录

### A. 完整 HIR 文件位置

- `/tmp/hir_output.txt` - 完整 HIR 导出（202 行）
- `/tmp/hir_demo.py` - 测试脚本

### B. 导出命令

```bash
source /tmp/cinderx-debug/bin/activate
cd /Users/luchen/Agents-Repo/OpenCode/cinderx
PYTHONJITDEBUG=1 python -X jit-list-file=<(echo "__main__:bench_regex_compile") \
  -X jit-dump-final-hir /tmp/hir_regex.py
```

### C. 关键文件

- `cinderx/Jit/hir/builder.cpp` - HIR 构建
- `cinderx/Jit/hir/guard_removal.cpp` - 守卫移除优化
- `cinderx/Jit/hir/refcount_insertion.cpp` - 引用计数优化
- `cinderx/Jit/hir/slot_version_guard_elimination.cpp` - 守卫消除

---

**结论**: HIR 分析揭示了性能瓶颈主要在 **Deopt 点**（UNPACK_SEQUENCE 类型检查）。通过放宽类型检查条件和启用 HIR Inliner，有望消除 17.6% 的性能劣化。
