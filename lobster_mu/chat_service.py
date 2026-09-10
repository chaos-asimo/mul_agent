# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 流式聊天核心（复制改造自 lobster_claw.chat_stream，会话/记忆/工具/脚本均按 user_id 隔离）"""
import json
import re
import threading
from collections import defaultdict
from datetime import datetime
from typing import Optional, Dict, List, Any

from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from lobster_mu import session_store, memory_store, tools, script_service
from lobster_mu.security import PBKDF2_ITERATIONS  # noqa: F401 (保持包依赖清晰)
from lobster_mu.db import get_conn

# 复用原版纯函数（无用户态，只读）
from web.routes.lobster_claw import (
    detect_tool_intent,
    detect_generation_type,
    extract_important_facts,
)

MAX_CHAT_HISTORY = session_store.MAX_CHAT_HISTORY

MCP_CALL_PATTERN = re.compile(r"\[MCP_CALL\](.*?)\[/MCP_CALL\]", re.DOTALL)
WEB_SEARCH_PATTERN = re.compile(r"\[WEB_SEARCH\](.*?)\[/WEB_SEARCH\]", re.DOTALL)
AGENT_CALL_PATTERN = re.compile(r"\[AGENT_CALL\](.*?)\[/AGENT_CALL\]", re.DOTALL)
PPT_GEN_PATTERN = re.compile(r"\[PPT_GEN\](.*?)\[/PPT_GEN\]", re.DOTALL)


def _build_ppt_prompt_block(ppt_intent: bool) -> str:
    """构造 PPT 生成能力提示词段落。仅当检测到 PPT 意图时注入。"""
    if not ppt_intent:
        return ""
    return (
        "\n\n【PPT 生成能力 - 重要】用户希望制作 PPT 演示文稿，你必须直接输出一个大纲标记块来生成真实可下载的 PPT 文件。"
        "\n正确做法：直接输出下面这个标记块（独占一段，前后不要有其他解释文字）："
        '\n[PPT_GEN]{"title":"演示标题","subtitle":"副标题","theme":"blue","slides":[{"heading":"页标题","layout":"bullets","bullets":["要点1","要点2"],"note":"演讲备注"},{"heading":"数据页","layout":"text_chart","bullets":["结论1","结论2"],"chart":{"type":"bar","title":"销量对比","categories":["Q1","Q2","Q3"],"series":[{"name":"2026","values":[120,180,240]}]}}]}[/PPT_GEN]'
        "\n规则："
        "\n- theme 可选 blue（商务蓝，默认）/ orange（活力橙）/ gray（简约灰），根据用户指定的风格选择"
        "\n- slides 为内容页，5~15 页；每页 bullets 3~6 条，每条不超过 40 字；note 为演讲备注（可选）"
        "\n- layout 三种版式：bullets（纯要点，默认）/ chart（整页图表）/ text_chart（左侧要点+右侧图表，图文混排）"
        "\n- 涉及数据对比、占比、趋势的页面必须使用图表版式（chart 或 text_chart），并给出合理估算数据；chart.type 可选 bar（柱状）/ line（折线）/ pie（饼图）"
        "\n- chart 字段：type 必填；categories 为分类标签（≤8个）；series 为数据系列（≤3个），values 为数值数组且长度与 categories 一致"
        "\n- 一份 PPT 中至少 2 页使用图表版式，纯文字与图表页交替出现，避免全是 bullets"
        "\n- 不要生成封面页和目录页：封面由 title/subtitle 自动生成"
        "\n- JSON 必须合法，内容要紧扣用户主题、结构清晰"
        "\n- 特别注意：layout 的值只能是字符串 bullets/chart/text_chart，bullets 是独立的数组键，严禁写成 \"layout\":\"bullets\":[...] 这种合并形式"
        "\n- 严禁输出 [NEED_SCRIPT] 标记，不要编写脚本，系统收到标记后会自动渲染 PPT 并提供下载"
        "\n- 标记块之外只保留极简说明（如「已为你生成 PPT 大纲，正在渲染...」），不要输出其他内容"
    )


def _parse_ppt_gen(text: str) -> Optional[str]:
    """提取 [PPT_GEN] 标记内原始 JSON 字符串；无匹配返回 None。
    容错：闭合标记缺失（输出被截断）时取 [PPT_GEN] 到文本末尾。"""
    m = PPT_GEN_PATTERN.search(text or "")
    if m:
        return m.group(1).strip()
    if not text or "[PPT_GEN]" not in text:
        return None
    tail = text.split("[PPT_GEN]", 1)[1].strip()
    return tail or None


def _build_web_search_prompt_block(search_enabled: bool) -> str:
    """构造联网搜索能力提示词段落。仅当存在启用的搜索引擎时返回非空。"""
    if not search_enabled:
        return ""
    return (
        "\n\n【联网搜索能力 - 重要】你已接入互联网，可以搜索最新信息。"
        "\n只要用户询问以下任何内容，你必须立刻输出搜索标记，不得先用文字解释："
        "\n- 今天/最近/最新的新闻、天气、数据、事件、价格、赛果"
        "\n- 你不确定或可能过时的任何信息"
        "\n正确做法：直接输出下面这一行（独占一行，前后不要有任何其他文字）："
        "\n[WEB_SEARCH]搜索关键词[/WEB_SEARCH]"
        "\n关键词示例：「今日科技新闻」「北京天气」「最新AI进展」"
        "\n系统收到标记后会自动搜索并把结果发给你，你再基于结果回答。"
        "\n最终回答必须引用来源（标题和URL），不要保留标记。"
        "\n严禁说「我无法联网」「我没有实时数据」「我的知识截止」——这类话一律禁止，必须用搜索代替。"
        "\n只有纯常识/数学/编程/确定的历史问题才直接回答不搜索。"
    )


def _parse_web_search(text: str) -> str:
    """从模型回复中提取 [WEB_SEARCH] 查询关键词，返回第一个匹配；无匹配返回空字符串。"""
    m = WEB_SEARCH_PATTERN.search(text or "")
    if not m:
        return ""
    return m.group(1).strip()[:100]


class _MarkerFilter:
    """流式输出时实时剔除指定标记块（通用版，供 MCP/联网搜索/Agent 编排复用）。
    跨 chunk 安全：末尾疑似标记前缀的片段会保留到下一个 chunk 拼接判断。"""

    def __init__(self, marker_start: str, marker_end: str):
        self.MARKER_START = marker_start
        self.MARKER_END = marker_end
        self._open_hint = marker_start[:4]
        self.buf = ""
        self.in_marker = False

    def _hold_partial_tag(self, tag: str) -> None:
        hold = ""
        max_len = min(len(self.buf), len(tag) - 1)
        for length in range(max_len, 0, -1):
            suffix = self.buf[-length:]
            if tag.startswith(suffix):
                hold = suffix
                break
        self.buf = hold

    def _emit_hold_partial(self) -> str:
        before = self.buf
        self._hold_partial_tag(self.MARKER_START)
        return before[: len(before) - len(self.buf)] if self.buf else before

    def feed(self, text: str) -> str:
        self.buf += text
        out = []
        while self.buf:
            if self.in_marker:
                end = self.buf.find(self.MARKER_END)
                if end == -1:
                    self._hold_partial_tag(self.MARKER_END)
                    break
                self.buf = self.buf[end + len(self.MARKER_END):]
                self.in_marker = False
            else:
                start = self.buf.find(self.MARKER_START)
                if start == -1:
                    out.append(self._emit_hold_partial())
                    break
                out.append(self.buf[:start])
                self.buf = self.buf[start + len(self.MARKER_START):]
                self.in_marker = True
        return "".join(out)

    def flush(self) -> str:
        if self.in_marker or self.buf.lstrip().startswith(self._open_hint):
            self.buf = ""
            return ""
        out = self.buf
        self.buf = ""
        return out


def _WebSearchMarkerFilter() -> _MarkerFilter:
    return _MarkerFilter("[WEB_SEARCH]", "[/WEB_SEARCH]")


def _McpMarkerFilter() -> _MarkerFilter:
    """首轮流式输出时实时剔除 [MCP_CALL]...[/MCP_CALL] 块，
    使原始 JSON 标记不推送到前端（调用进度由后端单独推送）。"""
    return _MarkerFilter("[MCP_CALL]", "[/MCP_CALL]")


def _AgentMarkerFilter() -> _MarkerFilter:
    return _MarkerFilter("[AGENT_CALL]", "[/AGENT_CALL]")


