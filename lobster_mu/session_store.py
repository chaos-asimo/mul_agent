# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 聊天会话/消息存储（落库持久化 + 每用户 LRU 缓存）"""
from collections import OrderedDict, deque
from datetime import datetime
import json

from lobster_mu.db import get_conn

MAX_CHAT_HISTORY = 50
_CACHE_CAPACITY = 5          # 每用户最多缓存会话数
_CACHE_MSGS = MAX_CHAT_HISTORY  # 每会话缓存消息条数


def _parse_token_stats(raw):
    """数据库中 token_stats 为 JSON 字符串，需解析为 dict"""
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return None

# {user_id: OrderedDict[session_id -> deque[messages]]}
_msg_cache = {}


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _cache(user_id: int) -> OrderedDict:
    return _msg_cache.setdefault(user_id, OrderedDict())


def _cache_get(user_id: int, session_id: str) -> list:
    c = _cache(user_id)
    if session_id in c:
        c.move_to_end(session_id)
        return c[session_id]
    # miss：从库加载最近消息
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT role, content, model_name, token_stats, created_at FROM mu_chat_messages"
            " WHERE session_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, user_id, _CACHE_MSGS),
        ).fetchall()
    finally:
        conn.close()
    msgs = deque(
        [{"role": r["role"], "content": r["content"], "model_name": r["model_name"],
          "token_stats": _parse_token_stats(r["token_stats"]), "timestamp": r["created_at"]}
         for r in reversed(rows)],
        maxlen=_CACHE_MSGS,
    )
    c[session_id] = msgs
    while len(c) > _CACHE_CAPACITY:
        c.popitem(last=False)
    return msgs


def _cache_append(user_id: int, session_id: str, message: dict):
    c = _cache(user_id)
    msgs = _cache_get(user_id, session_id)
    msgs.append(message)
    if session_id not in c:
        c[session_id] = msgs
        while len(c) > _CACHE_CAPACITY:
            c.popitem(last=False)
    _trim_cache_session(user_id, session_id)


def _trim_cache_session(user_id: int, session_id: str):
    c = _cache(user_id)
    if session_id in c:
        while len(c[session_id]) > _CACHE_MSGS:
            c[session_id].popleft()


def _invalidate(user_id: int, session_id: str = None):
    c = _msg_cache.get(user_id)
    if not c:
        return
    if session_id:
        c.pop(session_id, None)
    else:
        c.clear()


def get_or_create_session(user_id: int, session_id: str = None, title: str = "") -> str:
    """返回属于该用户的会话 id；不存在则创建（落库）"""
    if session_id:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT id FROM mu_chat_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id),
            ).fetchone()
        finally:
            conn.close()
        if row:
            return session_id
    new_id = f"mu_s_{user_id}_{datetime.now().timestamp()}"
    now = _now()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO mu_chat_sessions (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (new_id, user_id, title or "新会话", now, now),
        )
        conn.commit()
    finally:
        conn.close()
    _cache(user_id)[new_id] = deque(maxlen=_CACHE_MSGS)
    while len(_cache(user_id)) > _CACHE_CAPACITY:
        _cache(user_id).popitem(last=False)
    return new_id


def append_message(user_id: int, session_id: str, role: str, content: str,
                   model_name: str = None, token_stats: dict = None):
    """写穿透：INSERT 落库 + 追加缓存；自动裁剪旧消息"""
    now = _now()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO mu_chat_messages (session_id, user_id, role, content, model_name, token_stats, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, user_id, role, content, model_name,
             __import__("json").dumps(token_stats, ensure_ascii=False) if token_stats else None, now),
        )
        # 第一条用户消息时，用问题简述更新会话标题
        if role == "user":
            existing = conn.execute(
                "SELECT COUNT(1) FROM mu_chat_messages WHERE session_id = ? AND role = 'user'",
                (session_id,),
            ).fetchone()[0]
            if existing <= 1:
                title = content.strip().replace("\n", " ")[:30]
                if title:
                    conn.execute(
                        "UPDATE mu_chat_sessions SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                        (title, now, session_id, user_id),
                    )
        conn.execute(
            "UPDATE mu_chat_sessions SET updated_at = ? WHERE id = ? AND user_id = ?",
            (now, session_id, user_id),
        )
        # 保持库内消息条数上限（裁剪最旧）
        conn.execute(
            "DELETE FROM mu_chat_messages WHERE session_id = ? AND id NOT IN ("
            "  SELECT id FROM mu_chat_messages WHERE session_id = ? ORDER BY id DESC LIMIT ?"
            ")",
            (session_id, session_id, _CACHE_MSGS),
        )
        conn.commit()
    finally:
        conn.close()
    _cache_append(user_id, session_id, {
        "role": role, "content": content, "model_name": model_name,
        "token_stats": token_stats, "timestamp": now,
    })


def get_messages(user_id: int, session_id: str) -> list:
    """返回该会话消息（校验归属）"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM mu_chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if not row:
            return None
    finally:
        conn.close()
    return list(_cache_get(user_id, session_id))


def list_sessions(user_id: int) -> list:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT s.id, s.title, s.created_at, s.updated_at, COUNT(m.id) AS message_count"
            " FROM mu_chat_sessions s LEFT JOIN mu_chat_messages m ON m.session_id = s.id"
            " WHERE s.user_id = ? GROUP BY s.id ORDER BY s.updated_at DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    result = []
    for r in rows:
        preview = ""
        try:
            msgs = _cache_get(user_id, r["id"])
            if msgs:
                preview = msgs[-1]["content"][:50]
        except Exception:
            pass
        result.append({
            "id": r["id"], "title": r["title"], "message_count": r["message_count"],
            "created_at": r["created_at"], "last_used": r["updated_at"], "preview": preview,
        })
    return result


def delete_session(user_id: int, session_id: str) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM mu_chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id)
        )
        conn.execute(
            "DELETE FROM mu_chat_messages WHERE session_id = ? AND user_id = ?", (session_id, user_id)
        )
        conn.execute(
            "DELETE FROM mu_session_summaries WHERE session_id = ? AND user_id = ?", (session_id, user_id)
        )
        conn.commit()
        deleted = cur.rowcount > 0
    finally:
        conn.close()
    _invalidate(user_id, session_id)
    return deleted


def clear_sessions(user_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM mu_chat_sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM mu_chat_messages WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM mu_session_summaries WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
    _invalidate(user_id)
