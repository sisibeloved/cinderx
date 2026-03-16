# Performance Experiment Tracker Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一份长期维护的性能实验提交跟踪表，让每个性能提交都能隔离记录、可回溯、可对比收益。

**Architecture:** 采用一份 Markdown 文件承载两张表：提交主表和 benchmark 明细表。主表面向“改动归因”，明细表面向“实验结果”，两者通过人工递增 `ID` 和 `Run ID` 关联。

**Tech Stack:** Markdown, git, pyperformance, 本地脚本 `scripts/arm/run_local_pyperf_matrix.py`

---

## 固化后的执行闭环

后续每一轮性能实验都必须按下面这套闭环执行：

1. 只选择一个主假设
   - 一个实验开关
   - 一个提交候选
2. 先写失败测试
   - 优先验证 HIR / deopt / lowering 形状是否真的命中
3. 最小实现
4. 本地重编并跑测试
5. 先跑目标 benchmark
6. 再跑固定全量集
   - `coroutines`
   - `comprehensions`
   - `richards`
   - `richards_super`
   - `go`
   - `deltablue`
   - `raytrace`
   - `nqueens`
   - `float`
   - `generators`
7. 计算几何平均
8. 按门槛决定提交内容
   - `几何平均 > 1.0x`
     - 可以提交性能代码
     - 可以提交测试
     - 必须回填跟踪表
   - `几何平均 <= 1.0x`
     - 不提交性能代码
     - 可以提交分析文档
     - 可以提交跟踪表和流程文档
     - 失败实验代码只保留在工作树或单独清理

## 每轮结束时的提交内容判定

每轮实验结束后，必须显式区分下面三类文件：

### 1. 可提交

- 跟踪表
- 分析文档
- 流程文档
- 已过门槛的单开关性能代码

### 2. 只保留为 WIP

- 已命中结构目标但未过 `几何平均 > 1.0x` 的性能代码
- 下一轮还会继续复用的实验测试

### 3. 必须清理

- `.dev_build`
- `__pycache__`
- 生成的 `opcode.py`
- 明显误改

这一步要在 `git add` 前完成，避免把失败实验代码和文档混进同一个正式提交。

---

## Chunk 1: 建立跟踪文件

### Task 1: 创建跟踪表模板

**Files:**
- Create: `docs/superpowers/plans/2026-03-14-performance-experiment-commit-tracker.md`

- [ ] **Step 1: 写出跟踪文件骨架**

包含：
- 口径定义
- 提交主表
- benchmark 明细表
- 当前优先实验队列

- [ ] **Step 2: 用最近已完成的基础设施提交填入第一行**

提交：
- `5aa24f54`

类型：
- `infra`

目的：
- 跑通本地 macOS Arm pyperformance JIT smoke path

- [ ] **Step 3: 保存文件并检查格式**

Run: `sed -n '1,260p' docs/superpowers/plans/2026-03-14-performance-experiment-commit-tracker.md`
Expected: 结构完整，表格列名一致

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-03-14-performance-experiment-commit-tracker.md
git commit -m "docs: add performance experiment commit tracker"
```

## Chunk 2: 定义填写规范

### Task 2: 固化实验录入规范

**Files:**
- Modify: `docs/superpowers/plans/2026-03-14-performance-experiment-commit-tracker.md`

- [ ] **Step 1: 在文件顶部补充填写规则**

明确：
- speedup 公式
- `prev-cinderx` 与 `cpython-anchor` 的区别
- 什么情况下记录 `accepted` / `rejected` / `superseded`

- [ ] **Step 2: 补充一组样例结果**

使用已有实验结果填入：
- `coroutines`
- `richards`

- [ ] **Step 3: 检查样例是否足够指导后续手工更新**

Run: `sed -n '1,320p' docs/superpowers/plans/2026-03-14-performance-experiment-commit-tracker.md`
Expected: 新同学只看文件也知道怎么填

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-03-14-performance-experiment-commit-tracker.md
git commit -m "docs: define performance tracker conventions"
```

## Chunk 3: 接入当前实验队列

### Task 3: 预登记下一批 Arm JIT 实验提交

**Files:**
- Modify: `docs/superpowers/plans/2026-03-14-performance-experiment-commit-tracker.md`

- [ ] **Step 1: 把下一批候选提交先登记为 planned**

至少包含：
- Arm coroutine fast path
- Arm instance-value aggressive fast path
- Arm numeric leaf fast path
- comprehensions correctness fix

- [ ] **Step 2: 为每条 planned 记录补全假设和目标 benchmark**

每条记录至少说明：
- 改动点
- 主实验开关
- 预期收益 benchmark

- [ ] **Step 3: 检查 planned 队列和现有设计文档一致**

参考：
- `docs/superpowers/specs/2026-03-14-arm-jit-first-absolute-improvement-design.md`

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-03-14-performance-experiment-commit-tracker.md
git commit -m "docs: seed planned arm jit experiment entries"
```

Plan complete and saved to `docs/superpowers/plans/2026-03-14-performance-experiment-tracker-implementation-plan.md`. Ready to execute?
