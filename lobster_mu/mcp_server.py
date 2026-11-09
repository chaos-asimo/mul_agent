# -*- coding: utf-8 -*-
"""MCP 服务端核心：低层 mcp.server.Server + StreamableHTTPSessionManager(stateless)。

设计要点：
- 每个 HTTP 请求在 ASGI 包装层解析 Bearer token → user_id，写入 ContextVar；
  stateless 模式下 session_manager 在本请求上下文内 spawn 服务任务，contextvar 正确传播。
- list_tools / call_tool handler 内从 ContextVar 取 user_id，实现按用户隔离的工具清单与执行。
- 工具三来源合并：mu_mcp_tools 配置化 API（api_<name>）+ 原生函数工具（NATIVE_TOOLS，方式 C）
  + mu_skills 中 api 执行器技能（skill_<skill_id>）。
- 新增原生工具：在 _register_native_tools() 内用 @native_tool 注册，
  fn(user_id, args) -> Any，自动 json 序列化与审计。
"""
import contextvars
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# 当前请求的归属用户（ASGI 包装层写入，handler 内读取）
current_mu_user: contextvars.ContextVar[int] = contextvars.ContextVar("mu_mcp_user_id", default=0)

# ---------------------------------------------------------------------------
# 原生函数工具注册（方式 C）：把内部 service 函数直接暴露为 MCP 工具，
# 不走 HTTP 回环。fn 签名：fn(user_id: int, args: dict) -> Any
#   - user_id 为当前请求归属用户（已鉴权）
#   - 返回值 dict/list 自动 json.dumps（ensure_ascii=False）
#   - 抛异常 → 返回错误文本，不中断会话
# 用法：
#   @native_tool("make_ppt", "按结构化数据生成 PPT", {...inputSchema...})
#   def _make_ppt(user_id, args): ...
# ---------------------------------------------------------------------------
NATIVE_TOOLS: Dict[str, Dict[str, Any]] = {}


def native_tool(name: str, description: str, schema: Dict[str, Any]):
    def deco(fn):
        NATIVE_TOOLS[name] = {"fn": fn, "description": description, "schema": schema or {"type": "object", "properties": {}}}
        return fn
    return deco


# 注册实际的原生工具
def _register_native_tools():
    from lobster_mu import ppt_service, cron_store, knowledge_store, file_store

    @native_tool(
        "make_ppt",
        "按结构化大纲生成 PPT 并保存到当前用户产物目录，返回下载链接。"
        "封面页自动渲染（title 作主标题，subtitle 可选），slides 为内容页列表。",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "演示文稿主标题（封面页用，必填）"},
                "subtitle": {"type": "string", "description": "封面页副标题（可选）"},
                "slides": {
                    "type": "array",
                    "description": "内容页列表，每项 {heading: 页标题, bullets: [要点字符串数组], chart: 可选图表规格, layout: bullets/chart/text_chart}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string", "description": "内容页标题"},
                            "bullets": {"type": "array", "items": {"type": "string"}, "description": "要点列表"},
                            "chart": {"type": "object", "description": "图表规格（可选）"},
                            "layout": {"type": "string", "enum": ["bullets", "chart", "text_chart"], "description": "页面布局（可选，自动推断）"},
                        },
                        "required": ["heading"],
                    },
                },
                "theme": {"type": "string", "description": "主题：blue / green / purple / orange / dark，默认 blue"},
            },
            "required": ["title", "slides"],
        },
    )
    def _make_ppt(user_id: int, args: Dict[str, Any]):
        return ppt_service.generate_ppt(user_id, args)

    @native_tool(
        "list_cron_tasks",
        "列出当前用户的定时任务（含启用状态、下次执行时间、最近运行状态）",
        {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "description": "true 仅启用 / false 仅停用 / 不传 全部"},
            },
        },
    )
    def _list_cron(user_id: int, args: Dict[str, Any]):
        return {"tasks": cron_store.list_tasks(user_id, args.get("enabled"))}

    @native_tool(
        "search_knowledge",
        "在用户知识库（含公共文档）做语义检索，返回最相关的文档片段",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词或自然语言问题（必填）"},
                "top_k": {"type": "integer", "description": "返回条数，默认 5，最大 20"},
            },
            "required": ["query"],
        },
    )
    def _search_kb(user_id: int, args: Dict[str, Any]):
        top_k = min(int(args.get("top_k") or 5), 20)
        return {"results": knowledge_store.search(user_id, args["query"], top_k=top_k)}

    @native_tool(
        "list_files",
        "列出当前用户产物目录中的文件（名称、大小、创建时间）",
        {"type": "object", "properties": {}},
    )
    def _list_files(user_id: int, args: Dict[str, Any]):
        return {"files": file_store.list_files(user_id)}


