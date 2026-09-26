# -*- coding: utf-8 -*-
"""存量知识库数据迁移：mu_knowledge_vectors → kb_content + kb_content_vectors

背景：知识库改为内容寻址共享存储后，旧数据仍按 user_id 隔离在 mu_knowledge_vectors。
本脚本将旧向量按文档内容 hash 去重后迁入 kb_content / kb_content_vectors，
并回填 mu_knowledge_docs.content_hash，使新旧数据统一走共享池检索。

用法：
  python migrate_kb_shared.py [--db /path/to/lobster_mu.db] [--dry-run]

  --dry-run   只统计不写入，查看有多少文档需要迁移、能去重多少
  --db        指定数据库文件（默认 lobster_mu/data/lobster_mu.db）

幂等：重复执行安全（已迁移的文档 content_hash 非空则跳过）。
迁移完成后旧表 mu_knowledge_vectors 数据可保留（search 已做兼容回退），
确认无问题后可手动 DROP TABLE mu_knowledge_vectors 释放空间。
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime


def _now():
    return datetime.now().isoformat()


def _doc_content_hash(doc_id: str, conn: sqlite3.Connection) -> str:
    """按文档所有 chunk 的 (chunk_index, content) 排序后拼合，计算 SHA-256。

    使用 doc_id 前缀避免不同用户相同内容的 doc 在 hash 层面混淆
    （实际上相同内容 → 相同 hash → 去重，正是期望行为）。
    """
    rows = conn.execute(
        "SELECT chunk_index, content FROM mu_knowledge_vectors"
        " WHERE doc_id = ? ORDER BY chunk_index",
        (doc_id,),
    ).fetchall()
    if not rows:
        return ""
    # 拼合所有 chunk 内容（含序号保证顺序）
    parts = []
    for r in rows:
        parts.append(f"{r['chunk_index']}:{r['content'] or ''}")
    combined = "\x00".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def migrate(db_path: str, dry_run: bool = False) -> dict:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # 确保新表存在（DDL 与 db.py 一致）
    conn.execute("""CREATE TABLE IF NOT EXISTS kb_content (
        content_hash TEXT PRIMARY KEY,
        filename     TEXT NOT NULL,
        file_size    INTEGER,
        chunk_count  INTEGER DEFAULT 0,
        created_at   TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS kb_content_vectors (
        content_hash TEXT NOT NULL,
        chunk_index  INTEGER,
        content      TEXT,
        vector       TEXT,
        PRIMARY KEY (content_hash, chunk_index)
    )""")
    # 确保 mu_knowledge_docs 有 content_hash 列
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(mu_knowledge_docs)").fetchall()}
    if "content_hash" not in cols:
        conn.execute("ALTER TABLE mu_knowledge_docs ADD COLUMN content_hash TEXT DEFAULT ''")
    conn.commit()

    stats = {
        "total_docs": 0,
        "already_migrated": 0,
        "new_content": 0,
        "deduplicated": 0,
        "empty_docs": 0,
        "total_vectors": 0,
        "vectors_migrated": 0,
        "errors": [],
    }

    # 查所有有向量的文档
    docs = conn.execute(
        "SELECT id, user_id, filename, file_size, chunk_count, content_hash"
        " FROM mu_knowledge_docs"
    ).fetchall()
    stats["total_docs"] = len(docs)

    for doc in docs:
        doc_id = doc["id"]

        # 已迁移的跳过
        if doc["content_hash"]:
            stats["already_migrated"] += 1
            continue

        # 无向量的空文档
        vec_count = conn.execute(
            "SELECT COUNT(*) AS c FROM mu_knowledge_vectors WHERE doc_id = ?", (doc_id,)
        ).fetchone()["c"]
        if vec_count == 0:
            stats["empty_docs"] += 1
            if not dry_run:
                conn.execute(
                    "UPDATE mu_knowledge_docs SET content_hash = ? WHERE id = ? AND user_id = ?",
                    (_doc_content_hash(doc_id, conn) or f"empty_{doc_id}", doc_id, doc["user_id"]),
                )
            continue

        stats["total_vectors"] += vec_count

        # 计算内容 hash
        c_hash = _doc_content_hash(doc_id, conn)
        if not c_hash:
            stats["errors"].append(f"doc {doc_id}: 无法计算 hash")
            continue

        # 查是否已有该内容
        existing = conn.execute(
            "SELECT content_hash FROM kb_content WHERE content_hash = ?", (c_hash,)
        ).fetchone()

        if existing:
            stats["deduplicated"] += 1
            # 已有内容，只回填引用
            if not dry_run:
                conn.execute(
                    "UPDATE mu_knowledge_docs SET content_hash = ? WHERE id = ? AND user_id = ?",
                    (c_hash, doc_id, doc["user_id"]),
                )
            continue

        # 新内容：写入 kb_content + kb_content_vectors
        stats["new_content"] += 1
        if not dry_run:
            conn.execute(
                "INSERT OR IGNORE INTO kb_content (content_hash, filename, file_size, chunk_count, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (c_hash, doc["filename"], doc["file_size"], vec_count, _now()),
            )
            # 批量迁移向量
            vecs = conn.execute(
                "SELECT chunk_index, content, vector FROM mu_knowledge_vectors"
                " WHERE doc_id = ? ORDER BY chunk_index",
                (doc_id,),
            ).fetchall()
            for v in vecs:
                conn.execute(
                    "INSERT OR IGNORE INTO kb_content_vectors (content_hash, chunk_index, content, vector)"
                    " VALUES (?, ?, ?, ?)",
                    (c_hash, v["chunk_index"], v["content"], v["vector"]),
                )
                stats["vectors_migrated"] += 1
            # 回填引用
            conn.execute(
                "UPDATE mu_knowledge_docs SET content_hash = ? WHERE id = ? AND user_id = ?",
                (c_hash, doc_id, doc["user_id"]),
            )

    if not dry_run:
        conn.commit()
    conn.close()

    # 输出报告
    print("=" * 60)
    print(f"{'[DRY-RUN] ' if dry_run else ''}知识库共享存储迁移报告")
    print("=" * 60)
    print(f"  文档总数:           {stats['total_docs']}")
    print(f"  已迁移（跳过）:     {stats['already_migrated']}")
    print(f"  空文档（无向量）:   {stats['empty_docs']}")
    print(f"  新内容（首次入库）: {stats['new_content']}")
    print(f"  去重命中（共享）:   {stats['deduplicated']}")
    print(f"  向量总数:           {stats['total_vectors']}")
    print(f"  已迁移向量:         {stats['vectors_migrated']}")
    if stats["errors"]:
        print(f"  错误:               {len(stats['errors'])}")
        for e in stats["errors"][:10]:
            print(f"    - {e}")
    if stats["total_docs"] > 0:
        dedup_rate = stats["deduplicated"] / max(stats["total_docs"] - stats["already_migrated"] - stats["empty_docs"], 1) * 100
        print(f"\n  去重率: {dedup_rate:.1f}%（{stats['deduplicated']} 篇文档与已有内容相同，无需重复存储向量）")
    print("=" * 60)
    if not dry_run:
        print("迁移完成。旧表 mu_knowledge_vectors 数据仍保留（兼容回退），确认无误后可手动删除。")

    return stats


def main():
    parser = argparse.ArgumentParser(description="知识库存量数据迁移到共享存储")
    default_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lobster_mu.db")
    parser.add_argument("--db", default=default_db, help="SQLite 数据库路径")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"错误：数据库文件不存在: {args.db}")
        sys.exit(1)

    migrate(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
