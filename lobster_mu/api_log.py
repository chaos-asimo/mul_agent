# -*- coding: utf-8 -*-
"""多用户龙虾Claw - 接口访问日志（记录 /api/lobster-mu 请求，仅管理员可查）"""
import sqlite3
from datetime import datetime

from lobster_mu import db


def log_api_access(
    method: str,
    path: str,
    status: int,
    duration_ms: int,
    ip: str = "",
    username: str = "",
    user_id: int = 0,
    auth_type: str = "",
):
    """同步写入一条接口访问日志（短连接，调用方用 asyncio.to_thread 包装）"""
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO mu_api_access_logs "
            "(method, path, status, duration_ms, ip, username, user_id, auth_type, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                method,
                path,
                status,
                duration_ms,
                ip,
                username,
                user_id,
                auth_type,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
