# 龙虾 Claw Agent 执行引擎改造规格说明

> 版本：v1.0（规划稿）
> 适用范围：`lobster_mu/chat_service.py` 主链路、`llm/` 适配器层、`v3/src/components/ChatPane.jsx` 流式渲染
> 目标：把「一次性计划 + 标记后处理」升级为「可迭代、可并行、可人工确认、可观测」的 Agent 编排引擎

---

## 一、现状基线（代码事实）

### 1.1 当前执行流程

入口：[chat_service.py:877 `chat_stream_response`](../../lobster_mu/chat_service.py)

```
用户消息
  │
  ├─ detect_tool_intent()  → 命中则【先】执行内置工具（exec/read_file/search/generate_pdf…）
  │                           并把结果拼进 user_content
  │
  ├─ 单次 LLM 调用（adapter.chat_stream）→ 流式输出正文 + 内嵌标记
  │      标记类型（全部为字符串标记，非 function calling）：
  │        [NEED_SCRIPT]  [SKILL_CALL]  [AGENT_CALL]  [MCP_CALL]  [PPT_GEN]  [WEB_SEARCH]
  │
  ├─ 流式期间：5 个 _MarkerFilter 串联（chat_service.py:1252）实时剔除标记块
  │
  └─ 首流结束后，按固定顺序【串行】检查 6 个分支：
        1276 [NEED_SCRIPT]  → 生成脚本 → 语法检查 → 执行 → 二次 LLM 解读
        1314 [AGENT_CALL]   → 逐个 _execute_sub_agent(506) → 二次 LLM 整合
        1402 [PPT_GEN]      → ppt_service 渲染
        1429 [WEB_SEARCH]   → 搜索 → 二次 LLM 整合
        1510 [MCP_CALL]     → 逐个 mcp_client.call_tool → 二次 LLM 整合
        1580 [SKILL_CALL]   → 技能执行（后台线程 + 队列轮询推进度）
```

### 1.2 结构性缺陷

| 编号 | 问题 | 代码位置 | 影响 |
|---|---|---|---|
| D1 | **无反馈循环**：工具结果只喂给「二次解读」，模型无法基于结果再决策 | 各分支末尾 `interpret_prompt` | 搜索失败/脚本报错无法自我纠正 |
| D2 | **标记解析脆弱**：字符串匹配 + JSON 正则，模型格式漂移即失效 | `AGENT_CALL_PATTERN` 等 | 解析失败只能 `raw_ok=False` 跳过 |
| D3 | **动作串行**：多个子 Agent / MCP 调用逐个等待 | 1316、1516 | N 个子任务耗时 = N 倍 |
| D4 | **无人工确认**：脚本执行、MCP 写操作、shell 命令直接跑 | 1281、1525 | 高危操作无安全闸 |
| D5 | **分支互斥但顺序硬编码**：先命中先执行，后置分支可能被前序改写覆盖 | `full_response` 反复赋值 | 复杂任务只能走一条路 |
| D6 | **过程不可见**：前端只看到「正在执行 X…」散落在正文里 | ChatPane.jsx:421 只读 `content` | 无法展示计划/步骤状态 |
| D7 | **适配器层无 tools 能力** | `llm/adapter_base.py:18` 只有 `chat`/`chat_stream` | 无法使用原生 function calling |

### 1.3 SSE 协议现状（改造的硬约束）

- 后端输出：`data: {"success":bool, "content":str, "session_id":str, "done":bool, "error":str, "token_stats":{}, "knowledge_sources":[]}`
- 前端解析：[ChatPane.jsx:409-437](../../v3/src/components/ChatPane.jsx) 只读取上述字段，**忽略任何未知字段**
- 结论：新增字段是安全的（旧前端忽略），**删改现有字段会破坏前端**

---

## 二、目标架构

### 2.1 总体形态

