# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - Agent 长期计划存储（mu_agent_plans，user_id 隔离）

一个计划 = 目标标题 + 步骤列表（JSON: [{text, done}]）。
Agent 执行任务时注入未完成的计划；子Agent通过 [PLAN_UPDATE] 标记勾选完成的步骤。
"""
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from lobster_mu.db import get_conn
from lobster_mu import agent_store

logger = logging = __import__("logging").getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _plan_to_dict(row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["steps"] = json.loads(d.get("steps") or "[]")
    except Exception:
        d["steps"] = []
    if not isinstance(d["steps"], list):
        d["steps"] = []
    return d


def _steps_json(steps: List[Any]) -> str:
    out = []
    for s in steps or []:
        if isinstance(s, dict):
            text = str(s.get("text", "")).strip()
            if text:
                out.append({"text": text, "done": bool(s.get("done"))})
        else:
            text = str(s).strip()
            if text:
                out.append({"text": text, "done": False})
    return json.dumps(out, ensure_ascii=False)


def create_plan(user_id: int, agent_id: int, title: str,
                steps: List[Any]) -> Optional[Dict[str, Any]]:
    """为 Agent 创建计划；agent 不存在返回 None"""
    if agent_store.get_agent(user_id, agent_id) is None:
        return None
    title = (title or "").strip()
    if not title:
        raise ValueError("计划标题不能为空")
    now = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO mu_agent_plans (user_id, agent_id, title, steps, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 'active', ?, ?)",
            (user_id, agent_id, title, _steps_json(steps), now, now),
        )
        conn.commit()
        plan_id = cur.lastrowid
    finally:
        conn.close()
    return get_plan(user_id, plan_id)


def list_plans(user_id: int, agent_id: int) -> Optional[List[Dict[str, Any]]]:
    """列出 Agent 全部计划（active 在前）；agent 不存在返回 None"""
    if agent_store.get_agent(user_id, agent_id) is None:
        return None
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_agent_plans WHERE agent_id = ? AND user_id = ?"
            " ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, id DESC",
            (agent_id, user_id),
        ).fetchall()
    finally:
        conn.close()
    return [_plan_to_dict(r) for r in rows]


def active_plans(user_id: int, agent_id: int) -> List[Dict[str, Any]]:
    """取 Agent 的活跃计划（子Agent上下文注入用）"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_agent_plans WHERE agent_id = ? AND user_id = ? AND status = 'active'"
            " ORDER BY id DESC LIMIT 5",
            (agent_id, user_id),
        ).fetchall()
    finally:
        conn.close()
    return [_plan_to_dict(r) for r in rows]


def get_plan(user_id: int, plan_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM mu_agent_plans WHERE id = ? AND user_id = ?", (plan_id, user_id)
        ).fetchone()
    finally:
        conn.close()
    return _plan_to_dict(row) if row else None


def _save_steps(user_id: int, plan_id: int, steps: List[Dict[str, Any]],
                auto_complete: bool = True) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE mu_agent_plans SET steps = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (json.dumps(steps, ensure_ascii=False), _now(), plan_id, user_id),
        )
        if auto_complete and steps and all(s.get("done") for s in steps):
            conn.execute(
                "UPDATE mu_agent_plans SET status = 'done', updated_at = ? WHERE id = ? AND user_id = ?",
                (_now(), plan_id, user_id),
            )
        conn.commit()
    finally:
        conn.close()
    return get_plan(user_id, plan_id)


def toggle_step(user_id: int, plan_id: int, step_index: int,
                done: bool) -> Optional[Dict[str, Any]]:
    """勾选/取消某步骤；plan 不存在返回 None，索引非法抛 ValueError"""
    plan = get_plan(user_id, plan_id)
    if plan is None:
        return None
    steps = plan["steps"]
    if step_index < 0 or step_index >= len(steps):
        raise ValueError("步骤索引非法")
    steps[step_index]["done"] = bool(done)
    return _save_steps(user_id, plan_id, steps)


def mark_step_done(user_id: int, agent_id: int, title: str,
                   step_text: str) -> Optional[Dict[str, Any]]:
    """子Agent [PLAN_UPDATE] 用：按标题找到活跃计划，把与 step_text 匹配的步骤标记完成。

    匹配规则：步骤文本精确相等，或包含 step_text/被 step_text 包含（归一化空白后）。
    找不到计划或步骤返回 None（调用方自行提示）。
    """
    def norm(s: str) -> str:
        return "".join((s or "").split())

    target = norm(step_text)
    if not target:
        return None
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_agent_plans WHERE agent_id = ? AND user_id = ? AND status = 'active'"
            " ORDER BY id DESC",
            (agent_id, user_id),
        ).fetchall()
    finally:
        conn.close()
    t_norm = norm(title)
    for r in rows:
        if t_norm and norm(r["title"]) != t_norm:
            continue
        plan = _plan_to_dict(r)
        for i, s in enumerate(plan["steps"]):
            if s.get("done"):
                continue
            st = norm(s["text"])
            if st == target or (target in st) or (st in target):
                return toggle_step(user_id, plan["id"], i, True)
    return None


def update_plan_status(user_id: int, plan_id: int, status: str) -> Optional[Dict[str, Any]]:
    if status not in ("active", "done", "archived"):
        raise ValueError("状态必须为 active/done/archived")
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE mu_agent_plans SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (status, _now(), plan_id, user_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    finally:
        conn.close()
    return get_plan(user_id, plan_id)


def delete_plan(user_id: int, plan_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM mu_agent_plans WHERE id = ? AND user_id = ?", (plan_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
