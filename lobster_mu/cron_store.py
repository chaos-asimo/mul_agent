# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 定时任务存储（mu_cron_tasks / mu_cron_runs，全部 user_id 隔离）

字段与原版 cron.db（cron/cron_manager.py）对齐，区别仅在于：
- 复用 lobster_mu.db 的 SQLite 连接（WAL）与 mu_ 前缀表
- 所有用户侧读写均带 WHERE user_id = ?
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from lobster_mu.db import get_conn

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat()


def _task_to_dict(row) -> Dict[str, Any]:
    d = dict(row)
    d["enabled"] = bool(d.get("enabled"))
    return d


def _run_to_dict(row) -> Dict[str, Any]:
    return dict(row)


def create(user_id: int, name: str, task_type: str, content: str,
           schedule: Optional[str] = None, run_at: Optional[str] = None,
           enabled: bool = True, timeout: int = 300,
           session_id: Optional[str] = None) -> Dict[str, Any]:
    """创建定时任务并返回任务 dict"""
    ts = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO mu_cron_tasks (user_id, name, task_type, content, schedule, run_at,"
            " enabled, timeout, session_id, created_at, updated_at, next_run_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (user_id, name, task_type, content, schedule, run_at,
             1 if enabled else 0, timeout, session_id, ts, ts),
        )
        conn.commit()
        task_id = cur.lastrowid
    finally:
        conn.close()
    task = get_task(user_id, task_id)
    assert task is not None
    return task


def list_tasks(user_id: int, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        if enabled is None:
            rows = conn.execute(
                "SELECT * FROM mu_cron_tasks WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM mu_cron_tasks WHERE user_id = ? AND enabled = ?"
                " ORDER BY updated_at DESC",
                (user_id, 1 if enabled else 0),
            ).fetchall()
    finally:
        conn.close()
    return [_task_to_dict(r) for r in rows]


def get_task(user_id: int, task_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM mu_cron_tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        ).fetchone()
    finally:
        conn.close()
    return _task_to_dict(row) if row else None


def update_task(user_id: int, task_id: int, **kwargs) -> bool:
    if not kwargs:
        return False
    kwargs = dict(kwargs)
    kwargs["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    params = list(kwargs.values()) + [task_id, user_id]
    conn = get_conn()
    try:
        cur = conn.execute(
            f"UPDATE mu_cron_tasks SET {set_clause} WHERE id = ? AND user_id = ?", params
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_task(user_id: int, task_id: int) -> bool:
    """删除任务并级联删除其运行记录"""
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM mu_cron_runs WHERE task_id = ? AND user_id = ?", (task_id, user_id)
        )
        cur = conn.execute(
            "DELETE FROM mu_cron_tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def toggle_task(user_id: int, task_id: int) -> Optional[Dict[str, Any]]:
    task = get_task(user_id, task_id)
    if not task:
        return None
    new_enabled = 0 if task["enabled"] else 1
    update_task(user_id, task_id, enabled=new_enabled)
    return get_task(user_id, task_id)


def set_next_run(user_id: int, task_id: int, next_run_at: str) -> bool:
    return update_task(user_id, task_id, next_run_at=next_run_at)


def add_run(user_id: int, task_id: int, status: str, output: str = "",
            error: str = "", started_at: Optional[str] = None,
            finished_at: Optional[str] = None, duration: float = 0.0) -> int:
    if started_at is None:
        started_at = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO mu_cron_runs (task_id, user_id, status, output, error,"
            " started_at, finished_at, duration) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, user_id, status, output, error, started_at, finished_at, duration),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_run(user_id: int, run_id: int, **kwargs) -> bool:
    if not kwargs:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    params = list(kwargs.values()) + [run_id, user_id]
    conn = get_conn()
    try:
        cur = conn.execute(
            f"UPDATE mu_cron_runs SET {set_clause} WHERE id = ? AND user_id = ?", params
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_runs(user_id: int, task_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_cron_runs WHERE task_id = ? AND user_id = ?"
            " ORDER BY started_at DESC LIMIT ?",
            (task_id, user_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [_run_to_dict(r) for r in rows]


def recent_runs(user_id: int, since_id: int = 0, limit: int = 50,
                only_finished: bool = True) -> List[Dict[str, Any]]:
    """跨任务最近运行记录（仅该用户），带任务名/类型/内容，按 id 升序返回"""
    sql_parts = [
        "SELECT r.id, r.task_id, r.status, r.output, r.error, r.started_at,"
        " r.finished_at, r.duration, t.name, t.task_type, t.content",
        "FROM mu_cron_runs r LEFT JOIN mu_cron_tasks t ON r.task_id = t.id",
        "WHERE r.user_id = ? AND r.id > ?",
    ]
    params: List[Any] = [user_id, int(since_id)]
    if only_finished:
        sql_parts.append("AND r.status != 'running'")
    sql_parts.append("ORDER BY r.id DESC LIMIT ?")
    params.append(int(limit))
    conn = get_conn()
    try:
        rows = conn.execute(" ".join(sql_parts), params).fetchall()
    finally:
        conn.close()
    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "task_id": row["task_id"],
            "status": row["status"],
            "output": row["output"],
            "error": row["error"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "duration": row["duration"],
            "task_name": row["name"] if row["name"] is not None else f"任务#{row['task_id']}",
            "task_type": row["task_type"] if row["task_type"] is not None else "unknown",
            "task_content": row["content"] if row["content"] is not None else "",
        })
    results.reverse()
    return results


# ============ 调度器内部方法（跨用户，仅供 cron_runner 使用，非用户端点） ============

def get_due_tasks() -> List[Dict[str, Any]]:
    """调度器用：查询所有用户已启用且到期的任务"""
    now = _now()
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_cron_tasks"
            " WHERE enabled = 1 AND (next_run_at IS NULL OR next_run_at <= ?)"
            " ORDER BY next_run_at ASC",
            (now,),
        ).fetchall()
    finally:
        conn.close()
    return [_task_to_dict(r) for r in rows]


def list_enabled_tasks() -> List[Dict[str, Any]]:
    """调度器用：启动时恢复所有用户已启用任务"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_cron_tasks WHERE enabled = 1 ORDER BY updated_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [_task_to_dict(r) for r in rows]
