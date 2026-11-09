# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 流式聊天核心（复制改造自 lobster_claw.chat_stream，会话/记忆/工具/脚本均按 user_id 隔离）"""
import json
import os
import queue
import re
import threading
from collections import defaultdict
from datetime import datetime
from typing import Optional, Dict, List, Any

from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from lobster_mu import session_store, memory_store, tools, script_service
from lobster_mu.security import PBKDF2_ITERATIONS  # noqa: F401 (保持包依赖清晰)
from lobster_mu.db import get_conn, get_config as db_get_config

# 提示词统一由 prompts 包管理（保留下划线别名以兼容既有内部引用与测试）
from prompts import (
    AGENT_INTERPRET_SYSTEM,
    CHAT_SYSTEM_BASE,
    CHAT_SYSTEM_ONCE,
    CHAT_SYSTEM_WITH_FILES,
    CHAT_SYSTEM_WITH_IMAGES,
    MCP_INTERPRET_SYSTEM,
    REACT_TOOL_DIRECTIVE,
    SCRIPT_DRAFT_APPENDIX_HEADER,
    SCRIPT_INTERPRET_SYSTEM,
    SKILL_INTERPRET_SYSTEM,
    SUB_AGENT_ASSISTANT_PLACEHOLDER,
    WEB_SEARCH_INTERPRET_SYSTEM,
    build_agent_interpret_prompt,
    build_agent_prompt_block as _build_agent_prompt_block,
    build_mcp_interpret_prompt,
    build_mcp_prompt_block as _build_mcp_prompt_block,
    build_ppt_prompt_block as _build_ppt_prompt_block,
    build_script_interpret_prompt,
    build_skill_interpret_prompt,
    build_skill_prompt_block as _build_skill_prompt_block,
    build_sub_agent_system_prompt,
    build_sub_agent_tool_followup,
    build_sub_agent_user_content,
    build_user_content_default,
    build_user_content_ppt,
    build_user_content_with_files,
    build_user_content_with_images,
    build_user_content_with_tool_result,
    build_web_search_interpret_prompt,
    build_web_search_prompt_block as _build_web_search_prompt_block,
    sub_agent_forbidden_marks,
)

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
SKILL_CALL_PATTERN = re.compile(r"\[SKILL_CALL\](.*?)\[/SKILL_CALL\]", re.DOTALL)

# 正在执行生成任务的会话集合（跨连接的服务端状态）。
# 客户端刷新/断开后后台线程仍继续执行，会话列表据此显示"执行中"标识。
_running_sessions: set = set()
_running_sessions_lock = threading.Lock()


def mark_session_running(session_id) -> None:
    if session_id is None:
        return
    try:
        with _running_sessions_lock:
            _running_sessions.add(str(session_id))
    except Exception:
        pass


def mark_session_done(session_id) -> None:
    if session_id is None:
        return
    try:
        with _running_sessions_lock:
            _running_sessions.discard(str(session_id))
    except Exception:
        pass


def get_running_session_ids() -> set:
    with _running_sessions_lock:
        return set(_running_sessions)


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


def _mcp_has_time_tool(mcp_tools) -> bool:
    """判断 MCP 工具清单中是否存在可查询当前时间的工具。"""
    for t in mcp_tools or []:
        name = str(t.get("name") or "").strip().lower()
        if name in ("get_system_time", "get_current_time", "current_time", "time_now"):
            return True
    return False


# 查询关键词中的绝对日期/时间片段（仅在用户未指定时间时剔除）
_QUERY_TIME_RE = re.compile(
    r"[（(]?\s*(?:"
    r"\d{4}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2}\s*日?"
    r"|\d{4}\s*年\s*\d{1,2}\s*月"
    r"|\d{1,2}\s*月\s*\d{1,2}\s*日"
    r")\s*[)）]?"
)
# 用户消息里是否已明确指定时间
_USER_TIME_RE = re.compile(
    r"今天|今日|昨天|明天|昨天|前天|后天|本周|上周|下周|本月|上月|下月|今年|去年|明年"
    r"|\d{4}\s*年|\d{1,2}\s*月\s*\d{1,2}(?:\s*日)?|\d{4}-\d{1,2}-\d{1,2}"
)


def _user_specified_time(message: str) -> bool:
    """用户是否在消息中明确给出了时间（显式日期或今天/本周等相对时间）。"""
    return bool(_USER_TIME_RE.search(message or ""))


def _clean_search_query(query: str, keep_time: bool = False) -> str:
    """清洗搜索关键词：用户未指定时间时，剔除模型自行拼进关键词的日期/年份。"""
    q = (query or "").strip()
    if keep_time:
        return q[:100]
    q = _QUERY_TIME_RE.sub(" ", q)
    q = re.sub(r"\s+", " ", q).strip(" ，,、；;:：-—_·")
    return q[:100]


def _parse_web_search(text: str) -> str:
    """从模型回复中提取 [WEB_SEARCH] 查询关键词，返回第一个匹配；无匹配返回空字符串。"""
    m = WEB_SEARCH_PATTERN.search(text or "")
    if not m:
        return ""
    return m.group(1).strip()[:100]


_TRAIL_PUNCT_RE = re.compile(r"[。．.，,、；;！!？?）)】」』\s]+$")
_MD_LINK_URL_RE = re.compile(r"\]\((<[^>]*>|[^)\s]+)\)")

def _clean_md_link_urls(text: str) -> str:
    """兜底清洗：去掉 Markdown 链接 URL 末尾误并入的标点（前端也会再清洗一层）。"""
    def _sub(m):
        url = m.group(1)
        if url.startswith("<") and url.endswith(">"):
            inner = _TRAIL_PUNCT_RE.sub("", url[1:-1])
            return f"](<{inner}>)"
        return f"]({_TRAIL_PUNCT_RE.sub('', url)})"
    return _MD_LINK_URL_RE.sub(_sub, text or "")


def _trace_marker(user_id, session_id, tool_name, detail=""):
    """旧标记链路也写入执行轨迹，保证管理后台能看到完整的执行过程。"""
    try:
        from lobster_mu.agent.trace_store import log_trace
        log_trace(user_id, session_id, 1, "tool", tool_name, "",
                  detail or f"标记执行：{tool_name}", "ok")
    except Exception:
        pass


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


class _FileLinkFilter:
    """流式过滤模型编造的产物下载链接（文件不存在/为空则整行丢弃）。

    模型常模仿历史回复里的"📎 生成的文件 + 下载地址"格式，自己编造文件名和
    URL，而实际上没有执行脚本或执行失败。这里对每行做真实性校验：
    - 含产物下载链接的行，若引用的文件都不存在 → 丢弃；
    - "📎 ...生成的文件"标题下若没有任何有效链接 → 标题一并丢弃。
    跨 chunk 安全：疑似链接/标题的尾部片段暂存到下一个 chunk 再判定。
    """

    _LINK_MARK = "/api/lobster-mu/script/files/download/"

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.buf = ""
        self._block = None  # [标题行, 后续行...]，正在收集"📎 文件块"

    @staticmethod
    def _is_heading(line: str) -> bool:
        s = line.strip()
        return ("生成的文件" in s) and ("📎" in s) and len(s) < 80

    def _is_dead_link_line(self, line: str) -> bool:
        try:
            return script_service._line_links_dead(self.user_id, line) is True
        except Exception:
            return False

    def _handle_line(self, line: str) -> list:
        if self._block is not None:
            if not line.strip():
                out = self._flush_block()
                return out + [line]
            self._block.append(line)
            return []
        if self._is_heading(line):
            self._block = [line]
            return []
        if self._is_dead_link_line(line):
            return []
        return [line]

    def _flush_block(self) -> list:
        block = self._block or []
        self._block = None
        if not block:
            return []
        head, rest = block[0], block[1:]
        kept = [ln for ln in rest if not self._is_dead_link_line(ln)]
        if any(script_service._DOWNLOAD_LINK_RE.search(ln) for ln in kept):
            return [head] + kept
        return []

    def _hold_partial(self) -> bool:
        b = self.buf
        if self._block is not None or self._LINK_MARK in b or "📎" in b:
            return True
        # 未写完的 markdown 链接（下一段可能补上产物下载地址）
        if re.search(r"\]\([^)\s]*$", b):
            return True
        # 尾部是下载地址前缀（被 chunk 截断）
        for i in range(len(self._LINK_MARK) - 1, 0, -1):
            if b.endswith(self._LINK_MARK[:i]):
                return True
        # 疑似"📎 ...生成的文件"标题的开头
        st = b.strip()
        if st in ("-", "*", "- 📎", "* 📎", "📎"):
            return True
        return False

    def feed(self, text: str) -> str:
        self.buf += text
        out = []
        while True:
            idx = self.buf.find("\n")
            if idx == -1:
                break
            line = self.buf[:idx]
            self.buf = self.buf[idx + 1:]
            for ln in self._handle_line(line):
                out.append(ln + "\n")
        if not self._hold_partial():
            out.append(self.buf)
            self.buf = ""
        return "".join(out)

    def flush(self) -> str:
        out = self._flush_block()
        if self.buf:
            leftover = self.buf
            self.buf = ""
            out.extend(self._handle_line(leftover))
            out.extend(self._flush_block())
        return "\n".join(out)


# 文件生成意图：用于模型漏输出 [NEED_SCRIPT] 时强制走脚本执行，避免"只给代码/只说已生成却不产文件"
_FILE_TYPE_RE = re.compile(
    r"(文件|文档|markdown|\.md\b|md\s*文件|pdf|word|docx|excel|xlsx|表格|csv|"
    r"ppt|pptx|幻灯片|演示文稿|txt|文本文件|json|html|图片|图表|压缩包|zip)", re.IGNORECASE)