```
用户消息
  │
  ├─ ToolRegistry 生成统一工具清单（6 个旧标记能力 + 内置工具 + MCP + 技能，统一为 JSON Schema）
  │
  ├─ 双轨路由（capability 探测）
  │     ├─ 轨 A：模型支持 function calling → adapter.chat_stream_with_tools()
  │     └─ 轨 B：不支持 → 保留现有标记注入 + 标记解析
  │
  ├─ ReAct 迭代循环（MAX_STEPS 可配，默认 5）
  │     每轮：模型输出（正文 / tool_calls）
  │           → 执行器执行（并行 where safe）
  │           → Observation 以 role=tool 消息回灌
  │           → 直到模型输出无 tool_calls 的终答，或达到步数上限
  │
  ├─ HITL 安全闸（按工具风险等级拦截）
  │
  └─ 虚拟单流：所有轮次内容仍拼成一条 SSE 流；新增可选 type 字段承载 status/plan 事件
```

### 2.2 三条不可动摇的设计决策

**决策 1：双轨过渡，不一次性下线标记**

标记机制深度嵌入流式过滤链（`_MarkerFilter` 5 层串联）与前端正文渲染。一次性替换会导致：
- 流式过滤链失效 → 标记原文泄漏给用户
- 技能/MCP 的进度推送依赖 `content` 文本 → 前端进度断流

因此 Phase 1 采用 **装饰器外层包装 + 内部双轨**，不重写既有分支体。

**决策 2：模型能力矩阵驱动降级**

`openai / claude / deepseek` 三家对 tools 支持程度不同，且用户可能配置自定义 base_url 的兼容网关。
规格要求：能力探测失败或请求报错（如 400 unsupported）时，**自动回落到轨 B**，且同一次会话内记住该模型不支持（避免反复探测）。

**决策 3：虚拟单流协议**

ReAct 多轮 LLM 调用必须对前端呈现为「一条消息」。定义：
- 正文增量 → 仍走 `content` 字段（前端零改动即可显示）
- 步骤状态 → 新增 `"type":"status"` + `"step":{...}`，旧前端忽略，新前端渲染为步骤条
- 计划 → 新增 `"type":"plan"` + `"steps":[]`
- 结束 → 保持 `done:true` 单次收尾（多轮内部不重复发 done）

---

## 三、Phase 1：统一工具注册表 + 双轨路由 + 最小 ReAct 循环

> 目标：在不破坏现有行为的前提下，让模型能「看到工具结果再决定下一步」，至少支持一次自我纠错。

### 3.1 改动范围

| 类型 | 文件 | 改动 |
|---|---|---|
| 新增 | `lobster_mu/agent/__init__.py` | 包初始化 |
| 新增 | `lobster_mu/agent/tool_registry.py` | 统一工具注册表：name / description / JSON Schema / executor / risk_level / legacy_marker |
| 新增 | `lobster_mu/agent/loop.py` | `ReActLoop`：步数控制、Observation 回灌、终止判定 |
| 新增 | `lobster_mu/agent/stream_adapter.py` | 多轮 LLM 输出 → 单条 SSE 流的转发器（虚拟单流） |
| 修改 | `llm/adapter_base.py` | 新增 `supports_tools() -> bool`（默认 False）、`chat_stream_with_tools()`（默认 NotImplemented → 上层回落） |
| 修改 | `llm/openai_adapter.py` | 实现 tools 透传（`tools` / `tool_choice=auto`，解析 `tool_calls` 增量） |
| 修改 | `llm/claude_adapter.py` | 实现 tools 映射（`tools` / `tool_use` 块 → 统一结构） |
| 修改 | `llm/deepseek_adapter.py` | 同 openai 格式（DeepSeek 兼容 OpenAI tools 协议） |
| 修改 | `lobster_mu/chat_service.py` | 在 `sync_stream_generator` 内部引入路由开关；**既有 6 分支代码保留不动**，仅在其前增加 function-calling 路径 |
| 新增 | `mu_config` 键 | `agent_react_enabled`(默认 false)、`agent_max_steps`(默认 3)、`agent_dual_track`(默认 true) |

### 3.2 工具注册表结构