def _build_mcp_prompt_block(mcp_tools: List[Dict[str, Any]]) -> str:
    """把启用的 MCP 工具清单构造为系统提示词段落"""
    if not mcp_tools:
        return ""
    lines = [
        "\n\n你可以调用以下 MCP 外部工具来完成任务。需要使用工具时，在回复中输出标记块（可一次输出多个，每个独占一行）：",
        '[MCP_CALL]{"server":"<server名>","tool":"<工具名>","arguments":{<参数JSON>}}[/MCP_CALL]',
        "规则：",
        "- arguments 必须是合法 JSON，且符合对应工具的参数说明",
        "- 只能使用下面列出的工具，不要编造工具名或 server 名",
        "- 工具调用结果由系统自动回传，你再基于结果给出最终回答；最终回复中不要保留 [MCP_CALL] 标记块",
        "- 【优先级】当任务能被下列某个 MCP 工具完成时，必须优先使用 [MCP_CALL] 调用该工具，不要改用 [NEED_SCRIPT] 编写脚本；只有当没有任何 MCP 工具能完成任务时，才考虑用脚本或其他方式",
        "",
        "可用 MCP 工具：",
    ]
    for t in mcp_tools:
        desc = (t.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:120] + "..."
        schema = t.get("input_schema") or {}
        props = schema.get("properties") if isinstance(schema, dict) else None
        args_hint = ""
        if isinstance(props, dict) and props:
            required = set(schema.get("required", []) or [])
            parts = []
            for pname, pdef in list(props.items())[:8]:
                ptype = pdef.get("type", "any") if isinstance(pdef, dict) else "any"
                parts.append(f"{pname}({ptype}{'*' if pname in required else ''})")
            args_hint = " 参数: " + ", ".join(parts)
        lines.append(f"- [server: {t['server']}] 工具: {t['name']} — {desc}{args_hint}")
    return "\n".join(lines)


def _parse_mcp_calls(text: str) -> List[Dict[str, Any]]:
    """从模型回复中解析 [MCP_CALL] 标记块，返回 [{server, tool, arguments, raw_ok}]"""
    calls = []
    for m in MCP_CALL_PATTERN.finditer(text or ""):
        payload = m.group(1).strip()
        try:
            obj = json.loads(payload)
            calls.append({
                "server": str(obj.get("server", "")),
                "tool": str(obj.get("tool", "")),
                "arguments": obj.get("arguments") or {},
                "raw_ok": True,
            })
        except Exception:
            calls.append({"server": "", "tool": "", "arguments": {}, "raw_ok": False, "raw": payload[:200]})
    return calls


def _build_agent_prompt_block(agents: List[Dict[str, Any]]) -> str:
    """把用户可用的 Agent 清单构造为系统提示词段落（多Agent编排）"""
    if not agents:
        return ""
    lines = [
        "\n\n【多Agent编排能力】你可以将子任务分派给以下专属 Agent 协作完成。",
        "需要分派时，在回复中输出标记块（可一次分派多个，每个独占一行）：",
        '[AGENT_CALL]{"agent":"<Agent名称>","task":"<交给该Agent的具体任务描述>"}[/AGENT_CALL]',
        "规则：",
        "- agent 必须是下面列出的 Agent 名称，不要编造",
        "- task 要具体明确，包含完成任务所需的全部上下文信息",
        "- 子Agent执行结果由系统自动回传，你再整合各结果给出最终回答；最终回复中不要保留 [AGENT_CALL] 标记块",
        "- 适合分派的场景：任务可拆分为不同专业角色的独立子任务（如写作、翻译、代码审查、数据分析）",
        "",
        "可用 Agent：",
    ]
    for a in agents:
        role = (a.get("role_description") or "").strip().replace("\n", " ")
        if len(role) > 80:
            role = role[:80] + "..."
        model = a.get("model_name") or "默认模型"
        tone = (a.get("tone") or "").strip()
        avatar = (a.get("avatar") or "🤖").strip() or "🤖"
        caps = a.get("capabilities") or []
        cap_parts = []
        if "web_search" in caps:
            cap_parts.append("可联网搜索")
        if "mcp" in caps:
            cap_parts.append("可调用MCP工具")
        cap_txt = f"，能力: {'/'.join(cap_parts)}" if cap_parts else ""
        tone_part = f"，语气: {tone}" if tone else ""
        lines.append(f"- 名称: {a['name']} — 职责: {role or '通用助手'}{tone_part}{cap_txt}（模型: {model}，头像: {avatar}）")
    return "\n".join(lines)


def _parse_agent_calls(text: str) -> List[Dict[str, Any]]:
    """从模型回复中解析 [AGENT_CALL] 标记块，返回 [{agent, task, raw_ok}]"""
    calls = []
    for m in AGENT_CALL_PATTERN.finditer(text or ""):
        payload = m.group(1).strip()
        try:
            obj = json.loads(payload)
            calls.append({
                "agent": str(obj.get("agent", "")),
                "task": str(obj.get("task", "")),
                "raw_ok": True,
            })
        except Exception:
            calls.append({"agent": "", "task": "", "raw_ok": False, "raw": payload[:200]})
    return calls


AGENT_MEM_PATTERN = re.compile(r"\[AGENT_MEM\](.*?)\[/AGENT_MEM\]", re.DOTALL)
PLAN_UPDATE_PATTERN = re.compile(r"\[PLAN_UPDATE\](.*?)\[/PLAN_UPDATE\]", re.DOTALL)


def _extract_keywords(text: str) -> set:
    """简易中文/英文关键词提取：去停用词后按2-gram+英文单词"""
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text or "")
    words = set(re.findall(r"[a-zA-Z0-9_]{2,}", text))
    cn = re.sub(r"\s+", "", text)
    stop = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一个", "我们", "你", "他们", "这", "那", "请", "任务"}
    for i in range(len(cn) - 1):
        g = cn[i:i + 2]
        if g not in stop:
            words.add(g)
    return words


def _rank_memories(mems: List[Dict[str, Any]], task: str, top_n: int = 5) -> List[Dict[str, Any]]:
    """按与任务的关键词重合度对记忆排序（相关优先，其次新的优先）"""
    if len(mems) <= top_n:
        return mems
    kw = _extract_keywords(task)
    def score(m):
        mkw = _extract_keywords(m.get("content", ""))
        return (len(kw & mkw), m.get("id", 0))
    return sorted(mems, key=score, reverse=True)[:top_n]


def _strip_agent_marks(text: str) -> str:
    """剥除子Agent回复中的 [AGENT_MEM] / [PLAN_UPDATE] 标记块与残留空行"""
    text = AGENT_MEM_PATTERN.sub("", text or "")
    text = PLAN_UPDATE_PATTERN.sub("", text)
    return text.strip()


def _parse_plan_update(text: str) -> Optional[Dict[str, Any]]:
    """解析第一个 [PLAN_UPDATE] 标记 → {title, step}；JSON 失败时退化为整段当 step"""
    m = PLAN_UPDATE_PATTERN.search(text or "")
    if not m:
        return None
    payload = m.group(1).strip()
    try:
        obj = json.loads(payload)
        return {"title": str(obj.get("title", "")), "step": str(obj.get("step", ""))}
    except Exception:
        return {"title": "", "step": payload[:100]}


def _parse_agent_memo(text: str) -> List[str]:
    """解析全部 [AGENT_MEM] 一句话标记"""
    return [m.group(1).strip()[:200] for m in AGENT_MEM_PATTERN.finditer(text or "")
            if m.group(1).strip()]


MAX_SUB_AGENT_TOOL_ROUNDS = 3


def _web_search_available() -> bool:
    try:
        from search.search_manager import SearchManager
        return len(SearchManager().get_enabled()) > 0
    except Exception:
        return False


def _run_web_search_sync(query: str, timeout: int = 15) -> str:
    """同步执行一次联网搜索，返回格式化结果文本；失败/无结果返回空串"""
    import concurrent.futures as _cf
    pool = None
    try:
        from search.search_manager import SearchManager
        sm = SearchManager()
        pool = _cf.ThreadPoolExecutor(max_workers=1)
        fut = pool.submit(sm.search_sync, query, None, 5)
        results = fut.result(timeout=timeout)
        lines = []
        for i, r in enumerate(results or [], 1):
            url = getattr(r, "url", "") or ""
            title = getattr(r, "title", "") or ""
            snippet = (getattr(r, "snippet", "") or "")[:300]
            if not url and any(k in title for k in ("失败", "无可用", "无法", "请在设置")):
                continue
            if url or snippet:
                lines.append(f"[{i}] {title}\n摘要: {snippet}\n来源: {url}")
        return "\n\n".join(lines[:6])
    except Exception as e:
        print(f"[DEBUG] 子Agent联网搜索失败: {e}")
        return ""
    finally:
        if pool:
            pool.shutdown(wait=False, cancel_futures=True)