_FILE_ACTION_RE = re.compile(
    r"(生成|导出|保存|输出|制作|创建|写成|写一份|写入|整理成|排版|转成|转换为|转换|转为|打包|下载)", re.IGNORECASE)
_FILE_DELEGATE_RE = re.compile(r"(帮我|给我|我要|我需要|需要你|来一份|请给我)", re.IGNORECASE)
_FILE_ASK_ONLY_RE = re.compile(
    r"((怎么|如何|怎样|为什么)[^。！？\n]{0,15}(生成|导出|保存|制作|创建|转换|转成|写))"
    r"|((能不能|可不可以|是否)[^。！？\n]{0,10}(生成|导出|保存))")


def _looks_like_file_request(message: str) -> bool:
    """粗判用户是否要求实际产出文件（用于兜底触发脚本执行）。"""
    s = message or ""
    # 明确否定/只要代码时不触发
    if re.search(r"(不需要|不用|不要|无需|不必).{0,6}(生成|导出|保存|输出|创建|制作).{0,10}(文件|文档|表格|pdf|word|excel|ppt|md|markdown)", s):
        return False
    if re.search(r"(只给|只要|直接给|仅需|只需).{0,4}(代码|脚本)", s):
        return False
    if not _FILE_TYPE_RE.search(s):
        return False
    if not (_FILE_ACTION_RE.search(s) or _FILE_DELEGATE_RE.search(s)):
        return False
    # 纯咨询（"怎么生成pdf文件/请介绍如何生成word"）不触发；带明确的委托动作才触发
    if _FILE_ASK_ONLY_RE.search(s) and not re.search(r"(帮我|给我|为我|我要|我需要|需要你|来一份|一份|生成一份|导出一份|做一个|写一份)", s):
        return False
    return True


def _script_task_with_context(message: str, context, max_user: int = 1200, max_assistant: int = 6000) -> str:
    """构造脚本生成需求。

    跟进类指令（如"检查报错原因，继续生成"）单看当前这句话会丢失真正任务，
    历史上因此生成过"检查报错"这类与需求无关的脚本。这里把上一轮用户需求与
    上一轮 AI 回复内容一并带上，保证脚本按真实任务产出文件。
    """
    current = (message or "").strip()
    parts = [f"用户当前需求: {current}"]
    last_user = ""
    last_assistant = ""
    for m in reversed(context or []):
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        text = str(m.get("content") or "").strip()
        if not text or role not in ("user", "assistant"):
            continue
        if role == "assistant" and not last_assistant:
            last_assistant = text
        elif role == "user" and not last_user:
            last_user = text
        if last_user and last_assistant:
            break
    if len(current) <= 60 and (last_user or last_assistant):
        if last_user:
            parts.append(f"上一轮用户需求: {last_user[:max_user]}")
        if last_assistant:
            parts.append("上一轮AI回复内容（本轮要产出的文件内容应以此为准）:\n" + last_assistant[:max_assistant])
        parts.append("请结合上述上下文生成完整可执行脚本并实际产出文件，不要生成占位/示例内容。")
    return "\n\n".join(parts)


def _is_continue_generation_request(message: str, context) -> bool:
    """跟进式指令（"检查报错原因，继续生成/重新生成一次"）且上一轮确实是文件生成需求。"""
    s = message or ""
    if not re.search(r"(继续|重新|再).{0,6}(生成|导出|保存|输出|制作)", s):
        return False
    for m in reversed(context or []):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        text = str(m.get("content") or "").strip()
        if text:
            return _looks_like_file_request(text)
    return False


# PDF 生成：指代上一轮内容的说法
_PDF_REF_RE = re.compile(r"(以上|上述|上面|前面|之前|刚才|刚刚|这段|这份|这些|上一条|上文|全文|该内容|这个内容)")
# 工具参数里常见的无效"正文"（其实是把指令本身当正文）
_PDF_BAD_BODY = {"文件", "文档", "pdf", "内容", "文本", "正文", "文字", "以上内容", "上述内容", "这份内容"}


def _last_assistant_content(context) -> str:
    """取最近一条有实质内容的 assistant 回复（用于"把以上内容生成PDF"）。"""
    for m in reversed(context or []):
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        text = str(m.get("content") or "").strip()
        if len(text) < 20:
            continue
        # 去掉工具结果外壳，只保留正文
        text = re.sub(r"^🔧 工具执行结果:\s*.*?\n---\s*\n", "", text, flags=re.S).strip()
        if text:
            return text
    return ""


def _resolve_pdf_content(message: str, extracted: str, context) -> str:
    """确定 PDF 的正文字段。

    工具意图识别常把"把以上内容生成pdf文件"解析成 content="文件"，
    导致 PDF 只有"文档/文件"两个字。这里：
    1) 显式正文（足够长且不是占位词）直接采用；
    2) 指代上一轮内容（以上/上述/刚才…）时取上一轮 AI 回复；
    3) 都没有则返回空串，不执行 PDF 工具，交给正常回答/脚本流程生成真实内容。
    """
    body = (extracted or "").strip()
    if body and body.lower() not in _PDF_BAD_BODY and len(body) >= 8:
        return body
    if _PDF_REF_RE.search(message or ""):
        return _last_assistant_content(context)
    return ""


