# Multi-Agent Document Enhancer

一个基于多Agent协作的智能文档增强系统，集成AI聊天、文档处理、定时任务、记忆管理等功能，支持流式输出、迭代处理和实时进度跟踪。

## 功能特性

### 核心功能
- **多Agent协作处理**：支持多个专业Agent协同处理文档，每个Agent可配置不同的角色和能力
- **迭代式优化**：文档经过多轮迭代处理，每轮由不同Agent完成特定任务
- **流式输出**：大模型输出实时流式显示，提升用户体验
- **WebSocket实时通信**：前后端通过WebSocket保持实时连接，状态更新即时推送
- **登录系统**：基于Session的会话认证，保障访问安全

### AI聊天功能
- **多角色对话**：多个AI角色同时参与对话，模拟真实讨论场景
- **流式消息显示**：AI回复实时流式显示，跟随大模型输出
- **字数统计**：每条消息显示字数统计和序号，便于追踪
- **文字强调**：支持Markdown格式的粗体和颜色强调
- **聊天记录独立访问**：支持通过独立页面查看聊天历史

### 龙虾Claw（Lobster Claw）智能助手
- **Claw对话**：集成类Agent能力的智能助手，支持流式响应
- **会话管理**：支持多会话切换、历史记录查看
- **模型选择**：可在龙虾聊天界面动态选择大模型配置
- **Token统计**：显示输入/输出Token数、耗时、每秒Token速率、模型名称
- **记忆唤起**：对话过程中自动检索相关记忆，增强上下文理解

### 记忆系统
- **多类型记忆**：支持即时（instant）、短期（short_term）、长期（long_term）三种记忆类型
- **权重机制**：通过weight字段和access_count实现记忆权重管理
- **重复检测**：基于余弦相似度的重复记忆检测，自动合并相同记忆
- **关键词检索**：支持中文n-gram分词，提升中文关键词提取和检索准确性
- **记忆管理界面**：支持搜索、筛选、删除记忆，支持最大化窗口

### 定时任务系统（Cron）
- **持久化存储**：基于SQLite存储任务定义和运行历史，重启不丢失
- **Cron表达式调度**：支持标准5字段cron表达式，每分钟检查执行
- **一次性任务**：支持run_at模式，在指定时间执行后自动清理
- **多种任务类型**：
  - `ai` - AI对话任务，调用LLM生成响应
  - `command` - Shell命令任务，执行白名单内的命令
- **超时处理**：可配置任务超时时间（默认300秒）
- **运行历史**：完整记录任务执行状态、输出、错误和耗时
- **服务恢复**：服务启动时自动恢复所有启用任务的调度

### 龙虾Claw命令执行能力
- **Shell命令执行**：基于白名单的安全命令执行（echo/ls/cat/grep等）
- **文件操作**：支持读取、写入、编辑、列表目录（路径白名单限制）
- **HTTP请求**：支持GET/POST请求
- **浏览器自动化**：浏览网页、截图等
- **Web搜索**：集成搜索引擎查询
- **安全机制**：危险命令黑名单 + 允许命令白名单双重保护

### 文档处理
- **多格式支持**：支持txt、doc、docx、pdf等格式文档处理
- **角色选择**：可选择特定Agent处理文档，而非使用全部Agent
- **搜索增强**：集成Bing搜索，为文档处理提供实时信息补充
- **Token统计**：详细统计每次处理的Token消耗

### 用户界面
- **实时进度显示**：迭代进度、步骤进度、运行时间实时更新
- **Agent状态监控**：每个Agent的执行状态、耗时、Token消耗一目了然
- **搜索日志查看**：可查看详细的搜索过程和结果
- **Markdown预览**：文档内容支持Markdown渲染
- **模型调用统计**：查看模型调用次数、Token消耗统计，支持日期查询

### 图像与视频生成
- **文生图**：支持DALL-E、Stable Diffusion等图像生成模型
- **文生视频**：支持视频生成模型
- **Agent分组**：按文本模型、文生图、文生视频对Agent分组展示

### 技能系统
- **技能发现**：自动发现和加载可用技能
- **技能执行**：通过API调用技能并获取结果
- **技能配置**：通过配置文件管理技能参数

