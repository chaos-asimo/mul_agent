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


def list_traces(user_id: Optional[int] = None, session_id: Optional[str] = None,
                page: int = 1, page_size: int = 50):
    """分页查询执行轨迹。page 从 1 开始，返回 (traces, total)。"""
    page = max(1, int(page))
    page_size = max(1, min(500, int(page_size)))
    offset = (page - 1) * page_size
    conn = get_conn()
    base_where, base_params = [], []
    if user_id is not None:
        base_where.append("user_id = ?")
        base_params.append(user_id)
    if session_id:
        base_where.append("session_id = ?")
        base_params.append(session_id)
    where_sql = (" WHERE " + " AND ".join(base_where)) if base_where else ""

    cur = conn.execute(f"SELECT COUNT(*) FROM mu_agent_traces{where_sql}", base_params)
    total = cur.fetchone()[0]

    sql = ("SELECT id, user_id, session_id, step, role, tool_name, arguments, content, status, created_at "
           f"FROM mu_agent_traces{where_sql} ORDER BY id DESC LIMIT ? OFFSET ?")
    cur = conn.execute(sql, base_params + [page_size, offset])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()], total


def delete_traces(trace_id: Optional[int] = None, session_id: Optional[str] = None) -> int:
    """删除执行轨迹：按 trace_id 删单条，或按 session_id 删整个会话。返回删除行数。"""
    if trace_id is not None:
        conn = get_conn()
        cur = conn.execute("DELETE FROM mu_agent_traces WHERE id = ?", (int(trace_id),))
        conn.commit()
        return cur.rowcount
    if session_id:
        conn = get_conn()
        cur = conn.execute("DELETE FROM mu_agent_traces WHERE session_id = ?", (session_id,))
        conn.commit()
        return cur.rowcount
    return 0
