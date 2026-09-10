#!/bin/bash
# ============================================================
# Multi-Agent Document Enhancer - 裸机部署脚本
# 用法:
#   ./deploy.sh             # 全流程部署
#   ./deploy.sh --rag       # 额外安装 RAG embedding 依赖
#   ./deploy.sh --no-frontend  # 跳过前端构建
#   ./deploy.sh --restart   # 仅重启服务
#   ./deploy.sh --logs      # 查看日志
#   ./deploy.sh --stop      # 停止服务
# ============================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/.venv"
SERVICE_NAME="mul-agent"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PIP_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ---------- 参数解析 ----------
INSTALL_RAG=false
SKIP_FRONTEND=false
ACTION="deploy"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --rag)          INSTALL_RAG=true; shift ;;
        --no-frontend)  SKIP_FRONTEND=true; shift ;;
        --restart)      ACTION="restart"; shift ;;
        --logs)         ACTION="logs"; shift ;;
        --stop)         ACTION="stop"; shift ;;
        --help|-h)
            echo "用法: ./deploy.sh [--rag] [--no-frontend] [--restart] [--logs] [--stop]"
            exit 0 ;;
        *) error "未知参数: $1" ;;
    esac
done

# ---------- 重启/日志/停止快捷操作 ----------
case "$ACTION" in
    restart)
        info "重启 $SERVICE_NAME..."
        sudo systemctl restart "$SERVICE_NAME"
        sudo systemctl status "$SERVICE_NAME" --no-pager || true
        exit 0 ;;
    logs)
        sudo journalctl -u "$SERVICE_NAME" -f --no-pager
        exit 0 ;;
    stop)
        info "停止 $SERVICE_NAME..."
        sudo systemctl stop "$SERVICE_NAME" || true
        exit 0 ;;
esac

# ---------- 环境检测 ----------
info "检测运行环境..."

# Python >= 3.11
if command -v python3.11 &>/dev/null; then
    PYTHON=python3.11
elif command -v python3 &>/dev/null; then
    PYTHON=python3
    PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    [[ "$PY_VER" < "3.11" ]] && error "需要 Python >= 3.11（当前 $PY_VER），请安装: sudo apt install python3.11 python3.11-venv"
else
    error "未找到 python3，请安装: sudo apt install python3.11 python3.11-venv"
fi
info "Python: $($PYTHON --version)"

# Node.js >= 18
if ! $SKIP_FRONTEND; then
    if ! command -v node &>/dev/null; then
        error "未找到 Node.js，请安装 >= 18: https://github.com/nodesource/distributions"
    fi
    NODE_VER=$(node -v | sed 's/v//' | cut -d. -f1)
    [[ "$NODE_VER" -lt 18 ]] && error "需要 Node.js >= 18（当前 $(node -v)）"
    info "Node.js: $(node -v)"
    command -v npm &>/dev/null || error "未找到 npm，请随 Node.js 一起安装"
fi

# ---------- 创建虚拟环境 ----------
if [ ! -d "$VENV_DIR" ]; then
    info "创建 Python 虚拟环境..."
    $PYTHON -m venv "$VENV_DIR"
fi

info "激活虚拟环境并安装依赖..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r "$APP_DIR/requirements-deploy.txt" -i "$PIP_INDEX"

# 可选 RAG embedding 依赖
if $INSTALL_RAG; then
    info "安装 RAG embedding 依赖（torch CPU 版）..."
    pip install torch transformers sentence-transformers huggingface-hub safetensors tokenizers \
        --extra-index-url https://download.pytorch.org/whl/cpu -i "$PIP_INDEX"
fi

# ---------- 构建前端 ----------
if ! $SKIP_FRONTEND; then
    info "安装前端依赖并构建..."
    cd "$APP_DIR"
    npm install --no-package-lock
    npm run build:v3
    info "前端构建完成 → web/static/v3/"
else
    warn "跳过前端构建（--no-frontend）"
fi

# ---------- 初始化配置（幂等） ----------
info "初始化配置文件..."
cd "$APP_DIR"

# 从 example 复制（不覆盖已有）
[ -f models.json ]          || cp models.example.json models.json
[ -f agents.json ]          || cp agents.example.json agents.json
[ -f skills.json ]          || cp skills.example.json skills.json
[ -f search_engines.json ]  || cp search_engines.example.json search_engines.json
[ -f data/feishu_config.json ] || { mkdir -p data && cp feishu.example.json data/feishu_config.json; }

# 创建运行时目录
mkdir -p data uploads logs packages \
    web/static/uploads \
    web/static/lobster-claw-files \
    web/static/mu-files

info "配置文件就绪。请编辑以下文件填入 API Key:"
echo "  - models.json          (LLM 模型配置)"
echo "  - agents.json          (Agent 配置)"
echo "  - skills.json          (技能配置)"
echo "  - search_engines.json  (搜索引擎配置)"
echo "  - data/feishu_config.json  (飞书配置，可选)"

# ---------- 生成 systemd 服务 ----------
info "生成 systemd 服务..."
RUN_USER="$(whoami)"
SERVICE_CONTENT="[Unit]
Description=Multi-Agent Document Enhancer
After=network.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${APP_DIR}
Environment=PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=${VENV_DIR}/bin/python -B web_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target"

echo "$SERVICE_CONTENT" | sudo tee "$SERVICE_FILE" > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

info "启动服务..."
sudo systemctl restart "$SERVICE_NAME"

# ---------- 状态检查 ----------
sleep 3
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    info "服务启动成功！"
    echo ""
    echo "  访问地址: http://$(hostname -I | awk '{print $1}'):8888/v3/login"
    echo "  查看日志: ./deploy.sh --logs"
    echo "  重启服务: ./deploy.sh --restart"
    echo ""
    warn "安全提醒: 请尽快修改 web_server.py 中的硬编码密码与 secret_key"
else
    error "服务启动失败，请查看日志: sudo journalctl -u $SERVICE_NAME -n 50"
fi
