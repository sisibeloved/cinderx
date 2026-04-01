# 2026-03-30 JIT 段错误修复与验证整理

## 背景

在 Kunpeng（aarch64）环境开启 AutoJIT 跑 `pyperformance` 时，出现两类核心问题：

1. 进程在 JIT 相关路径直接 `abort/core dumped`。
2. 命令可运行但 `PYTHONJITLOGFILE` 为空，实际未按预期进入 CinderX JIT。

本次整理只保留“稳定运行必需”的修复。

## 修复项

### 1) AArch64 `PyThreadState` 偏移探测失败时不再强制断言

- 文件：`cinderx/Jit/codegen/frame_asm.cpp`
- 修复点：
  - `initThreadStateOffset()` 在 aarch64 上未匹配到 TLS 访问模板时，不再 `assert(false)`。
  - 保持 `tstate_offset == -1`，由 `loadTState()` 走 `_PyThreadState_GetCurrent()` 回退路径。
  - 增加可选诊断日志开关 `PYTHONJITLOGTSTATEOFFSET`（默认关闭）。
- 目的：避免不同编译器/系统组合下，因指令模板不匹配导致进程启动期崩溃。

### 2) pyperformance hook 路径兼容容器与宿主机

- 文件：`docker/cinderx-test/scripts/benchmark_harness.py`
- 修复点：
  - `pyperformance_hook_root()` 优先使用显式环境变量；
  - 否则先尝试容器路径 `/pyperf_env_hook`；
  - 宿主机场景回退到 `scripts/arm/pyperf_env_hook`。
- 目的：避免宿主机运行时 `sitecustomize.py` 未加载，导致 JIT 配置不生效。

### 3) driver/worker 环境变量拆分，确保 worker 真正启用 AutoJIT

- 文件：
  - `docker/cinderx-test/scripts/test-benchmark.sh`
  - `scripts/arm/pyperf_env_hook/sitecustomize.py`
- 修复点：
  - driver 进程保持 `PYTHONJITDISABLE=1`；
  - worker 继承 `PYTHONJITAUTO`（不继承 `PYTHONJITDISABLE`）；
  - 真实环境使用 `python -m pyperformance run` 时，必须通过
    `--inherit-environ` 显式传递 `LD_LIBRARY_PATH`；
  - 在 worker hook 中显式执行：
    - `jit.auto()`
    - `jit.compile_after_n_calls(int(PYTHONJITAUTO))`
- 目的：解决“看似启用 JIT，实际阈值回到默认/未触发编译”的问题。
  - 补充说明：若未继承 `LD_LIBRARY_PATH`，pyperf worker 可能回退到系统
    `/lib64/libstdc++.so.6`，导致 `_cinderx` 导入时报
    `GLIBCXX_3.4.31 not found`，随后 `cinderjit` 不会被注册。

### 4) AArch64 生成器 deopt trampoline 栈槽位错位，导致 `async_generators` 崩溃

- 文件：`cinderx/Jit/codegen/gen_asm.cpp`
- 复现命令（真实环境最小样本）：

```bash
PYTHONPATH=/Users/luchen/Agents-Repo/Codex/cinderx/scripts/arm/pyperf_env_hook \
PYTHONJITAUTO=2 \
PYTHONJITHUGEPAGES=0 \
PYTHONJITSPECIALIZEDOPCODES=1 \
PYTHONJITDUMPSTATS=1 \
PYTHONJITDUMPFINALHIR=1 \
PYTHONJITLOGFILE=/home/jit-async_generators.log \
python /root/.pyenv/versions/3.14.3/lib/python3.14/site-packages/pyperformance/data-files/benchmarks/bm_async_generators/run_benchmark.py \
  --worker -l5 -w11 -n2
```

- 初始现象：
  - 进程稳定 `SIGSEGV`，`gdb` 栈停在 `prepareForDeopt(... deopt_idx=9)`。
  - 对应 HIR 固定落在 `__main__:bench_async_generators` 的
    `GetANext -> Send -> YieldFrom` 路径。
- 关键定位过程：
  1. 在 `send_core()` 断住时，`gen_footer->code_rt` 是正常值。
  2. 到 `prepareForDeopt()` 现场时，传入的 `code_runtime` 已变成
     `0xfffff591ce70` 这类明显错误的地址。
  3. 进一步 `gdb` 查看该坏地址内容时，发现前半段像 `RuntimeFrameState`，
     而不是完整 `CodeRuntime`，说明不是 metadata 本身损坏，而是 generator
     deopt trampoline 传错了基址。
  4. 打开 `CINDERX_AARCH64_DEOPT_TRACE=1` 后，确认问题集中在
     aarch64 generator-mode stage2 对 stage1 元数据的重排。
- 根因：
  - AArch64 generator-mode deopt trampoline 把“原始 `deopt_idx` 输入槽”和
    “新 frame 的 saved-fp 槽”混用了。
  - 同时又按错误偏移去取 `CodeRuntime`。
  - 第一层会把错误地址传入 `prepareForDeopt()`；
  - 修掉后又暴露出第二层问题：`fp/sp` 恢复错位，最终在 trampoline 末尾
    `ldp x29, x30, [sp], #16` 触发 `SIGBUS`。
- 修复点：
  - 将 generator-mode 的 stage1 输入槽位和 stage2 新 frame 槽位拆成显式偏移：
    - `stage1_saved_fp_offset`
    - `stage1_deopt_idx_input_offset`
    - `stage1_saved_pc_input_offset`
  - 不再把 `saved-fp` 与 `deopt_idx` 共用同一偏移。
  - 恢复 `CodeRuntime` 读取为基于正确 `fp` 的标准槽位。
- 效果：
  - 修复后 `prepareForDeopt()` 收到的 `code_runtime` 恢复为正确值；
  - `async_generators` 在 Kunpeng 真实环境最小复现下通过：
    - `async_generators: Mean +- std dev: 730 ms +- 0 ms`
    - `STATUS=0`

## 验证口径

建议命令（宿主机）：

```bash
BENCHMARK=regex_compile \
WARMUP=3 \
PYTHONJITAUTO=2 \
DIAG=1 \
JIT_LOG_FILE=/tmp/hir-regex.log \
OUTPUT_FILE=/tmp/hir-regex.json \
bash docker/cinderx-test/scripts/test-benchmark.sh
```

验收标准：

1. 命令可稳定完成，无 `core dumped`。
2. `JIT_LOG_FILE` 非空，且包含 `Optimized HIR for ...`。
3. worker 侧 AutoJIT 阈值按 `PYTHONJITAUTO` 生效。
4. 对生成器/协程类 benchmark，若出现 `prepareForDeopt()` 或 generator
   trampoline 相关崩溃，优先检查 aarch64 generator-mode 的 stage1/stage2
   栈槽位重排，而不是先怀疑 HIR。

## 注意事项

1. 功能验证阶段开启 `DIAG=1` 先确认“已进 JIT 且 HIR 正常”。
2. 性能对比阶段关闭额外 dump，避免日志 I/O 干扰。
3. 在本项目的 JIT benchmark 场景中建议显式设置：`PYTHONJITHUGEPAGES=0`。
4. 真实环境直跑 `pyperformance run` 时，`--inherit-environ` 至少应包含
   `LD_LIBRARY_PATH`、`PYTHONPATH` 以及各项 JIT 控制变量；否则 manager
   进程可导入 `_cinderx`，但 pyperf worker 可能因动态库版本不匹配而失败。