### 周易卜卦
- **卦象推演**：集成了完整的周易卜卦功能
- **卦辞解析**：支持384爻的详细解析

## 系统架构

```
mul_agent/
├── agents/              # Agent管理模块
│   ├── agent_config.py   # Agent配置模型
│   └── agent_manager.py  # Agent管理器
├── applogging/          # 应用日志
│   ├── log_entry.py     # 日志条目
│   └── log_manager.py   # 日志管理器
├── attachment/          # 附件管理
│   └── attachment_manager.py
├── cron/                # 定时任务模块
│   ├── cron_manager.py   # 任务和运行历史持久化
│   ├── cron_scheduler.py # 调度器（cron解析+循环检查）
│   └── task_executor.py  # 任务执行引擎（AI/Shell）
├── engine/               # 任务执行引擎
│   ├── agent_worker.py   # Agent工作器
│   └── iteration_controller.py  # 迭代控制器
├── llm/                  # 大语言模型适配器
│   ├── adapter_base.py   # 适配器基类
│   ├── openai_adapter.py # OpenAI适配器
│   ├── claude_adapter.py # Claude适配器
│   ├── deepseek_adapter.py  # DeepSeek适配器
│   ├── dalle_adapter.py  # DALL-E图像适配器
│   ├── image_adapter.py  # 图像适配器
│   ├── sd_adapter.py     # Stable Diffusion适配器
│   ├── video_adapter.py  # 视频适配器
│   └── model_call_logger.py  # 模型调用日志
├── memory/              # 记忆管理模块
│   └── memory_manager.py # 记忆存储、检索、权重管理
├── models/               # 模型配置管理
├── search/               # 搜索引擎模块
├── skills/               # 技能系统
├── utils/                # 工具
│   └── logger.py        # 日志工具
├── web/                  # Web服务
│   ├── routes/          # API路由
│   │   ├── agents.py    # Agent管理API
│   │   ├── ai_chat.py   # AI聊天API
│   │   ├── attachments.py # 附件API
│   │   ├── image.py     # 图像API
│   │   ├── lobster_claw.py # 龙虾Claw（核心）
│   │   ├── models.py    # 模型管理API
│   │   ├── search.py    # 搜索API
│   │   ├── skills.py    # 技能API
│   │   ├── system.py    # 系统API
│   │   └── video.py     # 视频API
│   ├── static/          # 静态资源
│   │   ├── css/        # 样式文件
│   │   └── js/         # JavaScript文件
│   └── templates/      # HTML模板
├── yijing/              # 周易卜卦模块
│   ├── divination.py    # 占卜逻辑
│   └── hexagrams.py     # 卦象数据
├── ai_chat_manager.py   # AI聊天管理器
└── web_server.py        # Web服务器入口
```

## 技术栈

### 后端
- **FastAPI**：高性能Web框架
- **WebSocket**：实时双向通信
- **SSE（Server-Sent Events）**：流式响应
- **Pydantic**：数据验证
- **Jinja2**：模板渲染
- **SQLite**：轻量级数据库（用于记忆和定时任务持久化）
- **SessionMiddleware**：会话管理

### 前端
- **原生JavaScript**：无框架依赖
- **CSS3**：响应式布局
- **Font Awesome**：图标库

### AI集成
- **OpenAI API**：GPT系列模型支持
- **Claude API**：Anthropic Claude模型支持
- **DeepSeek API**：DeepSeek模型支持
- **DALL-E / Stable Diffusion**：图像生成
- **视频生成模型**：文生视频

## 安装配置

### 环境要求
- Python 3.10+
- Windows/Linux/macOS

### 依赖安装
```bash
pip install -r requirements.txt
```

主要依赖：
- `fastapi` - Web框架
- `uvicorn` - ASGI服务器
- `httpx` - HTTP客户端
- `python-docx` - Word文档处理
- `msoffcrypto-tool` - 加密Office文档
- `pillow` - 图像处理
- `tiktoken` - Token计数
- `matplotlib` - 数据可视化

### 启动服务
```bash
python web_server.py
```

服务默认在 `http://localhost:8888` 启动。首次访问需要登录。

### 默认登录凭据
- 用户名：`shineyue`
- 密码：`shineyue@2026`

