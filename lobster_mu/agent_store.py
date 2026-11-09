# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - Agent 系统存储（mu_agents / mu_agent_memories，user_id 隔离）

替代原版 web/routes/lobster_claw.py 的内存全局列表 agents = []，落库并按用户隔离。
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from lobster_mu.db import get_conn

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat()


def _agent_to_dict(row) -> Dict[str, Any]:
    d = dict(row)
    try:
        caps = json.loads(d.get("capabilities") or "[]")
        d["capabilities"] = caps if isinstance(caps, list) else []
    except Exception:
        d["capabilities"] = []
    return d


def _memory_to_dict(row) -> Dict[str, Any]:
    return dict(row)


def create_agent(user_id: int, name: str, role_description: str = "",
                 model_id: Optional[str] = None, model_name: Optional[str] = None,
                 model_type: str = "text", avatar: str = "🤖", tone: str = "",
                 capabilities: Optional[List[str]] = None) -> Dict[str, Any]:
    ts = _now()
    caps = json.dumps(capabilities or [], ensure_ascii=False)
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO mu_agents (user_id, name, role_description, avatar, tone,"
            " model_id, model_name, model_type, capabilities, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, role_description or "", avatar or "🤖", tone or "",
             model_id, model_name, model_type, caps, ts, ts),
        )
        conn.commit()
        agent_id = cur.lastrowid
    finally:
        conn.close()
    return get_agent(user_id, agent_id)


def list_agents(user_id: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_agents WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ).fetchall()
    finally:
        conn.close()
    return [_agent_to_dict(r) for r in rows]


def get_agent(user_id: int, agent_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM mu_agents WHERE id = ? AND user_id = ?", (agent_id, user_id)
        ).fetchone()
    finally:
        conn.close()
    return _agent_to_dict(row) if row else None


def update_agent(user_id: int, agent_id: int, **fields) -> Optional[Dict[str, Any]]:
    """更新 Agent（name/role_description/avatar/tone/capabilities/model_id/model_name/model_type）"""
    allowed = {k: v for k, v in fields.items()
               if k in ("name", "role_description", "avatar", "tone", "capabilities",
                        "model_id", "model_name", "model_type")
               and v is not None}
    if "capabilities" in allowed and not isinstance(allowed["capabilities"], str):
        allowed["capabilities"] = json.dumps(allowed["capabilities"] or [], ensure_ascii=False)
    if not allowed:
        return get_agent(user_id, agent_id)
    allowed["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in allowed)
    params = list(allowed.values()) + [agent_id, user_id]
    conn = get_conn()
    try:
        cur = conn.execute(
            f"UPDATE mu_agents SET {set_clause} WHERE id = ? AND user_id = ?", params
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    finally:
        conn.close()
    return get_agent(user_id, agent_id)


def delete_agent(user_id: int, agent_id: int) -> bool:
    """删除 Agent 并级联删除其 memories"""
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM mu_agent_memories WHERE agent_id = ? AND user_id = ?",
            (agent_id, user_id),
        )
        cur = conn.execute(
            "DELETE FROM mu_agents WHERE id = ? AND user_id = ?", (agent_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ============ Agent 记忆 ============

def add_memory(user_id: int, agent_id: int, content: str, mtype: str = "short_term",
               source: str = "manual") -> Optional[int]:
    """为 Agent 添加记忆（需归属校验，agent 不存在返回 None；source=manual/auto）"""
    if get_agent(user_id, agent_id) is None:
        return None
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO mu_agent_memories (user_id, agent_id, content, source, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (user_id, agent_id, content, source or "manual", _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_memories(user_id: int, agent_id: int) -> Optional[List[Dict[str, Any]]]:
    """列出 Agent 记忆（按时间倒序）；agent 不存在返回 None"""
    if get_agent(user_id, agent_id) is None:
        return None
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_agent_memories WHERE agent_id = ? AND user_id = ?"
            " ORDER BY id DESC",
            (agent_id, user_id),
        ).fetchall()
    finally:
        conn.close()
    return [_memory_to_dict(r) for r in rows]


def delete_memory(user_id: int, agent_id: int, memory_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM mu_agent_memories WHERE id = ? AND agent_id = ? AND user_id = ?",
            (memory_id, agent_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def search_memory(user_id: int, keyword: str, agent_id: Optional[int] = None,
                  limit: int = 10) -> List[Dict[str, Any]]:
    """按关键字搜索该用户的 Agent 记忆（可限定单个 Agent）"""
    if not keyword:
        return []
    sql = ("SELECT m.*, a.name AS agent_name FROM mu_agent_memories m"
           " LEFT JOIN mu_agents a ON m.agent_id = a.id"
           " WHERE m.user_id = ? AND m.content LIKE ?")
    params: List[Any] = [user_id, f"%{keyword}%"]
    if agent_id:
        sql += " AND m.agent_id = ?"
        params.append(agent_id)
    sql += " ORDER BY m.id DESC LIMIT ?"
    params.append(int(limit))
    conn = get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [_memory_to_dict(r) for r in rows]
