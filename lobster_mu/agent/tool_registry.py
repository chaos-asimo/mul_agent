# -*- coding: utf-8 -*-
"""统一工具注册表：把 6 个旧标记能力映射为 JSON Schema 工具。

每个 ToolSpec 绑定一个 executor，该 executor 接收解析后的参数，返回 observation 文本。
ReAct 循环会把 observation 以 role=tool 消息回灌给模型。
"""
import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 子 Agent 取消事件注册表：cancel_token -> threading.Event
_SUB_AGENT_CANCEL_EVENTS: Dict[str, threading.Event] = {}
_SUB_AGENT_CANCEL_LOCK = threading.Lock()

# 工具执行进度上报（线程本地）：ReAct 循环在执行工具前注入 emitter，
# 执行器可通过 emit_progress() 把"脚本生成/沙箱执行"等过程事件实时推给前端
_PROGRESS_LOCAL = threading.local()


def set_progress_emitter(fn):
    _PROGRESS_LOCAL.emit = fn


def clear_progress_emitter():
    _PROGRESS_LOCAL.emit = None


def emit_progress(event: Dict[str, Any]):
    """执行器内部上报过程事件；无 emitter（非 ReAct 路径）时静默忽略。"""
    fn = getattr(_PROGRESS_LOCAL, "emit", None)
    if fn:
        try:
            fn(event)
        except Exception:
            pass


def register_sub_agent_cancel() -> str:
    """创建并注册一个子 Agent 取消事件，返回 cancel_token。"""
    token = uuid.uuid4().hex
    with _SUB_AGENT_CANCEL_LOCK:
        _SUB_AGENT_CANCEL_EVENTS[token] = threading.Event()
    return token


def cancel_sub_agent(token: str) -> bool:
    ev = _SUB_AGENT_CANCEL_EVENTS.pop(token, None)
    if ev:
        ev.set()
        return True
    return False


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: Dict[str, Any]
    executor: Callable[..., str]
    risk: str = "low"              # low / medium / high
    legacy_marker: str = ""        # 对应的旧标记（用于双轨过渡期的兼容提示）
    # HITL：medium 首次需确认；high 必须确认且仅管理员
    hitl_required: bool = False


# ---------- 工具执行器（复用 chat_service / 各 service）----------

