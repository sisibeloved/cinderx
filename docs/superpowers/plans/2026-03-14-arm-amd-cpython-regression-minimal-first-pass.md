# Arm 与 AMD 平台回退分析第一轮最小执行集

> **面向代理执行者：** 必须使用 `superpowers:subagent-driven-development`（若支持子代理）或 `superpowers:executing-plans` 来执行本计划。步骤使用复选框 `- [ ]` 跟踪。

**目标：** 用最少的运行次数，先把 4 条共享根因簇分开：解释器结构开销、Arm 默认特性开销、JIT mixed-numeric 问题、启动注入成本。

**覆盖 benchmark：**
- `coroutines`
- `richards`
- `raytrace`
- `python_startup`

**为什么只先跑这四个：**
- `coroutines`：代表 async/coroutine/awaitable 路径
- `richards`：代表高调用密度解释器路径
- `raytrace`：代表 JIT mixed int/float 与小 helper 过编译路径
- `python_startup`：代表启动注入与自动加载路径

---

## 产物目录

### 任务 1：建立第一轮证据目录

**文件：**
- 输出：`/Users/luchen/Repo/cinderx/artifacts/2026-03-14-first-pass/`

- [ ] **步骤 1：创建本地目录**

运行：
```bash
mkdir -p /Users/luchen/Repo/cinderx/artifacts/2026-03-14-first-pass
mkdir -p /Users/luchen/Repo/cinderx/artifacts/2026-03-14-first-pass/{coroutines,richards,raytrace,python_startup}
```

- [ ] **步骤 2：确认当前代码版本**

运行：
```bash
git -C /Users/luchen/Repo/cinderx rev-parse HEAD > /Users/luchen/Repo/cinderx/artifacts/2026-03-14-first-pass/cinderx_head.txt
git -C /Users/luchen/Repo/cpython rev-parse ebf955df7a89ed0c7968f79faec1de49f61ed7cb > /Users/luchen/Repo/cinderx/artifacts/2026-03-14-first-pass/cpython_base.txt
```

---

## 第一轮运行顺序

### 任务 2：先部署一次 ARM 当前分支

**文件：**
- 运行：`/Users/luchen/Repo/cinderx/scripts/push_to_arm.ps1`

- [ ] **步骤 1：仅做一次基线部署**

如果你是从 Windows 驱动 ARM 主机，先运行：
```powershell
powershell -ExecutionPolicy Bypass -File scripts\push_to_arm.ps1 `
  -RepoPath <your-git-clone> `
  -ArmHost <arm-host> `
  -WorkBranch bench-cur-7c361dce `
  -Benchmark richards `
  -AutoJit 50 `
  -CmakeParallel 1 `
  -SkipPyperformance
```

预期：
- ARM 侧 wheel 构建完成
- smoke tests 成功

### 任务 3：先跑两个解释器代表 benchmark

**文件：**
- 运行：`/Users/luchen/Repo/cinderx/scripts/arm/interp_feature_matrix.sh`

- [ ] **步骤 1：跑 `coroutines` 的解释器 feature matrix**

在 ARM 主机上运行：
```bash
BENCH=coroutines \
DRIVER_VENV=/root/venv-cinderx314 \
WORKDIR=/root/work/cinderx-main \
INCOMING_DIR=/root/work/incoming \
PARALLEL=1 \
COMBOS="1,1 1,0 0,1 0,0" \
/root/work/cinderx-main/scripts/arm/interp_feature_matrix.sh
```

保存：
- `summary.json`
- `results.tsv`
- 四个 combo 的 stdout/stderr/json

判读：
- 若 `0,0` 明显优于 `1,1`，优先怀疑 Arm 默认特性
- 若所有 combo 都明显慢，优先怀疑解释器结构额外开销或 coroutine 自定义路径

- [ ] **步骤 2：跑 `richards` 的解释器 feature matrix**

在 ARM 主机上运行：
```bash
BENCH=richards \
DRIVER_VENV=/root/venv-cinderx314 \
WORKDIR=/root/work/cinderx-main \
INCOMING_DIR=/root/work/incoming \
PARALLEL=1 \
COMBOS="1,1 1,0 0,1 0,0" \
/root/work/cinderx-main/scripts/arm/interp_feature_matrix.sh
```

判读：
- 若 `richards` 与 `coroutines` 都对 `adaptive/lightweight` 开关敏感，优先建立“Arm-only 默认特性”结论
- 若 `richards` 对开关不敏感但仍明显慢，优先建立“解释器结构开销”结论

### 任务 4：只对 `raytrace` 做第一轮 JIT 专项

**文件：**
- 运行：`/Users/luchen/Repo/cinderx/scripts/arm/bench_pyperf_direct.py`

- [ ] **步骤 1：先跑 `none` 模式**

在 ARM 主机上运行：
```bash
. /root/venv-cinderx314/bin/activate
python /root/work/cinderx-main/scripts/arm/bench_pyperf_direct.py \
  --module-path <raytrace benchmark 模块路径> \
  --module-name bm_raytrace_first_pass \
  --bench-func <benchmark 入口函数名> \
  --samples 5 \
  --prewarm-runs 1 \
  --compile-strategy none \
  --output /root/work/arm-sync/raytrace_direct_none.json