def _run_mcp_call_sync(user_id: int, call: Dict[str, Any]):
    """同步执行一个 MCP 调用，返回 (ok, 结果文本)"""
    try:
        from lobster_mu import mcp_client
        res = mcp_client.call_tool(user_id, call.get("server", ""), call.get("tool", ""),
                                   call.get("arguments") or {})
        if res.get("success"):
            return True, str(res.get("result") or "")[:4000]
        return False, str(res.get("error") or "未知错误")
    except Exception as e:
        return False, str(e)


def _strip_all_marks(text: str) -> str:
    """剥除子Agent回复中的全部工具/记忆/计划标记"""
    text = AGENT_MEM_PATTERN.sub("", text or "")
    text = PLAN_UPDATE_PATTERN.sub("", text)
    text = MCP_CALL_PATTERN.sub("", text)
    text = WEB_SEARCH_PATTERN.sub("", text)
    return text.strip()


def _execute_sub_agent(user_id: int, agent: Dict[str, Any], task: str) -> Dict[str, Any]:
    """执行子Agent：以其人设作系统提示、绑定模型（未绑定则用默认模型）、
    注入该 Agent 的相关记忆与活跃长期计划，独立完成 LLM 调用并返回结果文本。

    批次3：具备能力（capabilities: web_search / mcp）的子Agent可在最多
    MAX_SUB_AGENT_TOOL_ROUNDS 轮内调用工具，工具结果回注后继续生成；
    执行过程通过 events 返回进度；结束后自动处理 [AGENT_MEM]/[PLAN_UPDATE]。"""
    from lobster_mu import agent_store, plan_store

    adapter = None
    bound = (agent.get("model_name") or "").strip()
    if bound:
        try:
            adapter = get_default_llm_adapter(bound)
        except Exception:
            adapter = None
    if adapter is None:
        adapter = get_default_llm_adapter()
    if adapter is None:
        return {"success": False, "error": "没有可用的LLM模型"}

    events: List[str] = []

    memory_block = ""
    try:
        mems = agent_store.list_memories(user_id, agent["id"]) or []
        if mems:
            mems = _rank_memories(mems, task)
            memory_block = "\n\n🧠 你的历史记忆（供参考）：\n" + "\n".join(
                f"- {m.get('content', '')}" for m in mems
            )
    except Exception:
        memory_block = ""

    plan_block = ""
    try:
        plans = plan_store.active_plans(user_id, agent["id"])
        if plans:
            lines = ["\n\n🎯 你的当前长期计划（完成任务后若达成某步骤，可用标记更新进度）："]
            for p in plans:
                steps_txt = "\n".join(
                    f"  {'✅' if s.get('done') else '⬜'} {s.get('text', '')}"
                    for s in p.get("steps", [])
                ) or "  （无步骤）"
                lines.append(f"- 计划《{p['title']}》：\n{steps_txt}")
            plan_block = "\n".join(lines)
    except Exception:
        plan_block = ""

    # ===== 能力（工具）配置 =====
    caps = agent.get("capabilities") or []
    can_search = "web_search" in caps and _web_search_available()
    can_mcp = "mcp" in caps
    mcp_block = ""
    if can_mcp:
        try:
            from lobster_mu import mcp_client
            mcp_tools = mcp_client.get_enabled_tools(user_id) or []
            if mcp_tools:
                mcp_block = _build_mcp_prompt_block(mcp_tools)
            else:
                can_mcp = False
        except Exception:
            can_mcp = False
    web_block = _build_web_search_prompt_block(can_search)

    role = (agent.get("role_description") or "").strip()
    tone = (agent.get("tone") or "").strip()
    forbidden = ["[AGENT_CALL]", "[NEED_SCRIPT]"]
    if not can_mcp:
        forbidden.append("[MCP_CALL]")
    if not can_search:
        forbidden.append("[WEB_SEARCH]")
    system_prompt = (
        f"你是子Agent「{agent['name']}」，是多Agent协作系统中的一个专职角色。"
        + (f"\n你的职责设定：{role}" if role else "")
        + (f"\n你的表达风格：{tone}，回答要保持这种语气和人设。" if tone else "")
        + "\n请专注于完成分配给你的任务，直接输出任务结果本身，"
        + f"不要输出 {' / '.join(forbidden)} 等任何标记，不要反问用户。"
        + (plan_block + "\n计划进度更新规则：完成任务若达成了某计划的某个步骤，在回答最后单独一行输出：\n"
           '[PLAN_UPDATE]{"title":"计划标题","step":"完成的步骤文本"}[/PLAN_UPDATE]' if plan_block else "")
        + "\n记忆沉淀规则：若本次任务产生了值得长期记住的关键结论、用户偏好或重要事实，"
        "在回答最后单独一行输出：\n[AGENT_MEM]一句话总结[/AGENT_MEM]\n"
        "（以上标记每类最多一行，最终面向用户的正文不要包含任何标记）"
        + web_block + mcp_block
    )
    user_content = f"任务：{task}{memory_block}\n\n请直接完成上述任务并输出结果。"

    try:
        messages = adapter.create_prompt(system_prompt, user_content, [])
        rounds_content: List[str] = []
        final_content = ""
        used_tools = False

        for round_i in range(MAX_SUB_AGENT_TOOL_ROUNDS):
            resp = adapter.chat(messages)
            content = resp.get("content", "") if isinstance(resp, dict) else (getattr(resp, "content", "") or str(resp))
            rounds_content.append(content)

            tool_blocks = []
            if can_search and "[WEB_SEARCH]" in content:
                q = _parse_web_search(content)
                if q:
                    events.append(f"🔍 联网搜索: {q}")
                    res_text = _run_web_search_sync(q)
                    tool_blocks.append("联网搜索结果：\n" + (res_text or "（未获取到有效结果，请基于已有知识回答）"))
            if can_mcp and "[MCP_CALL]" in content:
                for idx, call in enumerate(_parse_mcp_calls(content), 1):
                    if not call.get("raw_ok"):
                        tool_blocks.append(f"[MCP调用 {idx}] 标记格式错误（非合法JSON），已跳过")
                        continue
                    label = f"{call['server']}/{call['tool']}"
                    events.append(f"🔧 调用工具: {label}")
                    ok, txt = _run_mcp_call_sync(user_id, call)
                    tool_blocks.append(f"[MCP工具 {label}] {'结果' if ok else '调用失败'}：\n{txt}")

            if not tool_blocks:
                final_content = content
                break

            used_tools = True
            is_last = round_i == MAX_SUB_AGENT_TOOL_ROUNDS - 1
            followup = (
                "系统已执行你请求的工具调用，结果如下：\n\n"
                + "\n\n".join(tool_blocks)
                + "\n\n请基于上述工具结果继续完成任务。"
                + ("若还需调用工具可继续输出对应标记；否则直接输出最终任务结果（不要保留任何工具标记）。"
                   if not is_last else
                   "工具调用次数已达上限，请直接基于以上所有信息输出最终任务结果，不要再输出任何工具标记。")
            )
            messages = messages + [
                {"role": "assistant", "content": _strip_all_marks(content) or "（已请求工具调用）"},
                {"role": "user", "content": followup},
            ]
            final_content = content
            if is_last:
                # 最后一轮：直接取回收尾回答
                resp2 = adapter.chat(messages)
                c2 = resp2.get("content", "") if isinstance(resp2, dict) else (getattr(resp2, "content", "") or str(resp2))
                rounds_content.append(c2)
                final_content = c2

        # 自动沉淀记忆（跨所有轮次收集，source=auto，去重）
        mems_saved = 0
        try:
            existing = {(m.get("content") or "").strip()
                        for m in (agent_store.list_memories(user_id, agent["id"]) or [])}
            for raw in rounds_content:
                for memo in _parse_agent_memo(raw):
                    if memo not in existing:
                        agent_store.add_memory(user_id, agent["id"], memo, source="auto")
                        existing.add(memo)
                        mems_saved += 1
        except Exception as _e:
            print(f"[DEBUG] 子Agent记忆沉淀失败: {_e}")

        # 更新长期计划进度（跨所有轮次，取第一个有效标记）
        plan_updated = ""
        try:
            for raw in rounds_content:
                pu = _parse_plan_update(raw)
                if pu:
                    done = plan_store.mark_step_done(user_id, agent["id"], pu["title"], pu["step"])
                    if done:
                        plan_updated = f"《{done['title']}》步骤「{pu['step']}」已完成"
                        break
        except Exception as _e:
            print(f"[DEBUG] 计划进度更新失败: {_e}")

        return {"success": True, "result": _strip_all_marks(final_content),
                "mems_saved": mems_saved, "plan_updated": plan_updated,
                "events": events, "used_tools": used_tools}
    except Exception as e:
        return {"success": False, "error": str(e)}


class ChatMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatStreamRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    model_name: Optional[str] = None
    files: Optional[List[Dict[str, Any]]] = None
    images: Optional[List[Dict[str, Any]]] = None


# 每用户 SSE 并发信号量（2）
_sse_semaphores: Dict[int, threading.BoundedSemaphore] = {}
_sem_lock = threading.Lock()


def _sem(user_id: int) -> threading.BoundedSemaphore:
    with _sem_lock:
        if user_id not in _sse_semaphores:
            _sse_semaphores[user_id] = threading.BoundedSemaphore(2)
        return _sse_semaphores[user_id]


def get_default_llm_adapter(model_name: Optional[str] = None):
    try:
        from engine.agent_worker import create_llm_adapter
        from models.model_manager import ModelManager

        model_manager = ModelManager()
        configured_models = [m for m in model_manager.get_all() if m.api_key and m.model_type == "text"]
        if not configured_models:
            return None
        if model_name:
            model = next((m for m in configured_models if m.model_name == model_name), None)
            if model:
                return create_llm_adapter(model)
        return create_llm_adapter(configured_models[0])
    except Exception:
        return None


def get_image_models():
    try:
        from models.model_manager import ModelManager
        model_manager = ModelManager()
        return [m for m in model_manager.get_all() if m.api_key and m.enabled and m.model_type == "image"]
    except Exception:
        return []


def get_video_models():
    try:
        from models.model_manager import ModelManager
        model_manager = ModelManager()
        return [m for m in model_manager.get_all() if m.api_key and m.enabled and m.model_type == "video"]
    except Exception:
        return []


