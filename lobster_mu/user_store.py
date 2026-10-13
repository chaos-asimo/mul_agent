# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 用户表 CRUD + bootstrap 管理员"""
import os
from datetime import datetime

from lobster_mu.db import get_conn
from lobster_mu.security import hash_password, new_salt

# 管理员凭据：优先从环境变量读取，默认值仅用于首次 bootstrap
BOOTSTRAP_ADMIN = (
    os.environ.get("MU_ADMIN_USERNAME", "shineyue"),
    os.environ.get("MU_ADMIN_PASSWORD", "shineyue@2026"),
)


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def parse_device(ua: str) -> str:
    """从 User-Agent 解析出友好的设备/浏览器描述（如「Windows · Chrome」「iPhone · 微信」）。"""
    ua = ua or ""
    if not ua.strip():
        return "未知设备"
    low = ua.lower()
    # 操作系统
    if "iphone" in low or "ipad" in low:
        os_ = "iPhone/iPad" if "iphone" in low else "iPad"
    elif "android" in low:
        os_ = "Android"
    elif "windows" in low:
        os_ = "Windows"
    elif "mac os x" in low or "macintosh" in low:
        os_ = "macOS"
    elif "linux" in low:
        os_ = "Linux"
    else:
        os_ = ""
    # 浏览器 / 宿主 App（注意顺序：Edge/企业微信/微信 先于 Chrome/Safari）
    if "wxwork" in low or "wecom" in low:
        browser = "企业微信"
    elif "micromessenger" in low:
        browser = "微信"
    elif "edg/" in low:
        browser = "Edge"
    elif "firefox" in low:
        browser = "Firefox"
    elif "chrome" in low and "chromium" not in low:
        browser = "Chrome"
    elif "safari" in low:
        browser = "Safari"
    else:
        browser = ""
    parts = [p for p in (os_, browser) if p]
    label = " · ".join(parts) if parts else ua[:40]
    return label[:60]


def _row_to_dict(r) -> dict:
    return {
        "id": r["id"],
        "username": r["username"],
        "role": r["role"],
        "display_name": r["display_name"],
        "disabled": bool(r["disabled"]),
        "totp_enabled": bool(r["totp_enabled"]),
        "created_at": r["created_at"],
        "last_login_at": r["last_login_at"],
        "last_login_device": r["last_login_device"],
    }


def init_users():
    """建默认管理员（仅 users 表为空时）"""
    conn = get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if count == 0:
            username, password = BOOTSTRAP_ADMIN
            salt = new_salt()
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role, display_name, created_at)"
                " VALUES (?, ?, ?, 'admin', ?, ?)",
                (username, hash_password(password, salt), salt, "管理员", _now()),
            )
            conn.commit()
    finally:
        conn.close()


def get_by_username(username: str):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()


def get_by_id(user_id: int):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()


def is_disabled(user_id: int) -> bool:
    row = get_by_id(user_id)
    return row is None or bool(row["disabled"])


def create_user(username: str, password: str, role: str = "user", display_name: str = ""):
    if get_by_username(username):
        raise ValueError(f"用户名已存在: {username}")
    salt = new_salt()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, salt, role, display_name, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (username, hash_password(password, salt), salt, role, display_name, _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_users() -> list:
    conn = get_conn()
    try:
        # 只取前端展示所需列（排除 password_hash/salt/totp_secret 等敏感大字段），
        # 按 created_at 降序命中 idx_users_created 索引，避免全表 filesort
        rows = conn.execute(
            "SELECT id, username, role, display_name, disabled, totp_enabled,"
            " created_at, last_login_at, last_login_device FROM users ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def update_user(user_id: int, role: str = None, display_name: str = None,
                disabled: bool = None, new_password: str = None) -> bool:
    """部分更新；返回是否有改动"""
    row = get_by_id(user_id)
    if not row:
        return False
    conn = get_conn()
    try:
        if role is not None:
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        if display_name is not None:
            conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, user_id))
        if disabled is not None:
            conn.execute("UPDATE users SET disabled = ? WHERE id = ?", (1 if disabled else 0, user_id))
        if new_password:
            salt = new_salt()
            conn.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
                (hash_password(new_password, salt), salt, user_id),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_user(user_id: int) -> bool:
    """删除用户及其全部数据（同库按 user_id 清理）"""
    conn = get_conn()
    try:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return False
        # 删除各业务数据（同库，直接按 user_id 清理）
        # 注意：mu_knowledge_docs 只删引用行，kb_content/kb_content_vectors 共享内容保留
        # （其他用户可能还在用），由 gc_orphaned_content() 定期清理无引用孤儿
        for table in ["mu_chat_messages", "mu_chat_sessions", "mu_memories", "mu_scripts",
                      "mu_cron_runs", "mu_cron_tasks", "mu_agent_memories", "mu_agents",
                      "mu_knowledge_docs", "mu_operation_logs"]:
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        # 旧表兼容：清理该用户在 mu_knowledge_vectors 的遗留向量（未迁移的旧数据）
        conn.execute("DELETE FROM mu_knowledge_vectors WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
    return True


def update_last_login(user_id: int, user_agent: str = None):
    """记录最后登录时间；传入 User-Agent 时同时记录登录设备。"""
    device = parse_device(user_agent) if user_agent else None
    conn = get_conn()
    try:
        if device is not None:
            conn.execute(
                "UPDATE users SET last_login_at = ?, last_login_device = ? WHERE id = ?",
                (_now(), device, user_id),
            )
        else:
            conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (_now(), user_id))
        conn.commit()
    finally:
        conn.close()


def count_admins_excluding(user_id: int) -> int:
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'admin' AND disabled = 0 AND id != ?",
            (user_id,),
        ).fetchone()["c"]
    finally:
        conn.close()


# ============ TOTP（微软 Authenticator） ============

def set_totp_secret(user_id: int, secret: str):
    """设置 TOTP 密钥（临时保存，未启用前 totp_enabled=0）"""
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET totp_secret = ?, totp_enabled = 0 WHERE id = ?",
                     (secret, user_id))
        conn.commit()
    finally:
        conn.close()


def enable_totp(user_id: int):
    """启用 TOTP（确认码验证通过后调用）"""
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET totp_enabled = 1 WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def disable_totp(user_id: int):
    """禁用 TOTP（清空密钥）"""
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET totp_enabled = 0, totp_secret = '' WHERE id = ?",
                     (user_id,))
        conn.commit()
    finally:
        conn.close()
