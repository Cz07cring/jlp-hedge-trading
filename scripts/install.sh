#!/bin/bash
#
# JLP Hedge Executor - Quick Install Script
#
# Usage:
#   curl -fsSL https://jlp.finance/install.sh | bash
#
# Or download and run:
#   chmod +x install.sh && ./install.sh
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Banner
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                                                               ║"
echo "║              JLP Hedge Executor Installer                     ║"
echo "║              Delta Neutral Hedging for JLP                    ║"
echo "║                                                               ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 检查 Docker
check_docker() {
    info "Checking Docker installation..."
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed. Please install Docker first: https://docs.docker.com/get-docker/"
    fi
    
    if ! docker info &> /dev/null; then
        error "Docker daemon is not running. Please start Docker."
    fi
    
    success "Docker is ready"
}

# 检查 Docker Compose
check_docker_compose() {
    info "Checking Docker Compose..."
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        error "Docker Compose is not installed. Please install Docker Compose."
    fi
    
    success "Docker Compose is ready ($COMPOSE_CMD)"
}

# 创建安装目录
create_install_dir() {
    INSTALL_DIR="${HOME}/jlp-hedge"
    
    info "Creating installation directory: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"/{config,data,logs}
    cd "$INSTALL_DIR"
    
    success "Directory created"
}

# 下载配置文件
download_files() {
    info "Downloading configuration files..."
    
    # docker-compose.yml
    cat > docker-compose.yml << 'COMPOSE_EOF'
version: '3.8'

services:
  jlp-hedge:
    image: ring07c/jlphedge:latest
    container_name: jlp-hedge
    restart: unless-stopped
    volumes:
      - ./config:/app/config:ro
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - LICENSE_KEY=${LICENSE_KEY:-}
      - CLOUD_ENABLED=${CLOUD_ENABLED:-true}
      - CLOUD_API_URL=${CLOUD_API_URL:-https://api.jlp.finance}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - TZ=${TZ:-Asia/Shanghai}
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    healthcheck:
      test: ["CMD", "pgrep", "-f", "python main.py"]
      interval: 60s
      timeout: 10s
      retries: 3
COMPOSE_EOF
    
    # 配置文件模板
    cat > config/accounts.json << 'CONFIG_EOF'
{
  "accounts": [
    {
      "name": "主账户",
      "enabled": true,
      "asterdex": {
        "chain": "solana",
        "user_address": "YOUR_WALLET_ADDRESS",
        "api_key": "YOUR_API_KEY",
        "api_secret": "YOUR_API_SECRET"
      },
      "trading": {
        "leverage": 1,
        "slippage": 0.001,
        "min_order_size": {
          "SOL": 0.01,
          "ETH": 0.001,
          "BTC": 0.0001
        },
        "maker_order": {
          "enabled": true,
          "order_timeout": 1.0,
          "total_timeout": 600,
          "check_interval_ms": 100,
          "price_tolerance": 0.0001
        }
      }
    }
  ],
  "global": {
    "hedge_api_url": "https://jlp.finance",
    "rebalance_interval": 600,
    "rebalance_threshold": 0.02
  },
  "cloud": {
    "enabled": true,
    "api_url": "https://jlp.finance",
    "license_key": "YOUR_LICENSE_KEY",
    "report_interval": 300
  }
}
CONFIG_EOF

    # .env 文件
    cat > .env << 'ENV_EOF'
# JLP Hedge Configuration
# 请填入您的 License Key

LICENSE_KEY=JLP-XXXX-XXXX-XXXX-XXXX
LOG_LEVEL=INFO
TZ=Asia/Shanghai
ENV_EOF
    
    success "Configuration files created"
}

# 交互式配置
interactive_config() {
    echo ""
    info "Please configure your settings:"
    echo ""
    
    # License Key
    read -p "Enter your License Key (JLP-XXXX-XXXX-XXXX-XXXX): " LICENSE_KEY
    if [ -n "$LICENSE_KEY" ]; then
        sed -i.bak "s/LICENSE_KEY=.*/LICENSE_KEY=$LICENSE_KEY/" .env
        sed -i.bak "s/YOUR_LICENSE_KEY/$LICENSE_KEY/" config/accounts.json
        rm -f .env.bak config/accounts.json.bak 2>/dev/null
    fi
    
    # Wallet Address
    read -p "Enter your Wallet Address: " WALLET_ADDRESS
    if [ -n "$WALLET_ADDRESS" ]; then
        sed -i.bak "s/YOUR_WALLET_ADDRESS/$WALLET_ADDRESS/" config/accounts.json
        rm -f config/accounts.json.bak 2>/dev/null
    fi
    
    # API Key
    read -p "Enter your AsterDex API Key: " API_KEY
    if [ -n "$API_KEY" ]; then
        sed -i.bak "s/YOUR_API_KEY/$API_KEY/" config/accounts.json
        rm -f config/accounts.json.bak 2>/dev/null
    fi
    
    # API Secret
    read -s -p "Enter your AsterDex API Secret: " API_SECRET
    echo ""
    if [ -n "$API_SECRET" ]; then
        sed -i.bak "s/YOUR_API_SECRET/$API_SECRET/" config/accounts.json
        rm -f config/accounts.json.bak 2>/dev/null
    fi
    
    success "Configuration saved"
}

# 拉取 Docker 镜像
pull_image() {
    info "Pulling Docker image..."
    docker pull ring07c/jlphedge:latest || warn "Image not found in registry yet. Please check https://jlp.finance for updates."
}

# 启动服务
start_service() {
    echo ""
    read -p "Do you want to start the service now? (y/n): " START_NOW
    
    if [ "$START_NOW" = "y" ] || [ "$START_NOW" = "Y" ]; then
        info "Starting JLP Hedge Executor..."
        $COMPOSE_CMD up -d
        
        echo ""
        success "JLP Hedge Executor is now running!"
        echo ""
        info "Useful commands:"
        echo "  View logs:     $COMPOSE_CMD logs -f"
        echo "  Stop service:  $COMPOSE_CMD down"
        echo "  Restart:       $COMPOSE_CMD restart"
        echo ""
        info "Installation directory: $INSTALL_DIR"
    else
        echo ""
        success "Installation complete!"
        echo ""
        info "To start the service later, run:"
        echo "  cd $INSTALL_DIR && $COMPOSE_CMD up -d"
    fi
}

# 打印完成信息
print_completion() {
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}                  Installation Complete!                        ${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "📁 Installation directory: $INSTALL_DIR"
    echo ""
    echo "📝 Configuration files:"
    echo "   - $INSTALL_DIR/config/accounts.json"
    echo "   - $INSTALL_DIR/.env"
    echo ""
    echo "🚀 Quick commands:"
    echo "   cd $INSTALL_DIR"
    echo "   $COMPOSE_CMD up -d      # Start"
    echo "   $COMPOSE_CMD logs -f    # View logs"
    echo "   $COMPOSE_CMD down       # Stop"
    echo ""
    echo "📖 Documentation: https://jlp.finance/docs"
    echo "💬 Support: https://jlp.finance/support"
    echo ""
}

# 主流程
main() {
    check_docker
    check_docker_compose
    create_install_dir
    download_files
    interactive_config
    pull_image
    start_service
    print_completion
}

# 运行
main "$@"