def get_chat_models() -> dict:
    try:
        from models.model_manager import ModelManager
        model_manager = ModelManager()
        configured_models = [m for m in model_manager.get_all() if m.api_key and m.enabled and m.model_type == "text"]
        return {
            "success": True,
            "models": [{"name": m.model_name, "provider": m.api_type, "model_id": m.name} for m in configured_models],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_environment_block() -> str:
    try:
        from web.routes.lobster_claw import get_environment_snapshot, format_environment_for_prompt
        env_aware_text = format_environment_for_prompt(get_environment_snapshot())
    except Exception:
        env_aware_text = ""
    return "\n\n" + env_aware_text + "\n" if env_aware_text else ""


def _knowledge_context(user_id: int, message: str) -> str:
    """知识库检索（user_id 过滤）；接入向量检索，任何失败都返回空串保持聊天流不中断"""
    try:
        from lobster_mu import knowledge_store
        results = knowledge_store.search(user_id, message, top_k=3, threshold=0.3)
        if not results:
            return ""
        context = "\n\n📖 以下是与当前问题相关的知识库内容，请参考这些信息回答：\n"
        for i, r in enumerate(results, 1):
            context += f"{i}. [{r.get('filename', '未知文档')}] (相关度 {r.get('score', 0):.2f})\n{r.get('content', '')}\n"
        return context
    except Exception:
        return ""


def _warmup_knowledge() -> None:
    """后台预热知识库 embedding 模型（失败静默，不影响聊天流）"""
    try:
        from lobster_mu import knowledge_store
        knowledge_store.warmup()
    except Exception:
        pass


def chat_stream_response(user_id: int, request: ChatStreamRequest) -> StreamingResponse:
    """多用户流式聊天入口"""
    session_id = session_store.get_or_create_session(user_id, request.session_id)

    # 构建包含文件信息的消息内容
    full_message = request.message
    has_images = bool(request.images)
    if has_images:
        print(f"[DEBUG] mu收到 {len(request.images)} 张图片 (user {user_id})")
        for i, img in enumerate(request.images):
            url = img.get('data_url', '') if isinstance(img, dict) else ''
            print(f"[DEBUG] mu图片 {i + 1}: {img.get('name', '未知')}, data_url长度: {len(url)}")
    if request.files:
        print(f"[DEBUG] mu收到 {len(request.files)} 个文件 (user {user_id})")
        file_info = []
        for i, file_item in enumerate(request.files):
            filename = file_item.get('filename', '')
            content = file_item.get('content', '')
            print(f"[DEBUG] mu文件 {i + 1}: {filename}, 内容长度: {len(content) if content else 0}")
            if filename:
                if content:
                    file_info.append(f"\n📄 文件: {filename}\n```\n{content}\n```")
                else:
                    file_info.append(f"\n📄 文件: {filename} (已上传但无法提取内容)")
        if file_info:
            full_message = request.message + "\n\n" + "".join(file_info)

    if has_images:
        img_count = len(request.images)
        full_message = full_message + f"\n\n🖼️ 附带 {img_count} 张图片"

    session_store.append_message(user_id, session_id, "user", full_message)
    generation_type = detect_generation_type(request.message)
    # PPT 意图：纯文本对话才生效（文件/图片消息不触发），走文本分支 + [PPT_GEN] 标记机制
    ppt_intent = generation_type == "ppt" and not request.files and not has_images

    # ============ 图片生成分支 ============
    if generation_type == "image":
        image_models = get_image_models()
        if not image_models:
            def error_generator():
                yield f"data: {json.dumps({'success': False, 'error': '未配置文生图模型，请先在模型配置中添加文生图模型'})}\n\n"
            return StreamingResponse(error_generator(), media_type="text/event-stream")

        def image_generator():
            try:
                from engine.agent_worker import create_image_adapter

                yield f"data: {json.dumps({'success': True, 'content': '🎨 正在调用文生图模型生成图片...', 'session_id': session_id})}\n\n"
                model = image_models[0]
                adapter = create_image_adapter(model)
                prompt = request.message
                for keyword in ["画图", "画画", "绘图", "绘制", "生成图片", "图片生成", "生成图像", "图像生成", "生成图", "画一张", "画个"]:
                    prompt = prompt.replace(keyword, "").strip()
                response = adapter.generate(prompt=prompt, n=1, size="1024x1024")
                if response.success:
                    image_url = response.image_url
                    image_data = response.image_data.decode('utf-8') if response.image_data else None
                    if image_url:
                        content = f"🖼️ 图片生成成功！\n\n![生成的图片]({image_url})"
                    elif image_data:
                        content = f"🖼️ 图片生成成功！\n\n![生成的图片](data:image/png;base64,{image_data})"
                    else:
                        content = "🖼️ 图片生成成功，但无法获取图片数据"
                    session_store.append_message(user_id, session_id, "assistant", content)
                    yield f"data: {json.dumps({'success': True, 'content': content, 'session_id': session_id})}\n\n"
                else:
                    error_msg = f"❌ 图片生成失败: {response.error}"
                    session_store.append_message(user_id, session_id, "assistant", error_msg)
                    yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"
                yield f"data: {json.dumps({'success': True, 'content': '', 'session_id': session_id, 'done': True})}\n\n"
            except Exception as e:
                error_msg = f"❌ 图片生成异常: {str(e)}"
                session_store.append_message(user_id, session_id, "assistant", error_msg)
                yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"

        return StreamingResponse(image_generator(), media_type="text/event-stream")

    # ============ 视频生成分支 ============
    if generation_type == "video":
        video_models = get_video_models()
        if not video_models:
            def error_generator():
                yield f"data: {json.dumps({'success': False, 'error': '未配置文生视频模型，请先在模型配置中添加文生视频模型'})}\n\n"
            return StreamingResponse(error_generator(), media_type="text/event-stream")

        def video_generator():
            try:
                from engine.agent_worker import create_video_adapter
                import time

                yield f"data: {json.dumps({'success': True, 'content': '🎬 正在调用文生视频模型生成视频...', 'session_id': session_id})}\n\n"
                model = video_models[0]
                adapter = create_video_adapter(model)
                prompt = request.message
                for keyword in ["生成视频", "视频生成", "画视频", "制作视频", "视频制作", "视频内容"]:
                    prompt = prompt.replace(keyword, "").strip()
                video_data = {
                    "model": model.model_name,
                    "prompt": prompt,
                    "width": 1024, "height": 576, "num_frames": 48, "frame_rate": 8,
                }
                response = adapter.generate(**video_data)
                if response.success and (hasattr(response, 'video_id') or hasattr(response, 'task_id')):
                    video_id = getattr(response, 'video_id', getattr(response, 'task_id', None))
                    yield f"data: {json.dumps({'success': True, 'content': '⏳ 视频生成任务已创建，正在生成中...', 'session_id': session_id})}\n\n"
                    max_wait_time = 300
                    start_time = time.time()
                    while time.time() - start_time < max_wait_time:
                        task_info = adapter.get_status(video_id)
                        if task_info:
                            status = task_info.get("status", "unknown")
                            progress = task_info.get("progress", 0)
                            if status == "completed" and task_info.get("video_url"):
                                content = f"🎬 视频生成成功！\n\n<video src=\"{task_info['video_url']}\" controls style=\"max-width: 100%; border-radius: 8px;\"></video>"
                                session_store.append_message(user_id, session_id, "assistant", content)
                                yield f"data: {json.dumps({'success': True, 'content': content, 'session_id': session_id})}\n\n"
                                break
                            elif status == "failed":
                                error_msg = f"❌ 视频生成失败: {task_info.get('error', '未知错误')}"
                                session_store.append_message(user_id, session_id, "assistant", error_msg)
                                yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"
                                break
                            else:
                                yield f"data: {json.dumps({'success': True, 'content': f'⏳ 视频生成中... {progress}%', 'session_id': session_id})}\n\n"
                        time.sleep(3)
                    else:
                        error_msg = "❌ 视频生成超时，请稍后查询视频状态"
                        session_store.append_message(user_id, session_id, "assistant", error_msg)
                        yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"
                else:
                    error_msg = f"❌ 创建视频生成任务失败: {response.error}"
                    session_store.append_message(user_id, session_id, "assistant", error_msg)
                    yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"
                yield f"data: {json.dumps({'success': True, 'content': '', 'session_id': session_id, 'done': True})}\n\n"
            except Exception as e:
                error_msg = f"❌ 视频生成异常: {str(e)}"
                session_store.append_message(user_id, session_id, "assistant", error_msg)
                yield f"data: {json.dumps({'success': False, 'error': error_msg, 'session_id': session_id})}\n\n"

        return StreamingResponse(video_generator(), media_type="text/event-stream")

    # ============ 文本聊天分支 ============
    adapter = get_default_llm_adapter(request.model_name)
    if not adapter:
        def error_generator():
            yield f"data: {json.dumps({'success': False, 'error': '未找到可用的LLM适配器'})}\n\n"
        return StreamingResponse(error_generator(), media_type="text/event-stream")

    env_block = get_environment_block()
    if request.files:
        system_prompt = """你是龙虾Claw，一个强大的AI智能体助手。你可以帮助用户回答问题、分析信息、提供建议。当提供了工具执行结果时，请基于结果给出详细的解答和说明。

你拥有记忆能力，可以记住用户的偏好、重要事实和历史对话。以下是与当前问题相关的记忆信息，请参考这些信息来回答用户的问题。

重要规则：用户已上传文件，请直接分析文件内容并给出回答，不需要创建脚本。""" + env_block
    elif has_images:
        system_prompt = """你是龙虾Claw，一个强大的AI智能体助手。用户已上传图片，请直接分析图片内容并给出回答，不需要创建脚本。""" + env_block
    else:
        system_prompt = """你是龙虾Claw，一个强大的AI智能体助手。你可以帮助用户回答问题、分析信息、提供建议。当提供了工具执行结果时，请基于结果给出详细的解答和说明。

你拥有记忆能力，可以记住用户的偏好、重要事实和历史对话。以下是与当前问题相关的记忆信息，请参考这些信息来回答用户的问题。

你具备以下特殊能力：
- 生成中文PDF文档：当用户要求生成PDF时，你可以通过编写Python脚本来生成。系统已安装fpdf2库，并且会自动查找系统中文字体（微软雅黑等）来确保中文正确显示。生成的PDF文件会自动保存并提供下载链接。

重要规则：当你发现无法直接通过文字回答完成用户的任务时（例如需要计算、数据处理、文件操作、系统检查、生成PDF等），请在回复开头添加标记 [NEED_SCRIPT]，表示需要创建Python脚本来自动完成任务。系统会自动根据你的回复生成并执行脚本。""" + env_block

    # 有文件或图片上传时跳过工具检测，直接将内容传给大模型
    tool_call = None if (request.files or has_images) else detect_tool_intent(request.message)

    def sync_stream_generator():
        full_response = ""
        tool_result = ""
        token_stats = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        sem = _sem(user_id)
        acquired = sem.acquire(timeout=30)
        # MCP 工具清单 + Agent 编排清单（仅纯文本对话注入；发现失败静默降级）
        mcp_block = ""
        agent_block = ""
        web_search_enabled = False
        web_search_block = ""
        if not request.files and not has_images:
            try:
                from lobster_mu import mcp_client
                mcp_block = _build_mcp_prompt_block(mcp_client.get_enabled_tools(user_id))
            except Exception as _e:
                print(f"[DEBUG] MCP 工具发现失败，跳过注入: {_e}")
                mcp_block = ""
            try:
                from lobster_mu import agent_store
                agent_block = _build_agent_prompt_block(agent_store.list_agents(user_id))
            except Exception as _e:
                print(f"[DEBUG] Agent 清单发现失败，跳过注入: {_e}")
                agent_block = ""
            # 检查是否有启用的搜索引擎
            try:
                from search.search_manager import SearchManager
                _sm = SearchManager()
                web_search_enabled = len(_sm.get_enabled()) > 0
            except Exception as _e:
                print(f"[DEBUG] 搜索引擎检查失败: {_e}")
                web_search_enabled = False
            web_search_block = _build_web_search_prompt_block(web_search_enabled)
        ppt_block = _build_ppt_prompt_block(ppt_intent)
        effective_system_prompt = system_prompt + web_search_block + agent_block + mcp_block + ppt_block
        try:
            if tool_call:
                tool_name = tool_call.get("tool")
                tool_desc = {"exec": "执行命令", "read_file": "读取文件", "list_dir": "列出目录", "search": "网页搜索",
                             "script_create": "创建脚本", "script_execute": "执行脚本", "script_list": "列出脚本",
                             "generate_pdf": "生成PDF"}.get(tool_name, tool_name)
                tool_header = "\n🔧 正在执行工具: " + tool_desc + "...\n\n"
                yield f"data: {json.dumps({'success': True, 'content': tool_header, 'session_id': session_id})}\n\n"
                tool_result = tools.execute_tool_call(tool_call, user_id)
                if tool_result:
                    result_header = "📋 工具执行结果:\n" + tool_result + "\n\n---\n\n"
                    yield f"data: {json.dumps({'success': True, 'content': result_header, 'session_id': session_id})}\n\n"

            # 上下文压缩：近期消息保留原文，更早历史增量压缩为摘要（失败静默降级）
            try:
                from lobster_mu import context_compressor
                context, summary_context = context_compressor.build_context(user_id, session_id, adapter)
            except Exception as _e:
                print(f"[DEBUG] 上下文压缩构建失败，降级为截断窗口: {_e}")
                context = session_store.get_messages(user_id, session_id)[-10:] or []
                summary_context = ""

            # 记忆检索（user_id 隔离）
            memory_context = ""
            keywords = memory_store.extract_keywords(request.message, max_keywords=8)
            if keywords:
                long_term_memories = memory_store.retrieve_by_keywords(user_id, keywords, memory_type='long_term', limit=5)
                short_term_memories = memory_store.retrieve_by_keywords(user_id, keywords, memory_type='short_term', limit=5)
                all_memories = long_term_memories + short_term_memories
                if all_memories:
                    memory_context = "\n\n📚 根据历史对话，以下信息可能对回答有帮助：\n"
                    for i, memory in enumerate(all_memories[:8], 1):
                        mem_type = {"long_term": "长期记忆", "short_term": "短期记忆"}.get(memory['type'], memory['type'])
                        weight_info = f" (权重: {memory.get('weight', 1.0):.1f})" if memory.get('weight') else ""
                        memory_context += f"{i}. [{mem_type}{weight_info}] {memory['content']}\n"

            # 知识库：有文档的用户首次聊天同步预热 embedding 模型（首次数十秒，之后秒级），
            # 保证本轮即可注入知识库上下文与参考来源
            knowledge_sources = []
            try:
                from lobster_mu import knowledge_store as _ks
                if _ks.user_has_docs(user_id) and not _ks.is_model_ready():
                    _ks.warmup_sync()
            except Exception:
                pass
            knowledge_context = _knowledge_context(user_id, request.message)
            if knowledge_context:
                try:
                    knowledge_sources = _ks.search_for_display(user_id, request.message, top_k=3, threshold=0.3)
                except Exception:
                    knowledge_sources = []

            if tool_result:
                user_content = f"""用户问题: {request.message}

我已经为你执行了相关工具，以下是工具执行结果：

{tool_result}

{summary_context}{memory_context}{knowledge_context}

请基于上述工具执行结果、记忆信息和知识库参考，为用户提供详细的分析和解答。
如果你无法直接通过文字完成用户的任务，请在回复开头添加 [NEED_SCRIPT] 标记。"""
            elif has_images:
                img_count = len(request.images)
                user_content = f"""用户问题: {request.message}

用户已上传 {img_count} 张图片，图片已随消息一起发送给你。请直接查看并分析图片内容，基于图片内容回答用户问题。

{summary_context}{memory_context}{knowledge_context}

重要：图片已经附加在本次消息中，请直接分析图片，不要创建脚本，不要添加 [NEED_SCRIPT] 标记。"""
            else:
                if ppt_intent:
                    user_content = f"""用户问题: {request.message}

{summary_context}{memory_context}{knowledge_context}

用户要求制作 PPT。请直接按系统提示中的 [PPT_GEN] 标记格式输出 PPT 大纲，不要输出 [NEED_SCRIPT] 标记，不要编写脚本。"""
                else:
                    user_content = f"""用户问题: {request.message}

{summary_context}{memory_context}{knowledge_context}

请基于上述记忆信息和知识库参考，为用户提供详细的解答。
如果你无法直接通过文字完成用户的任务（例如需要计算、数据处理、文件操作、系统检查等），请在回复开头添加 [NEED_SCRIPT] 标记，系统会自动生成并执行Python脚本来完成任务。"""

            messages = adapter.create_prompt_with_images(system_prompt, user_content, context, request.images) if has_images else adapter.create_prompt(effective_system_prompt, user_content, context)

            mcp_filter = _McpMarkerFilter()
            agent_filter = _AgentMarkerFilter()
            ws_filter = _WebSearchMarkerFilter()
            ppt_filter = _MarkerFilter("[PPT_GEN]", "[/PPT_GEN]")
            if ppt_intent:
                yield "data: " + json.dumps({'success': True, 'content': "📊 正在为您生成 PPT 大纲...\n\n", 'session_id': session_id}) + "\n\n"
            # PPT 大纲 JSON 较长，提高输出上限避免截断（openai 适配器不限制，claude/deepseek 默认2000）
            stream_kwargs = {"max_tokens": 8000} if ppt_intent else {}
            for chunk in adapter.chat_stream(messages, **stream_kwargs):
                if isinstance(chunk, dict):
                    content = chunk.get("content", "")
                    if chunk.get("usage"):
                        token_stats = chunk["usage"]
                else:
                    content = str(chunk)
                # 解析 __stats__ chunk 获取 token 统计
                if content and content.startswith("{\"__stats__"):
                    try:
                        stats = json.loads(content)
                        if stats.get("__stats__"):
                            token_stats = {
                                "prompt_tokens": stats.get("prompt_tokens", 0),
                                "completion_tokens": stats.get("completion_tokens", 0),
                                "total_tokens": stats.get("total_tokens", 0),
                                "tokens_per_second": stats.get("duration", 0) and round(
                                    stats.get("completion_tokens", 0) / stats.get("duration", 1), 1
                                ) or 0.0,
                            }
                    except Exception:
                        pass
                    continue
                if content and not content.startswith("{\"__stats__"):
                    full_response += content
                    # 串联过滤：PPT → AGENT → MCP → WEB_SEARCH
                    safe_content = ws_filter.feed(agent_filter.feed(mcp_filter.feed(ppt_filter.feed(content))))
                    if safe_content:
                        yield f"data: {json.dumps({'success': True, 'content': safe_content, 'session_id': session_id})}\n\n"

            # 首流结束，冲刷过滤器残留
            tail = ws_filter.feed(agent_filter.feed(mcp_filter.feed(ppt_filter.flush()))) + ws_filter.flush()
            if tail:
                yield f"data: {json.dumps({'success': True, 'content': tail, 'session_id': session_id})}\n\n"

            import time
            time.sleep(0.1)

            from llm.model_call_logger import model_call_logger
            recent_logs = model_call_logger.call_logs
            if recent_logs:
                latest_log = recent_logs[-1]
                token_stats = {
                    "prompt_tokens": latest_log.prompt_tokens,
                    "completion_tokens": latest_log.completion_tokens,
                    "total_tokens": latest_log.total_tokens,
                    "tokens_per_second": latest_log.tokens_per_second,
                }

            # 检测是否需要创建脚本（有文件或图片上传时不生成脚本；PPT 意图走 [PPT_GEN] 分支不生成脚本）
            if not request.files and not has_images and "[NEED_SCRIPT]" in full_response and "[PPT_GEN]" not in full_response:
                full_response = full_response.replace("[NEED_SCRIPT]", "").strip()
                script_task = request.message
                yield "data: " + json.dumps({'success': True, 'content': '\n\n🔧 检测到需要编写脚本完成任务，正在生成...\n', 'session_id': session_id}) + "\n\n"

                script_code, script_name, script_desc = script_service.generate_script_code(script_task)
                if script_code:
                    syntax_result = script_service.check_script_syntax(script_code)
                    if syntax_result["success"]:
                        script_service.save_script_to_file(user_id, script_name, script_code)
                        script_service.create_script(user_id, script_name, script_code, description=script_desc, is_approved=True)
                        script_info = '✅ 脚本已生成并保存到脚本库\n📝 脚本: ' + script_name + '（' + script_desc + '）\n\n正在执行...\n'
                        yield "data: " + json.dumps({'success': True, 'content': script_info, 'session_id': session_id}) + "\n\n"

                        exec_result = script_service.execute_python_script(user_id, script_code)
                        exec_result_str = exec_result.get("result", "") if isinstance(exec_result, dict) else str(exec_result)

                        yield "data: " + json.dumps({'success': True, 'content': '📋 执行结果:\n\n', 'session_id': session_id}) + "\n\n"
                        interpret_prompt = '用户问题: ' + request.message + '\n\n我编写并执行了一个Python脚本来完成这个任务。\n\n脚本名称: ' + script_name + '\n脚本描述: ' + script_desc + '\n\n执行结果:\n' + exec_result_str + '\n\n请基于执行结果，为用户提供详细的分析和解答。'
                        interpret_messages = adapter.create_prompt(
                            "你是龙虾Claw，一个强大的AI智能体助手。请基于脚本执行结果为用户提供详细的解读。",
                            interpret_prompt, []
                        )
                        for chunk in adapter.chat_stream(interpret_messages):
                            if isinstance(chunk, dict):
                                content = chunk.get("content", "")
                            else:
                                content = str(chunk)
                            if content and not content.startswith("{\"__stats__\""):
                                yield "data: " + json.dumps({'success': True, 'content': content, 'session_id': session_id}) + "\n\n"
                        full_response = full_response + "\n\n📋 脚本执行结果:\n" + exec_result_str
                    else:
                        error_msg = '❌ 脚本语法错误:\n\n' + syntax_result["error"]
                        yield "data: " + json.dumps({'success': True, 'content': error_msg, 'session_id': session_id}) + "\n\n"
                else:
                    yield "data: " + json.dumps({'success': True, 'content': '❌ 脚本生成失败，请重试', 'session_id': session_id}) + "\n\n"

            # ============ 多Agent编排分支 ============
            if not request.files and not has_images and "[AGENT_CALL]" in full_response:
                from lobster_mu import agent_store
                agent_calls = _parse_agent_calls(full_response)
                # 去除标记块（最终答复以二次生成为准）
                full_response = AGENT_CALL_PATTERN.sub("", full_response).strip()
                agents_list = agent_store.list_agents(user_id)
                agents_by_name = {a["name"]: a for a in agents_list}
                agent_result_blocks = []
                for idx, call in enumerate(agent_calls, 1):
                    if not call.get("raw_ok"):
                        err_msg = f"第 {idx} 个 Agent 调用标记格式错误（不是合法 JSON），已跳过。原始内容: {call.get('raw', '')[:100]}"
                        yield "data: " + json.dumps({'success': True, 'content': f"⚠️ {err_msg}\n\n", 'session_id': session_id}) + "\n\n"
                        agent_result_blocks.append(f"[分派 {idx}] 失败: {err_msg}")
                        continue
                    name = call["agent"].strip()
                    sub = agents_by_name.get(name)
                    if not sub:
                        err_msg = f"Agent「{name}」不存在，已跳过"
                        yield "data: " + json.dumps({'success': True, 'content': f"⚠️ {err_msg}\n\n", 'session_id': session_id}) + "\n\n"
                        agent_result_blocks.append(f"[分派 {idx}] 失败: {err_msg}")
                        continue
                    avatar = (sub.get("avatar") or "🤖").strip() or "🤖"
                    yield "data: " + json.dumps({'success': True, 'content': f"\n{avatar} 正在调用子Agent「{name}」执行任务...\n", 'session_id': session_id}) + "\n\n"
                    sub_res = _execute_sub_agent(user_id, sub, call["task"])
                    if sub_res.get("success"):
                        for ev in (sub_res.get("events") or []):
                            yield "data: " + json.dumps({'success': True, 'content': f"{avatar} {ev}\n", 'session_id': session_id}) + "\n\n"
                        result_text = sub_res.get("result") or "（子Agent未返回内容）"
                        preview = result_text[:300] + ("..." if len(result_text) > 300 else "")
                        yield "data: " + json.dumps({'success': True, 'content': f"{avatar} 子Agent「{name}」已完成：\n{preview}\n\n", 'session_id': session_id}) + "\n\n"
                        extra = []
                        if sub_res.get("plan_updated"):
                            extra.append(f"🎯 {sub_res['plan_updated']}")
                        if sub_res.get("mems_saved"):
                            extra.append(f"🧠 已沉淀 {sub_res['mems_saved']} 条新记忆")
                        if extra:
                            yield "data: " + json.dumps({'success': True, 'content': " | ".join(extra) + "\n\n", 'session_id': session_id}) + "\n\n"
                        agent_result_blocks.append(
                            f"[分派 {idx}] Agent: {name}\n任务: {call['task'][:300]}\n结果:\n{result_text[:4000]}"
                        )
                    else:
                        err = sub_res.get("error") or "未知错误"
                        yield "data: " + json.dumps({'success': True, 'content': f"❌ 子Agent「{name}」执行失败: {err}\n\n", 'session_id': session_id}) + "\n\n"
                        agent_result_blocks.append(f"[分派 {idx}] Agent: {name}\n执行失败: {err}")

                if agent_result_blocks:
                    agent_summary = "\n\n".join(agent_result_blocks)
                    interpret_prompt = (
                        f"用户问题: {request.message}\n\n"
                        f"系统已按你的要求把任务分派给了子Agent，执行结果如下：\n\n{agent_summary}\n\n"
                        "请整合上述各子Agent的结果，为用户提供完整、连贯的最终解答。"
                        "直接给出回答内容，不要输出任何 [AGENT_CALL] 标记，也不要向用户解释标记机制。"
                    )
                    interpret_messages = adapter.create_prompt(
                        "你是龙虾Claw，一个强大的AI智能体助手。请基于子Agent的执行结果为用户提供整合后的最终解答。",
                        interpret_prompt, []
                    )
                    # 二次生成流串联三种过滤器，防止任一标记泄漏给前端
                    agent_secondary_filter = _AgentMarkerFilter()
                    mcp_secondary_filter = _McpMarkerFilter()
                    ws_mcp_filter = _WebSearchMarkerFilter()
                    agent_final = ""

                    def _agent_emit(safe_text: str):
                        if safe_text:
                            return "data: " + json.dumps({'success': True, 'content': safe_text, 'session_id': session_id}) + "\n\n"
                        return ""

                    for chunk in adapter.chat_stream(interpret_messages):
                        if isinstance(chunk, dict):
                            content = chunk.get("content", "")
                        else:
                            content = str(chunk)
                        if content and not content.startswith("{\"__stats__\""):
                            safe = ws_mcp_filter.feed(agent_secondary_filter.feed(mcp_secondary_filter.feed(content)))
                            agent_final += safe
                            ev = _agent_emit(safe)
                            if ev:
                                yield ev
                    tail = ws_mcp_filter.feed(agent_secondary_filter.feed(mcp_secondary_filter.flush())) + ws_mcp_filter.flush()
                    agent_final += tail
                    ev = _agent_emit(tail)
                    if ev:
                        yield ev
                    if agent_final.strip():
                        full_response = agent_final.strip()

            # ============ PPT 生成分支 ============
            if not request.files and not has_images and "[PPT_GEN]" in full_response:
                from lobster_mu import ppt_service
                raw_payload = _parse_ppt_gen(full_response) or ""
                full_response = PPT_GEN_PATTERN.sub("", full_response)
                full_response = re.sub(r"\[PPT_GEN\].*$", "", full_response, flags=re.DOTALL).strip()  # 未闭合标记一并剥除
                data = ppt_service.parse_ppt_json(raw_payload)
                if not data:
                    degrade = "⚠️ PPT 大纲格式解析失败，已降级为文字大纲：\n\n" + (raw_payload[:2000] or "（无有效内容）")
                    yield "data: " + json.dumps({'success': True, 'content': degrade + "\n\n", 'session_id': session_id}) + "\n\n"
                    full_response = (full_response + "\n\n" + degrade).strip()
                else:
                    yield "data: " + json.dumps({'success': True, 'content': "⏳ 正在渲染幻灯片...\n", 'session_id': session_id}) + "\n\n"
                    result = ppt_service.generate_ppt(user_id, data)
                    if result.get("success"):
                        trunc_note = "（页数超出上限，已截断）" if result.get("truncated") else ""
                        done_msg = (
                            f"✅ PPT 已生成{trunc_note}：{result['title']}（{result['slide_count']} 页，{result['theme_name']}主题）\n"
                            f"📥 [点击下载 PPT 文件]({result['download_url']})\n\n"
                        )
                        yield "data: " + json.dumps({'success': True, 'content': done_msg, 'session_id': session_id}) + "\n\n"
                        full_response = (full_response + "\n\n" + done_msg).strip()
                    else:
                        fail_msg = f"❌ PPT 生成失败: {result.get('error', '未知错误')}。以下为文字版大纲：\n\n{raw_payload[:2000]}"
                        yield "data: " + json.dumps({'success': True, 'content': fail_msg + "\n\n", 'session_id': session_id}) + "\n\n"
                        full_response = (full_response + "\n\n" + fail_msg).strip()

            # ============ 联网搜索分支 ============
            if not request.files and not has_images and "[WEB_SEARCH]" in full_response and web_search_enabled:
                search_query = _parse_web_search(full_response)
                if search_query:
                    yield "data: " + json.dumps({'success': True, 'content': f"\n🔍 正在搜索: {search_query}...\n", 'session_id': session_id}) + "\n\n"
                    search_results = []
                    _pool = None
                    try:
                        import concurrent.futures as _cf
                        from search.search_manager import SearchManager
                        _sm_search = SearchManager()
                        _pool = _cf.ThreadPoolExecutor(max_workers=1)
                        _future = _pool.submit(_sm_search.search_sync, search_query, None, 5)
                        search_results = _future.result(timeout=15)
                    except _cf.TimeoutError:
                        yield "data: " + json.dumps({'success': True, 'content': "⚠️ 搜索超时，将基于已有知识回答\n\n", 'session_id': session_id}) + "\n\n"
                        search_results = []
                    except Exception as _se:
                        yield "data: " + json.dumps({'success': True, 'content': f"⚠️ 搜索失败: {str(_se)[:80]}\n\n", 'session_id': session_id}) + "\n\n"
                        search_results = []
                    finally:
                        if _pool:
                            _pool.shutdown(wait=False, cancel_futures=True)

                    if search_results:
                        # 过滤掉占位/错误结果（无 URL 且标题含失败/无可用提示）
                        def _is_real(r):
                            url = getattr(r, "url", "") or ""
                            title = getattr(r, "title", "") or ""
                            if url:
                                return True
                            if any(k in title for k in ("失败", "无可用", "无法", "请在设置")):
                                return False
                            return bool(getattr(r, "snippet", ""))
                        real_results = [r for r in search_results if _is_real(r)]
                        if real_results:
                            yield "data: " + json.dumps({'success': True, 'content': f"📋 搜索到 {len(real_results)} 条结果，正在整理...\n\n", 'session_id': session_id}) + "\n\n"
                            result_lines = []
                            for i, r in enumerate(real_results, 1):
                                title = getattr(r, "title", "")
                                url = getattr(r, "url", "")
                                snippet = getattr(r, "snippet", "")[:300]
                                result_lines.append(f"[{i}] {title}\n摘要: {snippet}\n来源: {url}")
                            search_summary = "\n\n".join(result_lines)
                            interpret_prompt = (
                                f"用户问题: {request.message}\n\n"
                                f"系统已联网搜索，结果如下：\n\n{search_summary}\n\n"
                                "请基于上述搜索结果，为用户提供完整、准确的解答。"
                                "每条信息必须标注来源，格式为：（来源：标题 - URL）。"
                                "必须把 URL 完整写出来，不要用 [1][2] 之类的编号代替。"
                                "直接给出回答内容，不要输出 [WEB_SEARCH] 标记。"
                            )
                            interpret_messages = adapter.create_prompt(
                                "你是龙虾Claw，一个强大的AI智能体助手。请基于联网搜索结果为用户提供准确的解答，并标注信息来源。",
                                interpret_prompt, []
                            )
                            ws_secondary = _WebSearchMarkerFilter()
                            mcp_secondary = _McpMarkerFilter()
                            ws_final = ""
                            for chunk in adapter.chat_stream(interpret_messages):
                                if isinstance(chunk, dict):
                                    content = chunk.get("content", "")
                                else:
                                    content = str(chunk)
                                if content and not content.startswith("{\"__stats__\""):
                                    safe = ws_secondary.feed(mcp_secondary.feed(content))
                                    ws_final += safe
                                    if safe:
                                        yield "data: " + json.dumps({'success': True, 'content': safe, 'session_id': session_id}) + "\n\n"
                            ws_final += ws_secondary.feed(mcp_secondary.flush()) + ws_secondary.flush()
                            if ws_final.strip():
                                full_response = ws_final.strip()
                        else:
                            yield "data: " + json.dumps({'success': True, 'content': "⚠️ 未搜索到有效结果，将基于已有知识回答\n\n", 'session_id': session_id}) + "\n\n"
                    else:
                        yield "data: " + json.dumps({'success': True, 'content': "⚠️ 未获得搜索结果，将基于已有知识回答\n\n", 'session_id': session_id}) + "\n\n"

            # ============ MCP 外部工具调用分支 ============
            if not request.files and not has_images and "[MCP_CALL]" in full_response:
                from lobster_mu import mcp_client
                mcp_calls = _parse_mcp_calls(full_response)
                # 去除标记块（最终答复以二次生成为准）
                full_response = MCP_CALL_PATTERN.sub("", full_response).strip()
                mcp_result_blocks = []
                for idx, call in enumerate(mcp_calls, 1):
                    if not call.get("raw_ok"):
                        err_msg = f"第 {idx} 个 MCP 调用标记格式错误（不是合法 JSON），已跳过。原始内容: {call.get('raw', '')[:100]}"
                        yield "data: " + json.dumps({'success': True, 'content': f"⚠️ {err_msg}\n\n", 'session_id': session_id}) + "\n\n"
                        mcp_result_blocks.append(f"[调用 {idx}] 失败: {err_msg}")
                        continue
                    label = f"{call['server']}/{call['tool']}"
                    yield "data: " + json.dumps({'success': True, 'content': f"\n🔧 正在调用 MCP 工具: {label}...\n", 'session_id': session_id}) + "\n\n"
                    mcp_res = mcp_client.call_tool(user_id, call["server"], call["tool"], call["arguments"])
                    if mcp_res.get("success"):
                        result_text = mcp_res.get("result") or ""
                        yield "data: " + json.dumps({'success': True, 'content': f"📋 MCP 工具 {label} 调用成功，正在整理结果...\n\n", 'session_id': session_id}) + "\n\n"
                        mcp_result_blocks.append(
                            f"[调用 {idx}] 工具: {label}\n参数: {json.dumps(call['arguments'], ensure_ascii=False)[:500]}\n"
                            f"结果:\n{result_text[:4000]}"
                        )
                    else:
                        err = mcp_res.get("error") or "未知错误"
                        yield "data: " + json.dumps({'success': True, 'content': f"❌ MCP 工具 {label} 调用失败: {err}\n\n", 'session_id': session_id}) + "\n\n"
                        mcp_result_blocks.append(f"[调用 {idx}] 工具: {label}\n调用失败: {err}")

                if mcp_result_blocks:
                    mcp_summary = "\n\n".join(mcp_result_blocks)
                    interpret_prompt = (
                        f"用户问题: {request.message}\n\n"
                        f"系统已按你的要求调用了 MCP 外部工具，结果如下：\n\n{mcp_summary}\n\n"
                        "请基于上述工具调用结果，为用户提供完整、准确的最终解答。"
                        "直接给出回答内容，不要输出任何 [MCP_CALL] 标记，也不要向用户解释标记机制。"
                    )
                    interpret_messages = adapter.create_prompt(
                        "你是龙虾Claw，一个强大的AI智能体助手。请基于 MCP 工具调用结果为用户提供详细解答。",
                        interpret_prompt, []
                    )
                    # 二次生成流串联两种过滤器，防止任一标记泄漏给前端
                    mcp_secondary_filter = _McpMarkerFilter()
                    ws_mcp_filter = _WebSearchMarkerFilter()
                    mcp_final = ""

                    def _mcp_emit(safe_text: str):
                        if safe_text:
                            return "data: " + json.dumps({'success': True, 'content': safe_text, 'session_id': session_id}) + "\n\n"
                        return ""

                    for chunk in adapter.chat_stream(interpret_messages):
                        if isinstance(chunk, dict):
                            content = chunk.get("content", "")
                        else:
                            content = str(chunk)
                        if content and not content.startswith("{\"__stats__\""):
                            safe = ws_mcp_filter.feed(mcp_secondary_filter.feed(content))
                            mcp_final += safe
                            ev = _mcp_emit(safe)
                            if ev:
                                yield ev
                    tail = ws_mcp_filter.feed(mcp_secondary_filter.flush()) + ws_mcp_filter.flush()
                    mcp_final += tail
                    ev = _mcp_emit(tail)
                    if ev:
                        yield ev
                    if mcp_final.strip():
                        full_response = mcp_final.strip()

            # 安全网：剥除任何残留标记（闭合块/未闭合片段），不进入最终答复与历史
            full_response = AGENT_CALL_PATTERN.sub("", full_response)
            full_response = MCP_CALL_PATTERN.sub("", full_response)
            full_response = WEB_SEARCH_PATTERN.sub("", full_response)
            full_response = PPT_GEN_PATTERN.sub("", full_response)
            full_response = re.sub(r"\[AGENT_CALL\].*$", "", full_response, flags=re.DOTALL)
            full_response = re.sub(r"\[MCP_CALL\].*$", "", full_response, flags=re.DOTALL)
            full_response = re.sub(r"\[WEB_SEARCH\].*$", "", full_response, flags=re.DOTALL)
            full_response = re.sub(r"\[PPT_GEN\].*$", "", full_response, flags=re.DOTALL).strip()
            final_response = full_response
            if tool_result:
                final_response = f"🔧 工具执行结果:\n{tool_result}\n\n---\n\n{full_response}"

            session_store.append_message(user_id, session_id, "assistant", final_response,
                                         model_name=getattr(adapter, "model_name", None),
                                         token_stats=token_stats)

            # 对话记忆自动保存（user_id 隔离）
            response_keywords = memory_store.extract_keywords(full_response, max_keywords=8)
            combined_keywords = keywords + response_keywords
            short_term_content = f"对话记录: 用户问 '{request.message}', AI回答要点: {full_response[:150]}"
            memory_store.store(user_id, 'short_term', short_term_content,
                               keywords=combined_keywords, session_id=session_id, weight=1.0)
            if len(request.message) > 8 and len(full_response) > 20:
                important_facts = extract_important_facts(request.message, full_response)
                for fact in important_facts[:3]:
                    memory_store.store(user_id, 'long_term', f"重要事实: {fact}",
                                       keywords=memory_store.extract_keywords(fact),
                                       session_id=session_id, weight=1.5)

            done_event = {'success': True, 'content': '', 'session_id': session_id, 'done': True, 'model_name': adapter.model_name, 'token_stats': token_stats}
            if knowledge_sources:
                done_event['knowledge_sources'] = knowledge_sources
            yield f"data: {json.dumps(done_event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'success': False, 'error': str(e), 'session_id': session_id})}\n\n"
        finally:
            if acquired:
                try:
                    sem.release()
                except Exception:
                    pass

    return StreamingResponse(sync_stream_generator(), media_type="text/event-stream")


def chat_message_once(user_id: int, request: ChatMessageRequest) -> dict:
    """非流式聊天"""
    adapter = get_default_llm_adapter()
    if not adapter:
        return {"success": False, "error": "未找到可用的LLM适配器"}
    session_id = session_store.get_or_create_session(user_id, request.session_id)
    try:
        env_block = get_environment_block()
        system_prompt = "你是龙虾Claw，一个强大的AI智能体助手。" + env_block
        context = session_store.get_messages(user_id, session_id)[-10:] or []
        messages = adapter.create_prompt(system_prompt, request.message, context)
        response = adapter.chat(messages)
        content = response.content
        session_store.append_message(user_id, session_id, "user", request.message)
        session_store.append_message(user_id, session_id, "assistant", content)
        return {"success": True, "content": content, "session_id": session_id}
    except Exception as e:
        return {"success": False, "error": str(e)}
