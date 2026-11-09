# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - MCP client 管理器

- mcp SDK 可选导入：未安装时 MCP_AVAILABLE=False，所有公开方法返回降级错误，不抛异常
- 支持 stdio / sse / streamable-http 三种 transport
- 每次调用按需建立连接、用后即关（async with 确保子进程清理）
- 工具清单内存缓存（TTL 5 分钟），避免每次对话重复连接
- 同步对外接口（asyncio.run 包装），便于在 FastAPI async 路由与 chat_service 同步生成器中复用
"""
import asyncio
import json
import logging
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamablehttp_client
    MCP_AVAILABLE = True
except Exception as _e:  # ImportError 或传递依赖缺失
    MCP_AVAILABLE = False
    _IMPORT_ERROR = str(_e)
    logger.warning("MCP SDK 不可用，MCP 功能将降级: %s", _e)

INSTALL_HINT = "MCP 功能不可用：未安装 mcp 依赖。请在项目环境执行 pip install mcp 后重启服务。"

TOOL_CACHE_TTL = 300  # 工具清单缓存 5 分钟
CALL_TIMEOUT = 60     # 单次工具调用超时（秒）
CONNECT_TIMEOUT = 30  # 连接/握手超时（秒）

# Windows 下这些命令需要 cmd /c 包装（npx/npm 等是 .cmd 脚本）
_WIN_SHELL_CMDS = {"npx", "npm", "pnpm", "yarn", "node", "uvx", "uv"}

# { (user_id, server_id): (tools_list, fetched_at) }
_tools_cache: Dict[tuple, tuple] = {}
_cache_lock = threading.Lock()

# 参数名视为“文件系统路径”的键（用于跨用户越权拦截）
_PATH_KEYS = {
    "path", "paths", "dir", "directory", "root", "folder", "file", "filename",
    "filepath", "file_path", "files", "source", "src", "destination", "dest",
    "from", "to", "cwd", "workdir", "work_dir",
}


def _win_wrap_command(command: str, args: List[str]):
    """Windows 下 npx/uvx 等需经 cmd /c 启动，否则 subprocess 找不到可执行文件"""
    if os.name == "nt" and command.lower() in _WIN_SHELL_CMDS:
        return "cmd", ["/c", command] + list(args or [])
    return command, list(args or [])


# ---------------------------------------------------------------------------
# 多用户隔离加固
#
# 外部 MCP server（尤其是 filesystem 类原生工具）自身没有 user 概念：
#   - 它继承主进程 cwd
#   - 它的根目录来自用户填写的 args
# 因此若把整个 uploads/ 作为根，任何用户都能 list 出别人的文件。
#
# 三道防护：
#   1) stdio 子进程 cwd 强制指向该用户的沙箱目录（mu-files/{uid}）
#   2) 注入 MU_USER_ID / MU_USER_ROOT 环境变量（强制覆盖用户配置，防伪造）
#   3) 调用前拦截参数里指向他人目录的绝对路径
# ---------------------------------------------------------------------------

def _user_sandbox_root(user_id: int) -> str:
    """当前用户的沙箱根目录（MCP stdio 子进程 cwd）"""
    from lobster_mu import paths
    return paths.mu_files_dir(user_id)


def _build_stdio_params(srv: Dict[str, Any], user_id: int):
    """构造 stdio 启动参数：强制 per-user cwd + 注入用户上下文环境变量"""
    command, args = _win_wrap_command(srv.get("command", ""), srv.get("args", []))
    env = dict(srv.get("env") or {})
    try:
        root = _user_sandbox_root(user_id)
        env["MU_USER_ID"] = str(user_id)
        env["MU_USER_ROOT"] = root
        env["MU_SANDBOX"] = "1"
        cwd = root
    except Exception:
        cwd = None
    return StdioServerParameters(command=command, args=args, env=env or None, cwd=cwd)


def _looks_like_path(value: str) -> bool:
    s = (value or "").strip()
    if not s:
        return False
    if s.startswith("~"):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", s):
        return True
    if s.startswith("/") or s.startswith("\\\\"):
        return True
    return False


def _iter_string_values(obj: Any, key: str = None):
    """递归产出 (key, str_value)"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _iter_string_values(v, k)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_string_values(v, key)
    elif isinstance(obj, str):
        yield key, obj


