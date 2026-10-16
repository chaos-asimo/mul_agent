# -*- coding: utf-8 -*-
"""MCP 服务端 - 配置化 API 封装工具仓库（mu_mcp_tools，按 user_id 隔离）"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from lobster_mu.db import get_conn


def _now() -> str:
    return datetime.now().isoformat()


def _row_to_dict(row) -> Dict[str, Any]:
    d = dict(row)
    for k in ("headers", "query_params"):
        try:
            d[k] = json.loads(d.get(k) or "{}")
        except Exception:
            d[k] = {}
    try:
        d["params_schema"] = json.loads(d.get("params_schema") or "[]")
    except Exception:
        d["params_schema"] = []
    d["enabled"] = bool(d.get("enabled"))
    return d


def list_tools(user_id: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_mcp_tools WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def list_enabled(user_id: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM mu_mcp_tools WHERE user_id = ? AND enabled = 1 ORDER BY name",
            (user_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_tool(user_id: int, tool_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM mu_mcp_tools WHERE id = ? AND user_id = ?",
            (tool_id, user_id),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def get_tool_by_name(user_id: int, name: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM mu_mcp_tools WHERE user_id = ? AND name = ? AND enabled = 1",
            (user_id, name),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def _norm(data: Dict[str, Any]) -> Dict[str, Any]:
    """规整写入字段：JSON 列序列化、method 大写白名单"""
    method = str(data.get("method") or "GET").upper()
    if method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
        method = "GET"
    headers = data.get("headers") or {}
    query = data.get("query_params") or {}
    schema = data.get("params_schema") or []
    return {
        "name": str(data.get("name") or "").strip()[:64],
        "description": str(data.get("description") or "")[:500],
        "url": str(data.get("url") or "").strip()[:2000],
        "method": method,
        "headers": json.dumps(headers, ensure_ascii=False) if not isinstance(headers, str) else headers,
        "query_params": json.dumps(query, ensure_ascii=False) if not isinstance(query, str) else query,
        "body_template": str(data.get("body_template") or ""),
        "params_schema": json.dumps(schema, ensure_ascii=False) if not isinstance(schema, str) else schema,
        "timeout": max(1, min(300, int(data.get("timeout") or 30))),
    }


def create_tool(user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    f = _norm(data)
    if not f["name"] or not f["url"]:
        return {"success": False, "error": "名称与 URL 不能为空"}
    now = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO mu_mcp_tools (user_id, name, description, url, method, headers, "
            "query_params, body_template, params_schema, timeout, enabled, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (user_id, f["name"], f["description"], f["url"], f["method"], f["headers"],
             f["query_params"], f["body_template"], f["params_schema"], f["timeout"], now, now),
        )
        conn.commit()
        return {"success": True, "tool": get_tool(user_id, cur.lastrowid)}
    except Exception as e:
        return {"success": False, "error": f"创建失败（名称重复？）: {e}"}
    finally:
        conn.close()


def update_tool(user_id: int, tool_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    if not get_tool(user_id, tool_id):
        return {"success": False, "error": "工具不存在或无权修改"}
    f = _norm(data)
    if not f["name"] or not f["url"]:
        return {"success": False, "error": "名称与 URL 不能为空"}
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE mu_mcp_tools SET name=?, description=?, url=?, method=?, headers=?, "
            "query_params=?, body_template=?, params_schema=?, timeout=?, updated_at=? "
            "WHERE id=? AND user_id=?",
            (f["name"], f["description"], f["url"], f["method"], f["headers"],
             f["query_params"], f["body_template"], f["params_schema"], f["timeout"],
             _now(), tool_id, user_id),
        )
        conn.commit()
        return {"success": True, "tool": get_tool(user_id, tool_id)}
    except Exception as e:
        return {"success": False, "error": f"更新失败: {e}"}
    finally:
        conn.close()


def delete_tool(user_id: int, tool_id: int) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM mu_mcp_tools WHERE id = ? AND user_id = ?", (tool_id, user_id))
        conn.commit()
        if cur.rowcount == 0:
            return {"success": False, "error": "工具不存在或无权删除"}
        return {"success": True}
    finally:
        conn.close()


def toggle_tool(user_id: int, tool_id: int, enabled: bool) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE mu_mcp_tools SET enabled=?, updated_at=? WHERE id=? AND user_id=?",
            (1 if enabled else 0, _now(), tool_id, user_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return {"success": False, "error": "工具不存在或无权操作"}
        return {"success": True}
    finally:
        conn.close()
