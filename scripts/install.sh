#!/bin/bash
# JLP Hedge Executor 一键安装脚本
# 使用方法: 
#   基本安装: sudo bash -c "$(curl -fsSL https://jlp.finance/install.sh)"
#   预配置安装: sudo LICENSE_KEY="xxx" ASTERDEX_API_KEY="xxx" WALLET_ADDRESS="xxx" bash -c "$(curl -fsSL https://jlp.finance/install.sh)"

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 预设环境变量（可通过命令行传入）
PRE_LICENSE_KEY="${LICENSE_KEY:-}"
PRE_API_KEY="${ASTERDEX_API_KEY:-}"
PRE_API_SECRET="${ASTERDEX_API_SECRET:-}"
PRE_WALLET_ADDRESS="${WALLET_ADDRESS:-}"

# 标记是否需要重新登录
NEED_RELOGIN=false

# Logo
echo -e "${CYAN}"
echo "     ██╗██╗     ██████╗     ██╗  ██╗███████╗██████╗  ██████╗ ███████╗"
echo "     ██║██║     ██╔══██╗    ██║  ██║██╔════╝██╔══██╗██╔════╝ ██╔════╝"
echo "     ██║██║     ██████╔╝    ███████║█████╗  ██║  ██║██║  ███╗█████╗  "
echo "██   ██║██║     ██╔═══╝     ██╔══██║██╔══╝  ██║  ██║██║   ██║██╔══╝  "
echo "╚█████╔╝███████╗██║         ██║  ██║███████╗██████╔╝╚██████╔╝███████╗"
echo " ╚════╝ ╚══════╝╚═╝         ╚═╝  ╚═╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝"
echo -e "${NC}"
echo -e "${GREEN}JLP Hedge Executor - One-Click Installer${NC}"
echo "==========================================="
echo ""

# 获取实际用户（即使通过 sudo 运行）
if [ -n "$SUDO_USER" ]; then
    REAL_USER="$SUDO_USER"
    REAL_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
else
    REAL_USER="$USER"
    REAL_HOME="$HOME"
fi

# 安装目录（始终安装到实际用户的 home 目录）
INSTALL_DIR="$REAL_HOME/jlp-hedge"

# 检查操作系统
check_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="mac"
    else
        echo -e "${RED}Error: Unsupported operating system${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓${NC} Operating System: $OS"
}

# 检查并安装 Docker
install_docker() {
    if command -v docker &> /dev/null; then
        echo -e "${GREEN}✓${NC} Docker is installed"
    else
        echo -e "${YELLOW}Docker not found. Installing...${NC}"
        
        if [[ "$OS" == "linux" ]]; then
            curl -fsSL https://get.docker.com | sh
            echo -e "${GREEN}✓${NC} Docker installed successfully"
        elif [[ "$OS" == "mac" ]]; then
            echo -e "${RED}Please install Docker Desktop from: https://www.docker.com/products/docker-desktop${NC}"
            exit 1
        fi
    fi
    
    # 确保用户在 docker 组中（仅 Linux）
    if [[ "$OS" == "linux" ]]; then
        if ! groups "$REAL_USER" | grep -q docker; then
            echo -e "${YELLOW}Adding $REAL_USER to docker group...${NC}"
            usermod -aG docker "$REAL_USER"
            NEED_RELOGIN=true
            echo -e "${GREEN}✓${NC} User added to docker group"
        fi
    fi
}

# 检查 Docker Compose
check_docker_compose() {
    if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
        echo -e "${GREEN}✓${NC} Docker Compose is available"
    else
        echo -e "${RED}Error: Docker Compose not found${NC}"
        exit 1
    fi
}

# 创建安装目录
create_install_dir() {
    if [ -d "$INSTALL_DIR" ]; then
        echo -e "${YELLOW}Directory $INSTALL_DIR already exists${NC}"
        read -p "Overwrite? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Installation cancelled"
            exit 1
        fi
        rm -rf "$INSTALL_DIR"
    fi
    
    mkdir -p "$INSTALL_DIR/data"
    mkdir -p "$INSTALL_DIR/logs"
    
    # 如果通过 sudo 运行，修复目录权限
    if [ -n "$SUDO_USER" ]; then
        chown -R "$SUDO_USER:$SUDO_USER" "$INSTALL_DIR"
    fi
    
    echo -e "${GREEN}✓${NC} Created directory: $INSTALL_DIR"
}

