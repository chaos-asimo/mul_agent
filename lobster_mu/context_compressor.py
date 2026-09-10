# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 会话上下文压缩

窗口策略：近期消息（WINDOW 条）保持原文进入对话；窗口外的更早历史在累计超过
COMPRESS_THRESHOLD 条时，用 LLM 增量压缩为摘要（连同上次摘要一起），持久化到
mu_session_summaries，之后每轮作为"历史对话摘要"注入，从而在有限上下文里保留
更多有效信息。任何失败静默降级为不注入摘要，不阻断聊天流。
"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple

from lobster_mu.db import get_conn

logger = logging.getLogger(__name__)

# 与聊天流保持一致：近期原文窗口大小
WINDOW = 10
# 窗口外未压缩消息累计达到该条数才触发一次 LLM 压缩，避免频繁调用
COMPRESS_THRESHOLD = 20
# 库内每会话保留的消息上限（与 session_store.MAX_CHAT_HISTORY 一致）
MAX_LOOKBACK = 50
# 压缩输入时每条消息内容截断长度
_PER_MSG_LIMIT = 200
# 摘要最大长度
_SUMMARY_LIMIT = 800

_COMPRESS_SYSTEM = (
    "你是对话摘要助手。请把历史对话压缩成一份简洁摘要（不超过500字），"
    "重点保留：用户的需求与偏好、已确认的关键决定、重要事实与结论、未完成的待办。"
    "直接输出摘要正文，不要任何解释或开场白。"
)


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def get_summary(user_id: int, session_id: str) -> Dict[str, Any]:
    """读取会话已有摘要；无则返回 None"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM mu_session_summaries WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def _upsert_summary(user_id: int, session_id: str, summary: str, covered_until_id: int):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO mu_session_summaries (user_id, session_id, summary, covered_until_id, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(session_id) DO UPDATE SET"
            " summary = excluded.summary, covered_until_id = excluded.covered_until_id,"
            " updated_at = excluded.updated_at",
            (user_id, session_id, summary, covered_until_id, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def delete_summary(user_id: int, session_id: str):
    """删除会话摘要（删除会话/清空时调用）"""
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM mu_session_summaries WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def _load_messages(user_id: int, session_id: str) -> List[Dict[str, Any]]:
    """取库内最近 MAX_LOOKBACK 条消息（升序，含 id）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, role, content FROM mu_chat_messages"
            " WHERE session_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, user_id, MAX_LOOKBACK),
        ).fetchall()
    finally:
        conn.close()
    return [{"id": r["id"], "role": r["role"], "content": r["content"] or ""}
            for r in reversed(rows)]


def _compress(user_id: int, session_id: str, adapter, prev_summary: str,
              msgs: List[Dict[str, Any]]) -> str:
    """调用 LLM 压缩：上次摘要 + 未覆盖消息 → 新摘要"""
    lines = []
    for m in msgs:
        content = m["content"].strip().replace("\n", " ")[:_PER_MSG_LIMIT]
        if not content:
            continue
        who = "用户" if m["role"] == "user" else "AI"
        lines.append(f"{who}: {content}")
    if not lines:
        return prev_summary
    prompt = ""
    if prev_summary:
        prompt += f"上一份摘要：\n{prev_summary[:_SUMMARY_LIMIT]}\n\n"
    prompt += "请在上份摘要基础上，合并以下新增对话，输出更新后的完整摘要：\n" + "\n".join(lines)
    resp = adapter.chat(adapter.create_prompt(_COMPRESS_SYSTEM, prompt, []))
    text = resp.get("content", "") if isinstance(resp, dict) else getattr(resp, "content", "") or ""
    text = (text or "").strip()
    return text[:_SUMMARY_LIMIT] if text else prev_summary


def build_context(user_id: int, session_id: str, adapter) -> Tuple[List[Dict[str, Any]], str]:
    """构建聊天上下文。返回 (近期原文消息, 摘要注入文本)。

    - 近期 WINDOW 条保持原文（role/content 结构与聊天流兼容）
    - 窗口外消息累计超阈值时增量压缩并持久化；摘要以提示词段落形式返回
    """
    summary_text = ""
    context: List[Dict[str, Any]] = []
    try:
        msgs = _load_messages(user_id, session_id)
        if not msgs:
            return [], ""
        context = [{"role": m["role"], "content": m["content"]} for m in msgs[-WINDOW:]]
        older = msgs[:-WINDOW]
        if not older:
            return context, ""

        prev = get_summary(user_id, session_id)
        prev_summary = prev["summary"] if prev else ""
        covered_until = prev["covered_until_id"] if prev else 0
        pending = [m for m in older if m["id"] > covered_until]

        if prev_summary and not pending:
            # 已有摘要且无新增待压缩消息：直接复用
            summary_text = f"\n\n📜 历史对话摘要（更早的对话已压缩）：\n{prev_summary}"
            return context, summary_text
        if len(pending) < COMPRESS_THRESHOLD:
            # 未达压缩阈值：已有摘要则复用，没有则暂不注入
            if prev_summary:
                summary_text = f"\n\n📜 历史对话摘要（更早的对话已压缩）：\n{prev_summary}"
            return context, summary_text

        new_summary = _compress(user_id, session_id, adapter, prev_summary, pending)
        if new_summary:
            _upsert_summary(user_id, session_id, new_summary, pending[-1]["id"])
            summary_text = f"\n\n📜 历史对话摘要（更早的对话已压缩）：\n{new_summary}"
        return context, summary_text
    except Exception as e:
        logger.warning("上下文压缩失败（已降级跳过）: %s", e)
        return context, ""
