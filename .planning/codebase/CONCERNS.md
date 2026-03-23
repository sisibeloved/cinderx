# CinderX 代码库问题清单（按严重程度排序）

> 范围：`README.md`、`cinderx/Jit/code_allocator.cpp`、`cinderx/Jit/pyjit.cpp`、`cinderx/Jit/threaded_compile.h`、`cinderx/TestScripts/cinder_jit_ignore_tests.txt`

## 严重（Critical）

### 1) JIT 代码页使用 RWX 映射，扩大可利用面（安全风险）
- **证据**：`cinderx/Jit/code_allocator.cpp:40` 使用 `PROT_EXEC | PROT_READ | PROT_WRITE`；`cinderx/Jit/code_allocator.cpp:50` 使用 `PAGE_EXECUTE_READWRITE`。
- **影响**：可写且可执行内存违反 W^X 最小权限原则，若存在内存破坏漏洞，攻击者更容易把数据页转为执行载荷。
- **关联技术债**：当前分配流程未体现“写入后改为 RX”的页权限收敛步骤。

### 2) 代码释放未实现，JIT 内存仅增不减（技术债 + 性能/稳定性风险）
- **证据**：`cinderx/Jit/code_allocator.cpp:212`、`cinderx/Jit/code_allocator.cpp:351` 明确 `TODO(T233607793): Actually implement deallocating memory.`
- **影响**：长生命周期进程中代码缓存持续增长，可能触发 RSS 上升、碎片化、最终 OOM 或性能退化。

## 高（High）

### 3) 多线程编译路径复杂且脆弱，存在并发正确性维护成本
- **证据**：
  - `cinderx/Jit/pyjit.cpp:1039-1048`：多线程编译时主动关闭 GIL 检查，转为“自管锁”。
  - `cinderx/Jit/threaded_compile.h:152-160`：明确承认“尚不够纪律化”，使用递归锁兜底。
  - `cinderx/Jit/threaded_compile.h:157-169`：注释指出断言可能有假阴性，依赖约定而非强保证。
  - `cinderx/Jit/threaded_compile.h:202-216`：`ThreadedRef` 直接操作 refcount，且明确说明调试统计会失真。
- **影响**：并发 bug（竞态/死锁/引用计数不一致）排查难度高；在 free-threading 场景下更容易出现边界问题。

### 4) JIT 初始化受架构门槛限制，功能可用性易与预期不一致
- **证据**：`cinderx/Jit/pyjit.cpp:3643-3648` 非 `x86_64/aarch64` 直接禁用 JIT。
- **影响**：在支持矩阵外环境会“可安装但运行时降级/禁用”，容易造成用户误判与生产环境行为偏差。

### 5) 平台支持不对称：macOS 可导入但大部分功能禁用，Windows 不支持
- **证据**：`README.md:31-33`。
- **影响**：跨平台一致性弱；本地开发（尤其 macOS）与 Linux 线上表现差异大，增加排障与验证成本。

## 中（Medium）

### 6) 大量已知功能缺口通过“忽略测试”绕过，覆盖盲区明显（技术债）
- **证据**：
  - `cinderx/TestScripts/cinder_jit_ignore_tests.txt:1-3` 说明依赖不支持特性，JIT 开启时手动禁用。
  - `...:22` 递归限制不支持。
  - `...:112` `locals()` 不支持。
  - `...:122` `settrace()/setprofile()` 不支持。
  - `...:143` 不做 bytecode quickening。
  - `...:163` 不遵循 PEP-523。
- **影响**：行为与 CPython 差异较大，功能回归风险更容易“被忽略列表掩盖”。

### 7) 编译流程存在串行化/回退路径，吞吐上限受限（性能瓶颈）
- **证据**：
  - `cinderx/Jit/code_allocator.cpp:154`、`278`：关键分配流程被 `ThreadedCompileSerialize` 包裹。
  - `cinderx/Jit/pyjit.cpp:1065-1072`：多线程失败单元会回退串行重试。
- **影响**：高并发批量编译时，锁竞争和串行 fallback 会拉低理论加速比。

## 低（Low）

### 8) 关闭 cinderx 模块内编译的“临时性 Hack”暴露生命周期耦合
- **证据**：`cinderx/Jit/pyjit.cpp:162-169` 注释直接称为 hack，用于避免模块无法 finalize 与潜在 UAF/ASAN 问题。
- **影响**：这是对生命周期问题的规避而非根治，后续重构时易成为脆弱点。

---

## 重点脆弱区域总览
- `cinderx/Jit/threaded_compile.h`：多线程状态机 + 自定义 refcount 路径。
- `cinderx/Jit/code_allocator.cpp`：可执行内存策略、释放逻辑缺失。
- `cinderx/Jit/pyjit.cpp`：初始化/停用/探针补丁逻辑集中，跨平台与工具链条件分支密集。
