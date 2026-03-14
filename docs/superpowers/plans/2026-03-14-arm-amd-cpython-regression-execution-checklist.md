# Arm 与 AMD 平台 CPython 基准回退执行清单

> **面向代理执行者：** 必须使用 `superpowers:subagent-driven-development`（若支持子代理）或 `superpowers:executing-plans` 来执行本计划。步骤使用复选框 `- [ ]` 跟踪。

**目标：** 把回退分析计划落成一套可直接执行的命令顺序、产物目录和判定规则。

**总体方法：** 按层执行：先确认构建与运行时特性状态，再建立基线矩阵，之后分离 startup / interpreter / JIT 成本，最后只对共享根因无法解释的 benchmark 做专项深挖。

**技术栈：** PowerShell 部署脚本、ARM 远端构建脚本、pyperformance、CinderX JIT runtime stats、CPython 基线 worktree

---

## 前置准备

### 任务 1：确认本地与远端执行入口

**文件：**
- 阅读：`/Users/luchen/Repo/cinderx/scripts/push_to_arm.ps1`
- 阅读：`/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh`
- 阅读：`/Users/luchen/Repo/cinderx/scripts/arm/interp_feature_matrix.sh`
- 阅读：`/Users/luchen/Repo/cinderx/scripts/arm/bench_pyperf_direct.py`

- [ ] **步骤 1：确认当前分支与基线提交**

运行：
```bash
git -C /Users/luchen/Repo/cinderx rev-parse HEAD
git -C /Users/luchen/Repo/cpython rev-parse ebf955df7a89ed0c7968f79faec1de49f61ed7cb
```

预期：
- 两个 revision 都能成功解析

- [ ] **步骤 2：创建本地证据目录**

运行：
```bash
mkdir -p /Users/luchen/Repo/cinderx/artifacts/2026-03-14-arm-amd-regression
```

- [ ] **步骤 3：确认 Arm 默认构建特性**

运行：
```bash
cd /Users/luchen/Repo/cinderx
python3 - <<'PY'
from setup import should_enable_adaptive_static_python, should_enable_lightweight_frames
print("arm adaptive", should_enable_adaptive_static_python("3.14", False, "arm64"))
print("arm lightweight", should_enable_lightweight_frames("3.14", False, "arm64"))
print("amd adaptive", should_enable_adaptive_static_python("3.14", False, "x86_64"))
print("amd lightweight", should_enable_lightweight_frames("3.14", False, "x86_64"))
PY
```

预期：
- Arm 两项默认值都是 `True`
- x86_64 两项默认值都是 `False`

### 任务 2：建立 ARM 远端部署循环

**文件：**
- 阅读：`/Users/luchen/Repo/cinderx/scripts/push_to_arm.ps1`
- 阅读：`/Users/luchen/Repo/cinderx/arm_jit_guide.md`

- [ ] **步骤 1：把当前分支部署到 ARM 主机**

若你当前仍使用 Windows/PowerShell 驱动远端部署，运行：
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
- tarball 推送成功
- ARM 端 wheel 构建成功
- smoke test 成功

- [ ] **步骤 2：记录 ARM 远端环境**

在 ARM 主机上记录：
```bash
uname -a
/opt/python-3.14/bin/python3.14 -V
/root/venv-cinderx314/bin/python -V
```

保存到：
- `artifacts/2026-03-14-arm-amd-regression/arm-env.txt`

---

## 测量矩阵

### 任务 3：在 ARM 上建立解释器 feature matrix

**文件：**
- 运行：`/Users/luchen/Repo/cinderx/scripts/arm/interp_feature_matrix.sh`
- 输出：`/root/work/arm-sync/interp_feature_matrix_<run_id>/`

- [ ] **步骤 1：先用一个代表 benchmark 跑通矩阵**

从 `richards` 开始：
```bash
BENCH=richards \
DRIVER_VENV=/root/venv-cinderx314 \
WORKDIR=/root/work/cinderx-main \
INCOMING_DIR=/root/work/incoming \
PARALLEL=1 \
COMBOS="1,1 1,0 0,1 0,0" \
/root/work/cinderx-main/scripts/arm/interp_feature_matrix.sh
```

预期：
- 生成一个 `summary.json`
- 生成一个 `results.tsv`
- 四个 feature combo 都有结果

- [ ] **步骤 2：对解释器簇 benchmark 逐个重复**

继续跑：
- `coroutines`
- `comprehensions`
- `richards_super`
- `go`
- `deltablue`
- `nqueens`

判读规则：
- 如果 `0,0` 明显优于 `1,1`，说明 Arm-only 默认特性是主要原因之一
- 如果所有组合都明显落后于 CPython，则剩余差距更偏结构性的解释器开销

- [ ] **步骤 3：把结果回收至本地**

建议本地目录：
```bash
artifacts/2026-03-14-arm-amd-regression/interp-matrix/
```

### 任务 4：建立原始 pyperformance 模式矩阵

**文件：**
- 直接运行 pyperformance
- 输出：`/root/work/arm-sync/<bench>_<mode>_<run_id>.json`

