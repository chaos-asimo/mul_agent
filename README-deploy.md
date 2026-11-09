# 部署指南

## 方式一：Docker 部署（推荐）

### 前置要求
- Docker >= 20.10
- Docker Compose >= 2.0
- 磁盘空间 >= 10GB（镜像约 4.3GB，含 torch CPU + RAG 模型 + 全栈）
- 建议内存 >= 4GB（RAG embedding 模型加载需约 1GB）

### 宿主机安装 Docker

**Debian / Ubuntu**
```bash
curl -fsSL https://get.docker.com | sh
```

**CentOS / RHEL（yum/dnf）**
```bash
# 移除旧版 docker（如有）
sudo yum remove docker docker-client docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
# 配置官方仓库
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
# 安装
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

### 步骤

```bash
# 1. 复制环境变量模板
cp .env.example .env
# 2. 编辑 .env：务必修改 SESSION_SECRET_KEY、MU_ADMIN_PASSWORD，按需填 API_KEYS
vi .env

# 3. 初始化配置文件（从 example 复制）
cp models.example.json models.json
cp agents.example.json agents.json
cp skills.example.json skills.json
cp search_engines.example.json search_engines.json
mkdir -p data && cp feishu.example.json data/feishu_config.json

# 4. 编辑配置，填入 API Key
vi models.json       # LLM 模型配置（含 embedding 模型，api_type=local 走 RAG）
vi agents.json       # Agent 配置
vi skills.json       # 技能配置

# 5. 创建持久化目录
mkdir -p data uploads logs packages \
    web/static/uploads web/static/lobster-claw-files web/static/mu-files

# 6. 构建并启动（首次构建下载依赖 + RAG 模型，耗时较长）
docker compose up -d --build

# 7. 查看日志
docker compose logs -f
```

访问 `http://服务器IP:8888/v3/login`

### 常用命令

```bash
docker compose down        # 停止
docker compose restart    # 重启
docker compose up -d --build  # 重新构建
```

### RAG 本地 Embedding（已内置启用）

Dockerfile 已默认安装 RAG 依赖并**构建期预下载** embedding 模型，无需额外操作：
- 依赖：`torch`(CPU-only) + `transformers` + `sentence-transformers` 等
- 预载模型：`BAAI/bge-base-zh-v1.5`（约 400MB），缓存于镜像内 `HF_HOME`
- 模型缓存通过 `hf_cache` 卷持久化到宿主机，重启容器不会重复下载

如需更换 embedding 模型，构建时覆盖 ARG：
```bash
docker compose build --build-arg EMBEDDING_MODEL=其他/模型名 mul-agent
```

> 注意：要在 `models.json` 中配置一个 `api_type: "local"`、`model_type: "embedding"` 的模型，RAG 知识库检索才会生效。

### 投产核对清单（Checklist）

构建/上线前逐项确认：

- [ ] `.env` 中 `SESSION_SECRET_KEY` 已改为随机强密钥（`openssl rand -hex 32`），非默认值
- [ ] `.env` 中 `MU_ADMIN_PASSWORD` 已改为强密码（bootstrap 首启管理员）
- [ ] `.env` 中 `API_KEYS` 已配置（如需 API Key 访问 `/docs`、`/openapi.json`、`/api/*`）
- [ ] `models.json` / `agents.json` / `skills.json` 已填入真实 LLM API Key
- [ ] `data/feishu_config.json` 飞书配置（如启用飞书接入）
- [ ] 持久化目录已创建：`data/ uploads/ logs/ packages/ web/static/uploads/ web/static/lobster-claw-files/ web/static/mu-files/`
- [ ] 防火墙放行 8888 端口
- [ ] `docker compose up -d --build` 后 `docker compose logs -f` 确认无报错、`Application startup complete`
- [ ] 浏览器访问 `http://服务器IP:8888/v3/login` 能登录
- [ ] （如启用 RAG）确认知识库文档上传后可正常语义检索

### 故障排查：Docker Hub 拉取失败（中国网络）

**现象**：`docker compose up -d --build` 报
`failed to resolve source metadata for docker.io/langgenius/dify-agent-local-sandbox:1.16.1`、
`dial tcp ...: i/o timeout`。

**根因**：`lobster-sandbox` 服务的 `FROM langgenius/dify-agent-local-sandbox:1.16.1` 基础镜像
来自 Docker Hub，中国网络无法直连 `registry-1.docker.io`。**注意：应用主镜像 `mul-agent` 构建
本身不受影响**（其 `FROM python:3.11` 走的是 pip 清华源 + 本地构建，非 Docker Hub 镜像拉取），
失败仅由 sandbox 镜像拖累。

**解决方案（任选其一）**：

1. **用国内镜像源覆盖 sandbox 基础镜像**（推荐，最省事）：
   ```bash
   # 实测（2026-09）：DaoCloud 源稳定可用；轩辕免费节点易限流（报"免费节点当前繁忙"）
   BASE_IMAGE=docker.m.daocloud.io/langgenius/dify-agent-local-sandbox:1.16.1 \
     docker compose build lobster-sandbox
   # 之后正常启动
   docker compose up -d
   ```
   备选源：`docker.1ms.run`、`docker.aityp.com`、`docker.xuanyuan.me`（限流时换用）。

