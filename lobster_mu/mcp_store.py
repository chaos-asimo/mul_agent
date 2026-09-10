# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - MCP server 配置存储（mu_mcp_servers，user_id 隔离）

- 所有读写均带 WHERE user_id = ?
- args/env 以 JSON 字符串落库，读取时解析为 list/dict
- env 含密钥，对外（API 列表/详情）脱敏：仅返回键名，值替换为 "***"
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from lobster_mu.db import get_conn

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat()


def _parse_json(raw: Any, default: Any):
    if not raw:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


def _row_to_dict(row, mask_env: bool = True) -> Dict[str, Any]:
    d = dict(row)
    d["enabled"] = bool(d.get("enabled"))
    d["args"] = _parse_json(d.get("args"), [])
    env = _parse_json(d.get("env"), {})
    if mask_env and isinstance(env, dict):
        # 脱敏：仅保留键名，值掩码；空 dict 保持空
        d["env"] = {k: "***" for k in env.keys()}
    else:
        d["env"] = env
    return d


def list_servers(user_id: int, enabled_only: bool = False) -> List[Dict[str, Any]]:
    """列出用户的 MCP server 配置（env 脱敏）"""
    conn = get_conn()
    try:
        if enabled_only:
            rows = conn.execute(
                "SELECT * FROM mu_mcp_servers WHERE user_id = ? AND enabled = 1 ORDER BY id",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM mu_mcp_servers WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()
    finally:
        conn.close()
    return [_row_to_dict(r, mask_env=True) for r in rows]


def get_server(user_id: int, server_id: int, mask_env: bool = True) -> Optional[Dict[str, Any]]:
    """获取单个 server 配置（默认 env 脱敏）"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM mu_mcp_servers WHERE id = ? AND user_id = ?",
            (server_id, user_id),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row, mask_env=mask_env) if row else None


def get_server_raw(user_id: int, server_id: int) -> Optional[Dict[str, Any]]:
    """获取含明文 env 的完整配置（仅后端连接 MCP 时使用，不经过 API）"""
    return get_server(user_id, server_id, mask_env=False)


def create_server(user_id: int, name: str, transport: str,
                  command: str = "", args: Optional[List[str]] = None,
                  env: Optional[Dict[str, str]] = None, url: str = "",
                  enabled: bool = True) -> Dict[str, Any]:
    ts = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO mu_mcp_servers (user_id, name, transport, command, args, env, url,"
            " enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, transport, command or "",
             json.dumps(args or [], ensure_ascii=False),
             json.dumps(env or {}, ensure_ascii=False),
             url or "", 1 if enabled else 0, ts, ts),
        )
        conn.commit()
        server_id = cur.lastrowid
    finally:
        conn.close()
    srv = get_server(user_id, server_id)
    assert srv is not None
    return srv


def update_server(user_id: int, server_id: int, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新配置；fields 可含 name/transport/command/args(list)/env(dict)/url/enabled。
    注意：env 为脱敏 dict（值为 ***）时表示未修改，跳过 env 更新。"""
    current = get_server_raw(user_id, server_id)
    if not current:
        return None

    sets = []
    vals: List[Any] = []
    for key in ("name", "transport", "command", "url"):
        if key in fields:
            sets.append(f"{key} = ?")
            vals.append(fields[key] or "")
    if "args" in fields:
        sets.append("args = ?")
        vals.append(json.dumps(fields["args"] or [], ensure_ascii=False))
    if "env" in fields:
        new_env = fields["env"]
        if isinstance(new_env, dict):
            # 编辑表单回传的是当前 env 的全量键集合（未改行的值为脱敏 "***"）：
            # - 值为 "***"：保持原明文
            # - 值为 "" 或该键已不在回传集合中（整行删除）：移除
            # - 其余：更新为新值
            old_env = dict(current.get("env") or {})
            merged: Dict[str, str] = {}
            for k, v in new_env.items():
                if v == "***":
                    if k in old_env:
                        merged[k] = old_env[k]
                elif v != "":
                    merged[k] = v
            sets.append("env = ?")
            vals.append(json.dumps(merged, ensure_ascii=False))
    if "enabled" in fields:
        sets.append("enabled = ?")
        vals.append(1 if fields["enabled"] else 0)

    if not sets:
        return get_server(user_id, server_id)

    sets.append("updated_at = ?")
    vals.append(_now())
    vals.extend([server_id, user_id])

    conn = get_conn()
    try:
        conn.execute(
            f"UPDATE mu_mcp_servers SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
            vals,
        )
        conn.commit()
    finally:
        conn.close()
    return get_server(user_id, server_id)


def delete_server(user_id: int, server_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM mu_mcp_servers WHERE id = ? AND user_id = ?",
            (server_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def toggle_server(user_id: int, server_id: int) -> Optional[Dict[str, Any]]:
    current = get_server(user_id, server_id)
    if not current:
        return None
    update_server(user_id, server_id, {"enabled": not current["enabled"]})
    return get_server(user_id, server_id)
