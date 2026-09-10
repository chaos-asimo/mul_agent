# 部署指南

## 方式一：Docker 部署（推荐）

### 前置要求
- Docker >= 20.10
- Docker Compose >= 2.0

### 步骤

```bash
# 1. 复制环境变量模板
cp .env.example .env

# 2. 初始化配置文件（从 example 复制）
cp models.example.json models.json
cp agents.example.json agents.json
cp skills.example.json skills.json
cp search_engines.example.json search_engines.json
mkdir -p data && cp feishu.example.json data/feishu_config.json

# 3. 编辑配置，填入 API Key
vi models.json       # LLM 模型配置
vi agents.json       # Agent 配置
vi skills.json       # 技能配置

# 4. 创建持久化目录
mkdir -p data uploads logs packages \
    web/static/uploads web/static/lobster-claw-files web/static/mu-files

# 5. 构建并启动
docker compose up -d --build

# 6. 查看日志
docker compose logs -f
```

访问 `http://服务器IP:8888/v3/login`

### 常用命令

```bash
docker compose down        # 停止
docker compose restart    # 重启
docker compose up -d --build  # 重新构建
```

### 启用 RAG 本地 Embedding

编辑 `Dockerfile`，在 `pip install` 行后添加：
```dockerfile
RUN pip install --no-cache-dir torch transformers sentence-transformers \
    --extra-index-url https://download.pytorch.org/whl/cpu
```

---

## 方式二：裸机部署

### 前置要求
- Python >= 3.11
- Node.js >= 18
- npm

### 步骤

```bash
# 1. 全流程部署（检测环境 → venv → 依赖安装 → 前端构建 → systemd → 启动）
chmod +x deploy.sh
./deploy.sh

# 2. 编辑配置填入 API Key
vi models.json
vi agents.json
vi skills.json

# 3. 重启生效
./deploy.sh --restart
```

### 可选参数

```bash
./deploy.sh --rag          # 额外安装 RAG embedding 依赖
./deploy.sh --no-frontend  # 跳过前端构建
./deploy.sh --restart      # 重启服务
./deploy.sh --logs         # 查看实时日志
./deploy.sh --stop         # 停止服务
```

---

## 配置说明

| 文件 | 用途 |
|---|---|
| `models.json` | LLM 模型配置（API Key、模型名、地址） |
| `agents.json` | Agent 定义（角色、系统提示词） |
| `skills.json` | 技能配置（Python 脚本工具） |
| `search_engines.json` | 搜索引擎配置 |
| `data/feishu_config.json` | 飞书接入配置（可选） |

均有 `.example.json` 模板，首次部署时自动复制。

---

## 持久化目录

| 目录 | 用途 |
|---|---|
| `data/` | SQLite 数据库（lobster_mu.db、memory.db 等） |
| `uploads/` | 用户上传文件 |
| `logs/` | 应用日志 |
| `packages/` | 运行时 pip 安装的第三方包（脚本功能） |
| `web/static/uploads/` | 用户上传静态资源 |
| `web/static/lobster-claw-files/` | 脚本生成文件 |

Docker 部署时这些目录已通过卷挂载持久化。裸机部署时直接在项目目录下操作。
