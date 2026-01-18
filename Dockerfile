# ===========================================
# JLP Hedge Executor
# Delta Neutral Hedging for JLP Token
# ===========================================
#
# Build:
#   docker build -t ring07c/jlphedge:latest .
#
# Run:
#   docker run -d --name jlp-hedge \
#     -e LICENSE_KEY=JLP-XXXX-XXXX-XXXX-XXXX \
#     -v $(pwd)/config:/app/config:ro \
#     -v $(pwd)/data:/app/data \
#     -v $(pwd)/logs:/app/logs \
#     ring07c/jlphedge:latest

FROM python:3.11-slim AS builder

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ===========================================
# Production Stage
# ===========================================
FROM python:3.11-slim

# 标签
LABEL maintainer="JLP Hedge <support@jlp.finance>"
LABEL version="1.0"
LABEL description="JLP Delta Neutral Hedge Executor"

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/hedge/.local/bin:$PATH" \
    # 默认配置
    LOG_LEVEL=INFO \
    TZ=Asia/Shanghai

# 创建非 root 用户
RUN useradd -m -u 1000 hedge

# 设置工作目录
WORKDIR /app

# 从 builder 复制已安装的依赖
COPY --from=builder /root/.local /home/hedge/.local

# 复制应用代码（排除 .dockerignore 中的文件）
COPY --chown=hedge:hedge . .

# 创建运行时目录
RUN mkdir -p /app/config /app/data /app/logs && \
    chown -R hedge:hedge /app

# 切换到非 root 用户
USER hedge

# 健康检查 - 检查主进程是否在运行
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD pgrep -f "python main.py" > /dev/null || exit 1

# 暴露可能的监控端口（可选）
# EXPOSE 8080

# 默认命令
CMD ["python", "main.py"]