# 下载配置文件
download_files() {
    echo -e "${BLUE}Downloading configuration files...${NC}"
    
    # 下载 docker-compose.yml
    cat > "$INSTALL_DIR/docker-compose.yml" << 'EOF'
services:
  jlp-hedge:
    image: ring07c/jlphedge:latest
    container_name: jlp-hedge-executor
    restart: always
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
EOF
    
    echo -e "${GREEN}✓${NC} Downloaded docker-compose.yml"
}

# 交互式配置（支持预填充）
configure_env() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo -e "${CYAN}       Configuration Setup${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════${NC}"
    echo ""
    
    # 检查是否有预填充配置
    if [ -n "$PRE_LICENSE_KEY" ] && [ -n "$PRE_API_KEY" ] && [ -n "$PRE_API_SECRET" ]; then
        echo -e "${GREEN}✓${NC} Pre-configured credentials detected!"
        LICENSE_KEY="$PRE_LICENSE_KEY"
        ASTERDEX_API_KEY="$PRE_API_KEY"
        ASTERDEX_API_SECRET="$PRE_API_SECRET"
        WALLET_ADDRESS="$PRE_WALLET_ADDRESS"
    else
        # License Key
        echo -e "${YELLOW}Step 1/2: License Key${NC}"
        echo "Get your license key from: https://jlp.finance/settings/license"
        echo ""
        if [ -n "$PRE_LICENSE_KEY" ]; then
            LICENSE_KEY="$PRE_LICENSE_KEY"
            echo -e "${GREEN}✓${NC} License Key: ${LICENSE_KEY:0:8}...${LICENSE_KEY: -4} (pre-configured)"
        else
            read -p "Enter your LICENSE_KEY: " LICENSE_KEY
        fi
        
        if [ -z "$LICENSE_KEY" ]; then
            echo -e "${RED}Error: License key is required${NC}"
            exit 1
        fi
        
        echo ""
        
        # AsterDex API
        echo -e "${YELLOW}Step 2/2: AsterDex API Credentials${NC}"
        echo "Get your API keys from: https://www.asterdex.com/api-management"
        echo ""
        
        if [ -n "$PRE_API_KEY" ]; then
            ASTERDEX_API_KEY="$PRE_API_KEY"
            echo -e "${GREEN}✓${NC} API Key: (pre-configured)"
        else
            read -p "Enter your ASTERDEX_API_KEY: " ASTERDEX_API_KEY
        fi
        
        if [ -n "$PRE_API_SECRET" ]; then
            ASTERDEX_API_SECRET="$PRE_API_SECRET"
            echo -e "${GREEN}✓${NC} API Secret: (pre-configured)"
        else
            read -p "Enter your ASTERDEX_API_SECRET: " ASTERDEX_API_SECRET
        fi
        
        if [ -z "$ASTERDEX_API_KEY" ] || [ -z "$ASTERDEX_API_SECRET" ]; then
            echo -e "${RED}Error: AsterDex API credentials are required${NC}"
            exit 1
        fi
        
        if [ -n "$PRE_WALLET_ADDRESS" ]; then
            WALLET_ADDRESS="$PRE_WALLET_ADDRESS"
        else
            read -p "Enter your Wallet Address: " WALLET_ADDRESS
        fi
        
        if [ -z "$WALLET_ADDRESS" ]; then
            echo -e "${RED}Error: Wallet address is required${NC}"
            exit 1
        fi
    fi
    
    # 创建 .env 文件
    cat > "$INSTALL_DIR/.env" << EOF
# JLP Hedge Executor Configuration
# Generated by install script on $(date)

# License (Required)
LICENSE_KEY=$LICENSE_KEY
CLOUD_API_URL=https://jlp.finance

