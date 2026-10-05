# 项目结构文档

> Multi-Agent Document Enhancer（mul_agent）
> 基于 FastAPI + SQLite + React 的多智能体协作平台，集成 AI 对话、多用户工作台（v3）、文档/PPT 生成、脚本沙箱、知识库 RAG、定时任务、飞书对接等能力。
> 本文档描述仓库目录结构与各模块职责，便于快速定位代码。最后更新：2026-10。

## 一、技术栈概览

| 层 | 技术 |
|---|---|
| 后端 | Python 3.x · FastAPI · Uvicorn · SQLite（标准库 sqlite3）· Session Cookie 鉴权 · API Key |
| LLM | 多模型适配器（OpenAI / Claude / DeepSeek / DALLE / SD 图像 / 视频 / 本地 Embedding） |
| 前端 v3 | React（Vite 构建）· 多用户工作台主界面，产物 `web/static/v3` |
| 前端 v1/v2 | 旧版 React 面板（`src/`）+ 原生 JS/CSS（`web/static/js`、`web/static/css`） |
| 运维 | Docker / docker-compose（应用 + 沙箱双镜像）· 一键打包 `package-deploy.py` |

- 服务端口：**8888**；本地开发用 `venv\Scripts\python -B web_server.py`。
- 代码量：约 **6.27 万行 / 264 文件**，其中 Python ≈ 3.0 万行（48%）、JSX ≈ 1.3 万行（20%）。

## 二、顶层文件

```
web_server.py            # 应用入口：组装 FastAPI、挂载路由、静态资源、生命周期
Dockerfile               # 应用镜像构建（含模型预下载、依赖安装）
docker-compose.yml       # 编排 mul-agent(应用) + 沙箱服务，端口/网络/extra_hosts
deploy.sh                # Linux 部署脚本
package-deploy.py        # 一键打包 Linux 部署 tarball（排除 venv/node_modules/data 等）
seed_public_skills.py    # 公共技能种子脚本（幂等，部署后初始化默认技能）
requirements.txt         # 开发依赖
requirements-deploy.txt  # 部署依赖
.env.example             # 环境变量示例（直登/限流/模型密钥等）
package.json / vite.config.js / postcss.config.js / tailwind.config.js  # 前端构建配置
pytest.ini               # 测试配置
migrate_kb_shared.py / rehash_kb.py / script_manager.py / ai_chat_manager.py  # 运维/迁移脚本
agents.json / models.json / skills.json / search_engines.json  # 运行时配置（.example 为模板）
direct-login.html / index.html / README.md / README-deploy.md  # 直登页/首页/文档
```

## 三、后端模块（Python）

### 入口与 Web 层
| 路径 | 职责 |
|---|---|
| `web_server.py` | 应用入口，FastAPI 实例、路由挂载、静态文件、启动/关闭钩子 |
| `web/auth.py` | 鉴权：session 登录、API Key 校验 |
| `web/schemas.py` | Pydantic 请求/响应模型 |
| `web/routes/lobster_mu.py` | **v3 多用户工作台核心路由**（会话/技能/脚本/知识库/MCP/记忆/计划/建议/管理端） |
| `web/routes/lobster_claw.py` | 单用户 Lobster Claw 路由（含默认 LLM 适配器 `get_default_llm_adapter`） |
| `web/routes/` 其他 | `agents.py` `ai_chat.py` `attachments.py` `feishu.py` `image.py` `models.py` `search.py` `skills.py` `system.py` `video.py` |
| `web/templates/` | v1/v2 HTML 模板（chat_history_viewer / index / login） |
| `web/static/` | 前端构建产物（`v3/` 主界面、`v2/`、原生 `js/` `css/`）+ 脚本示例 `scripts/` + 生成文件目录 |

### 多用户核心：`lobster_mu/`
v3 工作台的后端业务层，按能力拆分为独立 store/service：