```python
# lobster_mu/agent/tool_registry.py（示意）
TOOLS = {
    "run_python_script": ToolSpec(
        description="当需要计算/数据处理/文件操作时，生成并执行 Python 脚本",
        schema={"type": "object", "properties": {
            "task": {"type": "string", "description": "要完成的任务描述"},
            "code": {"type": "string", "description": "可选的现成代码"},
        }, "required": ["task"]},
        executor=exec_script, risk="medium", legacy_marker="[NEED_SCRIPT]",
    ),
    "delegate_agent":   ToolSpec(..., risk="low",   legacy_marker="[AGENT_CALL]"),
    "call_mcp_tool":    ToolSpec(..., risk="high",  legacy_marker="[MCP_CALL]"),   # 写操作需确认
    "run_skill":        ToolSpec(..., risk="medium",legacy_marker="[SKILL_CALL]"),
    "generate_ppt":     ToolSpec(..., risk="low",   legacy_marker="[PPT_GEN]"),
    "web_search":       ToolSpec(..., risk="low",   legacy_marker="[WEB_SEARCH]"),
}
```

**映射原则**：一个工具 = 一个旧标记能力。轨 A 用 schema 调用，轨 B 仍用标记文本，执行器（executor）复用同一份实现，保证双轨行为一致。

### 3.3 ReAct 循环（Phase 1 最小版）

```
step = 0
messages = 初始 prompt（system + 历史 + user_content）
while step < MAX_STEPS:
    resp = adapter.chat_stream_with_tools(messages, tools=registry.to_schemas())
    流式输出正文 → 直接转发 SSE（content）
    if not resp.tool_calls:  break            # 终答，退出
    for call in resp.tool_calls:
        obs = registry.execute(call)           # Phase 1 串行
        messages.append({"role":"assistant","tool_calls":[...]})
        messages.append({"role":"tool","tool_call_id":..., "content": obs_text})
    step += 1
若退出时 step 已达上限且仍有 tool_calls：输出降级提示「已达最大执行步数」
```

**终止条件**（三选一，先到先退）：
1. 模型输出无 `tool_calls`（正常终答）
2. `step >= MAX_STEPS`（超限，输出提示）
3. 用户中断（前端 abort → 生成器收到 GeneratorExit）

### 3.4 接口变更清单

| 接口 | 变更 | 兼容性 |
|---|---|---|
| `LLMAdapter.chat_stream` | 不改签名 | 完全兼容 |
| `LLMAdapter.supports_tools()` | 新增，默认 `return False` | 旧适配器自动走轨 B |
| `LLMAdapter.chat_stream_with_tools(messages, tools, **kw)` | 新增，返回 `StreamResult{text_deltas, tool_calls, usage}` | 新增 |
| SSE payload | **仅新增** `type`、`step`、`plan`、`tool_name` 字段 | 旧前端忽略未知字段（已验证 ChatPane.jsx:409） |
| `mu_config` | 新增 3 个键 | 无表结构变更（键值表） |

### 3.5 不改动清单（验收红线）

以下行为在 Phase 1 必须**逐字不变**：

1. `[PPT_GEN]` 大纲解析 → `ppt_service.generate_ppt` → 下载链接文案格式
2. `[SKILL_CALL]` 的 `_material` 注入逻辑与进度队列推送
3. `[AGENT_CALL]` 的 `_execute_sub_agent` 事件流（`{avatar} {ev}`）与 300 字预览
4. `[WEB_SEARCH]` 的 `_clean_md_link_urls` URL 规范化
5. `[MCP_CALL]` 的 `_inject_ctx` 登录态注入
6. 每用户 `BoundedSemaphore(2)` 并发限制（`_sem`）
7. `{"__stats__"...}` token 统计 chunk 的解析与透传
8. 文件/图片消息**不触发**工具与 Agent 编排（现有守卫条件）

### 3.6 回滚方案

- 开关：`agent_react_enabled=false` → 完全回到现有单次调用路径（代码保留，不删）
- 灰度：`agent_dual_track=true` 时按 `supports_tools()` 自动分流；`false` 时强制轨 B
- 回滚粒度：单用户级（`mu_config` 支持 user 级覆盖则不启用，Phase 1 用全局键）