# Logging
LOG_LEVEL=INFO
TZ=Asia/Shanghai
EOF
    
    # 创建 accounts.json 配置文件（放在 data 目录）
    cat > "$INSTALL_DIR/data/accounts.json" << EOF
{
  "accounts": [
    {
      "name": "Main Account",
      "enabled": true,
      "asterdex": {
        "chain": "solana",
        "user_address": "$WALLET_ADDRESS",
        "api_key": "$ASTERDEX_API_KEY",
        "api_secret": "$ASTERDEX_API_SECRET"
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
          "order_timeout": 5.0,
          "total_timeout": 600,
          "split_order_enabled": true,
          "split_order_threshold": 1500.0,
          "split_order_min_value": 300.0,
          "split_order_max_value": 800.0
        }
      }
    }
  ],
  "global": {
    "hedge_api_url": "https://api.jlp.finance",
    "rebalance_interval": 600,
    "rebalance_threshold": 0.02,
    "max_funding_rate": 0.001,
    "min_margin_ratio": 0.5,
    "max_daily_loss": 0.02
  },
  "cloud": {
    "enabled": true,
    "api_url": "https://jlp.finance",
    "license_key": "$LICENSE_KEY",
    "report_interval": 300,
    "sync_interval": 300
  }
}
EOF
    
    # 如果通过 sudo 运行，修复配置文件权限
    if [ -n "$SUDO_USER" ]; then
        chown -R "$SUDO_USER:$SUDO_USER" "$INSTALL_DIR"
    fi
    
    echo -e "${GREEN}✓${NC} Configuration saved to $INSTALL_DIR/.env"
    echo -e "${GREEN}✓${NC} Account config saved to $INSTALL_DIR/data/accounts.json"
}

# 验证 License
verify_license() {
    echo ""
    echo -e "${BLUE}Verifying license...${NC}"
    
    RESPONSE=$(curl -s -X POST "https://jlp.finance/api/hedge/verify" \
        -H "Content-Type: application/json" \
        -d "{\"license_key\": \"$LICENSE_KEY\", \"device_id\": \"install-script\"}" 2>/dev/null || echo '{"valid":false}')
    
    if echo "$RESPONSE" | grep -q '"valid":true'; then
        echo -e "${GREEN}✓${NC} License verified successfully!"
    else
        echo -e "${YELLOW}⚠${NC} Could not verify license (this may be normal for first-time setup)"
        echo "  The executor will verify the license when it starts"
    fi
}

# 启动服务
start_service() {
    echo ""
    echo -e "${BLUE}Starting JLP Hedge Executor...${NC}"
    
    cd "$INSTALL_DIR"
    
    # 拉取最新镜像
    docker pull ring07c/jlphedge:latest
    
    # 启动服务
    if command -v docker-compose &> /dev/null; then
        docker-compose up -d
    else
        docker compose up -d
    fi
    
    echo -e "${GREEN}✓${NC} JLP Hedge Executor started!"
}

# 显示完成信息
show_completion() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════${NC}"
    echo -e "${GREEN}     Installation Complete!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════${NC}"
    echo ""
    echo -e "Installation directory: ${CYAN}$INSTALL_DIR${NC}"
    echo ""
    echo -e "${YELLOW}Useful Commands:${NC}"
    echo "  View logs:      cd $INSTALL_DIR && docker compose logs -f"
    echo "  Stop:           cd $INSTALL_DIR && docker compose down"
    echo "  Restart:        cd $INSTALL_DIR && docker compose restart"
    echo "  Update:         cd $INSTALL_DIR && docker compose pull && docker compose up -d"
    echo ""
    echo -e "${YELLOW}Configuration:${NC}"
    echo "  Edit config:    nano $INSTALL_DIR/data/accounts.json"
    echo "  Edit .env:      nano $INSTALL_DIR/.env"
    echo "  Multi-account:  Add more entries to 'accounts' array in accounts.json"
    echo ""
    echo -e "${YELLOW}Monitor & Notifications:${NC}"
    echo "  Dashboard:      https://jlp.finance/dashboard"
    echo "  Notifications:  https://jlp.finance/hedge/config"
    echo ""
    
    # 如果需要重新登录才能使用 docker
    if [ "$NEED_RELOGIN" = true ]; then
        echo -e "${YELLOW}════════════════════════════════════════════${NC}"
        echo -e "${YELLOW}  IMPORTANT: Please log out and back in${NC}"
        echo -e "${YELLOW}  to use docker without sudo${NC}"
        echo -e "${YELLOW}════════════════════════════════════════════${NC}"
        echo ""
        echo "  After re-login, run: cd ~/jlp-hedge && docker compose logs -f"
        echo ""
    fi
    
    echo -e "${CYAN}Need help? Contact: support@jlp.finance${NC}"
    echo ""
}

# 主流程
main() {
    echo "Starting installation..."
    echo ""
    
    check_os
    install_docker
    check_docker_compose
    create_install_dir
    download_files
    configure_env
    verify_license
    start_service
    show_completion
}

# 运行
main
