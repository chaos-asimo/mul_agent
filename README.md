# Multi-Agent Document Enhancer

一个基于多Agent协作的智能文档增强系统，支持流式输出、迭代处理和实时进度跟踪。

## 功能特性

### 核心功能
- **多Agent协作处理**：支持多个专业Agent协同处理文档，每个Agent可配置不同的角色和能力
- **迭代式优化**：文档经过多轮迭代处理，每轮由不同Agent完成特定任务
- **流式输出**：大模型输出实时流式显示，提升用户体验
- **WebSocket实时通信**：前后端通过WebSocket保持实时连接，状态更新即时推送

### AI聊天功能
- **多角色对话**：多个AI角色同时参与对话，模拟真实讨论场景
- **流式消息显示**：AI回复实时流式显示，跟随大模型输出
- **字数统计**：每条消息显示字数统计和序号，便于追踪
- **文字强调**：支持Markdown格式的粗体和颜色强调

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

## 系统架构

```
mul_agent/
├── agents/              # Agent管理模块
│   ├── agent_config.py   # Agent配置模型
│   └── agent_manager.py  # Agent管理器
├── engine/               # 任务执行引擎
│   ├── agent_worker.py   # Agent工作器
│   └── iteration_controller.py  # 迭代控制器
├── llm/                  # 大语言模型适配器
│   ├── adapter_base.py   # 适配器基类
│   ├── openai_adapter.py # OpenAI适配器
│   ├── claude_adapter.py # Claude适配器
│   └── deepseek_adapter.py  # DeepSeek适配器
├── models/               # 模型配置管理
├── search/               # 搜索引擎模块
├── skills/               # 技能系统
├── web/                  # Web服务
│   ├── static/          # 静态资源
│   │   ├── css/        # 样式文件
│   │   └── js/         # JavaScript文件
│   └── templates/      # HTML模板
├── ai_chat_manager.py   # AI聊天管理器
├── main.py              # 主程序入口
└── web_server.py        # Web服务器
```

## 技术栈

### 后端
- **FastAPI**：高性能Web框架
- **WebSocket**：实时双向通信
- **Pydantic**：数据验证
- **Jinja2**：模板渲染

### 前端
- **原生JavaScript**：无框架依赖
- **CSS3**：响应式布局
- **Font Awesome**：图标库

### AI集成
- **OpenAI API**：GPT系列模型支持
- **Claude API**：Anthropic Claude模型支持
- **DeepSeek API**：DeepSeek模型支持

## 安装配置

### 环境要求
- Python 3.10+
- Windows/Linux/macOS

### 依赖安装
```bash
pip install fastapi uvicorn pydantic jinja2
```

### 模型配置
在系统设置中配置API密钥：
1. 打开Web界面，进入"系统设置"
2. 添加模型配置（OpenAI/Claude/DeepSeek）
3. 填写API密钥和其他参数
4. 保存配置

### Agent配置
1. 进入"Agent配置"页面
2. 添加或编辑Agent角色
3. 设置Agent名称、角色描述、绑定模型
4. 启用需要使用的Agent

## 使用指南

### 文档处理
1. **输入文档**：在左侧输入框输入文档内容或上传文件
2. **选择Agent**：点击"角色选择"按钮，选择处理角色
3. **设置参数**：配置迭代次数、是否启用搜索
4. **开始处理**：点击"开始处理"按钮启动任务
5. **查看结果**：处理完成后，右侧预览区域显示结果

### AI聊天
1. **选择角色**：在AI聊天面板选择参与对话的Agent角色
2. **设置主题**：输入聊天主题
3. **启动聊天**：点击"启动聊天"按钮
4. **查看对话**：实时查看多Agent的流式对话内容

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

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/status` | GET | 获取处理状态 |
| `/api/agents` | GET | 获取Agent列表 |
| `/api/models` | GET | 获取模型列表 |
| `/api/ai-chat/agents` | GET | 获取AI聊天Agent |
| `/api/clear` | POST | 清空内容 |
| `/api/search/logs` | GET | 获取搜索日志 |

## 界面布局

```
┌─────────────────────────────────────────────────────────────┐
│  Multi-Agent Document Enhancer                    [版本号]  │
├────────────────────────┬────────────────────────────────────┤
│                        │                                    │
│   [输入区域]           │   [预览区域]                        │
│                        │                                    │
│   文档内容输入框       │   处理结果预览                      │
│                        │   Markdown渲染                     │
│                        │                                    │
├────────────────────────┼────────────────────────────────────┤
│   [Agent配置]          │   [统计信息]                        │
│   管理Agent角色        │   迭代进度、步骤进度、Token统计     │
├────────────────────────┴────────────────────────────────────┤
│   [Agent状态表格]                                           │
│   Agent名称 | 状态 | 模型 | 迭代 | Tokens | 耗时            │
├─────────────────────────────────────────────────────────────┤
│   [日志区域]                                               │
│   实时显示处理日志                                          │
└─────────────────────────────────────────────────────────────┘
```

## 版本历史

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

## License

MIT License
