# ============================================================
# Multi-Agent Document Enhancer - Dockerfile
# 多阶段构建：Stage 1 前端，Stage 2 后端
# ============================================================

# ---------- Stage 1: 前端构建 ----------
FROM docker.m.daocloud.io/node:20-alpine AS frontend

WORKDIR /build

# 先 COPY 依赖声明，利用 Docker 层缓存
COPY package.json ./

# 安装依赖并构建
RUN npm install --no-package-lock --legacy-peer-deps

# COPY 前端源码与构建配置
COPY v3/ ./v3/
COPY src/ ./src/
COPY vite.config.js postcss.config.js tailwind.config.js index.html ./

# 构建 v3 前端（产物输出到 /build/web/static/v3）
RUN npm run build:v3

# ---------- Stage 2: 后端运行 ----------
FROM docker.m.daocloud.io/python:3.11-slim-bookworm AS runtime

# 系统依赖：libgl1（matplotlib）、中文字体（fpdf PDF 生成）
# 直写清华 Debian 源（避免镜像代理导致签名错误）
RUN echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian bookworm main contrib non-free non-free-firmware\n\
deb https://mirrors.tuna.tsinghua.edu.cn/debian bookworm-updates main contrib non-free non-free-firmware\n\
deb https://mirrors.tuna.tsinghua.edu.cn/debian-security bookworm-security main contrib non-free non-free-firmware' \
    > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    fonts-dejavu \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先 COPY 依赖清单，利用层缓存
COPY requirements-deploy.txt ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements-deploy.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# COPY 项目源码（.dockerignore 已排除 packages/node_modules/data/logs 等）
COPY . .

# 从 Stage 1 拷贝前端构建产物
COPY --from=frontend /build/web/static/v3 ./web/static/v3

# 创建运行时目录（数据卷挂载点）
# v2 前端未在 Docker 构建，创建空目录避免 StaticFiles 报错
RUN mkdir -p data uploads logs \
    web/static/v2/assets \
    web/static/uploads \
    web/static/lobster-claw-files \
    web/static/mu-files \
    packages

EXPOSE 8888

# 启动命令：python -B 禁用 __pycache__
CMD ["python", "-B", "web_server.py"]