def _exec_run_python_script(user_id: int, args: Dict[str, Any]) -> str:
    task = args.get("task", "") or args.get("code", "")
    if not task:
        return "失败：缺少 task 参数"
    from lobster_mu import script_service
    try:
        def _status(payload):
            """脚本执行/依赖安装过程上报：字符串转状态行，dict 直接透传（含 pip 明细）。"""
            if isinstance(payload, dict):
                emit_progress(payload)
                return
            msg = str(payload)
            ev = {"stage": "executing", "text": msg[:300]}
            if "📦" in msg or "安装" in msg:
                ev["stage"] = "install"
                if msg.startswith("✅"):
                    ev["success"] = True
                elif msg.startswith("❌") or "失败" in msg:
                    ev["success"] = False
            emit_progress(ev)

        emit_progress({"stage": "generating", "text": "正在让模型编写脚本…"})
        code, name, desc = script_service.generate_script_code(task)
        if not code:
            emit_progress({"stage": "error", "text": "脚本生成失败：未获得有效代码"})
            return "脚本生成失败：未获得有效代码"
        # 把生成的脚本推给前端展示（截断保护，完整代码已在产物文件中）
        emit_progress({
            "stage": "script",
            "name": name,
            "desc": desc,
            "code": code[:6000],
            "truncated": len(code) > 6000,
        })
        syntax = script_service.check_script_syntax(code)
        if not syntax.get("success"):
            emit_progress({"stage": "error", "text": f"语法错误：{syntax.get('error', '未知错误')[:200]}"})
            return f"脚本生成失败：语法错误 - {syntax.get('error', '未知错误')}"
        script_service.save_script_to_file(user_id, name, code)
        script_service.create_script(user_id, name, code, description=desc, is_approved=True)

        max_fix_rounds = 2
        gen_files = []
        for attempt in range(max_fix_rounds + 1):
            emit_progress({"stage": "executing", "text": f"正在沙箱中执行《{name}》…" if attempt == 0 else f"执行修复后的脚本（第 {attempt} 次）…"})
            res = script_service.execute_python_script(user_id, code, status_cb=_status)
            out = (res.get("result") or res.get("output") or "")[:8000]
            err = (res.get("error") or "")[:2000]
            ok = bool(res.get("success", True))
            gen_files = res.get("generated_files") or []

            if ok or attempt >= max_fix_rounds:
                emit_progress({
                    "stage": "output",
                    "success": ok,
                    "output": out[:4000],
                    "error": err,
                    "files": gen_files,
                })
                break

            # 执行失败：把报错回喂模型修复脚本，重试
            emit_progress({
                "stage": "fixing",
                "text": f"执行出错，正在让模型修复脚本（第 {attempt + 1}/{max_fix_rounds} 次）…",
                "error": err[:1000],
            })
            fixed = script_service.fix_script_code(code, err or out[-2000:], task)
            if not fixed or fixed == code:
                emit_progress({"stage": "output", "success": False, "output": out[:4000], "error": err})
                break
            syntax = script_service.check_script_syntax(fixed)
            if not syntax.get("success"):
                emit_progress({"stage": "output", "success": False, "output": out[:4000], "error": err})
                break
            code = fixed
            emit_progress({
                "stage": "script",
                "name": name,
                "desc": f"修复后的版本（第 {attempt + 1} 次修复）",
                "code": code[:6000],
                "truncated": len(code) > 6000,
            })
            script_service.save_script_to_file(user_id, name, code)

        result_text = f"脚本《{name}》执行结果（成功: {res.get('success', True)}）：\n{out}\n{err}".strip()
        # 把产物文件的真实下载链接回喂给模型，避免最终回答里只出现干巴巴的文件名
        if gen_files:
            link_lines = ["", "【生成的文件】（请原样保留下面这些链接，方便用户直接点击打开/下载）"]
            for f in gen_files:
                link_lines.append(f"- [{f.get('original_name') or f.get('name')}]({f.get('download_url')})")
            result_text = result_text + "\n" + "\n".join(link_lines)
        return result_text
    except Exception as e:
        emit_progress({"stage": "error", "text": f"脚本执行失败：{str(e)[:300]}"})
        return f"脚本执行失败：{str(e)[:500]}"


def _exec_delegate_agent(user_id: int, args: Dict[str, Any]) -> str:
    agent_name = args.get("agent", "")
    task = args.get("task", "")
    if not agent_name or not task:
        return "失败：缺少 agent 或 task 参数"
    from lobster_mu import agent_store
    from lobster_mu.chat_service import _execute_sub_agent
    agents = agent_store.list_agents(user_id)
    target = next((a for a in agents if a.get("name") == agent_name), None)
    if not target:
        return f"失败：未找到名为 {agent_name} 的 Agent"
    # 注册可取消事件（若需取消可通过 cancel_sub_agent(token) 触发）
    cancel_token = register_sub_agent_cancel()
    cancel_event = _SUB_AGENT_CANCEL_EVENTS.get(cancel_token)
    try:
        res = _execute_sub_agent(user_id, target, task, cancel_event=cancel_event)
    finally:
        _SUB_AGENT_CANCEL_EVENTS.pop(cancel_token, None)
    if not res.get("success"):
        return f"子Agent {agent_name} 执行失败：{res.get('error', '')}"
    suffix = "\n（已被用户取消，返回部分结果）" if res.get("cancelled") else ""
    return (res.get("result") or "")[:8000] + suffix