def guard_tool_arguments(user_id: int, tool_name: str, arguments: Dict[str, Any]) -> None:
    """调用外部 MCP 工具前校验参数：禁止出现指向其他用户目录的绝对路径。

    允许：
      - 干净相对路径（相对 per-user cwd，天然落在沙箱内）
      - 落在当前用户 mu-files / uploads / lobster-claw-files 内的绝对路径
      - data/ 只读目录内的绝对路径
    拒绝：
      - 其他用户的绝对路径、系统目录、项目根目录等
    """
    from lobster_mu import paths
    violations: List[str] = []
    for key, val in _iter_string_values(arguments or {}):
        k = (key or "").lower()
        is_path_key = k in _PATH_KEYS
        if not is_path_key and not _looks_like_path(val):
            continue
        if not _looks_like_path(val):
            continue  # 相对路径：由 cwd 约束，安全
        try:
            ok = paths.is_user_path(user_id, val, write=False)
        except Exception:
            ok = False
        if not ok:
            violations.append(f"{key}={val}")
    if violations:
        raise PermissionError(
            f"MCP 工具 {tool_name} 参数越权：{'; '.join(violations[:3])}"
            f"（仅允许访问当前用户目录）"
        )


def _is_self_mcp_shared_identity(srv: Dict[str, Any]) -> bool:
    """是否为“公共配置 + 固定 mcp_ 令牌 + 指向本机 /mcp”的配置。

    这种配置会让所有用户共用同一个令牌身份，从而看到令牌所有者的私有数据
    （例如其 list_files / search_knowledge 结果）。多租户下必须按用户换发令牌。
    """
    if not srv.get("is_public"):
        return False
    url = (srv.get("url") or "").strip()
    if "/mcp" not in url.lower():
        return False
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if host not in ("127.0.0.1", "localhost", "::1"):
        return False
    headers = srv.get("headers") or {}
    if not isinstance(headers, dict):
        return False
    for k, v in headers.items():
        if str(k).lower() == "authorization" and "mcp_" in str(v):
            return True
    return False


# 自动换发的每用户令牌明文缓存：{ (user_id, server_id): plaintext }
_auto_tokens: Dict[tuple, str] = {}
_auto_token_lock = threading.Lock()


def _per_user_token(user_id: int, server_id: int) -> Optional[str]:
    """为公共自身 MCP server 按用户换发/复用令牌（进程内缓存明文）。"""
    key = (user_id, server_id)
    with _auto_token_lock:
        cached = _auto_tokens.get(key)
    if cached:
        return cached
    try:
        from lobster_mu import mcp_token_store
        # 清理该用户此前自动换发的旧令牌，避免表中无限累积
        try:
            conn = mcp_token_store.get_conn()
            try:
                conn.execute(
                    "DELETE FROM mu_mcp_tokens WHERE user_id = ? AND name = ?",
                    (user_id, f"auto:server{server_id}"),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as ce:
            logger.debug("清理旧自动令牌失败（忽略）: %s", ce)
        _, plaintext = mcp_token_store.create_token(
            user_id, name=f"auto:server{server_id}", expires_at="")
        with _auto_token_lock:
            _auto_tokens[key] = plaintext
        logger.info("为公共 MCP server=%s 换发用户 %s 的独立令牌", server_id, user_id)
        return plaintext
    except Exception as e:
        logger.error("换发用户令牌失败 user=%s server=%s: %s", user_id, server_id, e)
        return None


def _headers_for_user(user_id: int, srv: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """返回该用户应使用的请求头。公共自身 /mcp 场景下替换为每用户独立令牌。"""
    headers = dict(srv.get("headers") or {})
    if _is_self_mcp_shared_identity(srv):
        token = _per_user_token(user_id, int(srv.get("id") or 0))
        if token:
            for k in list(headers.keys()):
                if str(k).lower() == "authorization":
                    headers.pop(k)
            headers["Authorization"] = f"Bearer {token}"
    return headers or None


def invalidate_cache(user_id: int, server_id: Optional[int] = None):
    """配置变更/启停时清缓存"""
    with _cache_lock:
        keys = [k for k in _tools_cache if k[0] == user_id and (server_id is None or k[1] == server_id)]
        for k in keys:
            _tools_cache.pop(k, None)


def _tool_to_dict(tool) -> Dict[str, Any]:
    return {
        "name": getattr(tool, "name", ""),
        "description": getattr(tool, "description", "") or "",
        "input_schema": getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None),
    }


async def _connect_and_list(srv: Dict[str, Any], user_id: int = 0) -> List[Dict[str, Any]]:
    """建立连接并返回工具清单（内部异步实现）"""
    transport = srv.get("transport", "stdio")
    if transport == "stdio":
        params = _build_stdio_params(srv, user_id)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT)
                result = await asyncio.wait_for(session.list_tools(), timeout=CONNECT_TIMEOUT)
                return [_tool_to_dict(t) for t in result.tools]
    elif transport == "sse":
        async with sse_client(srv["url"], headers=srv.get("headers") or None) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT)
                result = await asyncio.wait_for(session.list_tools(), timeout=CONNECT_TIMEOUT)
                return [_tool_to_dict(t) for t in result.tools]
    elif transport in ("http", "streamable-http"):
        # 公共自身 /mcp 场景：按用户换发独立令牌，避免共享身份数据
        async with streamablehttp_client(srv["url"], headers=_headers_for_user(user_id, srv)) as (read, write, _):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT)
                result = await asyncio.wait_for(session.list_tools(), timeout=CONNECT_TIMEOUT)
                return [_tool_to_dict(t) for t in result.tools]
    raise ValueError(f"不支持的 transport 类型: {transport}")


