# MDP getSuccessors Whole-Helper 优化报告

本报告记录 `bm_mdp.Battle.getSuccessors` 的第四轮真实优化、HIR 前后对比，以及当前已经确认的本地近似与 ARM Docker 正式收益。

## 1. `Battle.getSuccessors` 的 whole-helper 路径

本轮实现：

- 在 [simplify.cpp](/Users/luchen/Agents-Repo/Codex/cinderx/cinderx/Jit/hir/simplify.cpp) 中新增实验开关 `PYTHONJIT_ARM_MDP_GET_SUCCESSORS_WHOLE_HELPER`
- 在 [jit_rt.h](/Users/luchen/Agents-Repo/Codex/cinderx/cinderx/Jit/jit_rt.h) 与 [jit_rt.cpp](/Users/luchen/Agents-Repo/Codex/cinderx/cinderx/Jit/jit_rt.cpp) 中新增 `JITRT_MdpGetSuccessorsWholeHelper(...)`
- 新增回归测试 [test_jit_mdp_get_successors_experiments.py](/Users/luchen/Agents-Repo/Codex/cinderx/cinderx/PythonLib/test_cinderx/test_jit_mdp_get_successors_experiments.py)

设计要点：

- 不是继续做“miss 后仍保留 `KeyError`”的窄 helper
- 而是在 `Battle.getSuccessors` 的 `self.successors[statep]` 处直接返回整函数最终结果
- 命中时直接返回 cache value
- miss 时 helper 内部完成 `_getSuccessorsA/_B/_C`、排序与回填缓存，再返回最终结果

## 2. 优化前后 HIR 对比

优化前关键片段：

```text
fun bm_mdp:Battle.getSuccessors {
  ...
  bb 17 (preds 15, 16) {
    v28:Object = Phi<15, 16> v26 v27
    UpdatePrevInstr<idx:14 line_no:186: no parent>
    v23:Object = BinaryOp<Subscript> v28 v11
    Decref v28
    Return v23
  }
}
```

优化后关键片段：

```text
fun bm_mdp:Battle.getSuccessors {
  ...
  bb 17 (preds 15, 16) {
    v28:Object = Phi<15, 16> v26 v27
    UpdatePrevInstr<idx:14 line_no:186: no parent>
    v29:OptObject = CallStatic<..., 3> v14 v28 v11
    v30:Object = CheckExc v29
    Return v30
  }
}
```

结论：

- 优化前热点集中在 `BinaryOp<Subscript>` 触发 `UnhandledException`
- 优化后同一位置改为 `CallStatic + CheckExc`
- 这条路径不再依赖 `KeyError` 驱动 Python 级控制流

## 3. 关键调试结论

本轮中期路线分成了两个阶段：

### 3.1 第一版 whole-helper

- helper 自己重新 `PyObject_GetAttrString(self, "successors")`
- 结果虽然把 `Battle.getSuccessors` 的 deopt 清零，但本地近似中位数反而从 `6.005080s` 轻微退化到 `6.097405s`

判断：

- 这说明“消灭 deopt”本身不够
- 如果 helper 重复做 HIR 已经做过的属性读取，仍然会把命中路径拖重

### 3.2 第二版 whole-helper

- helper 改为直接复用 HIR 里已经拿到的 `successors` 对象
- `simplify.cpp` 在 `BinaryOp<Subscript>` 处传入 `self`、`successors`、`statep`
- 避免 helper 内部再次属性读取

这是当前保留在工作树里的版本。

## 4. 当前已确认的收益

`Battle.getSuccessors` 单点 HIR opcode 统计：

- baseline: `BinaryOp = 1`，`CallStatic = 0`，`CheckExc = 0`
- 优化后: `BinaryOp = 0`，`CallStatic = 1`，`CheckExc = 1`

`Battle.getSuccessors` 的局部运行时结果：

- baseline: `deopt = 2000`
- 优化后: `deopt = 0`

`mdp` 热点白名单本地近似跑分：

- 前三轮开关：`median_wall_sec = 6.005080s`
- 前四轮开关：`median_wall_sec = 5.745508s`
- 在前三轮基础上再提升约 `4.32%`

`mdp` 头部 deopt：

- 前三轮开关：`Battle.getSuccessors` 仍有 `14463` 次 `BinaryOp / UnhandledException`
- 前四轮开关：`total_deopt_count = 0`

判断：

- 这轮已经不是“只有 HIR 变好看”的实验
- `Battle.getSuccessors` 的异常控制流确实是 `mdp` 的一条主差距来源
- 采用中等粒度的 whole-helper 后，局部 deopt 与本地近似总时间都出现了同向改善

## 5. 当前判断

- 短期窄 helper 路径已经可以定性为无效方向，不值得继续
- 中期 whole-helper 路径已经证明可行，而且是当前 `mdp` 中最强的新收益点之一

## 6. ARM Docker 正式复核

命令：

```bash
docker exec cpython-baseline-test sh -lc 'BENCHMARK=mdp SAMPLES=5 WARMUP=1 /scripts/test-comparison.sh'
```

结果摘要：

- `stock CPython 3.14.0 + JIT = 1.038002s`
- `CinderX JIT = 1.113288s`
- `CinderX JIT + mdp 四轮优化 = 1.035180s`
- 当前 `CinderX JIT` 相对 `stock CPython JIT` 落后约 `6.76%`
- 四轮优化后的 `CinderX JIT` 相对 `stock CPython JIT` 领先约 `0.27%`
- 本轮及其前置三轮合并后的正式优化收益约 `7.55%`

判断：

- 第四轮不是只在本地近似口径上成立，ARM Docker 正式结果也已经同向验证
- `Battle.getSuccessors` 的异常控制流确实是 `mdp` 的真实主差距来源之一
- 在前置三轮优化基础上，whole-helper 路径是把 `mdp` 从“明显落后”拉到“基本持平并略有领先”的关键一步