def _register_misc_native_tools():
    """注册系统级原生工具（与具体业务无关，仅依赖标准库）。"""

    @native_tool(
        "get_system_time",
        "返回当前服务器系统时间（ISO 8601 + 可读格式 + Unix 时间戳）",
        {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "IANA 时区名（如 Asia/Shanghai、America/New_York），默认服务器本地时区",
                },
            },
        },
    )
    def _get_system_time(user_id: int, args: Dict[str, Any]):
        from datetime import datetime
        import time
        tz_name = (args or {}).get("timezone")
        if tz_name:
            try:
                from zoneinfo import ZoneInfo
                dt = datetime.now(ZoneInfo(tz_name))
            except Exception:
                dt = datetime.now()
        else:
            dt = datetime.now()
        return {
            "iso": dt.isoformat(),
            "readable": dt.strftime("%Y-%m-%d %H:%M:%S %Z").strip(),
            "unix": int(time.time()),
            "timezone": tz_name or "local",
        }


_register_native_tools()
_register_misc_native_tools()

try:
    import mcp.types as types
    from mcp.server.lowlevel import Server
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    MCP_SERVER_AVAILABLE = True
except Exception as e:  # pragma: no cover
    logger.warning("mcp 服务端依赖不可用: %s", e)
    MCP_SERVER_AVAILABLE = False