### 模型配置
在系统设置中配置API密钥：
1. 打开Web界面，登录后进入"系统设置"
2. 添加模型配置（OpenAI/Claude/DeepSeek等）
3. 填写API密钥、模型名称、Base URL等参数
4. 保存配置

可参考 `models.example.json` 创建模型配置。

### Agent配置
1. 进入"Agent配置"页面
2. 添加或编辑Agent角色
3. 设置Agent名称、角色描述、绑定模型
4. 启用需要使用的Agent

可参考 `agents.example.json` 创建Agent配置。

### 搜索引擎配置
可参考 `search_engines.example.json` 配置搜索引擎（Bing等）。

### 技能配置
可参考 `skills.example.json` 配置技能。

## 使用指南

### 文档处理
1. **输入文档**：在左侧输入框输入文档内容或上传文件
2. **选择Agent**：点击"角色选择"按钮，选择处理角色
3. **设置参数**：配置迭代次数、是否启用搜索
4. **开始处理**：点击"开始处理"按钮启动任务
5. **查看结果**：处理完成后，右侧预览区域显示结果

### AI多角色聊天
1. **选择角色**：在AI聊天面板选择参与对话的Agent角色
2. **设置主题**：输入聊天主题
3. **启动聊天**：点击"启动聊天"按钮
4. **查看对话**：实时查看多Agent的流式对话内容

### 龙虾Claw对话
1. **打开Claw**：在主界面打开龙虾Claw面板
2. **选择模型**：在发送按钮旁选择大模型
3. **开始对话**：输入消息，支持流式响应
4. **管理会话**：可创建多个会话、查看历史

### 记忆管理
1. **打开记忆管理**：在Claw面板点击"记忆"按钮
2. **查看记忆**：浏览长期/短期记忆列表
3. **搜索记忆**：按关键词或类型搜索
4. **删除记忆**：单条删除或清空

### 定时任务管理
1. **打开任务管理**：在Claw面板点击"定时任务"按钮
2. **添加任务**：
   - 选择任务类型（AI对话/Shell命令）
   - 输入任务内容（AI提示词或命令）
   - 设置调度（cron表达式或一次性时间）
   - 配置超时和启用状态
3. **管理任务**：
   - 启用/禁用任务
   - 立即执行任务
   - 查看运行历史
   - 删除任务

支持的cron表达式格式（5字段）：`分 时 日 月 周`
- `*/1 * * * *` - 每分钟执行
- `0 * * * *` - 每小时整点执行
- `0 9 * * *` - 每天早上9点执行
- `0 9 * * 1` - 每周一早上9点执行

## API接口

### WebSocket接口

#### 文档处理 (`/ws/process`)
```javascript
// 发送处理请求
ws.send(JSON.stringify({
    content: "文档内容",
    iterations: 2,
    enable_search: true,
    agent_ids: ["agent1", "agent2"]
}));

// 接收处理状态
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.status === 'stats') {
        console.log('迭代进度', data.iteration);
        console.log('步骤进度', data.current_step);
    }
};
```

#### AI聊天 (`/ws/ai-chat`)
```javascript
// 发送聊天动作
ws.send(JSON.stringify({
    action: 'start',
    theme: '讨论主题'
}));

// 接收聊天消息
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.event === 'message') {
        console.log('新消息', data.data);
    }
};
```

### REST API

#### 系统接口
| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/status` | GET | 获取处理状态 |
| `/api/agents` | GET | 获取Agent列表 |
| `/api/models` | GET | 获取模型列表 |
| `/api/ai-chat/agents` | GET | 获取AI聊天Agent |
| `/api/clear` | POST | 清空内容 |
| `/api/search/logs` | GET | 获取搜索日志 |
| `/api/login` | POST | 用户登录 |
| `/api/logout` | POST | 用户退出 |

#### 龙虾Claw接口
| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/lobster-claw/chat/stream` | POST | 龙虾流式聊天 |
| `/api/lobster-claw/chat/sessions` | GET | 获取会话列表 |
| `/api/lobster-claw/chat/session/{id}` | GET | 获取会话详情 |
| `/api/lobster-claw/chat/session/{id}` | DELETE | 删除会话 |
| `/api/lobster-claw/memory/list` | GET | 获取记忆列表 |
| `/api/lobster-claw/memory/add` | POST | 添加记忆 |
| `/api/lobster-claw/memory/search` | POST | 搜索记忆 |
| `/api/lobster-claw/memory/{id}` | DELETE | 删除记忆 |
| `/api/lobster-claw/cron/add` | POST | 添加定时任务 |
| `/api/lobster-claw/cron/list` | GET | 获取任务列表 |
| `/api/lobster-claw/cron/{id}` | GET | 获取任务详情 |
| `/api/lobster-claw/cron/{id}` | PUT | 修改任务 |
| `/api/lobster-claw/cron/{id}` | DELETE | 删除任务 |
| `/api/lobster-claw/cron/toggle/{id}` | POST | 启用/禁用任务 |
| `/api/lobster-claw/cron/{id}/runs` | GET | 获取运行历史 |
| `/api/lobster-claw/cron/{id}/run-now` | POST | 立即执行任务 |

