# -*- coding: utf-8 -*-
"""Agent 执行轨迹持久化（mu_agent_traces 表）。"""
from datetime import datetime
from typing import Optional

from lobster_mu.db import get_conn


def log_trace(user_id: int, session_id: str, step: int, role: str,
              tool_name: str = "", arguments: str = "", content: str = "",
              status: str = "ok") -> None:
    """记录一步执行轨迹（异步上下文需注意 SQLite 写锁，串行写入更安全）。"""
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO mu_agent_traces (user_id, session_id, step, role, tool_name, arguments, content, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, session_id or "", step, role, tool_name[:100], arguments[:2000], content[:8000], status,
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    except Exception:
        # 轨迹记录失败不影响主流程
        pass


def list_traces(user_id: Optional[int] = None, session_id: Optional[str] = None, limit: int = 100):
    conn = get_conn()
    sql = "SELECT id, user_id, session_id, step, role, tool_name, arguments, content, status, created_at FROM mu_agent_traces"
    where, params = [], []
    if user_id is not None:
        where.append("user_id = ?")
        params.append(user_id)
    if session_id:
        where.append("session_id = ?")
        params.append(session_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
