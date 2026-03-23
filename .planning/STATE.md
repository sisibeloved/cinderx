# CinderX LTO/PGO 性能修复 - 项目状态

## 当前状态概览

**项目阶段**: Phase 1 执行中 - Plan 01 完成  
**最后更新**: 2026-03-23  
**下次更新**: Plan 01-02 完成时

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: 基础修复    [██░░░░░░░░] 33%  进行中              │
│  Phase 2: 功能完善    [██░░░░░░░░] 20%  进行中              │
│  Phase 3: 性能优化    [░░░░░░░░░░] 0%  等待中               │
└─────────────────────────────────────────────────────────────┘
```

---

## 已完成的决策

### 架构决策

| 决策 | 状态 | 日期 | 备注 |
|------|------|------|------|
| 默认禁用 LTO/PGO | ✅ 已批准 | 2026-03-23 | 直到修复完成 |
| 使用 `noinline` 标记保护 JITRT 函数 | ✅ 已批准 | 2026-03-23 | 主要修复策略 |
| PGO 训练使用 pyperformance | ✅ 已批准 | 2026-03-23 | 替代 CPython 测试套件 |
| macOS 优雅降级 | ✅ 已批准 | 2026-03-23 | 自动禁用 LTO |

### 技术选型

| 选型 | 选项 | 状态 | 理由 |
|------|------|------|------|
| 保护属性 | `__attribute__((noinline))` | ✅ 已选定 | 跨编译器支持 |
| API 设计 | `cinderx.is_lto_enabled()` | ✅ 已选定 | 与现有 API 一致 |
| 测试框架 | pytest + unittest | ✅ 已选定 | 项目标准 |
| CI 平台 | GitHub Actions | ✅ 已选定 | 现有基础设施 |

---

## 阻塞项

### 当前无阻塞项 🎉

所有前置条件已满足：
- ✅ 代码库分析完成
- ✅ 根因识别完成
- ✅ 技术方案确定
- ✅ 资源分配就绪

### 潜在风险监控

| 风险 | 概率 | 影响 | 监控指标 |
|------|------|------|----------|
| ARM 服务器不可用 | 中 | 高 | SSH 连接状态 |
| 工具链版本冲突 | 中 | 中 | 构建失败率 |
| 性能目标难达成 | 中 | 中 | 基准测试结果 |

---

## 进行中工作

### 当前 Sprint: Phase 1 执行中

**起止**: 2026-03-23 → 2026-03-30  
**目标**: 完成 Phase 1 基础修复 (Plans 01-01 至 01-05)

#### 已完成
- [x] 创建 GSD 项目配置
- [x] 编写 PROJECT.md（项目愿景）
- [x] 编写 REQUIREMENTS.md（需求文档）
- [x] 编写 ROADMAP.md（路线图）
- [x] 编写本 STATE.md（项目状态）
- [x] **Plan 01-01**: 标记 JITRT 函数为 noinline
  - 113 个函数声明和定义已标记
  - 符号表验证通过 (nm -C)
  - 构建测试通过

#### 进行中
- [ ] **Plan 01-02**: 更新 PGO 训练工作负载
- [ ] **Plan 01-03**: 添加工具链检查

#### Phase 2 已完成
- [x] **Plan 02-01**: 实现 LTO 检测 API `is_lto_enabled()`
- [x] **Plan 02-02**: 更新 LTO/PGO 文档

#### 待完成
- [ ] **Plan 01-04**: macOS 优雅降级
- [ ] **Plan 01-05**: 验证和测试

---

## 待办事项

### 高优先级（本周）

- [x] **TODO-001**: 提交 GSD 项目文档
  - 提交 `config.json`, `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`
  - Commit message: "gsd: 初始化 LTO/PGO 性能修复项目"

- [x] **TODO-002**: 完成 Task 1.1 (Plan 01-01)
  - 标记 JIT 运行时函数为 noinline
  - 文件: `cinderx/Jit/jit_rt.h`, `cinderx/Jit/jit_rt.cpp`
  - 结果: 113 个函数声明和定义已标记, 符号表验证通过

### 中优先级（下周）

- [ ] **TODO-003**: 执行 Task 1.2
  - 更新 PGO 工作负载
  - 文件: `setup.py`

- [ ] **TODO-004**: 执行 Task 1.3
  - 添加工具链检查
  - 文件: `setup.py`

### 低优先级（后续）

- [ ] **TODO-005**: 执行 Task 1.4
  - macOS 优雅降级
  - 文件: `CMakeLists.txt`

- [ ] **TODO-006**: Phase 1 集成测试
  - 验证 LTO 构建
  - 创建测试报告

---

## 资源状态

### 人力资源

| 角色 | 姓名 | 分配 | 状态 |
|------|------|------|------|
| C++ 工程师 | 待分配 | 1 FTE | 🔍 招募中 |
| Python 工程师 | 待分配 | 0.5 FTE | 🔍 招募中 |
| 项目经理 | 当前用户 | 0.2 FTE | ✅ 在职 |

### 硬件资源

| 资源 | 类型 | 状态 | 备注 |
|------|------|------|------|
| ARM64 Linux | 云服务器 | ⚠️ 待验证 | 124.70.162.35 |
| X86_64 Linux | 本地/云 | ✅ 可用 | 开发和 CI |
| macOS | 本地 | ✅ 可用 | 降级测试 |

### 工具链

| 工具 | 版本 | 状态 | 备注 |
|------|------|------|------|
| GCC | 13+ | ✅ 已安装 | 主要编译器 |
| Clang | 18+ | ⚠️ 待安装 | ARM 服务器 |
| llvm-ar | - | ⚠️ 待安装 | ARM 服务器 |
| pyperformance | latest | ✅ 已安装 | 基准测试 |

---

## 关键指标

### 基线数据（无 LTO）

| 基准测试 | 当前值 | 目标（LTO） | 单位 |
|----------|--------|-------------|------|
| Richards | 0.0516 | 0.0490 ~ 0.0552 | 秒 |
| N-body | TBD | TBD | 秒 |
| 构建时间 | 5 min | < 6.5 min | 分钟 |
| 内存占用 | 2 GB | < 3 GB | GB |

*注：TBD = 待测量*

### 质量指标

| 指标 | 当前 | 目标 | 监控方式 |
|------|------|------|----------|
| 构建成功率 | N/A | 100% | CI/CD |
| 测试通过率 | N/A | 100% | pytest |
| 性能劣化 | N/A | < 1% | pyperformance |
| 代码覆盖率 | N/A | > 80% | coverage.py |

---

## 参考链接

### 项目文档
- [项目愿景](./PROJECT.md)
- [需求文档](./REQUIREMENTS.md)
- [路线图](./ROADMAP.md)
- [技术分析报告](./LTO_PGO_PERFORMANCE_ANALYSIS.md)

### 代码库文档
- [技术栈](./codebase/STACK.md)
- [架构设计](./codebase/ARCHITECTURE.md)
- [已知问题](./codebase/CONCERNS.md)

### 外部资源
- CinderX GitHub: https://github.com/facebookincubator/cinderx
- pyperformance: https://github.com/python/pyperformance
- GCC LTO 文档: https://gcc.gnu.org/wiki/LinkTimeOptimization

---

## 变更历史

| 日期 | 变更 | 作者 | 备注 |
|------|------|------|------|
| 2026-03-23 | 初始化项目 | GSD | 创建所有规划文档 |
| 2026-03-23 | 完成技术分析 | GSD | 识别 5 大根因 |
| 2026-03-23 | 完成 Plan 01-01 | GSD | 标记 113 个 JITRT 函数为 noinline，符号表验证通过 |
| 2026-03-23 | 完成 Plan 02-01 | GSD | 实现 LTO 检测 API `cinderx.is_lto_enabled()`，包含 C++/Python 实现和测试 |
| 2026-03-23 | 完成 Plan 02-02 | GSD | 更新 LTO/PGO 文档：README.md 添加使用指南，创建 docs/build.md 完整构建文档 |
| 2026-03-23 | 更新 STATE.md | GSD | 更新项目状态、变更历史和下一步行动 |

---

---

## 下一步行动

1. **Phase 2 完成**: Plan 02-02 已完成 ✅
   - README.md 添加 LTO/PGO 使用指南
   - 创建 docs/build.md 完整构建文档
   - Commit: fb8bef2

2. **立即执行**: 开始 Plan 01-02
   - 更新 PGO 训练工作负载
   - 文件: `setup.py`

3. **本周**: 完成 Plan 01-02 和 01-03
   - PGO 工作负载更新 (01-02)
   - 工具链检查 (01-03)

4. **下周**: Phase 1 里程碑检查
   - 验证 LTO 构建成功
   - 运行回归测试

---

*文档版本: 1.0*  
*更新频率: 每阶段里程碑*  
*维护者: CinderX JIT 优化团队*