- [ ] **步骤 1：Arm 上游/解释器基线**

在 ARM 上运行：
```bash
. /root/venv-cinderx314/bin/activate
PYTHONJIT=0 python -m pyperformance run --debug-single-value -b richards -o /root/work/arm-sync/richards_arm_cinderx_interp.json
deactivate
```

如果有纯 upstream CPython 环境，也运行：
```bash
PYTHON_JIT=0 /opt/python-3.14/bin/python3.14 -m pyperformance run --debug-single-value -b richards -o /root/work/arm-sync/richards_arm_cpython_interp.json
```

- [ ] **步骤 2：Arm 上运行 CinderX jitlist**

```bash
cat >/tmp/jitlist_richards.txt <<'EOF'
__main__:*
EOF
. /root/venv-cinderx314/bin/activate
env PYTHONJITLISTFILE=/tmp/jitlist_richards.txt PYTHONJITENABLEJITLISTWILDCARDS=1 \
  python -m pyperformance run --debug-single-value -b richards \
  --inherit-environ PYTHONJITLISTFILE,PYTHONJITENABLEJITLISTWILDCARDS \
  -o /root/work/arm-sync/richards_arm_cinderx_jitlist.json
deactivate
```

- [ ] **步骤 3：Arm 上运行 CinderX autojit**

```bash
. /root/venv-cinderx314/bin/activate
env PYTHONJITAUTO=50 \
  python -m pyperformance run --debug-single-value -b richards \
  --inherit-environ PYTHONJITAUTO \
  -o /root/work/arm-sync/richards_arm_cinderx_autojit50.json
deactivate
```

- [ ] **步骤 4：对高优 benchmark 复用同一模式**

使用同样三种模式继续跑：
- `coroutines`
- `comprehensions`
- `richards`
- `richards_super`
- `go`
- `deltablue`

而 `raytrace`、`float`、`generators`、`python_startup` 放到后续专项模式分析。

---

## 启动成本隔离

### 任务 5：单独拆解 `python_startup`

**文件：**
- 阅读：`/Users/luchen/Repo/cinderx/scripts/arm/remote_update_build_test.sh`
- 阅读：`/Users/luchen/Repo/cinderx/cinderx/PythonBin/sitecustomize.py`

- [ ] **步骤 1：禁用 worker autoload 后运行 startup benchmark**

在 ARM 上 pyperformance venv 内运行：
```bash
SITEPKG="$(python -c 'import site; print(site.getsitepackages()[0])')"
mv "$SITEPKG/sitecustomize.py" "$SITEPKG/sitecustomize.py.disabled"
python -m pyperformance run --debug-single-value -b python_startup -o /root/work/arm-sync/python_startup_noautoload.json
mv "$SITEPKG/sitecustomize.py.disabled" "$SITEPKG/sitecustomize.py"
```

- [ ] **步骤 2：恢复 autoload 后再次运行**

```bash
python -m pyperformance run --debug-single-value -b python_startup -o /root/work/arm-sync/python_startup_autoload.json
```

- [ ] **步骤 3：额外采集 import timing**

```bash
python -X importtime -c "import cinderx" 2> /root/work/arm-sync/importtime_cinderx.txt
/opt/python-3.14/bin/python3.14 -X importtime -c "pass" 2> /root/work/arm-sync/importtime_cpython.txt
```

判读规则：
- 如果 benchmark body 还没开始就已经出现明显差距，`python_startup` 主要就是启动注入成本

---

## JIT 直跑取证

### 任务 6：使用 direct-run harness 深挖 `raytrace`、`float`、`generators`

**文件：**
- 运行：`/Users/luchen/Repo/cinderx/scripts/arm/bench_pyperf_direct.py`

- [ ] **步骤 1：`raytrace` direct-run 多模式对比**

示例命令：
```bash
. /root/venv-cinderx314/bin/activate
python /root/work/cinderx-main/scripts/arm/bench_pyperf_direct.py \
  --module-path <pyperformance-raytrace-module.py> \
  --bench-func <benchmark-entry> \
  --samples 5 \
  --prewarm-runs 1 \
  --compile-strategy all \
  --specialized-opcodes \
  --output /root/work/arm-sync/raytrace_direct_all.json
deactivate
```

随后继续跑：
- `--compile-strategy none`
- `--compile-strategy backedge`

重点看：
- `median_wall_sec`
- `compiled_count`
- `total_deopt_count`
- `top_deopts`

- [ ] **步骤 2：`float` direct-run**

用同一个 harness 对 `float` benchmark 模块或它的缩小复现执行。

重点看：
- 是否仍有 generic `BinaryOp`
- 是否没有出现 `DoubleBinaryOp`
- 当前热点是否还落在 accumulator promotion 和 `**2` rewrite 未覆盖的形状

- [ ] **步骤 3：`generators` direct-run**

继续使用同一个 harness，并观察：
- `LoadAttrCached`
- `LoadField`
- `Decref`
- `BatchDecref`

