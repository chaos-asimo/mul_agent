# -*- coding: utf-8 -*-
"""MCP 服务端 - 每用户访问令牌（mu_mcp_tokens；仅存 sha256，明文仅创建时返回一次）"""
import hashlib
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from lobster_mu.db import get_conn


def _now() -> str:
    return datetime.now().isoformat()


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _row_to_dict(row) -> Dict[str, Any]:
    d = dict(row)
    d["revoked"] = bool(d.get("revoked"))
    return d


def create_token(user_id: int, name: str = "", expires_at: str = "") -> Tuple[Dict[str, Any], str]:
    """生成令牌，返回 (行记录, 明文)。明文格式 mcp_<32hex>，仅此一次可见。"""
    plaintext = "mcp_" + secrets.token_hex(16)
    now = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO mu_mcp_tokens (user_id, name, token_hash, prefix, revoked, "
            "last_used_at, expires_at, created_at) VALUES (?, ?, ?, ?, 0, NULL, ?, ?)",
            (user_id, (name or "")[:64], _hash(plaintext), plaintext[:12], expires_at or "", now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM mu_mcp_tokens WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_dict(row), plaintext
    finally:
        conn.close()


def resolve_token(plaintext: str) -> Optional[int]:
    """校验令牌并返回 user_id；无效/已吊销/已过期返回 None。命中时更新 last_used_at。"""
    if not plaintext or not plaintext.startswith("mcp_"):
        return None
    now = _now()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM mu_mcp_tokens WHERE token_hash = ? AND revoked = 0",
            (_hash(plaintext),),
        ).fetchone()
        if not row:
            return None
        exp = row["expires_at"] or ""
        if exp and exp < now:
            return None
        conn.execute("UPDATE mu_mcp_tokens SET last_used_at = ? WHERE id = ?", (now, row["id"]))
        conn.commit()
        return int(row["user_id"])
    finally:
        conn.close()


def list_tokens(user_id: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, user_id, name, prefix, revoked, last_used_at, expires_at, created_at "
            "FROM mu_mcp_tokens WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def revoke_token(user_id: int, token_id: int) -> Dict[str, Any]:
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE mu_mcp_tokens SET revoked = 1 WHERE id = ? AND user_id = ?",
            (token_id, user_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return {"success": False, "error": "令牌不存在或无权吊销"}
        return {"success": True}
    finally:
        conn.close()