| 文件 | 职责 |
|---|---|
| `db.py` | SQLite 连接与全表 DDL（mu_users / mu_skills / mu_sessions / mu_knowledge / mu_cron 等） |
| `chat_service.py` | 对话生成器：system prompt 注入（技能/MCP/Agent/网页搜索/PPT 块）、`[XXX_CALL]` 标记块解析分发执行 + 二次生成 + 安全网剥离 |
| `skill_store.py` | **技能仓库 + 执行器**（llm / script / search / api），统一返回、异常不抛、归属与公共权限校验 |
| `agent_store.py` | 子 Agent 管理 |
| `knowledge_store.py` | 多用户知识库（文件/分片/向量） |
| `mcp_store.py` / `mcp_client.py` | MCP 服务器配置与客户端调用 |
| `memory_store.py` | 对话记忆 |
| `plan_store.py` | 计划/任务（Plan） |
| `session_store.py` | 会话与消息历史 |
| `cron_store.py` / `cron_runner.py` | 定时任务存储与调度 |
| `sandbox.py` / `sandbox_config.py` | **Docker 沙箱**：脚本执行隔离（普通用户走沙箱，管理员直通） |
| `script_service.py` | 脚本 CRUD / 生成 / 执行 |
| `tools.py` | Agent 工具分发 `execute_tool_call`（含 `use_skill` 分支） |
| `security.py` | 越权/路径安全校验 |
| `upload_service.py` / `ppt_service.py` | 文件上传、PPT 生成 |
| `context_compressor.py` | 上下文压缩 |
| `api_log.py` / `paths.py` | 操作审计日志、用户数据目录 |

### LLM / 能力模块
| 路径 | 职责 |
|---|---|
| `llm/` | 多模型适配器：`adapter_base.py`（基类）、`openai_adapter.py`、`claude_adapter.py`、`deepseek_adapter.py`、`image_adapter.py`、`dalle_adapter.py`、`sd_adapter.py`、`video_adapter.py`、`local_embedding_adapter.py`、`model_call_logger.py`、`model_speed_stats.py` |
| `agents/` | Agent 配置与调度（`agent_manager.py`、`agent_config.py`） |
| `engine/` | 迭代处理引擎（`agent_worker.py`、`iteration_controller.py`） |
| `rag/` | 知识库 RAG（`knowledge_base.py`、`vector_store.py`、`text_chunker.py`） |
| `memory/` | 记忆管理（`memory_manager.py`） |
| `skills/` | 技能配置/执行/管理（v1 侧，`skill_config.py` 等） |
| `search/` | 联网搜索（`search_manager.py`、`search_adapters.py`、`search_tool.py`） |
| `cron/` | 全局定时任务（`cron_scheduler.py`、`task_executor.py`） |
| `feishu/` | 飞书对接（`feishu_client.py`、`feishu_handler.py`、`feishu_ws_client.py`） |
| `models/` | 模型配置/管理（`model_manager.py`、`model_config.py`） |
| `attachment/` | 附件管理 |
| `applogging/` | 应用日志（log_entry / log_manager） |
| `yijing/` | 易经占卜（divination / hexagrams） |
| `utils/` | 通用工具（`logger.py`） |
| `sandbox/` | **沙箱镜像**：`Dockerfile`（独立构建）、`README.md` |

### 前端 v3：`v3/`
React 多用户工作台，构建产物输出到 `web/static/v3`（改 `v3/src` 后需 `npm run build:v3`）。

```
v3/src/pages/Workbench.jsx      # 工作台主页面：TABS 注册中心（技能/会话/知识库/脚本/MCP/记忆/计划/定时…）
v3/src/pages/Login.jsx          # 登录页
v3/src/pages/AdminUsers.jsx     # 管理员用户管理
v3/src/pages/AdminKnowledge.jsx # 管理员知识库
v3/src/pages/AdminModelSpeed.jsx# 模型速度统计
v3/src/components/*Tab.jsx      # 各能力 Tab（SkillsTab / ChatPane / KnowledgeTab / ScriptsTab / McpTab / MemoryTab / AgentTab / CronTab / FilesTab …）
v3/src/components/CodeEditor.jsx# 代码编辑窗口（默认最大化 + 关键字高亮）
v3/src/components/MarkdownContent.jsx # Markdown 渲染 + 代码块高亮
v3/src/utils/highlight.js       # 关键字高亮工具
v3/src/api/client.js            # API 封装 apiGet/apiPost/apiPut/apiDelete，base=/api/lobster-mu
v3/src/stores/                  # authStore / themeStore（状态）
v3/src/App.jsx / main.jsx / index.css
```

**前端模式约定**：每个能力 = 一个 `*Tab.jsx` → 在 `Workbench.jsx` 的 `TABS` 数组注册 → 渲染区 `{activeTab === 'xxx' && <XxxTab />}`；API 统一走 `client.js`。