### 3.7 验收标准

| 编号 | 用例 | 期望 |
|---|---|---|
| A1 | 普通问答「今天天气如何」 | 单轮流式输出，无工具调用，SSE 与改造前逐字节等价（content 拼接一致） |
| A2 | 「写个脚本统计 data.csv 行数」 | 轨 A/B 均能生成脚本→执行→输出结果，最终 `done` 一次 |
| A3 | 「用 A Agent 写文案，B Agent 翻译」 | 两个 `delegate_agent` 调用，结果整合为终答 |
| A4 | 「生成一个 5 页 PPT」 | 走 PPT 分支，下载链接格式不变 |
| A5 | 搜索失败场景（断网模拟） | 模型收到 Observation 后**改写查询或放弃**并给出说明（体现反馈循环） |
| A6 | 模型不支持 tools（配置旧版网关） | 自动回落轨 B，功能不缺失，日志有且仅一次 capability 探测失败 |
| A7 | 步数上限 | 设 `MAX_STEPS=1`，构造需两步的任务 → 输出「已达最大执行步数」且流正常收尾 |
| A8 | 并发 2 用户同时长任务 | 各自 `BoundedSemaphore(2)` 生效，不串扰 |

### 3.8 测试方式

```
# 后端单测（新增）
pytest tests/agent/test_tool_registry.py
pytest tests/agent/test_react_loop.py -k "max_steps or fallback"

# 回归（手工，对照 sse 抓包）
curl -N -X POST http://localhost:8888/api/lobster-mu/chat/stream \
  -H "Cookie: session=<token>" -H "Content-Type: application/json" \
  -d '{"message":"今天天气如何","model_name":"<model>"}' > before.txt
# 开启 agent_react_enabled=true 后重复，diff before/after 应只多不少、content 拼接一致
```

---

## 四、Phase 2：动作并行 + HITL 安全闸

> 目标：多子任务不等同 N 倍耗时；高危动作执行前有人工确认。

### 4.1 并行执行

**改动**：`lobster_mu/agent/loop.py` 增加 `execute_parallel(calls)`。

| 项 | 规格 |
|---|---|
| 并发粒度 | 同一轮 ReAct 内的多个 `tool_calls` |
| 线程池 | `ThreadPoolExecutor(max_workers=4)`，单用户复用 |
| 只并行安全工具 | `risk=low`（`web_search`、`delegate_agent`、`generate_ppt`）并行；`risk≥medium` 串行 |
| 结果顺序 | 按 `tool_calls` 原始顺序回填 `messages`（不按完成顺序） |
| 超时 | 单工具 60s（`web_search` 15s 沿用现值），超时填 Observation 为「超时」 |
| 异常隔离 | 单工具异常不影响其它工具；异常写入 Observation |

**验收**：
- P1：3 个 `delegate_agent` 并行，总耗时 < 串行耗时的 60%（同一模型下测量）
- P2：1 个正常 + 1 个抛异常 → 另一结果正常返回，异常以 Observation 呈现给模型
- P3：并行结果顺序与 `tool_calls` 顺序一致（构造交错完成时间）

### 4.2 HITL 安全闸

**风险分级**：

| 等级 | 工具 | 行为 |
|---|---|---|
| low | `web_search`、`delegate_agent`、`generate_ppt` | 直接执行 |
| medium | `run_python_script`、`run_skill` | **首次**需确认；会话内批准后可「本会话不再询问」 |
| high | `call_mcp_tool`（非 GET 语义）、内置 `exec` | 必须确认，且仅管理员可批准 |

**协议**：新增 SSE 事件

```json
{"type":"confirm","request_id":"c_xxx","tool":"run_python_script",
 "summary":"将执行 Python 脚本：统计 data.csv 行数（约 12 行代码）",
 "risk":"medium","expires_in":120}
```

