#!/bin/bash
#
# JLP Hedge Executor - Docker Build Script
#
# Usage:
#   ./scripts/build-docker.sh [tag]
#
# Examples:
#   ./scripts/build-docker.sh              # Build with tag 'latest'
#   ./scripts/build-docker.sh v1.0.0       # Build with tag 'v1.0.0'
#   ./scripts/build-docker.sh latest dev   # Build with both tags
#

set -e

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

# 默认配置
IMAGE_NAME="ring07c/jlphedge"
TAG="${1:-latest}"
PLATFORMS="linux/amd64,linux/arm64"

# Banner
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║           JLP Hedge Executor - Docker Build                   ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 检查 Docker
info "Checking Docker..."
if ! docker info &> /dev/null; then
    echo "Error: Docker daemon is not running"
    exit 1
fi

# 检查 Buildx
info "Setting up Docker Buildx..."
docker buildx create --name jlp-builder --use 2>/dev/null || docker buildx use jlp-builder

# 构建镜像
info "Building Docker image: ${IMAGE_NAME}:${TAG}"
info "Platforms: ${PLATFORMS}"
echo ""

# 构建参数
BUILD_ARGS="--platform ${PLATFORMS} -t ${IMAGE_NAME}:${TAG}"

# 如果有多个 tag
if [ -n "$2" ]; then
    BUILD_ARGS="${BUILD_ARGS} -t ${IMAGE_NAME}:$2"
    info "Additional tag: ${IMAGE_NAME}:$2"
fi

# 构建并推送
docker buildx build ${BUILD_ARGS} --push .

echo ""
success "Docker image built and pushed successfully!"
echo ""
info "Image: ${IMAGE_NAME}:${TAG}"
info "Pull command: docker pull ${IMAGE_NAME}:${TAG}"
echo ""
