# CinderX LTO 性能验证 - 快速指南

**日期**: 2026-03-24
**状态**: 🔄 正在验证
**环境**: macOS Darwin 26.3.0 (arm64) → Docker Linux ARM64

---

## 🎯 目标

在 Linux ARM64 环境中验证 LTO 性能提升：
- **运行时性能**: +5% ~ +10%
- **构建时间增加**: < 30%
- **无性能退化**: < 1%

---

## ⚠️ 已知问题与解决方案

### 问题 1: macOS 不支持 LTO

**症状**: setup.py 会自动禁用 LTO

**解决方案**: 使用 Docker Linux ARM64 容器
```bash
# 在 Docker 容器中构建
docker compose -f docker/cpython-baseline/docker-compose.yml build
docker compose -f docker/cpython-baseline/docker-compose.yml run cpython-baseline \
  bash -c 'CINDERX_ENABLE_LTO=1 python setup.py build_ext --inplace'
```

### 问题 2: 网络问题 (502 Bad Gateway)

**症状**: apt-get 失败

**解决方案**: 使用本地镜像或等待网络恢复
```bash
# 方法 1: 预构建基础镜像
cd docker/cpython-baseline
docker compose build  # 首次构建会慢，但会缓存

# 方法 2: 使用重试逻辑
for i in {1..3}; do
  apt-get update && apt-get install -y <packages> && break
  sleep 10
done
```

### 问题 3: 构建时间长

**预期**: 15-30 分钟（单线程避免OOM）

**优化建议**:
```bash
# 使用预构建的依赖镜像
FROM cinderx-cpython-baseline:arm64

# 或使用多阶段构建缓存
```

---

## 🚀 推荐的验证流程

### 方案 A: 使用现有框架（推荐）

```bash
# 1. 使用 cpython-baseline 框架
cd docker/cpython-baseline
docker compose build  # 构建镜像（首次需要时间）
docker compose up -d

# 2. 在容器内构建 LTO wheel
docker compose exec cpython-baseline bash -c '
  set -e
  export CINDERX_ENABLE_LTO=1
  export CINDERX_BUILD_JOBS=1

  echo "Building LTO wheel..."
  python -m build --wheel

  echo "Verifying..."
  ls -lh dist/*.whl
'

# 3. 运行性能测试
docker compose exec cpython-baseline \
  BENCHMARK=generators SAMPLES=10 /scripts/test-lto-comparison.sh
```

### 方案 B: 直接在 CI/CD 中验证

```yaml
# .github/workflows/lto-performance.yml
name: LTO Performance
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-24.04-arm  # 真实 ARM64 环境
    steps:
      - uses: actions/checkout@v6
      - name: Build and test
        run: |
          export CINDERX_ENABLE_LTO=1
          python -m build --wheel
          pip install dist/*.whl
          python scripts/bench/validate_lto_performance.py
```

---

## 📝 当前尝试的构建

**任务 ID**: `b54gdmljp`
**状态**: 🔄 运行中
**预计完成**: ~20:35 (5分钟后检查)

**监控命令**:
```bash
# 实时监控
watch -n 30 'tail -50 /private/tmp/.../tasks/b54gdmljp.output'

# 或检查容器状态
docker ps --filter "ancestor=python:3.14-slim"
docker logs $(docker ps -q --filter "ancestor=python:3.14-slim" | head -1)
```

---

## 🎯 下一步

### 立即（优先级：高）

1. **等待当前构建完成** (~5-10分钟)
2. **如果失败**: 切换到方案 A（使用现有框架）
3. **如果成功**: 验证 wheel 并运行性能测试

### 中期（优先级：中）

1. **CI/CD 集成**: 添加 GitHub Actions workflow
2. **自动化测试**: 每次提交自动运行 LTO 验证
3. **性能基线**: 建立性能历史数据库

### 长期（优先级：低）

1. **优化构建时间**: 缓存、预构建镜像
2. **扩展测试**: 更多 benchmark、更多平台
3. **PGO 集成**: 测试 LTO+PGO 组合

---

## 💡 教训

1. **复用现有框架**: 不要手动运行 Docker，使用已有的 compose 配置
2. **网络可靠性**: 添加重试逻辑或使用预构建镜像
3. **预期管理**: ARM64 单线程构建确实需要 15-30 分钟

---

**结论**: Phase 03B-02 的工具链已完成，现在需要在真实 Linux ARM64 环境中验证。推荐使用现有的 Docker Compose 框架或直接在 CI/CD 中运行。

**更新时间**: 2026-03-24 20:30