- 前端弹出确认卡（新前端）；旧前端忽略 → 默认策略由 `mu_config.agent_hitl_default` 决定（`deny` 安全优先）
- 批准/拒绝通过 `POST /api/lobster-mu/chat/confirm`（body: `{request_id, approved}`）回传
- 服务端以 `threading.Event` 等待，超时（120s）视为拒绝，Observation 写入「用户未确认，已跳过」
- **不允许**在无 confirm 能力时静默执行 high 风险工具

**验收**：
- H1：medium 工具触发 confirm 事件，批准后正常执行
- H2：拒绝 → Observation 为「已跳过」，模型给出替代方案说明
- H3：超时未响应 → 与拒绝同路径，流正常 `done`
- H4：旧前端（不发 confirm 请求）→ 按 `agent_hitl_default=deny` 不执行 high 风险工具

---

## 五、Phase 3：完整 ReAct 能力（错误恢复 / 计划可视化 / 子 Agent 可中断）

### 5.1 错误恢复策略

| 场景 | 规格 |
|---|---|
| 工具返回 `success=false` | Observation 含 `error` 原文（截断 2000 字）+ `retry_hint`；允许模型下一步换参数重试 |
| 同一工具连续失败 2 次 | 注入系统提示「该工具连续失败，请改用其他方式或告知用户」 |
| 脚本语法错误 | 保留现有「语法检查→报错」逻辑，但报错作为 Observation 回灌而非直接终止（模型可重写） |
| 解析失败（轨 B 标记非法 JSON） | 保留现有 `raw_ok=False` 跳过 + 前端提示，但**额外回灌 Observation**让模型重发 |
| 模型 400/上下文超长 | 现有 `_trim_messages_to_budget` 先执行；仍失败则终止并给用户明确错误 |

### 5.2 计划可视化

**新增工具**：`update_plan`

```json
{"type":"object","properties":{
  "steps":{"type":"array","items":{"type":"string"}}
},"required":["steps"]}
```

- 模型在首轮主动调用（或在 prompt 中要求「复杂任务先列计划」）
- 后端广播 `{"type":"plan","steps":[{"id":1,"title":"...","status":"pending"}]}`
- 每步执行完毕广播 `{"type":"status","step_id":1,"status":"done"}`（`running`/`done`/`failed`/`skipped`）
- 前端：`ChatPane.jsx` 增加步骤条组件；旧前端忽略字段，仍显示正文
- 持久化：`plan` 写入会话元数据（`mu_sessions.meta` 或独立表 `mu_agent_plans`），重开历史可见

**验收**：
- V1：复杂任务（≥3 步）出现 plan 事件，步骤状态随执行推进
- V2：重开会话可见上次计划（持久化生效）
- V3：旧前端不发散字段解析错误（内容仍完整）

### 5.3 子 Agent 可中断 / 部分结果

| 项 | 规格 |
|---|---|
| 部分结果 | `_execute_sub_agent` 支持 `on_event` 回调，Phase 3 起把中间事件作为 Observation 的 `partial` 字段 |
| 主 Agent 决策 | 主 Agent 可在子 Agent 未完成时决定 `cancel_subagent`（新增工具） |
| 取消实现 | 子 Agent 执行体检查 `threading.Event.is_set()`，在步骤边界退出 |
| 超时 | 子 Agent 默认 180s，超时返回已完成部分 + `truncated=true` |

**验收**：
- S1：子 Agent 执行中超时 → 主 Agent 收到 partial，能整合并给出说明
- S2：主 Agent 主动取消 → 子 Agent 在步骤边界退出，无脏写

### 5.4 执行可观测性（贯穿 Phase 3）

- 每次工具调用写 `mu_agent_traces`（`trace_id`/`session_id`/`step`/`tool`/`args_hash`/`duration_ms`/`status`/`error`）
- 管理页新增「Agent 轨迹」查看（按会话/时间筛选）
- 采样：全部 medium/high 风险必写；low 风险按 `mu_config.agent_trace_sample`（默认 0.2）

---

## 六、跨 Phase 通用约束

### 6.1 性能