deactivate
```

- [ ] **步骤 2：再跑 `all` 模式**

```bash
. /root/venv-cinderx314/bin/activate
python /root/work/cinderx-main/scripts/arm/bench_pyperf_direct.py \
  --module-path <raytrace benchmark 模块路径> \
  --module-name bm_raytrace_first_pass \
  --bench-func <benchmark 入口函数名> \
  --samples 5 \
  --prewarm-runs 1 \
  --compile-strategy all \
  --specialized-opcodes \
  --output /root/work/arm-sync/raytrace_direct_all.json
deactivate
```

- [ ] **步骤 3：如果 `all` 比 `none` 更差，再跑 `backedge`**

```bash
. /root/venv-cinderx314/bin/activate
python /root/work/cinderx-main/scripts/arm/bench_pyperf_direct.py \
  --module-path <raytrace benchmark 模块路径> \
  --module-name bm_raytrace_first_pass \
  --bench-func <benchmark 入口函数名> \
  --samples 5 \
  --prewarm-runs 1 \
  --compile-strategy backedge \
  --specialized-opcodes \
  --output /root/work/arm-sync/raytrace_direct_backedge.json
deactivate
```

第一轮只看：
- `median_wall_sec`
- `compiled_count`
- `total_deopt_count`
- `top_deopts`

判读：
- 若 `all` 明显更差且 deopt 很高，优先怀疑 mixed numeric / overcompile
- 若 `none` 已经慢于预期，说明不是纯 JIT 问题

### 任务 5：只对 `python_startup` 做启动注入隔离

**文件：**
- 阅读：`/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh`

- [ ] **步骤 1：禁用 worker autoload 后运行**

在 ARM 主机上运行：
```bash
. /root/venv-cinderx314/bin/activate
SITEPKG="$(python -c 'import site; print(site.getsitepackages()[0])')"
mv "$SITEPKG/sitecustomize.py" "$SITEPKG/sitecustomize.py.disabled"
python -m pyperformance run --debug-single-value -b python_startup -o /root/work/arm-sync/python_startup_noautoload.json
mv "$SITEPKG/sitecustomize.py.disabled" "$SITEPKG/sitecustomize.py"
deactivate
```

- [ ] **步骤 2：恢复 autoload 后再次运行**

```bash
. /root/venv-cinderx314/bin/activate
python -m pyperformance run --debug-single-value -b python_startup -o /root/work/arm-sync/python_startup_autoload.json
deactivate
```

- [ ] **步骤 3：补一份 importtime**

```bash
. /root/venv-cinderx314/bin/activate
python -X importtime -c "import cinderx" 2> /root/work/arm-sync/importtime_cinderx.txt
deactivate
/opt/python-3.14/bin/python3.14 -X importtime -c "pass" 2> /root/work/arm-sync/importtime_cpython.txt
```

判读：
- 如果 `autoload` 和 `noautoload` 差异就很大，`python_startup` 第一结论就是启动注入成本

---

## 第一轮停止条件

### 任务 6：满足以下任一条件就结束第一轮

**文件：**
- 更新：`/Users/luchen/Repo/cinderx/artifacts/2026-03-14-first-pass/summary.md`

- [ ] **步骤 1：解释器路径已经足够明确**

满足任一：
- `coroutines` 与 `richards` 都对 feature combo 敏感
- `coroutines` 与 `richards` 都对 feature combo 不敏感，但都明显慢于 CPython

- [ ] **步骤 2：JIT 路径已经足够明确**

满足任一：
- `raytrace all` 明显差于 `none` / `backedge`
- `raytrace` 的 `top_deopts` 已明确指向 mixed numeric 或小 helper 过编译

- [ ] **步骤 3：启动路径已经足够明确**

满足任一：
- `python_startup autoload` 显著差于 `noautoload`
- `importtime` 已显示 `import cinderx` 是启动主成本

---

## 第一轮结论模板

### 任务 7：把四个 benchmark 的第一结论写成一页

**文件：**
- 创建：`/Users/luchen/Repo/cinderx/artifacts/2026-03-14-first-pass/summary.md`

- [ ] **步骤 1：使用固定模板**

```markdown
## coroutines
- 第一结论：
- 主要根因簇：
- 下一步是否需要深挖：

## richards
- 第一结论：
- 主要根因簇：
- 下一步是否需要深挖：

## raytrace
- 第一结论：
- 主要根因簇：
- 下一步是否需要深挖：

## python_startup
- 第一结论：
- 主要根因簇：
- 下一步是否需要深挖：
```

- [ ] **步骤 2：只回答三件事**

第一轮只回答：
- 是解释器问题、JIT 问题还是启动问题
- 更像 Arm-only、x86-only，还是共享结构性差异
- 值不值得进入第二轮专项分析