class _InlineCodeDropFilter:
    """文件生成流程中丢弃模型的内联代码块。

    真实脚本由系统生成并执行、单独展示；模型贴在回复里的代码（常带
    "文件已生成"之类文案）会误导用户以为文件已产出，这里直接不展示。
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.buf = ""
        self.in_block = False

    def _handle_line(self, line: str) -> list:
        s = line.strip()
        if self.in_block:
            if s.startswith("```"):
                self.in_block = False
            return []
        if s.startswith("```"):
            self.in_block = True
            return []
        return [line]

    def _hold_partial(self) -> bool:
        if self.in_block:
            return True
        st = self.buf.strip()
        return bool(st) and "```".startswith(st[:3])

    def feed(self, text: str) -> str:
        if not self.enabled:
            return text
        self.buf += text
        out = []
        while True:
            idx = self.buf.find("\n")
            if idx == -1:
                break
            line = self.buf[:idx]
            self.buf = self.buf[idx + 1:]
            for ln in self._handle_line(line):
                out.append(ln + "\n")
        if not self._hold_partial():
            out.append(self.buf)
            self.buf = ""
        return "".join(out)

    def flush(self) -> str:
        if not self.enabled:
            return ""
        out = []
        if self.buf and not self.in_block:
            out.extend(self._handle_line(self.buf))
        self.buf = ""
        self.in_block = False
        return "\n".join(out)


def _strip_inline_code_blocks(text: str) -> str:
    """移除内联代码块（含 ```python … ```），用于脚本流程的兜底文本清洗。"""
    return re.sub(r"(?ms)^[ \t]*```[^\n]*\n.*?^[ \t]*```[ \t]*$", "", text)


class _ThinkTagFilter:
    """流式抽取内联 <think>…</think> 块：feed() 返回 (可见文本, 思考文本)。

    部分模型把思考过程以 <think>/<thinking> 标签内联输出在 content 中，
    该过滤器把思考内容从正文剥离，供前端折叠展示，避免标签原文暴露给用户。
    跨 chunk 安全：疑似标签前缀的尾部片段会保留到下一个 chunk 再判断。
    """

    _OPEN_TAGS = ("<think>", "<thinking>")
    _CLOSE_TAGS = ("</think>", "</thinking>")

    def __init__(self):
        self.buf = ""
        self.in_think = False
        self._close_tag = "</think>"

    @staticmethod
    def _hold_prefix(text: str, tags) -> str:
        """返回末尾与任一标签前缀重叠的部分（需要暂存）。"""
        max_len = max(len(t) for t in tags) - 1
        max_len = min(max_len, len(text))
        for length in range(max_len, 0, -1):
            suffix = text[-length:]
            if any(t.startswith(suffix) for t in tags):
                return suffix
        return ""

    def feed(self, text: str):
        self.buf += text
        visible, thinking = [], []
        while self.buf:
            if self.in_think:
                end = self.buf.find(self._close_tag)
                if end == -1:
                    hold = self._hold_prefix(self.buf, self._CLOSE_TAGS)
                    thinking.append(self.buf[: len(self.buf) - len(hold)])
                    self.buf = hold
                    break
                thinking.append(self.buf[:end])
                self.buf = self.buf[end + len(self._close_tag):]
                self.in_think = False
            else:
                starts = [(self.buf.find(t), t) for t in self._OPEN_TAGS]
                starts = [(i, t) for i, t in starts if i != -1]
                if not starts:
                    hold = self._hold_prefix(self.buf, self._OPEN_TAGS)
                    visible.append(self.buf[: len(self.buf) - len(hold)])
                    self.buf = hold
                    break
                start, tag = min(starts, key=lambda x: x[0])
                visible.append(self.buf[:start])
                self.buf = self.buf[start + len(tag):]
                self.in_think = True
                self._close_tag = "</thinking>" if tag == "<thinking>" else "</think>"
        return "".join(visible), "".join(thinking)

    def flush(self):
        """流结束：缓冲区剩余内容按当前状态归位。"""
        if self.in_think:
            return "", self.buf
        out = self.buf
        self.buf = ""
        # 尾部若是未闭合的疑似标签前缀（如 "<thi"），直接丢弃
        if self._hold_prefix(out, self._OPEN_TAGS) == out:
            return "", ""
        return out, ""


def _strip_think_tags(text: str) -> str:
    """从完整回复中剔除 <think>/<thinking> 块（用于入库前的清洗）。"""
    import re as _re
    text = _re.sub(r'<think(?:ing)?>.*?</think(?:ing)?>', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r'<think(?:ing)?>.*$', '', text, flags=_re.DOTALL | _re.IGNORECASE)
    return text.strip()


def _WebSearchMarkerFilter() -> _MarkerFilter:
    return _MarkerFilter("[WEB_SEARCH]", "[/WEB_SEARCH]")


def _McpMarkerFilter() -> _MarkerFilter:
    """首轮流式输出时实时剔除 [MCP_CALL]...[/MCP_CALL] 块，
    使原始 JSON 标记不推送到前端（调用进度由后端单独推送）。"""
    return _MarkerFilter("[MCP_CALL]", "[/MCP_CALL]")


def _AgentMarkerFilter() -> _MarkerFilter:
    return _MarkerFilter("[AGENT_CALL]", "[/AGENT_CALL]")


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


def _parse_skill_calls(text: str) -> List[Dict[str, Any]]:
    """从模型回复中解析 [SKILL_CALL] 标记块"""
    calls = []
    for m in SKILL_CALL_PATTERN.finditer(text or ""):
        payload = m.group(1).strip()
        try:
            obj = json.loads(payload)
            calls.append({
                "skill_id": str(obj.get("skill_id", "")),
                "params": obj.get("params") or {},
                "raw_ok": True,
            })
        except Exception:
            calls.append({"skill_id": "", "params": {}, "raw_ok": False, "raw": payload[:200]})
    # 兜底：模型忘写 [/SKILL_CALL] 闭合标签时，尝试解析尾部 JSON 片段，
    # 避免整次技能调用被静默丢弃（此前表现为只保存一句"正在调用技能..."）
    if not calls and text and "[SKILL_CALL]" in text:
        frag = text.split("[SKILL_CALL]", 1)[1].strip()
        start = frag.find("{")
        if start >= 0:
            cand = frag[start:]
            variants = [cand]
            end = cand.rfind("}")
            if end > 0:
                variants.append(cand[:end + 1])
            for v in variants:
                try:
                    obj = json.loads(v)
                    calls.append({
                        "skill_id": str(obj.get("skill_id", "")),
                        "params": obj.get("params") or {},
                        "raw_ok": True,
                    })
                    break
                except Exception:
                    continue
    return calls


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


def _run_web_search_sync(query: str, timeout: int = 15, keep_time: bool = False) -> str:
    """同步执行一次联网搜索，返回格式化结果文本；失败/无结果返回空串"""
    query = _clean_search_query(query, keep_time=keep_time)
    if not query:
        return ""
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


def _inject_ctx(arguments: Dict[str, Any], ctx: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """服务端会话上下文占位符替换：arguments 中的 {{login_token}} 等占位值
    在执行前替换为 session 中的真实值。模型上下文只接触占位符，不接触真实令牌。"""
    if not ctx or not isinstance(arguments, dict):
        return arguments

    def _sub(v):
        if isinstance(v, str):
            for k, val in ctx.items():
                if val:
                    v = v.replace("{{" + k + "}}", str(val))
            return v
        if isinstance(v, dict):
            return {kk: _sub(vv) for kk, vv in v.items()}
        if isinstance(v, list):
            return [_sub(x) for x in v]
        return v

    return _sub(arguments)


def _run_mcp_call_sync(user_id: int, call: Dict[str, Any], ctx: Optional[Dict[str, Any]] = None):
    """同步执行一个 MCP 调用，返回 (ok, 结果文本)"""
    try:
        from lobster_mu import mcp_client
        arguments = _inject_ctx(call.get("arguments") or {}, ctx)
        res = mcp_client.call_tool(user_id, call.get("server", ""), call.get("tool", ""),
                                   arguments)
        if res.get("success"):
            return True, str(res.get("result") or "")[:20000]
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


def _execute_sub_agent(user_id: int, agent: Dict[str, Any], task: str,
                       cancel_event=None) -> Dict[str, Any]:
    """执行子Agent（支持取消：cancel_event 为 threading.Event，置位则返回部分结果）。"""
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
    mcp_tools: List[Dict[str, Any]] = []
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
    web_block = _build_web_search_prompt_block(can_search, _mcp_has_time_tool(mcp_tools))

    forbidden = sub_agent_forbidden_marks(can_mcp, can_search)
    system_prompt = build_sub_agent_system_prompt(
        agent, plan_block, web_block, mcp_block, forbidden)
    user_content = build_sub_agent_user_content(task, memory_block)

    try:
        messages = adapter.create_prompt(system_prompt, user_content, [])
        rounds_content: List[str] = []
        final_content = ""
        used_tools = False

        for round_i in range(MAX_SUB_AGENT_TOOL_ROUNDS):
            if cancel_event is not None and cancel_event.is_set():
                events.append("⏹️ 用户已取消子Agent执行，返回部分结果")
                final_content = "\n".join(rounds_content)
                return {"success": True, "result": _strip_all_marks(final_content),
                        "mems_saved": 0, "plan_updated": "",
                        "events": events, "used_tools": used_tools, "cancelled": True}
            resp = adapter.chat(messages)
            content = resp.get("content", "") if isinstance(resp, dict) else (getattr(resp, "content", "") or str(resp))
            rounds_content.append(content)

            tool_blocks = []
            if can_search and "[WEB_SEARCH]" in content:
                q = _parse_web_search(content)
                if q:
                    events.append(f"🔍 联网搜索: {q}")
                    res_text = _run_web_search_sync(q, keep_time=_user_specified_time(task))
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
            followup = build_sub_agent_tool_followup("\n\n".join(tool_blocks), is_last)
            messages = messages + [
                {"role": "assistant", "content": _strip_all_marks(content) or SUB_AGENT_ASSISTANT_PLACEHOLDER},
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
                "events": events, "used_tools": used_tools, "cancelled": False}
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


# ============ 三层配额：全局闸 / 每用户闸 / 会话锁 ============
# 全局聊天并发上限：单进程内所有用户共享，防止长任务打满线程池
_GLOBAL_CHAT_MAX = max(1, int(os.environ.get("MU_GLOBAL_CHAT_MAX", "8")))
_global_sem = threading.BoundedSemaphore(_GLOBAL_CHAT_MAX)
# 全局闸等待上限（秒）：取不到立即拒绝，不长时间排队
_GLOBAL_ACQUIRE_TIMEOUT = float(os.environ.get("MU_GLOBAL_ACQUIRE_TIMEOUT", "8"))
# 会话锁等待上限（秒）
_SESSION_ACQUIRE_TIMEOUT = float(os.environ.get("MU_SESSION_ACQUIRE_TIMEOUT", "120"))

# 会话级串行锁：同一会话同一时刻仅允许一个生成器写入历史
_session_locks: Dict[str, threading.Lock] = {}
_session_locks_guard = threading.Lock()
_SESSION_LOCK_MAX = 512


def _session_lock(user_id: int, session_id: str) -> threading.Lock:
    """取指定会话的串行锁（按需创建；字典超限时清理未持有的锁）"""
    key = f"{user_id}:{session_id}"
    with _session_locks_guard:
        lock = _session_locks.get(key)
        if lock is None:
            if len(_session_locks) >= _SESSION_LOCK_MAX:
                for stale in [k for k, v in _session_locks.items() if not v.locked()]:
                    _session_locks.pop(stale, None)
            lock = threading.Lock()
            _session_locks[key] = lock
        return lock


def _busy_event(message: str, session_id: str) -> str:
    """配额拒绝时的 SSE 事件（前端已有 success=false 分支，可直接展示）"""
    return "data: " + json.dumps(
        {'success': False, 'error': message, 'session_id': session_id, 'type': 'busy'},
        ensure_ascii=False,
    ) + "\n\n"


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


def _get_model_context_window(model_name: Optional[str] = None) -> int:
    """取模型配置的上下文窗口（token）；未配置/默认占位时返回保守默认值"""
    try:
        from models.model_manager import ModelManager
        mm = ModelManager()
        models = [m for m in mm.get_all() if getattr(m, "api_key", "") and getattr(m, "model_type", "") == "text"]
        if not models:
            return 200000
        model = next((m for m in models if m.model_name == model_name), None) if model_name else None
        model = model or models[0]
        cw = int(getattr(model, "context_window", 0) or 0)
        return cw if cw > 4000 else 200000
    except Exception:
        return 200000


def _trim_messages_to_budget(messages, budget_chars: int):
    """将 messages 文本总量控制在 budget_chars 以内：超长时优先截断最大的非 system 文本
    （通常是上传的大文件内容），避免触发模型 400 InvalidParameter（输入超长）。"""
    if not messages or budget_chars <= 0:
        return messages

    def _tlen(m):
        c = m.get("content")
        if isinstance(c, str):
            return len(c)
        if isinstance(c, list):
            return sum(len(p.get("text", "")) for p in c if isinstance(p, dict) and p.get("type") == "text")
        return 0

    def _set_text(m, text):
        c = m.get("content")
        if isinstance(c, str):
            m["content"] = text
        elif isinstance(c, list):
            for p in c:
                if isinstance(p, dict) and p.get("type") == "text":
                    p["text"] = text
                    return

    suffix = "…\n[内容过长，已自动截断]"
    total = sum(_tlen(m) for m in messages)
    guard = 0
    while total > budget_chars and guard < 60:
        guard += 1
        idx, best = -1, 0
        for i, m in enumerate(messages):
            if m.get("role") == "system":
                continue
            l = _tlen(m)
            if l > best:
                best, idx = l, i
        if idx < 0 or best <= 0:
            break
        m = messages[idx]
        overflow = total - budget_chars
        cur = _tlen(m)
        keep = cur - overflow - len(suffix)
        if keep <= 0:
            keep = max(0, budget_chars - (total - cur))
        c = m.get("content")
        text = c if isinstance(c, str) else next(
            (p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"), "")
        new_text = text[:keep] + suffix
        _set_text(m, new_text)
        total = total - cur + len(new_text)
    return messages


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


def get_environment_block(user_id: int = None) -> str:
    try:
        from web.routes.lobster_claw import get_environment_snapshot, format_environment_for_prompt
        snapshot = get_environment_snapshot()
        # 环境快照的知识库统计读的是全局 rag.KnowledgeBase（多用户场景下为空），
        # 这里用当前用户的 knowledge_store 统计覆盖，让 LLM 看到“我的知识库”真实数量。
        if user_id is not None:
            try:
                from lobster_mu import knowledge_store
                st = knowledge_store.stats(user_id)
                snapshot = dict(snapshot)
                snapshot["knowledge_base"] = {
                    "documents": int(st.get("documents", 0)),
                    "chunks": int(st.get("chunks", 0)),
                }
            except Exception:
                pass
        env_aware_text = format_environment_for_prompt(snapshot)
    except Exception:
        env_aware_text = ""
    return "\n\n" + env_aware_text + "\n" if env_aware_text else ""


def _knowledge_context(user_id: int, message: str):
    """知识库检索（user_id 过滤），返回 (context, sources) 元组；任何失败都返回 ("", []) 保持聊天流不中断

    采纳门槛 threshold=0.5：低于该相关度的片段视为"未被问题采纳"，
    既不注入上下文、也不向前端返回参考来源（避免低相关噪声）。
    context 与 sources 来自同一份检索结果，保证前端展示与注入完全一致。
    """
    try:
        from lobster_mu import knowledge_store
        results = knowledge_store.search(user_id, message, top_k=3, threshold=0.5)
        if not results:
            return "", []
        context = "\n\n📖 以下是与当前问题相关的知识库内容，请参考这些信息回答：\n"
        for i, r in enumerate(results, 1):
            context += f"{i}. [{r.get('filename', '未知文档')}] (相关度 {r.get('score', 0):.2f})\n{r.get('content', '')}\n"
        return context, results
    except Exception:
        return "", []


def _warmup_knowledge() -> None:
    """后台预热知识库 embedding 模型（失败静默，不影响聊天流）"""
    try:
        from lobster_mu import knowledge_store
        knowledge_store.warmup()
    except Exception:
        pass


def chat_stream_response(user_id: int, request: ChatStreamRequest,
                         ctx: Optional[Dict[str, Any]] = None) -> StreamingResponse:
    """多用户流式聊天入口"""
    session_id = session_store.get_or_create_session(user_id, request.session_id)

    has_images = bool(request.images)
    if has_images:
        print(f"[DEBUG] mu收到 {len(request.images)} 张图片 (user {user_id})")
        for i, img in enumerate(request.images):
            url = img.get('data_url', '') if isinstance(img, dict) else ''
            print(f"[DEBUG] mu图片 {i + 1}: {img.get('name', '未知')}, data_url长度: {len(url)}")
    # 文件内容块（仅喂给模型）；存历史只保留文件名，避免重开历史会话时显示全文
    file_info = []
    if request.files:
        print(f"[DEBUG] mu收到 {len(request.files)} 个文件 (user {user_id})")
        for i, file_item in enumerate(request.files):
            filename = file_item.get('filename', '')
            content = file_item.get('content', '')
            print(f"[DEBUG] mu文件 {i + 1}: {filename}, 内容长度: {len(content) if content else 0}")
            if filename:
                if content:
                    file_info.append(f"\n📄 文件: {filename}\n```\n{content}\n```")
                else:
                    file_info.append(f"\n📄 文件: {filename} (已上传但无法提取内容)")

    # 展示文本（与前端乐观消息一致）：仅文件名 / 图片数，存入历史
    parts = []
    if request.message:
        parts.append(request.message)
    if request.files:
        names = ", ".join(f.get('filename', '') for f in request.files if f.get('filename'))
        if names:
            parts.append(f"📎 已上传文件: {names}")
    if has_images:
        parts.append(f"🖼️ 附带 {len(request.images)} 张图片")
    display_message = "\n\n".join(parts)

    session_store.append_message(user_id, session_id, "user", display_message)
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
                    "width": 1024, "height": 576, "num_frames": 49, "frame_rate": 8,
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

    env_block = get_environment_block(user_id)
    if request.files:
        system_prompt = CHAT_SYSTEM_WITH_FILES + env_block
    elif has_images:
        system_prompt = CHAT_SYSTEM_WITH_IMAGES + env_block
    else:
        system_prompt = CHAT_SYSTEM_BASE + env_block

    # 有文件或图片上传时跳过工具检测，直接将内容传给大模型
    tool_call = None if (request.files or has_images) else detect_tool_intent(request.message)
    if tool_call and tool_call.get("tool") == "generate_pdf":
        # PDF 正文纠偏：避免把"把以上内容生成pdf文件"这类指令解析成正文"文件"，
        # 导致 PDF 里只有"文档/文件"两个字。优先用显式正文或上一轮 AI 回复。
        try:
            _history = session_store.get_messages(user_id, session_id)[-10:] or []
        except Exception:
            _history = []
        _pdf_body = _resolve_pdf_content(request.message, tool_call.get("content") or "", _history)
        if _pdf_body:
            tool_call["content"] = _pdf_body
        else:
            tool_call = None

    def sync_stream_generator():
        """包装内核生成器：统一收集本轮后台生成的产物文件。

        通过在流开始/结束对比用户产物目录的文件名，识别出"本轮新增"的文件，
        随 done 事件下发给前端（对话里可直接点击下载），并挂到本轮助手消息上
        （重开历史会话仍可见）。该方式覆盖脚本/技能/PPT 等所有产出路径。"""
        files_before = script_service.snapshot_generated_names(user_id)
        _files = []
        _attached = False

        def _collect_new_files():
            new_names = script_service.snapshot_generated_names(user_id) - files_before
            return script_service.build_file_entries(user_id, new_names) if new_names else []

        try:
            for chunk in _sync_stream_generator_core():
                if chunk.startswith("data: "):
                    try:
                        payload = json.loads(chunk[6:].strip())
                    except Exception:
                        payload = None
                    if isinstance(payload, dict) and payload.get("done"):
                        _files = _collect_new_files()
                        if _files:
                            session_store.attach_files_to_last_message(user_id, session_id, _files)
                            _attached = True
                            payload['files'] = _files
                            chunk = "data: " + json.dumps(payload) + "\n\n"
                yield chunk
        finally:
            # 客户端中断（GeneratorExit）或未走到 done 的错误路径：
            # 仍把已产出的文件挂到本轮消息，避免"生成了却查不到"
            if not _attached:
                try:
                    _files = _files or _collect_new_files()
                    if _files:
                        session_store.attach_files_to_last_message(user_id, session_id, _files)
                except Exception:
                    pass

    def _sync_stream_generator_core():
        full_response = ""
        tool_result = ""
        token_stats = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        _files_before_core = script_service.snapshot_generated_names(user_id)

        def _final_file_links_block(already_text: str) -> str:
            """本轮新产物中、回复里尚未出现下载链接的文件 → 生成"下载地址 + 在线预览"Markdown 块。
            用于会话结束前兜底：确保回复末尾始终留有文件入口（无缺失则返回空串）。"""
            try:
                _new = script_service.snapshot_generated_names(user_id) - _files_before_core
                if not _new:
                    return ""
                _files = script_service.build_file_entries(user_id, _new)
                _missing = [f for f in _files if f.get("download_url") and f["download_url"] not in already_text]
                if not _missing:
                    return ""
                _lines = ["---", "", "📎 本次生成的文件："]
                for f in _missing:
                    _u = f["download_url"]
                    _dl = _u + ("&" if "?" in _u else "?") + "download=1"
                    _lines.append(f"- [{f.get('name')}]({_dl})（[在线预览]({_u})）")
                return "\n".join(_lines)
            except Exception:
                return ""
        # ===== 三层配额：获取顺序 全局 → 用户 → 会话（失败即拒绝，禁止绕过配额）=====
        if not _global_sem.acquire(timeout=_GLOBAL_ACQUIRE_TIMEOUT):
            yield _busy_event("服务繁忙，请稍后重试", session_id)
            return
        sem = _sem(user_id)
        if not sem.acquire(timeout=30):
            try:
                _global_sem.release()
            except Exception:
                pass
            yield _busy_event("您有过多任务正在处理中，请等待当前任务完成后再试", session_id)
            return
        session_lock = _session_lock(user_id, session_id)
        if not session_lock.acquire(timeout=_SESSION_ACQUIRE_TIMEOUT):
            for _rel in (sem.release, _global_sem.release):
                try:
                    _rel()
                except Exception:
                    pass
            yield _busy_event("该会话已有任务正在处理中，请等待其完成后再发送", session_id)
            return
        # MCP 工具清单 + Agent 编排清单（仅纯文本对话注入；发现失败静默降级）
        mcp_block = ""
        agent_block = ""
        skill_block = ""
        web_search_enabled = False
        web_search_block = ""
        mcp_tools_main: List[Dict[str, Any]] = []
        if not request.files and not has_images:
            try:
                from lobster_mu import mcp_client
                mcp_tools_main = mcp_client.get_enabled_tools(user_id) or []
                mcp_block = _build_mcp_prompt_block(
                    mcp_tools_main,
                    has_login_token=bool(ctx and ctx.get("login_token")),
                )
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
            web_search_block = _build_web_search_prompt_block(
                web_search_enabled, _mcp_has_time_tool(mcp_tools_main))
        # 技能清单始终注入（含带附件/图片的请求——技能常需处理用户上传的文件，
        # 否则模型看不到技能 ID 与标记格式，只会"口头声称"在调用技能）
        try:
            from lobster_mu import skill_store
            skill_block = _build_skill_prompt_block(skill_store.list_enabled(user_id))
        except Exception as _e:
            print(f"[DEBUG] 技能清单发现失败，跳过注入: {_e}")
            skill_block = ""
        ppt_block = _build_ppt_prompt_block(ppt_intent)
        effective_system_prompt = system_prompt + web_search_block + agent_block + mcp_block + skill_block + ppt_block
        try:
            if tool_call:
                tool_name = tool_call.get("tool")
                tool_desc = {"exec": "执行命令", "read_file": "读取文件", "list_dir": "列出目录", "search": "网页搜索",
                             "script_create": "创建脚本", "script_execute": "执行脚本", "script_list": "列出脚本",
                             "generate_pdf": "生成PDF"}.get(tool_name, tool_name)
                # 用户未指定时间时，剔除查询词里模型自行添加的日期/年份
                if tool_name in ("search", "web_search") and tool_call.get("query"):
                    tool_call["query"] = _clean_search_query(
                        tool_call["query"], keep_time=_user_specified_time(request.message))
                tool_header = "\n🔧 正在执行工具: " + tool_desc + "...\n\n"
                yield f"data: {json.dumps({'success': True, 'content': tool_header, 'session_id': session_id})}\n\n"
                yield f"data: {json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': '🔧 正在执行工具 ' + tool_desc + '...'})}\n\n"
                # 后台线程执行工具 + 队列轮询：脚本生成/执行/装依赖的实时状态推给前端
                _tool_q = queue.Queue()
                _tool_holder = {}

                def _tool_status_cb(text):
                    _tool_q.put(text)

                def _tool_run():
                    try:
                        _tool_holder['r'] = tools.execute_tool_call(tool_call, user_id, status_cb=_tool_status_cb)
                    except Exception as _te:
                        _tool_holder['r'] = f"❌ 工具执行异常: {_te}"

                _tool_thread = threading.Thread(target=_tool_run, daemon=True)
                _tool_thread.start()
                while _tool_thread.is_alive():
                    try:
                        st = _tool_q.get(timeout=0.5)
                        yield f"data: {json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': st})}\n\n"
                    except queue.Empty:
                        pass
                while not _tool_q.empty():
                    st = _tool_q.get_nowait()
                    yield f"data: {json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': st})}\n\n"
                tool_result = _tool_holder.get('r', '')
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

            # 知识库：embedding 模型未就绪时异步触发后台加载，不阻塞当前请求
            # （注：经排查「空闲后首请求卡 30 秒」根因在反代网络层，此处仅消除潜在同步阻塞路径）
            knowledge_sources = []
            _kb_model_ready = True
            try:
                import threading as _kb_th
                from lobster_mu import knowledge_store as _ks
                if _ks.user_has_docs(user_id) and not _ks.is_model_ready():
                    _kb_model_ready = False
                    # 后台线程触发 warmup（daemon=True，不阻塞进程退出）
                    def _async_warmup():
                        try:
                            _ks.warmup()
                        except Exception:
                            pass
                    _kb_th.Thread(target=_async_warmup, daemon=True).start()
            except Exception:
                pass
            knowledge_context, knowledge_sources = (
                _knowledge_context(user_id, request.message) if _kb_model_ready else ("", [])
            )

            if tool_result:
                user_content = build_user_content_with_tool_result(
                    request.message, tool_result, summary_context, memory_context, knowledge_context)
            elif request.files:
                user_content = build_user_content_with_files(
                    request.message, "".join(file_info), summary_context, memory_context, knowledge_context)
            elif has_images:
                user_content = build_user_content_with_images(
                    request.message, len(request.images), summary_context, memory_context, knowledge_context)
            else:
                if ppt_intent:
                    user_content = build_user_content_ppt(
                        request.message, summary_context, memory_context, knowledge_context)
                else:
                    user_content = build_user_content_default(
                        request.message, summary_context, memory_context, knowledge_context)

            messages = adapter.create_prompt_with_images(system_prompt, user_content, context, request.images) if has_images else adapter.create_prompt(effective_system_prompt, user_content, context)

            # 超长输入保护：按模型上下文窗口截断，避免 400 InvalidParameter（输入超长）
            try:
                cw = _get_model_context_window(request.model_name)
                budget = max(4000, int(cw * 0.9))  # 预留输出与模板开销
                messages = _trim_messages_to_budget(messages, budget)
            except Exception:
                pass

            # ============ 双轨路由：ReAct（function calling）优先，失败/未启用回退标记路径 ============
            react_enabled = str(db_get_config("agent_react_enabled", "false")).lower() in ("1", "true", "yes")
            dual_track = str(db_get_config("agent_dual_track", "true")).lower() in ("1", "true", "yes")
            _use_react = (
                not request.files and not has_images and react_enabled and dual_track
                and getattr(adapter, "supports_tools", lambda: False)()
            )
            # 模型若仍输出旧方括号标记，则丢弃本次 ReAct 流式内容，改走下文的标记执行分支
            _react_marker_fallback = False
            if _use_react:
                try:
                    from lobster_mu.agent import TOOL_REGISTRY, ReActLoop, get_tool_schema_list

                    max_steps = int(db_get_config("agent_max_steps", "3") or "3")
                    # 注意：不可命名为 tools，会遮蔽模块级 tools 导入
                    tool_schemas = get_tool_schema_list()
                    ctx_local = {"user_id": user_id, "session_id": session_id}
                    loop = ReActLoop(adapter, tool_schemas, TOOL_REGISTRY, user_id, ctx_local, max_steps=max_steps)

                    # 标记模式的说明仍留在 system prompt 中，这里追加最高优先级指令消解冲突
                    _react_directive = REACT_TOOL_DIRECTIVE
                    if messages and messages[0].get("role") == "system":
                        messages[0]["content"] = str(messages[0].get("content", "")) + _react_directive

                    # ReAct 流的正文同样要过标记过滤器，避免标记文本直接暴露给用户
                    _rf_ppt = _MarkerFilter("[PPT_GEN]", "[/PPT_GEN]")
                    _rf_skill = _MarkerFilter("[SKILL_CALL]", "[/SKILL_CALL]")
                    _rf_mcp = _McpMarkerFilter()
                    _rf_agent = _AgentMarkerFilter()
                    _rf_ws = _WebSearchMarkerFilter()

                    def _rf_feed(chunk: str) -> str:
                        return _rf_ws.feed(_rf_agent.feed(_rf_mcp.feed(_rf_skill.feed(_rf_ppt.feed(chunk)))))

                    def _rf_flush() -> str:
                        return _rf_ws.feed(
                            _rf_agent.feed(_rf_mcp.feed(_rf_skill.feed(_rf_ppt.flush())))
                        ) + _rf_ws.flush()

                    _legacy_markers = ("[NEED_SCRIPT]", "[SKILL_CALL]", "[AGENT_CALL]",
                                       "[MCP_CALL]", "[PPT_GEN]", "[WEB_SEARCH]")

                    react_result = None
                    for evt in loop.run(messages):
                        etype = evt.get("type")
                        if etype == "content":
                            c = evt.get("content", "")
                            if c:
                                full_response += c
                                safe_react = _rf_feed(c)
                                if safe_react:
                                    yield "data: " + json.dumps({'success': True, 'content': safe_react, 'session_id': session_id}) + "\n\n"
                        elif etype == "thinking":
                            # 中间步骤的思考过程，推送给前端折叠展示
                            yield "data: " + json.dumps({
                                'success': True,
                                'session_id': session_id,
                                'type': 'thinking',
                                'content': evt.get("content", ""),
                            }) + "\n\n"
                        elif etype == "status":
                            # 思考/工具执行状态文本，推送给前端展示"后台正在运行"的反馈
                            yield "data: " + json.dumps({
                                'success': True,
                                'session_id': session_id,
                                'type': 'status',
                                'text': evt.get("text", ""),
                            }) + "\n\n"
                        elif etype == "confirm":
                            yield "data: " + json.dumps({
                                'success': True,
                                'session_id': session_id,
                                'type': 'confirm',
                                'request_id': evt.get("request_id"),
                                'summary': evt.get("summary"),
                                'meta': evt.get("meta"),
                            }) + "\n\n"
                        elif etype == "plan":
                            yield "data: " + json.dumps({
                                'success': True,
                                'session_id': session_id,
                                'type': 'plan',
                                'title': evt.get("title"),
                                'steps': evt.get("steps"),
                            }) + "\n\n"
                        elif etype == "tool_progress":
                            # 工具执行过程事件（脚本生成/沙箱执行/输出），前端折叠展示
                            yield "data: " + json.dumps({
                                'success': True,
                                'session_id': session_id,
                                'type': 'tool_progress',
                                'stage': evt.get("stage", ""),
                                'text': evt.get("text", ""),
                                'name': evt.get("name", ""),
                                'desc': evt.get("desc", ""),
                                'code': evt.get("code", ""),
                                'truncated': evt.get("truncated", False),
                                'output': evt.get("output", ""),
                                'error': evt.get("error", ""),
                                'files': evt.get("files", []),
                                'stage_success': evt.get("success", None),
                            }) + "\n\n"
                        elif etype == "reclassify":
                            # 中间步骤：把已发的 content 修正为 thinking（前端折叠展示）
                            yield "data: " + json.dumps({
                                'success': True,
                                'session_id': session_id,
                                'type': 'reclassify',
                                'from': evt.get("from", "content"),
                                'to': evt.get("to", "thinking"),
                            }) + "\n\n"
                        elif etype == "done":
                            react_result = evt.get("result")
                            break

                    _react_tail = _rf_flush()
                    if _react_tail:
                        yield "data: " + json.dumps({'success': True, 'content': _react_tail, 'session_id': session_id}) + "\n\n"

                    if any(tok in full_response for tok in _legacy_markers):
                        # 模型没有走 function calling，而是输出了旧标记：
                        # 丢弃本次输出，交给下方原有的标记执行分支真正执行
                        _react_marker_fallback = True
                        print("[ReAct] 检测到旧标记输出，回退到标记执行路径")

                    if not _react_marker_fallback:
                        if react_result is not None:
                            token_stats = react_result.token_stats or token_stats
                        # 会话结束兜底：回复末尾补齐本轮产物中模型未引用的"下载地址 + 在线预览"链接
                        _react_saved = script_service.strip_invalid_download_links(
                            user_id, _strip_think_tags(full_response))
                        _lk = _final_file_links_block(_react_saved)
                        if _lk:
                            _react_saved = _react_saved.rstrip() + "\n\n" + _lk
                            yield "data: " + json.dumps({'success': True, 'content': "\n\n" + _lk + "\n", 'session_id': session_id}) + "\n\n"
                        # 保存 AI 回复到数据库（ReAct 路径直接 return，不会走到下方常规保存逻辑）
                        session_store.append_message(user_id, session_id, "assistant", _react_saved,
                                                     model_name=getattr(adapter, "model_name", None),
                                                     token_stats=token_stats)
                        done_event = {'success': True, 'content': '', 'session_id': session_id, 'done': True,
                                      'model_name': adapter.model_name, 'token_stats': token_stats}
                        yield "data: " + json.dumps(done_event) + "\n\n"
                        return  # finally 会释放三层配额
                except Exception as e:
                    yield "data: " + json.dumps({'success': True, 'content': f"⚠️ ReAct 路径异常，回退常规模式：{str(e)[:120]}\n\n", 'session_id': session_id}) + "\n\n"
                    _use_react = False

            mcp_filter = _McpMarkerFilter()
            agent_filter = _AgentMarkerFilter()
            ws_filter = _WebSearchMarkerFilter()
            ppt_filter = _MarkerFilter("[PPT_GEN]", "[/PPT_GEN]")
            skill_filter = _MarkerFilter("[SKILL_CALL]", "[/SKILL_CALL]")
            if ppt_intent:
                yield "data: " + json.dumps({'success': True, 'content': "📊 正在处理您的 PPT 请求...\n\n", 'session_id': session_id}) + "\n\n"
            # PPT 大纲 JSON 较长，提高输出上限避免截断（openai 适配器不限制，claude/deepseek 默认2000）
            stream_kwargs = {"max_tokens": 8000} if ppt_intent else {}
            # ReAct 已产出旧标记时不再重复调用模型，直接用其输出做标记执行
            _think_filter = _ThinkTagFilter()
            _file_filter = _FileLinkFilter(user_id)
            # 文件生成请求下，模型不应对着用户贴代码；代码块会含"文件已生成"等误导文案，直接不展示
            _code_filter = _InlineCodeDropFilter(
                enabled=bool(_looks_like_file_request(request.message)
                             or _is_continue_generation_request(request.message, context)))
            if _react_marker_fallback:
                _stream_iter = iter(())
            else:
                # 首个 token 之前的空窗期：先给用户一个明确的"思考中"状态
                yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': '🧠 模型思考中…'}) + "\n\n"
                try:
                    _stream_iter = adapter.chat_stream(messages, include_reasoning=True, **stream_kwargs)
                except TypeError:
                    _stream_iter = adapter.chat_stream(messages, **stream_kwargs)
            for chunk in _stream_iter:
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
                # 思考模型的推理内容旁路 chunk：转发为 thinking 事件（前端折叠展示）
                if content and content.startswith("{\"__think__\""):
                    try:
                        _tk = json.loads(content).get("__think__", "")
                    except Exception:
                        _tk = ""
                    if _tk:
                        yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'thinking', 'content': _tk}) + "\n\n"
                    continue
                if content and not content.startswith("{\"__stats__"):
                    full_response += content
                    # 先剥离内联 <think> 块（部分模型把思考写在正文里）
                    visible_text, think_text = _think_filter.feed(content)
                    if think_text:
                        yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'thinking', 'content': think_text}) + "\n\n"
                    if not visible_text:
                        continue
                    # 串联过滤：PPT → SKILL → AGENT → MCP → WEB_SEARCH → 产物链接真实性 → 内联代码块
                    safe_content = ws_filter.feed(agent_filter.feed(mcp_filter.feed(skill_filter.feed(ppt_filter.feed(visible_text)))))
                    safe_content = _file_filter.feed(safe_content)
                    safe_content = _code_filter.feed(safe_content)
                    if safe_content:
                        yield f"data: {json.dumps({'success': True, 'content': safe_content, 'session_id': session_id})}\n\n"

            # 首流结束：先冲刷 think 过滤器，再冲刷标记过滤器残留
            tail_visible, tail_think = _think_filter.flush()
            if tail_think:
                yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'thinking', 'content': tail_think}) + "\n\n"
            tail = ws_filter.feed(agent_filter.feed(mcp_filter.feed(skill_filter.feed(ppt_filter.feed(tail_visible))))) + ws_filter.flush()
            tail = _file_filter.feed(tail) + _file_filter.flush()
            tail = _code_filter.feed(tail) + _code_filter.flush()
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
            # 兜底：用户明确要求产出文件但模型漏了 [NEED_SCRIPT]（只贴代码/只说已生成）时，也强制走脚本执行
            # PDF 工具已成功产出文件时，不再走脚本分支重复生成（否则会多跑一遍脚本，
            # 且脚本里常出现未注册字体样式等问题，把报错栈混进最终回复）
            _tool_pdf_ok = bool(
                tool_call and tool_call.get("tool") == "generate_pdf"
                and isinstance(tool_result, str) and "✅ PDF文件已生成" in tool_result
            )
            _wants_file = (not request.files and not has_images and not ppt_intent
                           and "[PPT_GEN]" not in full_response
                           and not _tool_pdf_ok
                           and not any(m in full_response for m in ("[SKILL_CALL]", "[AGENT_CALL]", "[MCP_CALL]", "[WEB_SEARCH]")))
            _need_script = "[NEED_SCRIPT]" in full_response and not _tool_pdf_ok
            if _tool_pdf_ok:
                full_response = full_response.replace("[NEED_SCRIPT]", "").strip()
            # 本轮已有新产物（如 ReAct 已执行脚本/技能）时不再重复生成
            _force_script = (_wants_file and not (script_service.snapshot_generated_names(user_id) - _files_before_core)
                             and (_looks_like_file_request(request.message)
                                  or _is_continue_generation_request(request.message, context)))
            if not request.files and not has_images and "[PPT_GEN]" not in full_response and (
                    _need_script or _force_script):
                _trace_marker(user_id, session_id, "run_python_script", "[NEED_SCRIPT] 标记触发脚本生成")
                full_response = full_response.replace("[NEED_SCRIPT]", "").strip()
                if not _need_script:
                    # 模型没有走脚本流程，它输出的"文件名/下载地址/已生成"都不可信，直接丢弃；
                    # 但其中已整理好的正文内容保留给脚本生成器，避免重新生成或产出占位内容
                    _draft = _strip_inline_code_blocks(
                        script_service.strip_invalid_download_links(user_id, full_response))
                    yield "data: " + json.dumps({'success': True, 'content': '🔧 检测到文件生成需求，改为实际执行脚本产出文件。\n\n', 'session_id': session_id}) + "\n\n"
                    full_response = ""
                    script_task = _script_task_with_context(request.message, context)
                    if _draft.strip():
                        script_task += SCRIPT_DRAFT_APPENDIX_HEADER + _draft[:6000]
                else:
                    # 清掉模型自行编造/未经验证的产物下载链接与内联代码块
                    full_response = script_service.strip_invalid_download_links(user_id, full_response)
                    full_response = _strip_inline_code_blocks(full_response)
                    script_task = _script_task_with_context(request.message, context)
                yield "data: " + json.dumps({'success': True, 'content': '\n\n🔧 检测到需要编写脚本完成任务，正在生成...\n', 'session_id': session_id}) + "\n\n"
                yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': '📝 正在生成脚本代码...'}) + "\n\n"

                script_code, script_name, script_desc = script_service.generate_script_code(script_task)
                if script_code:
                    yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': '✅ 脚本生成完成，正在检查语法...'}) + "\n\n"
                    syntax_result = script_service.check_script_syntax(script_code)
                    # 语法错误自动修复：把错误与代码回喂模型修复，最多 2 轮，避免一次语法错误直接中断会话
                    _fix_round = 0
                    while not syntax_result["success"] and _fix_round < 2:
                        _fix_round += 1
                        yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': f'⚠️ 检测到脚本语法错误，正在自动修复（第 {_fix_round} 次）...'}) + "\n\n"
                        _fixed_code = script_service.fix_script_code(
                            script_code, syntax_result.get("error", ""), script_task
                        )
                        if not _fixed_code or _fixed_code.strip() == script_code.strip():
                            break
                        script_code = _fixed_code
                        syntax_result = script_service.check_script_syntax(script_code)
                    if syntax_result["success"]:
                        script_service.save_script_to_file(user_id, script_name, script_code)
                        script_service.create_script(user_id, script_name, script_code, description=script_desc, is_approved=True)
                        script_info = '✅ 脚本已生成并保存到脚本库\n📝 脚本: ' + script_name + '（' + script_desc + '）\n\n正在执行...\n'
                        yield "data: " + json.dumps({'success': True, 'content': script_info, 'session_id': session_id}) + "\n\n"

                        # 后台线程执行脚本，队列轮询转发实时状态（依赖安装等长操作不静默）
                        _status_q = queue.Queue()
                        _exec_holder = {}

                        def _exec_status_cb(text):
                            _status_q.put(text)

                        def _exec_run():
                            try:
                                _exec_holder['r'] = script_service.execute_python_script(
                                    user_id, script_code, status_cb=_exec_status_cb
                                )
                            except Exception as _ee:
                                _exec_holder['r'] = {"success": False, "result": f"❌ 执行错误: {_ee}", "generated_files": []}

                        _exec_thread = threading.Thread(target=_exec_run, daemon=True)
                        _exec_thread.start()
                        while _exec_thread.is_alive():
                            try:
                                st = _status_q.get(timeout=0.5)
                                _st_text = (st.get('text') or st.get('line') or '') if isinstance(st, dict) else str(st)
                                yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': _st_text}) + "\n\n"
                            except queue.Empty:
                                pass
                        while not _status_q.empty():
                            st = _status_q.get_nowait()
                            _st_text = (st.get('text') or st.get('line') or '') if isinstance(st, dict) else str(st)
                            if not _st_text:
                                continue
                            yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': _st_text}) + "\n\n"
                        exec_result = _exec_holder.get('r') or {"success": False, "result": "❌ 脚本执行异常中断", "generated_files": []}
                        exec_result_str = exec_result.get("result", "") if isinstance(exec_result, dict) else str(exec_result)
                        _exec_ok = bool(exec_result.get("success")) if isinstance(exec_result, dict) else False
                        # 产物文件：只有"执行成功 + 文件真实存在且非空"才下发下载链接，
                        # 避免脚本失败/空文件时仍向用户展示文件名和下载地址
                        _gen_files = (exec_result.get("generated_files") or []) if isinstance(exec_result, dict) else []
                        _gen_files = script_service.filter_existing_files(user_id, _gen_files) if _exec_ok else []
                        # 用户要求产出文件却没有检测到任何产物：视为生成失败，不能向用户宣称成功
                        _expect_files = (_looks_like_file_request(request.message)
                                         or _is_continue_generation_request(request.message, context))
                        if _exec_ok and _expect_files and not _gen_files:
                            _exec_ok = False
                            exec_result_str = (exec_result_str.rstrip()
                                               + "\n\n⚠️ 未检测到任何产物文件：文件生成未成功。").strip()
                        if _gen_files:
                            _link_lines = ["", "📎 生成的文件（点击可直接打开）："]
                            for _f in _gen_files:
                                _link_lines.append(f"- [{_f.get('original_name') or _f.get('name')}]({_f.get('download_url')})")
                            _link_md = "\n".join(_link_lines)
                            yield "data: " + json.dumps({'success': True, 'content': _link_md + "\n", 'session_id': session_id}) + "\n\n"
                            exec_result_str = (exec_result_str.rstrip() + "\n" + _link_md).strip()

                        yield "data: " + json.dumps({'success': True, 'content': '📋 执行结果:\n\n', 'session_id': session_id}) + "\n\n"
                        interpret_prompt = build_script_interpret_prompt(
                            request.message, script_name, script_desc, _exec_ok, exec_result_str)
                        interpret_messages = adapter.create_prompt(
                            SCRIPT_INTERPRET_SYSTEM,
                            interpret_prompt, []
                        )
                        _interp_filter = _FileLinkFilter(user_id)
                        _interp_code = _InlineCodeDropFilter(True)
                        _interp_text = ""
                        for chunk in adapter.chat_stream(interpret_messages):
                            if isinstance(chunk, dict):
                                content = chunk.get("content", "")
                            else:
                                content = str(chunk)
                            if content and not content.startswith("{\"__stats__\""):
                                _safe = _interp_code.feed(_interp_filter.feed(content))
                                if _safe:
                                    _interp_text += _safe
                                    yield "data: " + json.dumps({'success': True, 'content': _safe, 'session_id': session_id}) + "\n\n"
                        _tail_parts = [x for x in (_interp_filter.flush(), _interp_code.flush()) if x]
                        _interp_tail = "\n".join(_tail_parts)
                        if _interp_tail:
                            _interp_text += _interp_tail
                            yield "data: " + json.dumps({'success': True, 'content': _interp_tail, 'session_id': session_id}) + "\n\n"
                        full_response = (full_response + "\n\n" + _interp_text).strip()
                        full_response = full_response + "\n\n📋 脚本执行结果:\n" + exec_result_str
                    else:
                        _err_detail = str(syntax_result.get("error") or "未知语法错误")
                        error_msg = ('❌ 脚本生成失败：语法错误，自动修复仍未通过。\n\n'
                                     f'错误信息：{_err_detail[:600]}\n\n'
                                     '💡 建议：把需求拆成更具体的步骤后重新发送，或稍后重试。')
                        yield "data: " + json.dumps({'success': True, 'content': error_msg, 'session_id': session_id}) + "\n\n"
                        full_response = (full_response + "\n\n" + error_msg).strip()
                else:
                    _gen_fail = '❌ 脚本生成失败，请重试'
                    yield "data: " + json.dumps({'success': True, 'content': _gen_fail, 'session_id': session_id}) + "\n\n"
                    full_response = (full_response + "\n\n" + _gen_fail).strip()

            # ============ 多Agent编排分支 ============
            if not request.files and not has_images and "[AGENT_CALL]" in full_response:
                _trace_marker(user_id, session_id, "delegate_agent", "[AGENT_CALL] 标记触发子 Agent")
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
                    interpret_prompt = build_agent_interpret_prompt(request.message, agent_summary)
                    interpret_messages = adapter.create_prompt(
                        AGENT_INTERPRET_SYSTEM,
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

            # ============ PPT 生成分支（技能调用优先：含 [SKILL_CALL] 时不走内置渲染） ============
            if not request.files and not has_images and "[PPT_GEN]" in full_response and "[SKILL_CALL]" not in full_response:
                _trace_marker(user_id, session_id, "generate_ppt", "[PPT_GEN] 标记触发 PPT 生成")
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
                    yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': '📊 正在生成 PPT（渲染幻灯片，可能需要 1-2 分钟）...'}) + "\n\n"
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
                _trace_marker(user_id, session_id, "web_search", "[WEB_SEARCH] 标记触发联网搜索")
                search_query = _clean_search_query(
                    _parse_web_search(full_response),
                    keep_time=_user_specified_time(request.message))
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
                            interpret_prompt = build_web_search_interpret_prompt(
                                request.message, search_summary)
                            interpret_messages = adapter.create_prompt(
                                WEB_SEARCH_INTERPRET_SYSTEM,
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
                                    safe = _clean_md_link_urls(ws_secondary.feed(mcp_secondary.feed(content)))
                                    ws_final += safe
                                    if safe:
                                        yield "data: " + json.dumps({'success': True, 'content': safe, 'session_id': session_id}) + "\n\n"
                            ws_final += ws_secondary.feed(mcp_secondary.flush()) + ws_secondary.flush()
                            if ws_final.strip():
                                full_response = _clean_md_link_urls(ws_final.strip())
                        else:
                            yield "data: " + json.dumps({'success': True, 'content': "⚠️ 未搜索到有效结果，将基于已有知识回答\n\n", 'session_id': session_id}) + "\n\n"
                    else:
                        yield "data: " + json.dumps({'success': True, 'content': "⚠️ 未获得搜索结果，将基于已有知识回答\n\n", 'session_id': session_id}) + "\n\n"

            # ============ MCP 外部工具调用分支 ============
            if not request.files and not has_images and "[MCP_CALL]" in full_response:
                _trace_marker(user_id, session_id, "call_mcp_tool", "[MCP_CALL] 标记触发 MCP 工具")
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
                    yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': f'🔌 正在调用 MCP 工具 {label}...'}) + "\n\n"
                    call_args = _inject_ctx(call["arguments"] or {}, ctx)
                    mcp_res = mcp_client.call_tool(user_id, call["server"], call["tool"], call_args)
                    if mcp_res.get("success"):
                        result_text = mcp_res.get("result") or ""
                        yield "data: " + json.dumps({'success': True, 'content': f"📋 MCP 工具 {label} 调用成功，正在整理结果...\n\n", 'session_id': session_id}) + "\n\n"
                        mcp_result_blocks.append(
                            f"[调用 {idx}] 工具: {label}\n参数: {json.dumps(call['arguments'], ensure_ascii=False)[:500]}\n"
                            f"结果:\n{result_text[:20000]}"
                        )
                    else:
                        err = mcp_res.get("error") or "未知错误"
                        yield "data: " + json.dumps({'success': True, 'content': f"❌ MCP 工具 {label} 调用失败: {err}\n\n", 'session_id': session_id}) + "\n\n"
                        mcp_result_blocks.append(f"[调用 {idx}] 工具: {label}\n调用失败: {err}")

                if mcp_result_blocks:
                    mcp_summary = "\n\n".join(mcp_result_blocks)
                    interpret_prompt = build_mcp_interpret_prompt(request.message, mcp_summary)
                    interpret_messages = adapter.create_prompt(
                        MCP_INTERPRET_SYSTEM,
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

            # ============ 技能(Skill)调用分支（允许带附件：技能常需处理用户上传的文件） ============
            if "[SKILL_CALL]" in full_response:
                _trace_marker(user_id, session_id, "run_skill", "[SKILL_CALL] 标记触发技能调用")
                from lobster_mu import skill_store
                skill_calls = _parse_skill_calls(full_response)
                full_response = SKILL_CALL_PATTERN.sub("", full_response).strip()
                skill_result_blocks = []
                for idx, call in enumerate(skill_calls, 1):
                    if not call.get("raw_ok"):
                        err_msg = f"第 {idx} 个技能调用标记格式错误（不是合法 JSON），已跳过。"
                        yield "data: " + json.dumps({'success': True, 'content': f"⚠️ {err_msg}\n\n", 'session_id': session_id}) + "\n\n"
                        skill_result_blocks.append(f"[技能 {idx}] 失败: {err_msg}")
                        continue
                    sid = call["skill_id"]
                    _skill_obj = skill_store.resolve(user_id, sid)
                    sname = (_skill_obj or {}).get("name") or sid
                    yield "data: " + json.dumps({'success': True, 'content': f"\n🔧 正在执行技能: {sname}（多步骤技能可能需要几分钟，下方为实时进度）\n", 'session_id': session_id}) + "\n\n"
                    yield "data: " + json.dumps({'success': True, 'session_id': session_id, 'type': 'status', 'text': f'🧩 正在执行技能 {sname}...'}) + "\n\n"
                    # 注入原始请求与附件文本作为技能素材（模型 params 通常只给主题，缺实际内容）
                    call_params = dict(call.get("params") or {})
                    _material_parts = []
                    if request.message:
                        _material_parts.append("用户需求: " + request.message)
                    if file_info:
                        _material_parts.append("附件内容:\n" + "".join(file_info))
                    if _material_parts and "_material" not in call_params:
                        call_params["_material"] = "\n\n".join(_material_parts)
                    # 后台线程执行技能 + 队列轮询：代理循环每步的执行情况实时推给前端
                    import queue as _queue
                    import threading as _threading
                    progress_q = _queue.Queue()

                    def _emit_progress(text):
                        try:
                            progress_q.put(str(text))
                        except Exception:
                            pass

                    _holder = {}

                    def _run_skill():
                        try:
                            _holder['res'] = skill_store.execute(user_id, sid, call_params, _emit_progress)
                        except Exception as _e:
                            _holder['res'] = {"success": False, "error": f"技能执行异常: {_e}"}

                    _t = _threading.Thread(target=_run_skill, daemon=True)
                    _t.start()

                    def _sse(msg):
                        return "data: " + json.dumps({'success': True, 'content': msg, 'session_id': session_id}) + "\n\n"
                    while _t.is_alive():
                        try:
                            yield _sse(progress_q.get(timeout=0.5))
                        except _queue.Empty:
                            pass
                    while not progress_q.empty():
                        yield _sse(progress_q.get_nowait())
                    res = _holder.get('res') or {"success": False, "error": "技能执行未返回结果"}
                    if res.get("success"):
                        _n_files = len(res.get("generated_files") or [])
                        _done = f"📋 技能 {sname} 执行完成" + (f"，生成 {_n_files} 个产物文件" if _n_files else "") + "。\n\n"
                        yield _sse(_done)
                        skill_result_blocks.append(
                            f"[技能 {idx}] {sname} (id={sid})\n参数: {json.dumps(call.get('params') or {}, ensure_ascii=False)[:500]}\n"
                            f"结果:\n{str(res.get('result', ''))[:4000]}"
                        )
                    else:
                        err = res.get("error") or "未知错误"
                        yield _sse(f"❌ 技能 {sname} 执行失败: {err}\n\n")
                        skill_result_blocks.append(f"[技能 {idx}] {sname} (id={sid})\n执行失败: {err}")
                if skill_result_blocks:
                    skill_summary = "\n\n".join(skill_result_blocks)
                    # 把技能执行结果实时流式输出（此前仅入库，导致需刷新才可见），
                    # 并做一次二次生成，让最终回答自然呈现且与入库内容一致。
                    interpret_prompt = build_skill_interpret_prompt(request.message, skill_summary)
                    interpret_messages = adapter.create_prompt(
                        SKILL_INTERPRET_SYSTEM,
                        interpret_prompt, []
                    )
                    skill_final = ""
                    _skill_file_filter = _FileLinkFilter(user_id)
                    for chunk in adapter.chat_stream(interpret_messages):
                        if isinstance(chunk, dict):
                            content = chunk.get("content", "")
                        else:
                            content = str(chunk)
                        if content and not content.startswith("{\"__stats__\""):
                            _safe = _skill_file_filter.feed(content)
                            if _safe:
                                skill_final += _safe
                                yield "data: " + json.dumps({'success': True, 'content': _safe, 'session_id': session_id}) + "\n\n"
                    _skill_tail = _skill_file_filter.flush()
                    if _skill_tail:
                        skill_final += _skill_tail
                        yield "data: " + json.dumps({'success': True, 'content': _skill_tail, 'session_id': session_id}) + "\n\n"
                    if skill_final.strip():
                        full_response = skill_final.strip()
                    else:
                        # 二次生成无输出时，退化为直接展示原始结果（仍需推给前端）
                        fallback = "\n\n" + skill_summary
                        full_response = (full_response + fallback).strip()
                        yield "data: " + json.dumps({'success': True, 'content': fallback, 'session_id': session_id}) + "\n\n"

            # 安全网：剥除任何残留标记（闭合块/未闭合片段），不进入最终答复与历史
            full_response = AGENT_CALL_PATTERN.sub("", full_response)
            full_response = MCP_CALL_PATTERN.sub("", full_response)
            full_response = SKILL_CALL_PATTERN.sub("", full_response)
            full_response = WEB_SEARCH_PATTERN.sub("", full_response)
            full_response = PPT_GEN_PATTERN.sub("", full_response)
            full_response = re.sub(r"\[AGENT_CALL\].*$", "", full_response, flags=re.DOTALL)
            full_response = re.sub(r"\[MCP_CALL\].*$", "", full_response, flags=re.DOTALL)
            full_response = re.sub(r"\[SKILL_CALL\].*$", "", full_response, flags=re.DOTALL)
            full_response = re.sub(r"\[WEB_SEARCH\].*$", "", full_response, flags=re.DOTALL)
            full_response = re.sub(r"\[PPT_GEN\].*$", "", full_response, flags=re.DOTALL).strip()
            # 入库前剥离内联 <think> 思考块，避免历史记录混入思考原文
            full_response = _strip_think_tags(full_response)
            # 剥离引用了不存在产物的下载链接（模型自造的文件名/地址），保证历史与展示一致
            full_response = script_service.strip_invalid_download_links(user_id, full_response)
            final_response = full_response
            if tool_result:
                final_response = f"🔧 工具执行结果:\n{tool_result}\n\n---\n\n{full_response}"

            # 会话结束兜底：回复末尾补齐本轮产物中模型未引用的"下载地址 + 在线预览"链接，
            # 确保用户要求生成的文件在会话结束后始终留有文件入口
            _lk = _final_file_links_block(final_response)
            if _lk:
                final_response = final_response.rstrip() + "\n\n" + _lk
                yield "data: " + json.dumps({'success': True, 'content': "\n\n" + _lk + "\n", 'session_id': session_id}) + "\n\n"

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
            # ===== 三层配额释放：顺序与会话/用户/全局相反（会话 → 用户 → 全局）=====
            for _rel in (session_lock.release, sem.release, _global_sem.release):
                try:
                    _rel()
                except Exception:
                    pass

    # ===== 与客户端连接解耦 =====
    # 生成过程放到独立线程，SSE 只负责把队列中的事件转发给当前连接。
    # 这样即使用户切换会话、新建会话或断开页面，后台仍会完整执行并把消息、
    # 产物与执行轨迹落库；用户回到会话即可看到完整结果，不会再"停在半截且查不到日志"。
    _event_q: "queue.Queue" = queue.Queue(maxsize=500)
    _conn = {'closed': False}

    def _producer():
        mark_session_running(session_id)
        try:
            for chunk in sync_stream_generator():
                if _conn['closed']:
                    continue
                try:
                    _event_q.put(chunk, timeout=1)
                except queue.Full:
                    # 连接侧积压（客户端已断开）：丢弃转发，但继续执行到底
                    pass
        except Exception as e:
            if not _conn['closed']:
                try:
                    _event_q.put(f"data: {json.dumps({'success': False, 'error': str(e), 'session_id': session_id})}\n\n", timeout=1)
                except Exception:
                    pass
        finally:
            mark_session_done(session_id)
            try:
                _event_q.put(None, timeout=1)
            except Exception:
                pass

    def _sse():
        threading.Thread(target=_producer, daemon=True).start()
        try:
            while True:
                try:
                    item = _event_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if item is None:
                    break
                yield item
        finally:
            # 连接已断开：停止入队（丢弃转发），但生成线程继续跑到底
            _conn['closed'] = True

    return StreamingResponse(_sse(), media_type="text/event-stream")


def chat_message_once(user_id: int, request: ChatMessageRequest) -> dict:
    """非流式聊天"""
    adapter = get_default_llm_adapter()
    if not adapter:
        return {"success": False, "error": "未找到可用的LLM适配器"}
    session_id = session_store.get_or_create_session(user_id, request.session_id)
    try:
        env_block = get_environment_block(user_id)
        system_prompt = CHAT_SYSTEM_ONCE + env_block
        context = session_store.get_messages(user_id, session_id)[-10:] or []
        messages = adapter.create_prompt(system_prompt, request.message, context)
        response = adapter.chat(messages)
        content = response.content
        session_store.append_message(user_id, session_id, "user", request.message)
        session_store.append_message(user_id, session_id, "assistant", content)
        return {"success": True, "content": content, "session_id": session_id}
    except Exception as e:
        return {"success": False, "error": str(e)}