判读规则：
- 若 attr load 已消失但仍慢，下一步应盯 decref/runtime，而不是继续怀疑 attr lookup

### 任务 7：用 autojit threshold 矩阵做稳定性与阈值敏感性检查

**文件：**
- 运行：`/Users/luchen/Repo/cinderx/scripts/arm/autojit_crash_matrix.sh`

- [ ] **步骤 1：对易出问题 benchmark 先做阈值扫描**

建议先对：
- `coroutines`
- `richards`
- `raytrace`

运行：
```bash
BENCH=coroutines \
DRIVER_VENV=/root/venv-cinderx314 \
THRESHOLDS="20 50 80 100 200" \
/root/work/cinderx-main/scripts/arm/autojit_crash_matrix.sh
```

预期：
- `summary.json`
- 各 threshold 的日志文件
- 若失败则附带 coredump 元数据

判读规则：
- 这个脚本主要用于稳定性与 threshold 敏感性，不是主要吞吐结论来源

---

## benchmark 执行顺序

### 任务 8：高优先级最小执行集

**文件：**
- 输出：`artifacts/2026-03-14-arm-amd-regression/priority-order.md`

- [ ] **步骤 1：`coroutines`**

按顺序执行：
1. `interp_feature_matrix.sh`
2. 原始 pyperformance `interp/autojit`
3. 若有必要，再跑 threshold crash matrix

判定规则：
- 如果 `adaptive/lightweight` 开关显著影响结果，优先归因到 Arm 默认特性
- 否则优先检查 awaitable/coroutine runtime 路径

- [ ] **步骤 2：`comprehensions`**

按顺序执行：
1. `interp_feature_matrix.sh`
2. 原始 pyperformance `interp/autojit`
3. 若可行，再采 perf counters

判定规则：
- 如果纯解释器已经明显慢，不要一开始就下钻 JIT HIR

- [ ] **步骤 3：`richards` 与 `richards_super`**

按顺序执行：
1. `interp_feature_matrix.sh`
2. 原始 pyperformance `interp/jitlist/autojit`
3. perf counters

判定规则：
- 如果纯解释器已解释大部分差距，就归类为解释器结构成本
- 如果 JIT 进一步恶化，再做 direct-run 热点分析

- [ ] **步骤 4：`go` 与 `deltablue`**

按顺序执行：
1. 原始 pyperformance `interp/autojit`
2. 结合 `richards` 结论进行类比
3. 仅在必要时下钻 JIT 热 helper

- [ ] **步骤 5：`raytrace`**

按顺序执行：
1. 原始 pyperformance `interp/autojit`
2. direct-run `none/all/backedge`
3. 仅对少数热点做 HIR/deopt dump

- [ ] **步骤 6：`nqueens`**

按顺序执行：
1. 原始 pyperformance `interp/autojit`
2. perf counters
3. 只有 JIT 明显改变结果时才做 direct-run

- [ ] **步骤 7：`float`**

按顺序执行：
1. 原始 pyperformance `interp/autojit`
2. direct-run float 缩小复现
3. 检查剩余慢点是否是新的 float 形状

- [ ] **步骤 8：`generators`**

按顺序执行：
1. 原始 pyperformance `interp/autojit`
2. direct-run generator 缩小复现
3. 检查 decref/runtime stats

- [ ] **步骤 9：`python_startup`**

按顺序执行：
1. no-autoload vs autoload pyperformance
2. `-X importtime`
3. 只有在启动路径很干净时，才考虑继续做 JIT HIR 分析

---

## 证据记录模板

### 任务 9：统一记录每个 benchmark 的结论

**文件：**
- 创建/更新：`artifacts/2026-03-14-arm-amd-regression/report.md`

- [ ] **步骤 1：使用统一模板**

```markdown
## <benchmark>
- 回退类别：
- 主要根因簇：
- 属于 Arm-only 还是 x86-only 还是两边都有：
- 最强证据：
- 关键代码文件：
- 下一步验证：
- 置信度：
```

- [ ] **步骤 2：统一置信度标签**

- `高`：当前代码 + 当前测量 + 历史 findings 三者一致
- `中`：当前代码 + 一类测量一致
- `低`：只有代码阅读或间接证据

---

## 停止条件

### 任务 10：定义“理解够了”的退出标准

**文件：**
- 更新：`artifacts/2026-03-14-arm-amd-regression/report.md`

- [ ] **步骤 1：满足以下任一条件即可结束该 benchmark 的第一轮分析**

- feature matrix 已把差距定位到 Arm 默认特性
- startup autoload 开关已把差距定位到启动注入
- direct-run JIT stats 已把差距定位到 deopt / boxing / overcompile
- 纯解释器基线已解释绝大部分 CinderX-vs-CPython 差距

- [ ] **步骤 2：只有全部失败时才升级到更深层源码分析**

只有在下面都不成立时才继续深挖：
- startup 路径已排除
- interpreter feature matrix 无法解释
- JIT direct-run 无法解释
- benchmark 仍有显著未解释差距