async def _connect_and_call(srv: Dict[str, Any], tool_name: str, arguments: Dict[str, Any],
                            user_id: int = 0) -> str:
    """建立连接并调用工具，返回文本结果（内部异步实现）"""
    # 越权拦截：参数里不得出现指向其他用户目录的绝对路径
    guard_tool_arguments(user_id, tool_name, arguments or {})
    transport = srv.get("transport", "stdio")
    if transport == "stdio":
        params = _build_stdio_params(srv, user_id)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT)
                result = await asyncio.wait_for(session.call_tool(tool_name, arguments or {}),
                                                timeout=CALL_TIMEOUT)
                return _serialize_result(result)
    elif transport == "sse":
        async with sse_client(srv["url"], headers=_headers_for_user(user_id, srv)) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT)
                result = await asyncio.wait_for(session.call_tool(tool_name, arguments or {}),
                                                timeout=CALL_TIMEOUT)
                return _serialize_result(result)
    elif transport in ("http", "streamable-http"):
        async with streamablehttp_client(srv["url"], headers=_headers_for_user(user_id, srv)) as (read, write, _):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=CONNECT_TIMEOUT)
                result = await asyncio.wait_for(session.call_tool(tool_name, arguments or {}),
                                                timeout=CALL_TIMEOUT)
                return _serialize_result(result)
    raise ValueError(f"不支持的 transport 类型: {transport}")


def _serialize_result(result: Any) -> str:
    """把 CallToolResult 内容块序列化为文本"""
    parts: List[str] = []
    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
        else:
            # 非文本块（图片/资源等）：给出类型提示，避免不可读二进制
            parts.append(f"[非文本内容: {type(block).__name__}]")
    if getattr(result, "isError", False):
        parts.append("（工具返回错误状态）")
    text = "\n".join(p for p in parts if p)
    return text or "（工具无文本输出）"


def _root_error(e: BaseException) -> BaseException:
    """解包 ExceptionGroup，返回最内层叶子异常，便于生成可读错误信息"""
    seen = set()
    cur = e
    while hasattr(cur, "exceptions") and cur.exceptions and id(cur) not in seen:
        seen.add(id(cur))
        cur = cur.exceptions[0]
    return cur


def _run_async(coro):
    """在独立守护线程的新事件循环中运行协程。

    必须用独立线程：MCP 接口从 FastAPI async 路由调用时，当前线程已运行
    uvicorn 事件循环，同线程再 run_until_complete 会报
    "Cannot run the event loop while another loop is running"。
    子进程（stdio）也绑定到该 worker 线程的 loop，确保用后随 loop 关闭清理。
    """
    box = {}

    def _worker():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                box["value"] = loop.run_until_complete(coro)
            finally:
                # 关闭 loop 前等待所有 transport/子进程清理
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                loop.close()
        except BaseException as e:  # 包含 KeyboardInterrupt 等
            box["error"] = e

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


# ============ 公开接口 ============

