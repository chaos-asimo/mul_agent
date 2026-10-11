# ============================================================
# Multi-Agent Document Enhancer - Dockerfile
# 多阶段构建：Stage 1 前端，Stage 2 后端
# ============================================================
# 镜像源可通过构建参数 REGISTRY 覆盖（中国网络直连 Docker Hub 失败时切换国内镜像）。
# 例如：docker compose build --build-arg REGISTRY=docker.1ms.run mul-agent
# 可用源（2026 实测）：docker.1ms.run / docker.xuanyuan.me / docker.aityp.com / docker.m.daocloud.io
ARG REGISTRY=docker.m.daocloud.io

# ---------- Stage 1: 前端构建 ----------
FROM ${REGISTRY}/node:20-alpine AS frontend

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
FROM ${REGISTRY}/python:3.11-slim-bookworm AS runtime

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
    ca-certificates \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# 安装 docker CLI（仅客户端，不装 daemon）：供用户命令沙箱以 Docker-out-of-Docker
# 方式调用宿主机 Docker（需 compose 挂载 /var/run/docker.sock）。
# 用清华 Docker CE 镜像源，避免直连 download.docker.com 失败。
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/debian/gpg \
       | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/debian bookworm stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先 COPY 依赖清单，利用层缓存
COPY requirements-deploy.txt ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements-deploy.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# RAG 本地向量化依赖
# torch 2.14.0 从清华源拉取（清华源有 linux manylinux wheel，本机已验证可下载）。
# CPU 机器上 torch 2.14.0 的 PyPI wheel（含 CUDA 依赖）可正常运行（不加载 CUDA，nvidia 包是可选的）。
# 构建时多 1-2 分钟下载 torch（~528MB），但无需预打包 wheel，源码包保持精简（~2.6MB）。
RUN pip install --no-cache-dir \
    torch==2.14.0 \
    transformers sentence-transformers huggingface-hub safetensors tokenizers \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

# numpy 版本守卫：RAG 依赖可能把 numpy 传递性升级到 2.4+（AVX512 版），
# 老 CPU（不支持 X86_V2/AVX2）上 import 会崩溃。强制回退到 2.2.6（baseline manylinux2014）。
RUN python -c "import numpy,sys; v=tuple(int(x) for x in numpy.__version__.split('.')[:2]); print('numpy', numpy.__version__); sys.exit(0 if v<(2,3) else 1)" \
    || pip install --no-cache-dir "numpy==2.2.6" -i https://pypi.tuna.tsinghua.edu.cn/simple

# COPY 项目源码（.dockerignore 已排除 packages/node_modules/data/logs 等）
COPY . .

# 构建期预下载 RAG embedding 模型到镜像缓存，避免生产首启时联网下载
# 默认模型 BAAI/bge-base-zh-v1.5（约 400MB）；可用 ARG 覆盖
# 用 huggingface-cli 下载（仅拉文件，不加载 torch/model 架构，比 import SentenceTransformer 快）
# 注意：RUN 用 /bin/sh（dash），不支持 ${var//} bash 扩展，--local-dir 用固定路径
ARG EMBEDDING_MODEL=BAAI/bge-base-zh-v1.5
ENV HF_ENDPOINT=https://hf-mirror.com \
    HF_HOME=/root/.cache/huggingface
RUN huggingface-cli download "${EMBEDDING_MODEL}" \
        --local-dir /root/.cache/huggingface/hub/models--BAAI--bge-base-zh-v1.5 \
    || echo "[WARN] RAG embedding 模型预下载失败，将在首次运行时联网下载（需容器可访问 hf-mirror.com）"

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