| 指标 | 目标 |
|---|---|
| 首 token 延迟（普通问答） | 与改造前一致（±100ms） |
| 单轮额外开销 | 工具清单序列化 < 5ms（缓存 registry schema） |
| 内存 | 每会话新增 < 2MB（Observation 文本截断：单条 20KB 上限） |
| 上下文膨胀 | Observation 回灌前按 token 预算裁剪，整体仍受 `_trim_messages_to_budget` 管控 |

### 6.2 安全

- 工具参数在执行前做 schema 校验（类型/必填/枚举），不合法直接拒绝并回灌错误
- `call_mcp_tool` 沿用 `_inject_ctx` 的登录态注入，禁止模型伪造 user 身份
- 脚本执行沿用 `script_service` 现有沙箱与审批字段（`is_approved`）
- 所有工具名与参数写入审计日志（沿用 `mcp_server` 审计口径）

### 6.3 可配置项汇总（`mu_config`）

| 键 | 默认 | Phase |
|---|---|---|
| `agent_react_enabled` | false | 1 |
| `agent_max_steps` | 3（Phase 3 起 5） | 1 |
| `agent_dual_track` | true | 1 |
| `agent_parallel_max_workers` | 4 | 2 |
| `agent_hitl_default` | deny | 2 |
| `agent_trace_sample` | 0.2 | 3 |

### 6.4 文档与回归节奏

- 每个 Phase 合并前必须：`A1` 普通问答回归通过（对照改造前 SSE 抓包）
- 新增单测目录：`tests/agent/`
- 手工验收记录写入 `docs/agent-orchestration-acceptance.md`（逐 Phase 勾选）

---

## 七、风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| function calling 解析在部分兼容网关上行为不一致 | 高 | 轨 A 不稳定 | `supports_tools()` 首次真实请求失败即永久回落轨 B |
| 多轮循环导致 token 成本上升 | 高 | 费用增加 | `MAX_STEPS` 默认 3；Observation 截断；步数进度可见 |
| 旧前端不识别 confirm → 高危工具被 deny 阻塞 | 中 | 功能「变慢/变不可用」 | `agent_hitl_default` 可配；medium 允许「本会话不再询问」 |
| 并行执行引发 SQLite 写竞争 | 中 | 偶发 `database is locked` | 并行仅限 low 风险（不写库）；写操作全部串行 |
| 流式过滤链与新路径冲突（标记泄漏） | 中 | 用户看到原始标记 | 轨 A 不产生标记文本；轨 B 保留现有过滤器；新增泄漏单测 |

---

## 八、实施顺序建议

```
Phase 1（最小闭环）
  1. tool_registry.py + 6 个 ToolSpec（executor 直接复用现有分支函数）
  2. adapter_base.supports_tools / chat_stream_with_tools（默认实现）
  3. openai_adapter 实现 tools → 打通轨 A
  4. loop.py 最小循环 + chat_service 路由开关（默认关闭）
  5. A1~A8 验收 → 打开 agent_react_enabled

Phase 2（并行 + 安全）
  6. execute_parallel（low 风险并行）
  7. confirm 事件 + 回传端点 + HITL 分级
  8. P1~P3、H1~H4 验收

Phase 3（完整能力）
  9. 错误恢复策略 + retry_hint
  10. update_plan + 计划持久化 + 前端步骤条
  11. 子 Agent 取消/部分结果 + mu_agent_traces + 管理页轨迹
  12. V1~V3、S1~S2 验收
```

---

## 九、多用户隔离与性能稳定性（贯穿三阶段，Phase 2 起强制）

> 本章是独立约束：ReAct 循环把「1 次 LLM 调用」放大为「最多 N 次 + 多个工具执行」，
> 若沿用现有并发模型，会成倍放大线程占用、token 成本与 SQLite 竞争。必须显式管控。

### 9.1 当前并发模型事实（改造前）