2. **配置 Docker daemon 全局镜像加速**（一劳永逸，对其它镜像也生效）：
   ```bash
   # 备份现有配置（如无则跳过）
   sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak 2>/dev/null

   # 写入镜像加速配置（DaoCloud 实测稳定，1ms/轩辕作备选）
   sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
   {
     "registry-mirrors": [
       "https://docker.m.daocloud.io",
       "https://docker.1ms.run",
       "https://docker.xuanyuan.me"
     ]
   }
   EOF

   # 重启 Docker 生效
   sudo systemctl daemon-reload
   sudo systemctl restart docker

   # 验证（应看到上面 3 个镜像源）
   docker info | grep -A 5 "Registry Mirrors"

   # 直接整体构建 + 启动（无需再传 BASE_IMAGE，daemon 自动从镜像源拉取基础镜像）
   docker compose up -d --build
   ```
   > 注：若现有 daemon.json 已有 `log-driver`、`dns` 等其它字段，请用编辑器手动把
   > `registry-mirrors` 数组合并进去，不要整文件覆盖。

3. **不启用龙虾沙箱**（若暂不需要执行用户命令）：
   注释掉 `docker-compose.yml` 中 `lobster-sandbox` 服务整段，再 `docker compose up -d --build`。
   应用照常运行，仅龙虾 Claw 的命令执行功能不可用。

### 故障排查：NumPy X86_V2 崩溃（老 CPU）

**现象**：容器启动即报
`RuntimeError: NumPy was built with baseline optimizations: (X86_V2) but your machine doesn't support: (X86_V2)`。

**根因**：NumPy 2.3+/2.4+ 的 manylinux wheel 编译时启用了 AVX/SSE4.2/POPCNT 等指令集
（`X86_V2` 基线优化），目标机器 CPU 太老（如 Xeon E5 v1/v2、老 Pentium）不支持，
import numpy 时直接崩溃。**与 Docker 无关，是 CPU 指令集问题。**

**修复**（本项目已内置）：
- `requirements-deploy.txt` 已锁 `numpy==2.2.6`（其 manylinux2014 wheel 为 baseline，
  兼容老 CPU）。
- `Dockerfile` 在 RAG 依赖安装后加了 numpy 版本守卫：若被传递依赖升到 2.3+，自动回退 2.2.6。

**若你仍遇到**（如自行改了依赖导致 numpy 被升级）：
```bash
# 进容器检查
docker compose exec mul-agent python -c "import numpy; print(numpy.__version__)"
# 若 >=2.3，强制降级
docker compose exec mul-agent pip install "numpy==2.2.6" -i https://pypi.tuna.tsinghua.edu.cn/simple
docker compose restart mul-agent
```

**验证 CPU 支持**（宿主机）：
```bash
grep -o 'avx2\|sse4_2\|popcnt' /proc/cpuinfo | sort -u
# 若无 avx2/sse4_2 → CPU 太老，必须用 numpy 2.2.6 或更低
```

---

## 直登接口（/api/lobster-mu/login/direct）

按用户名免密直登，用户不存在则自动创建。用于外部系统（如 OA、门户）跳转登录。

### 请求

```bash
POST /api/lobster-mu/login/direct
Content-Type: application/json
Credentials: include   # 跨域时必须

{
  "username": "3888",
  "display_name": "罗俊易",
  "login_token": "optional-platform-token"   # 可选，存入 session
}
```

- `login_token`：平台令牌，存入 session（`mu_login_token`），后续端点可通过 `request.session.get("mu_login_token")` 读取调用平台 API
- 自动创建的用户角色固定为 `user`（非 admin），密码 = `用户名 + "sy"`

### 跨域配置

服务端 CORS 中间件 `allow_origins=["*", "null"]`，允许任意来源的预检请求。实际访问控制由后端 `DIRECT_LOGIN_ALLOWED_ORIGINS` 环境变量完成：

| 配置 | 效果 |
|---|---|
| 不配置（空） | 拒绝所有跨域请求，仅同源 + `file://`（Origin=null）可访问 |
| `*.jbysoft.com` | 允许 `jbysoft.com` 所有子域名跨域调用 |
| `https://claw.jbysoft.com,https://appsy.jbysoft.com` | 精确允许列表（逗号分隔） |

`file://` 打开的 HTML 页面（Origin=null）**始终放行**，无需配置。

### 示例 HTML（direct-login.html）

放在本地或任意页面，输入用户名 + 显示名即可登录跳转 `/v3`：

```html
<script>
async function directLogin() {
  const resp = await fetch('https://claw.jbysoft.com/api/lobster-mu/login/direct', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',   // 必须，否则跨域 cookie 不生效
    body: JSON.stringify({ username: '3888', display_name: '罗俊易' })
  });
  if (resp.ok) window.location.href = 'https://claw.jbysoft.com/v3';
}
</script>
```

> 注意：cookie 属性为 `SameSite=None; Secure`（服务端自动设置），要求 HTTPS 环境。HTTP 下 `Secure` cookie 不会发送。

---

## 登录限流

登录接口（v1 `/api/login` + v3 `/api/lobster-mu/login` + `/login/2fa`）内置暴力破解防护：

- **锁定维度**：IP + 用户名组合（同一 IP 下不同账户互不影响）
- **触发条件**：15 分钟内同一 IP+用户 失败 5 次
- **锁定时长**：15 分钟（期间返回 429）
- **成功登录**：清除该 IP+用户 的失败计数

---

## 端口暴露模式

`docker-compose.yml` 使用 `ports: ["8888:8888"]` 端口映射（非 `network_mode: host`）。

- 容器内应用监听 `0.0.0.0:8888`
- 宿主机 8888 端口映射到容器
- 如需额外 hosts 条目（如内部域名解析），用 `extra_hosts`：

```yaml
extra_hosts:
  - "shineyue.ai:10.0.87.165"
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
