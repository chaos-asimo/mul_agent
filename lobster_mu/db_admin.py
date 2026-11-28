# -*- coding: utf-8 -*-
"""管理员 SQLite 数据库查看器：库发现、结构读取、受控 SQL 执行。

安全约束：
- 仅允许访问项目目录内（排除依赖/产物目录）的 .db/.sqlite/.sqlite3 文件，路径穿越会被拒绝；
- 默认只读（URI mode=ro + PRAGMA query_only=ON），写操作必须显式 allow_write；
- 禁止 ATTACH/DETACH，防止借此读写项目外文件；
- 仅允许单条语句（由 sqlite3 自身保证），执行带中断超时，返回行数有上限。
"""
import os
import re
import sqlite3
import time
import urllib.parse
from datetime import datetime

from lobster_mu.db import BASE_DIR

DB_EXTS = (".db", ".sqlite", ".sqlite3")
EXCLUDE_DIRS = {
    "node_modules", ".venv", "venv", "packages", ".git", "__pycache__",
    ".trae", ".pytest_cache", "dist", "build", ".idea", ".vscode",
}
MAIN_DB_REL = "data/lobster_mu.db"
MAX_ROWS_LIMIT = 1000
QUERY_TIMEOUT = 15.0
# 这些首关键字视为只读，其余语句需显式允许写
READONLY_KEYWORDS = {"select", "with", "pragma", "explain"}


def _split_rel(rel: str):
    return [p for p in rel.replace("\\", "/").split("/") if p and p != "."]


def _is_excluded(rel: str) -> bool:
    return any(p in EXCLUDE_DIRS for p in _split_rel(rel))


def resolve_db(db_id: str) -> str:
    """把前端传回的数据库标识（项目相对路径）解析为绝对路径并做安全校验。"""
    if not db_id or not str(db_id).strip():
        raise ValueError("缺少数据库标识")
    rel = str(db_id).strip().replace("\\", "/").lstrip("/")
    if not rel.lower().endswith(DB_EXTS):
        raise ValueError("仅支持 SQLite 数据库文件（.db/.sqlite/.sqlite3）")
    if _is_excluded(rel):
        raise ValueError("该目录不在可访问范围内")
    full = os.path.abspath(os.path.join(BASE_DIR, rel))
    base = os.path.abspath(BASE_DIR)
    if os.path.commonpath([full, base]) != base:
        raise ValueError("非法路径：不允许访问项目目录之外的文件")
    if not os.path.isfile(full):
        raise ValueError("数据库文件不存在")
    return full


def _connect(path: str, readonly: bool):
    mode = "ro" if readonly else "rw"
    uri = "file:" + urllib.parse.quote(path.replace("\\", "/"), safe="/:") + f"?mode={mode}"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    if readonly:
        conn.execute("PRAGMA query_only=ON")
    return conn


def _count_tables(path: str):
    try:
        conn = _connect(path, readonly=True)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()
    except Exception:
        return None


def list_databases():
    """扫描项目内的 SQLite 数据库文件，按相对路径作为前端标识。"""
    found = []
    for root, dirs, files in os.walk(BASE_DIR):
        rel_root = os.path.relpath(root, BASE_DIR)
        parts = [] if rel_root == "." else rel_root.split(os.sep)
        # 原地裁剪，避免进入依赖树与产物目录
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        if any(p in EXCLUDE_DIRS for p in parts):
            continue
        if len(parts) > 5:
            dirs[:] = []
            continue
        for fn in files:
            if not fn.lower().endswith(DB_EXTS):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, BASE_DIR).replace("\\", "/")
            try:
                st = os.stat(full)
            except OSError:
                continue
            found.append({
                "id": rel,
                "name": fn,
                "path": rel,
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                "is_main": rel == MAIN_DB_REL,
            })
    found.sort(key=lambda d: (not d["is_main"], d["id"]))
    for item in found:
        item["table_count"] = _count_tables(os.path.join(BASE_DIR, item["id"]))
    return found