def _exec_call_mcp_tool(user_id: int, args: Dict[str, Any]) -> str:
    server = args.get("server", "")
    tool = args.get("tool", "")
    arguments = args.get("arguments", {}) or {}
    if not server or not tool:
        return "失败：缺少 server 或 tool 参数"
    from lobster_mu import mcp_client
    res = mcp_client.call_tool(user_id, server, tool, arguments)
    if res.get("success"):
        return (res.get("result") or "")[:20000]
    return f"MCP 调用失败：{res.get('error', '未知错误')}"


def _exec_run_skill(user_id: int, args: Dict[str, Any]) -> str:
    skill_id = args.get("skill_id", "")
    params = args.get("params", {}) or {}
    if not skill_id:
        return "失败：缺少 skill_id 参数"
    from lobster_mu import skill_store
    obj = skill_store.resolve(user_id, skill_id)
    if not obj:
        return f"失败：未找到技能 {skill_id}"
    try:
        result = skill_store.execute(user_id, skill_id, params)
        if isinstance(result, dict):
            return (result.get("output") or result.get("result") or str(result))[:20000]
        return str(result)[:20000]
    except Exception as e:
        return f"技能执行失败：{str(e)[:500]}"


def _exec_generate_ppt(user_id: int, args: Dict[str, Any]) -> str:
    topic = args.get("topic") or args.get("title", "")
    if not topic:
        return "失败：缺少 topic 参数"
    from lobster_mu import ppt_service
    try:
        result = ppt_service.generate_ppt(topic)
        if result.get("success"):
            return f"PPT 已生成：{result.get('filename', '')}，下载地址：{result.get('download_url', '')}"
        return f"PPT 生成失败：{result.get('error', '')}"
    except Exception as e:
        return f"PPT 生成失败：{str(e)[:500]}"


def _exec_web_search(user_id: int, args: Dict[str, Any]) -> str:
    query = args.get("query", "")
    if not query:
        return "失败：缺少 query 参数"
    try:
        import concurrent.futures as cf
        from search.search_manager import SearchManager
        sm = SearchManager()
        pool = cf.ThreadPoolExecutor(max_workers=1)
        fut = pool.submit(sm.search_sync, query, None, 5)
        results = fut.result(timeout=15)
        pool.shutdown(wait=False)
        if not results:
            return "未搜索到有效结果"
        lines = []
        for i, r in enumerate(results, 1):
            title = getattr(r, "title", "")
            url = getattr(r, "url", "")
            snippet = getattr(r, "snippet", "")[:300]
            if not url and not snippet:
                continue
            lines.append(f"[{i}] {title}\n摘要: {snippet}\n来源: {url}")
        return "\n\n".join(lines) if lines else "未搜索到有效结果"
    except Exception as e:
        return f"搜索失败：{str(e)[:200]}"


def _exec_update_plan(user_id: int, args: Dict[str, Any]) -> str:
    """更新计划并持久化到 mu_agent_plans；返回简要确认文本。"""
    import json
    from datetime import datetime
    from lobster_mu.db import get_conn

    title = args.get("title", "执行计划")
    steps = args.get("steps") or []
    if not isinstance(steps, list):
        steps = [str(steps)]
    steps_str = json.dumps(steps, ensure_ascii=False)
    try:
        conn = get_conn()
        now = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO mu_agent_plans (user_id, agent_id, title, steps, status, created_at, updated_at) "
            "VALUES (?, 0, ?, ?, 'active', ?, ?)",
            (user_id, title, steps_str, now, now),
        )
        conn.commit()
    except Exception as e:
        return f"计划保存失败：{str(e)[:100]}"
    return f"计划已更新：共 {len(steps)} 步"


# ---------- 风险判定 ----------

# MCP 工具名里的破坏性动词：命中即视为高风险（仍需用户确认）
_MCP_HIGH_RISK_WORDS = {
    "delete", "remove", "drop", "truncate", "destroy", "update", "edit", "create",
    "insert", "add", "write", "upload", "send", "post", "put", "patch", "move",
    "rename", "execute", "exec", "run", "approve", "grant", "revoke", "pay",
    "transfer", "cancel", "close", "merge", "commit", "reset", "restart", "kill",
}


