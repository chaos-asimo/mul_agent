# -*- coding: utf-8 -*-
"""MCP 服务端核心：低层 mcp.server.Server + StreamableHTTPSessionManager(stateless)。

设计要点：
- 每个 HTTP 请求在 ASGI 包装层解析 Bearer token → user_id，写入 ContextVar；
  stateless 模式下 session_manager 在本请求上下文内 spawn 服务任务，contextvar 正确传播。
- list_tools / call_tool handler 内从 ContextVar 取 user_id，实现按用户隔离的工具清单与执行。
- 工具两来源合并：mu_mcp_tools 配置化 API（api_<name>）+ mu_skills 中 api 执行器技能（skill_<skill_id>）。
"""
import contextvars
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# 当前请求的归属用户（ASGI 包装层写入，handler 内读取）
current_mu_user: contextvars.ContextVar[int] = contextvars.ContextVar("mu_mcp_user_id", default=0)

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
        # 2) api 执行器技能（自己的 + 公共的，已启用）
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

    @_server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any]):
        from lobster_mu import mcp_tool_store, skill_store
        from lobster_mu.mcp_tool_executor import execute_api_tool, MAX_RESPONSE_CHARS

        user_id = _uid()
        args = dict(arguments or {})
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