def test_connection(server_config: Dict[str, Any], user_id: int = 0) -> Dict[str, Any]:
    """测试连接并拉取工具清单。server_config 为含明文 env 的完整配置 dict。
    返回 {success: bool, tools: [...], error: str}"""
    if not MCP_AVAILABLE:
        return {"success": False, "tools": [], "error": INSTALL_HINT}
    try:
        tools = _run_async(_connect_and_list(server_config, user_id))
        return {"success": True, "tools": tools, "error": None}
    except asyncio.TimeoutError:
        return {"success": False, "tools": [], "error": f"连接/握手超时（{CONNECT_TIMEOUT}秒），请检查命令或网络（stdio server 首次启动可能较慢）"}
    except FileNotFoundError as e:
        return {"success": False, "tools": [], "error": f"命令不存在: {e.filename or server_config.get('command')}，请确认已安装并在 PATH 中"}
    except Exception as e:
        root = _root_error(e)
        if isinstance(root, asyncio.TimeoutError):
            return {"success": False, "tools": [], "error": f"连接/握手超时（{CONNECT_TIMEOUT}秒），请检查命令或网络（stdio server 首次启动可能较慢）"}
        if isinstance(root, FileNotFoundError):
            return {"success": False, "tools": [], "error": f"命令不存在: {root.filename or server_config.get('command')}，请确认已安装并在 PATH 中"}
        logger.warning("MCP test_connection 失败: %s", e, exc_info=True)
        return {"success": False, "tools": [], "error": f"连接失败: {type(root).__name__}: {root}"}


def refresh_server_tools(user_id: int, server_id: int, server_config: Dict[str, Any]) -> Dict[str, Any]:
    """拉取并缓存某 server 的工具清单，返回 test_connection 同款结果"""
    result = test_connection(server_config, user_id=user_id)
    if result["success"]:
        with _cache_lock:
            _tools_cache[(user_id, server_id)] = (result["tools"], time.time())
    return result


def get_cached_tools(user_id: int, server_id: int) -> Optional[List[Dict[str, Any]]]:
    with _cache_lock:
        entry = _tools_cache.get((user_id, server_id))
        if entry and (time.time() - entry[1]) < TOOL_CACHE_TTL:
            return entry[0]
    return None


def get_enabled_tools(user_id: int) -> List[Dict[str, Any]]:
    """聚合当前用户所有启用 server（含公共）的工具（缓存优先，未命中按需拉取）。
    返回 [{server, server_id, name, description, input_schema}]；失败的 server 跳过。"""
    from lobster_mu import mcp_store

    servers = mcp_store.list_enabled_servers_with_public(user_id)
    aggregated: List[Dict[str, Any]] = []
    for srv in servers:
        sid = srv["id"]
        tools = get_cached_tools(user_id, sid)
        if tools is None:
            if not MCP_AVAILABLE:
                continue
            raw = mcp_store.get_server_raw(user_id, sid)
            if not raw:
                continue
            res = refresh_server_tools(user_id, sid, raw)
            if not res["success"]:
                logger.info("MCP server %s(id=%s) 工具拉取失败: %s", srv["name"], sid, res.get("error"))
                continue
            tools = res["tools"]
        for t in tools:
            aggregated.append({
                "server": srv["name"],
                "server_id": sid,
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("input_schema"),
            })
    return aggregated


def call_tool(user_id: int, server_name: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """调用指定 server 的工具。返回 {success, result, error}"""
    if not MCP_AVAILABLE:
        return {"success": False, "result": None, "error": INSTALL_HINT}
    from lobster_mu import mcp_store

    # 按名称匹配启用的 server（含公共，重名时取第一个）
    target = None
    for srv in mcp_store.list_enabled_servers_with_public(user_id):
        if srv["name"] == server_name:
            target = srv
            break
    if not target:
        return {"success": False, "result": None,
                "error": f"未找到名为「{server_name}」的已启用 MCP server"}
    raw = mcp_store.get_server_raw(user_id, target["id"])
    if not raw:
        return {"success": False, "result": None, "error": "server 配置不可用"}

    try:
        text = _run_async(_connect_and_call(raw, tool_name, arguments or {}, user_id=user_id))
        return {"success": True, "result": text, "error": None}
    except PermissionError as e:
        # 参数越权：明确告知，不执行
        logger.warning("MCP 参数越权拦截 user=%s server=%s tool=%s: %s",
                       user_id, server_name, tool_name, e)
        return {"success": False, "result": None, "error": str(e)}
    except Exception as e:
        root = _root_error(e)
        if isinstance(root, PermissionError):
            return {"success": False, "result": None, "error": str(root)}
        if isinstance(root, asyncio.TimeoutError):
            return {"success": False, "result": None, "error": f"工具调用超时（{CALL_TIMEOUT}秒）"}
        if isinstance(root, FileNotFoundError):
            return {"success": False, "result": None, "error": f"命令不存在: {root.filename or raw.get('command')}，请确认 MCP server 命令已安装"}
        logger.warning("MCP call_tool 失败 server=%s tool=%s: %s", server_name, tool_name, e, exc_info=True)
        return {"success": False, "result": None, "error": f"工具调用失败: {type(root).__name__}: {root}"}