| 机制 | 现状 | 问题 |
|---|---|---|
| 进程模型 | uvicorn 单 worker | 所有用户共享同一进程与线程池 |
| 每用户并发 | `_sem(user_id)` = `BoundedSemaphore(2)`（chat_service.py:700） | 仅限「同一用户不同会话」，**无全局上限** |
| 获取失败处理 | `acquired = sem.acquire(timeout=30)`（1059），`False` 时**仍然继续执行** | **缺陷**：高负载下配额被绕过，形同无限并发 |
| 生成器执行 | 同步生成器由 FastAPI 丢进线程池（默认 40 线程） | 长任务占线程；慢客户端 `yield` 阻塞也会占线程 |
| 工具执行 | Phase 2 计划用 `ThreadPoolExecutor` | 若全局共享且无配额，会**叠加**在上面两层之上，三倍放大 |
| SQLite | 连接 `timeout=30`，写串行 | 并行工具写库 → `database is locked` |

> 结论：**原规格只把 `_sem` 写进「不改动清单」，不足以保证多用户稳定**。以下为补充设计。

### 9.2 三层配额模型

```
第 1 层  全局并发闸（已实现）
        MU_GLOBAL_CHAT_MAX = 8（环境变量，默认 8）
        ├─ 等待上限 MU_GLOBAL_ACQUIRE_TIMEOUT = 8s，超时立即拒绝（不排队）
        └─ 快速通道（预留 2 槽给普通问答）→ 延后到 Phase 2，避免首版改动过大

第 2 层  用户并发闸（已修复缺陷）
        per-user = 2（沿用 _sem）
        ├─ acquire 失败 → 明确拒绝，**禁止继续执行**
        └─ ReAct 多轮共享同一 semaphore 持有者，不逐轮重复获取

第 3 层  会话串行锁（已实现）
        per-session Lock（key = user_id + session_id）
        └─ 同一会话同一时刻只允许一个生成器，防止历史消息交错写入
           等待上限 MU_SESSION_ACQUIRE_TIMEOUT = 120s
```

**改动点**：

| 文件 | 改动 |
|---|---|
| `lobster_mu/chat_service.py:1058-1059` | `if not acquired:` → 立即 yield 拒绝事件并 `return`（修复配额绕过） |
| `lobster_mu/chat_service.py` | 新增 `_global_sem()`、`_session_lock(user_id, session_id)` |
| `lobster_mu/agent/loop.py` | 工具线程池**不新建全局池**，统一走 `agent/executor_pool.py` 的受控池 |

### 9.3 工具执行线程池的配额化（Phase 2 前置条件）

| 规格项 | 取值 |
|---|---|
| 池类型 | 全局单例 `ThreadPoolExecutor(max_workers=8)` |
| 每用户占用上限 | 2（信号量 `user_tool_sem(user_id, 2)`） |
| 获取超时 | 5s，超时该工具 Observation 记为「资源繁忙，已跳过」 |
| 写库工具 | `risk>=medium` 一律串行执行（不进入池），避免 SQLite 锁竞争 |
| 池饥饿保护 | 普通问答路径不占用工具池 |

> 原规格「`max_workers=4` 单用户复用」应修正为：**全局 8 + 每用户 2**，否则 3 个用户同时并行即打满。

### 9.4 性能稳定性预算

| 预算 | 默认 | 说明 |
|---|---|---|
| 单请求最大步数 | 3（Phase 3 起 5） | 每步一次 LLM 调用 |
| 单请求总时长 | 120s | 超出则提前收尾并提示「任务复杂度超出限制」 |
| 单工具执行 | 60s（`web_search` 15s） | 超时填 Observation |
| 单条 Observation | 20KB / 预算 20% | 超出截断，防止上下文膨胀 |
| 单请求 token 总量 | 可配 `agent_token_budget`（默认按模型上下文 2 倍） | 防成本爆炸 |
| SSE 缓冲 | 每条事件 ≤ 8KB，单请求累计 ≤ 2MB | 防慢客户端拖内存 |

