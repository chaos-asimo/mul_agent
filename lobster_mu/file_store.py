# -*- coding: utf-8 -*-
"""用户文件库：记录上传文件的元数据与解析文本（user_id 隔离），供文件 Tab 管理与会话复用。"""
import os
from datetime import datetime

from lobster_mu import db


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def add(user_id: int, filename: str, stored_path: str, size: int, content: str) -> int:
    """登记一个已上传文件，返回文件 id。"""
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO mu_files (user_id, filename, stored_path, file_size, content, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, filename, stored_path, int(size or 0), content or "", _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_files(user_id: int):
    """列出用户全部文件（不含大字段 content，列表页轻量）。"""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT id, filename, file_size, created_at FROM mu_files "
            "WHERE user_id=? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get(user_id: int, file_id: int):
    """取单个文件（含 content），越权返回 None。"""
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT id, user_id, filename, stored_path, file_size, content, created_at "
            "FROM mu_files WHERE id=? AND user_id=?",
            (file_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete(user_id: int, file_id: int) -> bool:
    """删除文件记录并尝试删除物理文件。越权返回 False。"""
    conn = db.get_conn()
    path = None
    try:
        row = conn.execute(
            "SELECT stored_path FROM mu_files WHERE id=? AND user_id=?",
            (file_id, user_id),
        ).fetchone()
        if not row:
            return False
        path = row["stored_path"]
        conn.execute("DELETE FROM mu_files WHERE id=? AND user_id=?", (file_id, user_id))
        conn.commit()
    finally:
        conn.close()
    if path:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    return True
