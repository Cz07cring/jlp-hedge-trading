# Docker 发布指南

本文档介绍如何构建和发布 JLP Hedge Executor 的 Docker 镜像。

## 前提条件

1. **Docker Hub 账号**
   - 注册 [Docker Hub](https://hub.docker.com/) 账号
   - 使用账号 `ring07c`
   - 仓库 `jlphedge` 已创建

2. **Docker Hub Access Token**
   - 登录 Docker Hub → Account Settings → Security
   - 点击 "New Access Token"
   - 权限选择 "Read, Write, Delete"
   - 保存生成的 Token

## 方式一：GitHub Actions 自动发布（推荐）

### 配置 GitHub Secrets

在 GitHub 仓库中设置以下 Secrets：

1. 进入仓库 → Settings → Secrets and variables → Actions
2. 添加以下 secrets：

| Secret Name | 说明 |
|-------------|------|
| `DOCKERHUB_USERNAME` | Docker Hub 用户名 |
| `DOCKERHUB_TOKEN` | Docker Hub Access Token |

### 发布新版本

```bash
# 创建并推送 tag
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions 会自动：
- 构建多平台镜像 (amd64, arm64)
- 推送到 Docker Hub
- 创建 GitHub Release

### 手动触发构建

1. 进入 GitHub → Actions → Docker Build & Publish
2. 点击 "Run workflow"
3. 输入 tag（如 `latest`）
4. 点击 "Run workflow"

## 方式二：本地手动发布

### 1. 登录 Docker Hub

```bash
docker login
# 输入用户名和密码/Token
```

### 2. 构建镜像

**单平台构建（本机架构）：**

```bash
cd jlp-hedge-trading

# 构建
docker build -t ring07c/jlphedge:latest .

# 推送
docker push ring07c/jlphedge:latest
```

**多平台构建：**

```bash
# 设置 buildx
docker buildx create --name multiarch --use

# 构建并推送（同时支持 amd64 和 arm64）
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ring07c/jlphedge:latest \
  -t ring07c/jlphedge:v1.0.0 \
  --push .
```

**使用构建脚本：**

```bash
chmod +x scripts/build-docker.sh
./scripts/build-docker.sh v1.0.0
```

## 版本管理

### 标签策略

| Tag | 说明 |
|-----|------|
| `latest` | 最新稳定版 |
| `v1.0.0` | 特定版本 |
| `v1.0` | 主要.次要版本 |
| `v1` | 主版本 |
| `dev` | 开发版（可选） |

### 发布 Checklist

- [ ] 更新 `README.md` 中的版本号
- [ ] 测试 Docker 镜像本地运行正常
- [ ] 创建 git tag
- [ ] 推送 tag 触发 CI/CD
- [ ] 验证 Docker Hub 上的镜像
- [ ] 更新下载页面配置生成器

## 验证镜像

```bash
# 拉取镜像
docker pull ring07c/jlphedge:latest

# 检查镜像信息
docker inspect ring07c/jlphedge:latest

# 测试运行（会因缺少配置而退出，但能验证镜像是否正常）
docker run --rm ring07c/jlphedge:latest python -c "print('Image OK')"
```

## 镜像安全

### 安全扫描

```bash
# 使用 Docker Scout 扫描漏洞
docker scout cves ring07c/jlphedge:latest

# 或使用 Trivy
trivy image ring07c/jlphedge:latest
```

### 最小化镜像

当前 Dockerfile 已采用：
- 多阶段构建（减小镜像体积）
- 非 root 用户运行（提高安全性）
- 只包含运行时必要文件

## 常见问题

### Q: 构建失败 "no matching manifest for linux/arm64"

A: 基础镜像不支持 arm64，检查 `FROM` 指令使用的镜像是否支持多平台。

### Q: 推送失败 "denied: requested access to the resource is denied"

A: 检查 Docker Hub 登录状态和仓库权限。

### Q: 构建很慢

A: 启用 Docker 构建缓存：
```bash
docker buildx build --cache-from type=registry,ref=ring07c/jlphedge:cache ...
```

## 相关链接

- [Docker Hub - ring07c/jlphedge](https://hub.docker.com/r/ring07c/jlphedge)
- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [Docker Buildx 文档](https://docs.docker.com/buildx/working-with-buildx/)
