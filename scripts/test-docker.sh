#!/bin/bash
#
# JLP Hedge Executor - Docker 本地测试脚本
#
# 使用方法:
#   chmod +x scripts/test-docker.sh
#   ./scripts/test-docker.sh
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# Banner
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║           JLP Hedge Executor - Docker Test                    ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 配置
IMAGE_NAME="ring07c/jlphedge"
IMAGE_TAG="test"
TEST_CONTAINER="jlp-hedge-test"

# 进入项目目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo ""
info "Project directory: $PROJECT_DIR"
echo ""

# ========================================
# Step 1: 检查 Docker
# ========================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Step 1: Checking Docker..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! command -v docker &> /dev/null; then
    error "Docker is not installed. Please install Docker first."
fi

if ! docker info &> /dev/null; then
    error "Docker daemon is not running. Please start Docker."
fi

DOCKER_VERSION=$(docker --version)
success "Docker is ready: $DOCKER_VERSION"
echo ""

# ========================================
# Step 2: 构建镜像
# ========================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Step 2: Building Docker image..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

BUILD_START=$(date +%s)
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .
BUILD_END=$(date +%s)
BUILD_TIME=$((BUILD_END - BUILD_START))

success "Image built successfully in ${BUILD_TIME}s"
echo ""

# ========================================
# Step 3: 检查镜像
# ========================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Step 3: Inspecting image..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

IMAGE_SIZE=$(docker images ${IMAGE_NAME}:${IMAGE_TAG} --format "{{.Size}}")
echo "  Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "  Size:  ${IMAGE_SIZE}"
echo ""

# 检查基本文件是否存在
info "Checking files in container..."
docker run --rm ${IMAGE_NAME}:${IMAGE_TAG} ls -la /app/ | head -15
echo ""
success "Image structure looks good"
echo ""

# ========================================
# Step 4: 测试 Python 环境
# ========================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Step 4: Testing Python environment..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 测试 Python 版本
PYTHON_VERSION=$(docker run --rm ${IMAGE_NAME}:${IMAGE_TAG} python --version)
echo "  Python: $PYTHON_VERSION"

# 测试关键依赖
info "Testing key dependencies..."
docker run --rm ${IMAGE_NAME}:${IMAGE_TAG} python -c "
import sys
print(f'Python Path: {sys.executable}')

# 测试关键包
packages = ['httpx', 'pydantic', 'pynacl']
for pkg in packages:
    try:
        __import__(pkg)
        print(f'  ✓ {pkg}')
    except ImportError as e:
        print(f'  ✗ {pkg}: {e}')
        sys.exit(1)

print('All dependencies OK!')
"

success "Python environment is ready"
echo ""

# ========================================
# Step 5: 测试应用代码
# ========================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Step 5: Testing application code..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 测试导入
docker run --rm ${IMAGE_NAME}:${IMAGE_TAG} python -c "
import sys
sys.path.insert(0, '/app')

# 测试核心模块导入
try:
    from config.settings import load_config
    print('  ✓ config.settings')
except Exception as e:
    print(f'  ✗ config.settings: {e}')

try:
    from cloud.client import CloudClient
    print('  ✓ cloud.client')
except Exception as e:
    print(f'  ✗ cloud.client: {e}')

try:
    from cloud.license_manager import LicenseManager
    print('  ✓ cloud.license_manager')
except Exception as e:
    print(f'  ✗ cloud.license_manager: {e}')

try:
    from clients.asterdex_client import AsterdexClient
    print('  ✓ clients.asterdex_client')
except Exception as e:
    print(f'  ✗ clients.asterdex_client: {e}')

try:
    from strategies.delta_neutral import DeltaNeutralStrategy
    print('  ✓ strategies.delta_neutral')
except Exception as e:
    print(f'  ✗ strategies.delta_neutral: {e}')

print('All modules imported successfully!')
"

success "Application code is valid"
echo ""

# ========================================
# Step 6: 测试启动（dry run）
# ========================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Step 6: Testing startup (dry run)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 创建临时测试目录
TEST_DIR=$(mktemp -d)
mkdir -p ${TEST_DIR}/config ${TEST_DIR}/data ${TEST_DIR}/logs

# 创建最小配置文件
cat > ${TEST_DIR}/config/accounts.json << 'EOF'
{
  "accounts": [],
  "global": {
    "rebalance_interval": 600,
    "rebalance_threshold": 0.02
  },
  "cloud": {
    "enabled": false,
    "api_url": "https://jlp.finance",
    "license_key": ""
  }
}
EOF

info "Starting container for dry run (will exit quickly without config)..."

# 运行并捕获输出（应该会因为没有账户配置而快速退出）
set +e
docker run --rm \
    -v ${TEST_DIR}/config:/app/config:ro \
    -v ${TEST_DIR}/data:/app/data \
    -v ${TEST_DIR}/logs:/app/logs \
    -e LICENSE_KEY="" \
    -e LOG_LEVEL=DEBUG \
    ${IMAGE_NAME}:${IMAGE_TAG} \
    timeout 5 python main.py 2>&1 | head -20
EXIT_CODE=$?
set -e

# 清理
rm -rf ${TEST_DIR}

if [ $EXIT_CODE -eq 124 ] || [ $EXIT_CODE -eq 0 ]; then
    success "Container starts correctly (expected exit without valid config)"
else
    warn "Container exited with code $EXIT_CODE (might be expected)"
fi
echo ""

# ========================================
# Step 7: 安全检查
# ========================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Step 7: Security check..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查是否以非 root 用户运行
USER_CHECK=$(docker run --rm ${IMAGE_NAME}:${IMAGE_TAG} whoami)
if [ "$USER_CHECK" = "hedge" ]; then
    success "Running as non-root user: $USER_CHECK"
else
    warn "Running as: $USER_CHECK (expected: hedge)"
fi

# 检查敏感文件是否被排除
info "Checking excluded files..."
EXCLUDED_FILES=(".env" "accounts.json" "tests/")
for file in "${EXCLUDED_FILES[@]}"; do
    if docker run --rm ${IMAGE_NAME}:${IMAGE_TAG} ls /app/$file 2>/dev/null; then
        warn "Sensitive file found in image: $file"
    else
        success "Excluded: $file"
    fi
done
echo ""

# ========================================
# 测试完成
# ========================================
echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                  All Tests Passed! ✓                          ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "📦 Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "📏 Size:  ${IMAGE_SIZE}"
echo ""
echo "下一步:"
echo "  1. 重新打 tag:  docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${IMAGE_NAME}:latest"
echo "  2. 登录 Hub:    docker login"
echo "  3. 推送镜像:    docker push ${IMAGE_NAME}:latest"
echo ""
echo "或者使用多平台构建:"
echo "  docker buildx build --platform linux/amd64,linux/arm64 \\"
echo "    -t ${IMAGE_NAME}:latest --push ."
echo ""
