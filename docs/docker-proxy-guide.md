# Docker 代理配置指南

**日期**: 2026-03-24
**问题**: macOS Docker 容器无法访问宿主机 Clash 代理
**解决方案**: 使用 `host.docker.internal` + 重试逻辑

---

## 问题描述

### 原始错误

```
E: Failed to fetch http://deb.debian.org/debian/...
   Unable to connect to deb.debian.org:http
RuntimeError: Cannot find suitable C/C++ compiler
```

### 根本原因

1. **容器网络隔离**: 容器内部尝试连接 `127.0.0.1:7890` (容器自己的 localhost)
2. **应该连接**: `host.docker.internal:7890` (宿主机地址)
3. **网络不稳定**: Debian CDN 偶尔返回 502/500

---

## 解决方案

### 1. 使用 host.docker.internal

**关键参数**:
```bash
--add-host=host.docker.internal:host-gateway
-e http_proxy="http://host.docker.internal:7890"
-e https_proxy="http://host.docker.internal:7890"
-e no_proxy="localhost,127.0.0.1,.internal"
```

**说明**:
- `--add-host=host.docker.internal:host-gateway` 让容器能解析宿主机地址
- `http_proxy`/`https_proxy` 告诉 apt-get 使用代理
- `no_proxy` 避免本地地址走代理

### 2. 重试逻辑

```bash
for i in 1 2 3; do
  if apt-get install -y <packages>; then
    break
  else
    sleep 5
  fi
done
```

### 3. 使用预构建镜像

**推荐**: 使用已有 Python 3.14 的镜像
```bash
cinderx-cpython-baseline:arm64  # 已有 Python 3.14 + LLVM 19
```

**优势**:
- ✅ 无需 apt-get 安装 Python
- ✅ 无需编译 Python 3.14
- ✅ 只需安装 cmake (带重试)

---

## 完整示例

### Dockerfile 中使用代理

```dockerfile
FROM cinderx-cpython-baseline:arm64

# 不需要安装 Python 3.14！

# 只需安装 cmake（带重试）
RUN for i in 1 2 3; do \
      apt-get update && apt-get install -y cmake && break; \
      sleep 5; \
    done
```

### Docker run 使用代理

```bash
docker run --rm --platform linux/arm64 \
  --add-host=host.docker.internal:host-gateway \
  -e http_proxy="http://host.docker.internal:7890" \
  -e https_proxy="http://host.docker.internal:7890" \
  -e no_proxy="localhost,127.0.0.1,.internal" \
  cinderx-cpython-baseline:arm64 \
  bash -c 'apt-get update && apt-get install -y cmake'
```

### docker-compose.yml 使用代理

```yaml
services:
  cpython-baseline:
    image: cinderx-cpython-baseline:arm64
    environment:
      - http_proxy=http://host.docker.internal:7890
      - https_proxy=http://host.docker.internal:7890
      - no_proxy=localhost,127.0.0.1,.internal
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

---

## 验证代理工作

```bash
# 测试容器能否访问外网
docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -e http_proxy="http://host.docker.internal:7890" \
  openeuler/openeuler:24.03-lts-sp1 \
  curl -I https://www.google.com

# 应该看到: HTTP/1.1 200 Connection established
```

---

## 常见错误

### 错误 1: 使用 127.0.0.1

```bash
# ❌ 错误
-e http_proxy="http://127.0.0.1:7890"  # 容器自己的 localhost，没有代理
```

### 错误 2: 不设置 extra_hosts

```bash
# ❌ 可能失败
docker run -e http_proxy="http://host.docker.internal:7890" ...
# 报错: Could not resolve host: host.docker.internal
```

### 错误 3: 不设置 no_proxy

```bash
# ⚠️ 可能导致本地连接走代理
docker run -e http_proxy="http://host.docker.internal:7890" ...
# apt-get 连接 localhost 会很慢
```

---

## 最佳实践

### 1. 检测宿主机代理端口

```bash
# 检查 Clash 代理端口（默认 7890）
netstat -an | grep 7890 || echo "Clash not running on 7890"
```

### 2. 环境变量模板

```bash
# 创建代理环境变量文件
cat > .docker-proxy-env <<'EOF'
http_proxy=http://host.docker.internal:7890
https_proxy=http://host.docker.internal:7890
no_proxy=localhost,127.0.0.1,.internal
EOF

# 使用
docker run --env-file .docker-proxy-env ...
```

### 3. 构建脚本模板

```bash
#!/bin/bash
# 带代理的构建脚本

PROXY_PORT="${PROXY_PORT:-7890}"

docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -e http_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e https_proxy="http://host.docker.internal:$PROXY_PORT" \
  -e no_proxy="localhost,127.0.0.1,.internal" \
  -e CINDERX_ENABLE_LTO=1 \
  -v "$PWD:/workspace" \
  cinderx-cpython-baseline:arm64 \
  bash -c "python3 -m build --wheel"
```

---

## 推荐方案

### 方案 A: 使用预构建镜像（推荐）

```bash
# 使用 cinderx-cpython-baseline:arm64（已有 Python 3.14）
bash scripts/build-lto-python314.sh
```

**优势**:
- ✅ 无需编译 Python 3.14
- ✅ 只需安装 cmake（带重试）
- ✅ 构建速度快

### 方案 B: 从源码编译 Python 3.14（备选）

```bash
# 如果镜像不可用，从源码编译
# 参考: docs/guides/build-python-from-source.md
```

---

## 故障排查

### 问题: 代理测试失败

```bash
# 检查 Clash 是否运行
ps aux | grep clash

# 检查代理端口
lsof -i :7890

# 检查 TUN 模式
# Clash → 设置 → TUN 模式 → 开启
```

### 问题: apt-get 仍然失败

```bash
# 增加重试次数
for i in 1 2 3 4 5; do
  apt-get update && apt-get install -y cmake && break
  echo "Retry $i/5..."
  sleep 10
done
```

### 问题: cmake 安装成功但找不到

```bash
# 检查 PATH
which cmake || echo "cmake not in PATH"

# 重新安装
apt-get install --reinstall cmake
```

---

## 总结

**关键点**:
1. ✅ 使用 `host.docker.internal` 访问宿主机
2. ✅ 设置 `http_proxy`/`https_proxy`/`no_proxy`
3. ✅ 添加 `--add-host=host.docker.internal:host-gateway`
4. ✅ 使用重试逻辑
5. ✅ 使用预构建镜像避免编译 Python

**推荐脚本**: `scripts/build-lto-python314.sh`

**测试命令**:
```bash
PROXY_PORT=7890 bash scripts/build-lto-python314.sh
```