**背压**：同步生成器 `yield` 阻塞会占线程。规格要求：慢客户端场景下，全局闸的槽位在**客户端断开后 5s 内释放**（依赖 `GeneratorExit` + `finally` 释放，现有 `finally` 已释放 per-user，需同步覆盖全局闸）。

### 9.5 降级链路（保证「慢而不崩」）

| 触发 | 降级动作 | 用户感知 |
|---|---|---|
| 模型 tools 首次调用 400 | 轨 A → 轨 B，且该模型永久标记 | 无感（功能不缺失） |
| 工具池取不到槽位 | 该工具跳过，Observation 说明 | 结果可能不完整但流正常 |
| 搜索超时 | 跳过搜索，直接用已有知识 | 明确提示 |
| 子 Agent 超时 | 返回 partial + `truncated` | 提示「部分完成」 |
| 上下文超预算 | `_trim_messages_to_budget` 裁剪 | 无感 |
| 全局闸满 | 立即拒绝（不排队） | 「服务繁忙」 |

### 9.6 隔离性正确性要求

1. **数据隔离**：工具执行、Observation、记忆写入、trace 全部带 `user_id`，禁止跨用户读取（沿用现有 `mcp_server` / `memory_store` 的 user 隔离口径）
2. **状态隔离**：ReAct 的 `messages` 列表、步数计数、tool_call 状态均为**请求局部变量**，不得放入模块级全局（现有 `_sse_semaphores` 是唯一允许的全局字典，需加锁）
3. **资源隔离**：每个并发请求独立持有 semaphore、独立线程池槽位、独立 SQLite 连接（`get_conn()` 每次新建）
4. **成本隔离**：token 统计按 `user_id` 归集，ReAct 多轮累加到同一请求，避免成本统计失真

### 9.7 观测指标（Phase 3 起接入）

| 指标 | 采集点 |
|---|---|
| 并发活跃用户 / 活跃会话 | 全局闸计数器 |
| 每用户 semaphore 等待时长 P95 | acquire 前后时间戳 |
| 工具池队列长度 / 等待时长 | executor_pool |
| 首 token 延迟 P95 | 首个 SSE content 时间 |
| 单请求总时长 P95 | done 事件时间 |
| 429/繁忙拒绝次数 | 拒绝分支计数 |
| ReAct 平均步数分布 | loop 退出原因 |

### 9.8 多用户验收用例

| 编号 | 场景 | 期望 |
|---|---|---|
| M1 | 10 用户同时普通问答 | 全部成功；首 token P95 ≤ 基线 1.5 倍；无 429 |
| M2 | 3 用户同时各跑 3 步 ReAct | 会话内容互不串扰；各自 `done` 独立 |
| M3 | 单用户发起第 3 个并发请求 | 立即收到明确拒绝事件（不再静默执行） |
| M4 | 全局闸打满（8 并发）| 第 9 个请求立即收到「服务繁忙」，**不排队** |
| M5 | 慢客户端（手动挂起读取 60s） | 其他用户 P95 不受影响；断开后 5s 内槽位释放 |
| M6 | 同一会话并发两次发送 | 串行化，历史顺序正确无交错 |
| M7 | 长任务占满工具池 | 普通问答仍可用（预留通道生效） |
| M8 | 3 用户并行写记忆 | 无 `database is locked` 报错（写操作已串行） |

### 9.9 对原规格的修正项

| 原描述 | 修正 |
|---|---|
| Phase 2「`ThreadPoolExecutor(max_workers=4)`，单用户复用」 | 改为**全局 8 + 每用户 2 配额**，见 9.3 |
| 「每用户 `BoundedSemaphore(2)`」列入不改动清单 | **必须改**：修复 `acquire` 超时后仍继续执行的缺陷，见 9.2 |
| 未提全局并发上限 | 新增 `GLOBAL_CHAT_MAX=8` + 快速通道预留 2 槽 |
| 未提会话级串行 | 新增 per-session Lock |
| 未提总时长/token 预算 | 新增 9.4 预算表 |
| 风险表「并行引发 SQLite 写竞争」缓解为「写操作串行」 | 维持，并补充「trace 批量异步写」 |