if MCP_SERVER_AVAILABLE:
    _server: "Server" = Server("lobster-mu")
    _session_mgr = StreamableHTTPSessionManager(
        app=_server, event_store=None, json_response=False, stateless=True,
    )

    def _uid() -> int:
        return current_mu_user.get()

    def _tool_display_name(raw: str) -> str:
        return raw[:64]

    @_server.list_tools()
    async def _list_tools() -> List["types.Tool"]:
        from lobster_mu import mcp_tool_store, skill_store
        from lobster_mu.mcp_tool_executor import build_input_schema

        user_id = _uid()
        tools: List[types.Tool] = []
        # 1) 配置化 API 工具
        for t in mcp_tool_store.list_enabled(user_id):
            tools.append(types.Tool(
                name=_tool_display_name(f"api_{t['name']}"),
                description=t.get("description") or f"API 封装: {t['method']} {t['url'][:80]}",
                inputSchema=build_input_schema(t.get("params_schema")),
            ))
        # 2) 原生函数工具（方式 C：进程内 service 函数直接暴露）
        for tname, tdef in NATIVE_TOOLS.items():
            tools.append(types.Tool(
                name=_tool_display_name(tname),
                description=tdef["description"],
                inputSchema=tdef["schema"],
            ))
        # 3) api 执行器技能（自己的 + 公共的，已启用）
        for s in skill_store.list_enabled(user_id):
            if s.get("executor") != "api":
                continue
            cfg = s.get("config") or {}
            params = cfg.get("parameters")
            schema = {"type": "object", "properties": {}}
            if isinstance(params, dict) and params:
                schema = params
            elif isinstance(params, list):
                from lobster_mu.mcp_tool_executor import build_input_schema
                schema = build_input_schema(params)
            tools.append(types.Tool(
                name=_tool_display_name(f"skill_{s['skill_id']}"),
                description=s.get("description") or s.get("name") or "API 技能",
                inputSchema=schema,
            ))
        return tools

    def _to_text(value: Any) -> str:
        from lobster_mu.mcp_tool_executor import MAX_RESPONSE_CHARS
        if isinstance(value, str):
            return value[:MAX_RESPONSE_CHARS]
        try:
            return json.dumps(value, ensure_ascii=False, default=str)[:MAX_RESPONSE_CHARS]
        except Exception:
            return str(value)[:MAX_RESPONSE_CHARS]

    @_server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any]):
        from lobster_mu import mcp_tool_store, skill_store
        from lobster_mu.mcp_tool_executor import execute_api_tool, MAX_RESPONSE_CHARS

        user_id = _uid()
        args = dict(arguments or {})
        if name in NATIVE_TOOLS:
            # 原生函数工具（方式 C）：进程内直调，不走 HTTP 回环
            import asyncio
            try:
                res = await asyncio.to_thread(NATIVE_TOOLS[name]["fn"], user_id, args)
            except Exception as e:
                logger.exception("原生工具执行失败: %s", name)
                text = f"执行失败: {str(e)[:160]}"
            else:
                text = _to_text(res)
            _audit(user_id, name, text)
            return [types.TextContent(type="text", text=text)]
        if name.startswith("api_"):
            tool = mcp_tool_store.get_tool_by_name(user_id, name[4:])
            if not tool:
                return [types.TextContent(type="text", text=f"工具不存在或未启用: {name}")]
            result = await execute_api_tool(user_id, tool, args)
            _audit(user_id, name, result)
            return [types.TextContent(type="text", text=result)]
        if name.startswith("skill_"):
            skill_id = name[6:]
            import asyncio
            res = await asyncio.to_thread(skill_store.execute, user_id, skill_id, args)
            if isinstance(res, dict):
                text = res.get("result") or res.get("error") or json.dumps(res, ensure_ascii=False)
            else:
                text = str(res)
            _audit(user_id, name, text)
            return [types.TextContent(type="text", text=str(text)[:MAX_RESPONSE_CHARS])]
        return [types.TextContent(type="text", text=f"未知工具: {name}")]

    def _audit(user_id: int, tool_name: str, result: str) -> None:
        try:
            from lobster_mu import tools as mu_tools
            ok = not str(result).startswith(("调用失败", "参数错误", "配置错误"))
            mu_tools.log_operation(user_id, "mcp_tool_call", f"{tool_name} -> {str(result)[:80]}",
                                   success=ok, ip="mcp")
        except Exception:
            pass


@asynccontextmanager
async def run_session_manager():
    """挂到主应用 lifespan：建立 session_manager 的任务组（stateless 模式也必需）。"""
    if not MCP_SERVER_AVAILABLE:
        yield
        return
    async with _session_mgr.run():
        logger.info("MCP 服务端已就绪: /mcp (streamable-http, stateless)")
        yield


async def mcp_asgi(scope, receive, send):
    """/mcp 端点的 ASGI 入口：Bearer 鉴权 + 用户 contextvar 注入。"""
    from lobster_mu import mcp_token_store

    async def _json(status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        await send({
            "type": "http.response.start", "status": status,
            "headers": [(b"content-type", b"application/json; charset=utf-8"),
                        (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})

    if not MCP_SERVER_AVAILABLE:
        await _json(503, {"error": "MCP 服务端不可用（mcp 依赖缺失）"})
        return
    if scope.get("type") != "http":
        return
    # 挂载点 Mount("/mcp") 之下，root_path=/mcp，path 通常为 "/"
    headers = {k.decode("latin1").lower(): v.decode("latin1")
               for k, v in scope.get("headers", [])}
    auth = headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not token:
        await _json(401, {"error": "缺少 Authorization: Bearer <token>"})
        return
    user_id = mcp_token_store.resolve_token(token)
    if not user_id:
        await _json(401, {"error": "令牌无效、已吊销或已过期"})
        return
    current_mu_user.set(user_id)
    await _session_mgr.handle_request(scope, receive, send)