### 前端 v1/v2：`src/` 与 `web/static/`
```
src/pages/            # v1/v2 旧版页面（AIChat / AgentManager / MemoryManager / ModelManager / ScriptManager / Login …）
src/components/panels/# 旧版面板（AIChatPanel / AgentsPanel / SkillsPanel / VideoPanel / YijingPanel …）
src/stores/authStore.js
web/static/js/app.js, utils.js   # v1/v2 原生脚本
web/static/css/style-pc.css, style-mobile.css
web/static/scripts/              # 示例/测试脚本（PDF 生成、环境自检、易经等，多为演示产物）
web/static/v2/                   # v2 构建产物
```

## 四、其他目录

| 路径 | 说明 |
|---|---|
| `spec/` | 需求/设计文档（如 `user-command-sandbox/spec.md`） |
| `.trae/specs/` | Trae Spec 产物（spec.md / tasks.md / review.md） |
| `.trae/skills/` | 项目级 Trae Skill（v3-mu-capability-add / build-v3-package-deploy 等） |
| `tests/` | pytest 测试 |
| `uploads/` | 运行时上传目录（不入库） |
| `wheels/` | 本地 wheel（部署备用） |
| `data/` | 运行时 SQLite 数据（**不入库**，由部署后种子脚本初始化技能） |
| `.venv` / `venv` / `node_modules` / `packages` / `__pycache__` / `logs` | 依赖与缓存（已忽略） |

## 五、关键架构与约定

### 数据隔离（多用户）
- 所有用户数据按 `user_id` 隔离；`data/{user_id}/` 存文件，SQLite 表按 `user_id` 过滤。
- 公共数据约定：`user_id=0 且 is_public=1`（如公共技能）；非管理员只读，管理员经 `/admin/*` 路由维护。

### Agent 工具注入与分发（`chat_service.py`）
统一范式，技能/MCP/Agent/网页搜索/PPT 均遵循：
1. **注入**：纯文本分支（无文件/图片）时，用 `_build_*_prompt_block` 把可用工具清单写入 system prompt；失败静默降级为空块。
2. **分发**：生成器检测 `[XXX_CALL]...[/XXX_CALL]` 标记 → 解析 → 执行 → 结果回填。
3. **二次生成**：把执行结果拼回 prompt，再调用一次 LLM 产出最终回答。
4. **安全网**：入库前剥除所有残留标记（含未闭合片段）。
5. 路由顺序：字面路径置于 `/{id}` 参数路由前，避免 422。

### 沙箱执行（`sandbox.py`）
- 普通用户脚本 → Docker 沙箱镜像（`sandbox/Dockerfile` 独立构建）；管理员 → 直通。
- 依赖 `docker` 服务在线，部署需 compose 同时启动沙箱容器。

### 构建与部署
- **前端改动**：`npm run build:v3` → `web/static/v3`，再 `python -B package-deploy.py` 打包。
- **纯后端改动**：可跳过 build 直接打包。
- **部署（代码改动必须重建镜像）**：`docker compose build mul-agent && docker compose up -d`（仅 `restart` 不更新代码）。
- **初始化公共技能**：部署后 `docker compose exec mul-agent python -B seed_public_skills.py`（幂等）。
- 打包若报 `PermissionError [WinError 32]` 是文件锁，等 2-3 秒重试。

### 环境约定
- 端口 8888；本地 venv 解释器 `venv\Scripts\python -B`。
- 敏感配置文件（`models.json` 等）不入库，以 `.example` 为模板。

## 六、目录速查（精简树）

```
mul_agent/
├── web_server.py            # 入口
├── web/                     # 路由 / 鉴权 / 模板 / 静态产物
│   ├── routes/              #   FastAPI 路由（lobster_mu 为核心）
│   └── static/              #   v3 / v2 / 原生 js css / 示例脚本
├── lobster_mu/              # ★ 多用户后端核心（db / chat_service / skill_store / sandbox / tools …）
├── llm/                     # 多模型适配器
├── agents/ engine/ rag/ memory/ skills/ search/ cron/ feishu/ models/  # 能力模块
├── applogging/ attachment/ utils/ yijing/  # 日志 / 附件 / 工具 / 占卜
├── sandbox/                 # 沙箱镜像（独立 Dockerfile）
├── v3/                      # ★ 前端多用户工作台（React + Vite）
├── src/                     # 前端 v1/v2 旧版
├── tests/                   # pytest
├── spec/ .trae/             # 文档 / Trae 规范与技能
├── data/ uploads/           # 运行时数据（不入库）
└── Dockerfile docker-compose.yml package-deploy.py seed_public_skills.py  # 构建与部署
```