def get_schema(db_id: str):
    """读取指定库的表/视图清单、列定义与行数。"""
    path = resolve_db(db_id)
    conn = _connect(path, readonly=True)
    try:
        objects = conn.execute(
            "SELECT name, type, sql FROM sqlite_master "
            "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY type DESC, name"
        ).fetchall()
        tables = []
        for name, typ, sql in objects:
            safe = name.replace('"', '""')
            columns = []
            try:
                for cid, cname, ctype, notnull, dflt, pk in conn.execute(f'PRAGMA table_info("{safe}")'):
                    columns.append({
                        "name": cname, "type": ctype or "", "pk": bool(pk),
                        "notnull": bool(notnull), "default": dflt,
                    })
            except Exception:
                pass
            try:
                row_count = conn.execute(f'SELECT COUNT(*) FROM "{safe}"').fetchone()[0]
            except Exception:
                row_count = None
            indexes = []
            try:
                for r in conn.execute(f'PRAGMA index_list("{safe}")'):
                    indexes.append({"name": r[1], "unique": bool(r[2])})
            except Exception:
                pass
            tables.append({
                "name": name, "type": typ, "sql": sql or "",
                "columns": columns, "row_count": row_count, "indexes": indexes,
            })
        return {"success": True, "db": db_id, "tables": tables}
    finally:
        conn.close()


def _cell(value):
    if isinstance(value, bytes):
        text = value.hex()
        return "0x" + (text[:120] + f"…({len(value)} bytes)" if len(text) > 120 else text)
    return value


def _first_keyword(sql: str) -> str:
    m = re.match(r"^\s*(?:(?:--[^\n]*\n)|(?:/\*.*?\*/\s*))*([A-Za-z]+)", sql, re.S)
    return m.group(1).lower() if m else ""


def run_query(db_id: str, sql: str, max_rows: int = 200, allow_write: bool = False):
    """执行单条 SQL。只读语句直接执行；写语句必须 allow_write=True。"""
    sql = (sql or "").strip()
    if not sql:
        return {"success": False, "error": "SQL 不能为空"}
    if re.search(r"\b(attach|detach)\b", sql, re.I):
        return {"success": False, "error": "出于安全考虑，禁止 ATTACH / DETACH"}
    try:
        max_rows = max(1, min(int(max_rows or 200), MAX_ROWS_LIMIT))
    except (TypeError, ValueError):
        max_rows = 200

    keyword = _first_keyword(sql)
    readonly = keyword in READONLY_KEYWORDS
    if not readonly and not allow_write:
        return {"success": False,
                "error": f"该语句（{keyword or '未知'}）属于写操作，请勾选「允许写操作」后再执行"}

    try:
        path = resolve_db(db_id)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    started = time.time()
    conn = None
    try:
        conn = _connect(path, readonly=readonly)
        # 长查询自动中断，避免拖垮服务
        conn.set_progress_handler(lambda: 1 if time.time() - started > QUERY_TIMEOUT else 0, 1000)
        cur = conn.execute(sql)  # sqlite3 会拒绝多语句
        if cur.description:
            columns = [d[0] for d in cur.description]
            raw = cur.fetchmany(max_rows + 1)
            truncated = len(raw) > max_rows
            rows = [[_cell(v) for v in row] for row in raw[:max_rows]]
        else:
            columns, rows, truncated = [], [], False
        affected = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else None
        if not readonly:
            conn.commit()
        return {
            "success": True, "readonly": readonly,
            "columns": columns, "rows": rows, "truncated": truncated,
            "row_count": len(rows), "affected": affected,
            "elapsed_ms": round((time.time() - started) * 1000, 1),
        }
    except sqlite3.OperationalError as e:
        msg = str(e)
        if "interrupted" in msg.lower():
            msg = f"查询超过 {QUERY_TIMEOUT:.0f}s 已自动中断"
        return {"success": False, "error": msg}
    except (sqlite3.Warning, sqlite3.ProgrammingError) as e:
        return {"success": False, "error": f"{e}（仅支持单条 SQL 语句）"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if conn is not None:
            conn.close()