#### 其他接口
| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/image/generate` | POST | 图像生成 |
| `/api/video/generate` | POST | 视频生成 |
| `/api/skills/discover` | GET | 发现技能 |
| `/api/skills/execute` | POST | 执行技能 |

## 数据存储

- `data/memory.db` - 记忆数据库（SQLite）
- `data/cron.db` - 定时任务数据库（SQLite）
- `uploads/` - 上传文件目录
- `agents.example.json` - Agent配置示例
- `models.example.json` - 模型配置示例
- `search_engines.example.json` - 搜索引擎配置示例
- `skills.example.json` - 技能配置示例

## 界面布局

```
┌─────────────────────────────────────────────────────────────┐
│  Multi-Agent Document Enhancer                    [版本号]  │
├────────────────────────┬────────────────────────────────────┤
│                        │                                    │
│   [输入区域]           │   [预览区域]                        │
│                        │                                    │
│   文档内容输入框       │   处理结果预览                      │
│   附件上传             │   Markdown渲染                     │
│                        │                                    │
├────────────────────────┼────────────────────────────────────┤
│   [Agent配置]          │   [统计信息]                        │
│   管理Agent角色        │   迭代进度、步骤进度、Token统计     │
├────────────────────────┴────────────────────────────────────┤
│   [Agent状态表格]                                           │
│   Agent名称 | 状态 | 模型 | 迭代 | Tokens | 耗时            │
├─────────────────────────────────────────────────────────────┤
│   [龙虾Claw面板]                                            │
│   - AI对话（流式响应、模型选择、Token统计）                 │
│   - 记忆管理（列表、搜索、删除）                             │
│   - 定时任务（添加、管理、运行历史）                         │
├─────────────────────────────────────────────────────────────┤
│   [日志区域]                                               │
│   实时显示处理日志                                          │
└─────────────────────────────────────────────────────────────┘
```

## 安全机制

### 命令执行安全
- **危险命令黑名单**：禁止 rm、format、shutdown、regedit 等危险命令
- **允许命令白名单**：仅允许 echo、ls、cat、grep 等安全命令
- **路径白名单**：文件操作限制在项目目录内

### 访问控制
- **登录认证**：基于Session的会话认证
- **WebSocket验证**：检查session cookie
- **速率限制**：防止API滥用

## 版本历史

### v1.20260701
- 新增龙虾Claw定时任务系统
  - 支持cron表达式和一次性任务调度
  - 支持AI对话和Shell命令两种任务类型
  - 任务持久化存储，重启自动恢复
  - 完整的运行历史记录
- 完善记忆管理系统
  - 优化中文n-gram分词
  - 修复记忆唤起问题
  - 添加权重机制和访问计数
- 前端界面优化
  - 新增定时任务管理界面（支持最大化）
  - 模型调用统计支持日期查询
  - 修复Token统计显示问题

### v1.20260629
- 优化AI聊天流式输出
- 实现大模型输出实时显示
- 对话内容控制在256字以内
- 新增角色选择对话框
- 修复迭代进度步骤计算
- Agent状态按选择顺序排序

### v1.20260619
- 新增导出日志按钮
- 支持处理doc/docx/pdf附件
- 添加版本号显示

## 开发说明

### 运行测试
```bash
pytest
```

### 打包
项目支持使用PyInstaller打包为可执行文件。

## License

MIT License
