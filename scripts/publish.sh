#!/bin/bash
#
# JLP Hedge Executor - 一键测试和发布脚本
#
# 使用方法:
#   ./scripts/publish.sh           # 测试 + 发布到 Docker Hub
#   ./scripts/publish.sh --test    # 仅测试
#   ./scripts/publish.sh --push    # 仅发布
#

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# 配置
IMAGE_NAME="ring07c/jlphedge"
VERSION="1.0.0"

# 进入项目目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Banner
echo -e "${GREEN}"
cat << 'EOF'
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     ╦╦  ╔═╗  ╦ ╦╔═╗╔╦╗╔═╗╔═╗                                 ║
║     ║║  ╠═╝  ╠═╣║╣  ║║║ ╦║╣                                  ║
║    ╚╝╚═╝╩    ╩ ╩╚═╝═╩╝╚═╝╚═╝                                 ║
║                                                               ║
║              Docker Build & Publish Tool                      ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# 参数解析
TEST_ONLY=false
PUSH_ONLY=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --test) TEST_ONLY=true ;;
        --push) PUSH_ONLY=true ;;
        --version) VERSION="$2"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# ========================================
# Step 1: 环境检查
# ========================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Step 1: Environment Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! command -v docker &> /dev/null; then
    error "Docker is not installed"
fi
success "Docker: $(docker --version | cut -d' ' -f3)"

if ! docker info &> /dev/null; then
    error "Docker daemon is not running"
fi
success "Docker daemon is running"

# 检查是否已登录 Docker Hub
if ! docker info 2>/dev/null | grep -q "Username:"; then
    warn "Not logged in to Docker Hub"
    if [ "$PUSH_ONLY" = true ] || [ "$TEST_ONLY" = false ]; then
        info "Please login to Docker Hub:"
        docker login || error "Docker login failed"
    fi
fi
echo ""

# ========================================
# Step 2: 构建镜像
# ========================================
if [ "$PUSH_ONLY" = false ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    info "Step 2: Building Docker Image"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    BUILD_START=$(date +%s)
    
    docker build \
        -t ${IMAGE_NAME}:${VERSION} \
        -t ${IMAGE_NAME}:latest \
        --label "version=${VERSION}" \
        --label "build-date=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        .
    
    BUILD_END=$(date +%s)
    BUILD_TIME=$((BUILD_END - BUILD_START))
    
    success "Image built in ${BUILD_TIME}s"
    echo ""
fi

# ========================================
# Step 3: 测试镜像
# ========================================
if [ "$PUSH_ONLY" = false ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    info "Step 3: Testing Image"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # 镜像信息
    IMAGE_SIZE=$(docker images ${IMAGE_NAME}:${VERSION} --format "{{.Size}}")
    echo "  Image: ${IMAGE_NAME}:${VERSION}"
    echo "  Size:  ${IMAGE_SIZE}"
    echo ""
    
    # Python 环境测试
    info "Testing Python environment..."
    docker run --rm ${IMAGE_NAME}:${VERSION} python -c "
import sys
print(f'Python {sys.version}')

packages = ['httpx', 'pydantic', 'pynacl']
for pkg in packages:
    __import__(pkg)
    print(f'  ✓ {pkg}')
print('Dependencies OK!')
" || error "Python environment test failed"
    success "Python environment OK"
    echo ""
    
    # 模块导入测试
    info "Testing module imports..."
    docker run --rm ${IMAGE_NAME}:${VERSION} python -c "
from config.settings import load_config
from cloud.client import CloudClient
from cloud.license_manager import LicenseManager
from clients.asterdex_client import AsterdexClient
from strategies.delta_neutral import DeltaNeutralStrategy
print('All modules imported successfully!')
" || error "Module import test failed"
    success "Module imports OK"
    echo ""
    
    # 安全检查
    info "Security check..."
    USER_CHECK=$(docker run --rm ${IMAGE_NAME}:${VERSION} whoami)
    if [ "$USER_CHECK" = "hedge" ]; then
        success "Running as non-root user: $USER_CHECK"
    else
        warn "Running as: $USER_CHECK"
    fi
    echo ""
fi

# 如果只测试，到此结束
if [ "$TEST_ONLY" = true ]; then
    echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}                    Tests Passed! ✓                             ${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "To push to Docker Hub, run:"
    echo "  ./scripts/publish.sh --push"
    exit 0
fi

# ========================================
# Step 4: 推送到 Docker Hub
# ========================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Step 4: Pushing to Docker Hub"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
read -p "Push ${IMAGE_NAME}:${VERSION} and ${IMAGE_NAME}:latest to Docker Hub? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    info "Push cancelled"
    exit 0
fi

info "Pushing ${IMAGE_NAME}:${VERSION}..."
docker push ${IMAGE_NAME}:${VERSION}
success "Pushed ${IMAGE_NAME}:${VERSION}"

info "Pushing ${IMAGE_NAME}:latest..."
docker push ${IMAGE_NAME}:latest
success "Pushed ${IMAGE_NAME}:latest"

echo ""

# ========================================
# 完成
# ========================================
echo -e "${GREEN}"
cat << EOF
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║              🎉 Published Successfully! 🎉                    ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo "📦 Images:"
echo "   docker pull ${IMAGE_NAME}:${VERSION}"
echo "   docker pull ${IMAGE_NAME}:latest"
echo ""
echo "🔗 Docker Hub: https://hub.docker.com/r/${IMAGE_NAME}"
echo ""
echo "📝 Next steps:"
echo "   1. Verify image on Docker Hub"
echo "   2. Test pull on a fresh machine"
echo "   3. Update download page at https://jlp.finance/download"
echo ""