def classify_mcp_tool_risk(tool_name: str) -> str:
    """按 MCP 工具名判定风险：含破坏性动作 → high（需确认）；查询/读取类 → low（直接执行）。"""
    tokens = set(re.split(r"[_\-. ]+", (tool_name or "").lower()))
    return "high" if tokens & _MCP_HIGH_RISK_WORDS else "low"


# ---------- 注册表 ----------

TOOL_REGISTRY: Dict[str, ToolSpec] = {
    "run_python_script": ToolSpec(
        name="run_python_script",
        description="当用户需要计算、数据处理、文件操作、系统检查或生成PDF时，生成并执行 Python 脚本完成任务",
        schema={"type": "object", "properties": {
            "task": {"type": "string", "description": "要完成的具体任务描述（会基于此自动生成脚本）"},
            "code": {"type": "string", "description": "可选：若已写好代码可直接提供"},
        }, "required": ["task"]},
        executor=_exec_run_python_script,
        risk="medium",
        legacy_marker="[NEED_SCRIPT]",
    ),
    "delegate_agent": ToolSpec(
        name="delegate_agent",
        description="把可拆分的子任务分派给专属 Agent 协作完成（如写作、翻译、代码审查、数据分析）",
        schema={"type": "object", "properties": {
            "agent": {"type": "string", "description": "目标 Agent 的名称，必须是可用列表中的名称"},
            "task": {"type": "string", "description": "交给该 Agent 的具体任务描述，包含必要上下文"},
        }, "required": ["agent", "task"]},
        executor=_exec_delegate_agent,
        risk="low",
        legacy_marker="[AGENT_CALL]",
    ),
    "call_mcp_tool": ToolSpec(
        name="call_mcp_tool",
        description="调用已配置的 MCP 外部工具获取数据或执行操作",
        schema={"type": "object", "properties": {
            "server": {"type": "string"},
            "tool": {"type": "string"},
            "arguments": {"type": "object", "description": "工具所需的参数"},
        }, "required": ["server", "tool"]},
        executor=_exec_call_mcp_tool,
        risk="high",
        hitl_required=True,
        legacy_marker="[MCP_CALL]",
    ),
    "run_skill": ToolSpec(
        name="run_skill",
        description="执行用户已配置的技能（多步骤自动化能力）",
        schema={"type": "object", "properties": {
            "skill_id": {"type": "string"},
            "params": {"type": "object", "description": "技能参数"},
        }, "required": ["skill_id"]},
        executor=_exec_run_skill,
        risk="medium",
        legacy_marker="[SKILL_CALL]",
    ),
    "generate_ppt": ToolSpec(
        name="generate_ppt",
        description="根据主题生成 PPT 文件并提供下载链接",
        schema={"type": "object", "properties": {
            "topic": {"type": "string", "description": "PPT 主题"},
        }, "required": ["topic"]},
        executor=_exec_generate_ppt,
        risk="low",
        legacy_marker="[PPT_GEN]",
    ),
    "web_search": ToolSpec(
        name="web_search",
        description="联网搜索获取最新信息，结果会附带来源 URL",
        schema={"type": "object", "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
        }, "required": ["query"]},
        executor=_exec_web_search,
        risk="low",
        legacy_marker="[WEB_SEARCH]",
    ),
    "update_plan": ToolSpec(
        name="update_plan",
        description="更新当前任务的执行计划（步骤列表），供前端展示步骤条。参数 steps 为字符串数组。",
        schema={"type": "object", "properties": {
            "title": {"type": "string", "description": "计划标题"},
            "steps": {"type": "array", "items": {"type": "string"}, "description": "步骤描述列表"},
        }, "required": ["steps"]},
        executor=_exec_update_plan,
        risk="low",
    ),
}


def get_tool_schema_list() -> List[Dict[str, Any]]:
    """把注册表转为 OpenAI function calling 需要的 tools 列表"""
    out = []
    for spec in TOOL_REGISTRY.values():
        out.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.schema,
            },
        })
    return out
