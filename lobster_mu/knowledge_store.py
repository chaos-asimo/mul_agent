# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - RAG 知识库（内容寻址共享存储）

设计：
- 相同文件内容（SHA-256）全局只切块 + embedding 一次，存 kb_content / kb_content_vectors
- 用户文档 mu_knowledge_docs 仅存一行引用（user_id → content_hash）
- 检索时 JOIN 共享向量池，余弦相似度计算不变
- 删除用户文档只删引用，共享内容保留（其他用户可能还在用）

切块复用 rag.text_chunker.TextChunker（chunk_size=500/overlap=100），
embedding 调用方式照抄 rag/knowledge_base.py 的 _get_embedding_adapter，
向量以 JSON 数组存 SQLite。
"""
import hashlib
import json
import logging
import math
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from lobster_mu.db import get_conn

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat()


def _content_hash(content: str) -> str:
    """文件内容 SHA-256（内容寻址 key）"""
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


# 本地 BGE 等 embedding 模型加载耗时（首次数十秒），按签名缓存适配器实例
_adapter_cache: Dict[tuple, object] = {}
_adapter_cache_lock = None


def _get_adapter_cache_lock():
    global _adapter_cache_lock
    if _adapter_cache_lock is None:
        import threading
        _adapter_cache_lock = threading.Lock()
    return _adapter_cache_lock


def _get_embedding_adapter():
    """取第一个启用的 embedding 模型并缓存适配器（避免每次调用重复加载本地模型）"""
    try:
        from models.model_manager import ModelManager
        from engine.agent_worker import create_embedding_adapter

        model_manager = ModelManager()
        for model_config in model_manager.get_all():
            if not getattr(model_config, "enabled", False):
                continue
            if getattr(model_config, "model_type", "") != "embedding":
                continue
            # 本地模型（api_type=="local"，如 BGE）不需要 api_key；只有远程模型才校验 key。
            # 之前这里一律要求非空 api_key，会把本地 embedding 模型过滤掉，导致适配器为 None、
            # 知识库入库报错且检索恒为空——多用户环境下知识库完全失效的根因。
            if getattr(model_config, "api_type", "") != "local" and not getattr(model_config, "api_key", ""):
                continue
            signature = (
                getattr(model_config, "api_type", ""),
                getattr(model_config, "model_name", ""),
                getattr(model_config, "api_url", ""),
            )
            cached = _adapter_cache.get(signature)
            if cached is not None:
                return cached
            try:
                adapter = create_embedding_adapter(model_config)
            except Exception as e:
                logger.error(f"[mu-kb] 创建 embedding adapter 失败: {e}")
                continue
            if adapter is not None:
                with _get_adapter_cache_lock():
                    _adapter_cache[signature] = adapter
                return adapter
    except Exception as e:
        logger.error(f"[mu-kb] 获取 embedding 模型失败: {e}")
    return None


def add_document(user_id: int, filename: str, file_size: int, content: str, stored_name: str = "") -> Dict:
    """上传知识库文档（内容寻址去重 + 共享向量池）

    流程：
    1. 计算 content = SHA-256(文件内容)
    2. 若 kb_content 已有该 hash → 跳过切块+embedding，仅插一行用户引用（毫秒级）
    3. 否则 → 切块 + embedding + 写入 kb_content / kb_content_vectors（首次，~10-30s）
    4. 在 mu_knowledge_docs 插入用户引用行

    Raises:
        ValueError: 未配置 embedding 模型（与原版 KnowledgeBase 行为一致）
    """
    from rag.text_chunker import TextChunker

    c_hash = _content_hash(content)
    created_at = _now()

    conn = get_conn()
    try:
        # 查重：全局是否已有该内容
        existing = conn.execute(
            "SELECT content_hash, chunk_count FROM kb_content WHERE content_hash = ?",
            (c_hash,),
        ).fetchone()

        if existing:
            # 命中：跳过切块+embedding，直接引用
            chunk_count = existing["chunk_count"]
            doc_id = f"mu{user_id}_{uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO mu_knowledge_docs (id, user_id, filename, stored_name, file_size, chunk_count,"
                " content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (doc_id, user_id, filename, stored_name, file_size, chunk_count, c_hash, created_at),
            )
            conn.commit()
            logger.info(f"[mu-kb] user={user_id} 文件 {filename} 命中共享内容 (hash={c_hash[:16]}...)，跳过 embedding")
            return {"doc_id": doc_id, "filename": filename, "chunk_count": chunk_count,
                    "file_size": file_size, "shared": True}

        # 未命中：切块 + embedding + 写入共享池
        chunks = TextChunker().chunk(content or "")
        logger.info(f"[mu-kb] user={user_id} 文件 {filename} 新内容，分块 {len(chunks)} 块，开始 embedding")

        if not chunks:
            # 空文档：只记元数据
            conn.execute(
                "INSERT OR IGNORE INTO kb_content (content_hash, filename, file_size, chunk_count, created_at)"
                " VALUES (?, ?, ?, 0, ?)",
                (c_hash, filename, file_size, created_at),
            )
            doc_id = f"mu{user_id}_{uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO mu_knowledge_docs (id, user_id, filename, stored_name, file_size, chunk_count,"
                " content_hash, created_at) VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                (doc_id, user_id, filename, stored_name, file_size, c_hash, created_at),
            )
            conn.commit()
            return {"doc_id": doc_id, "filename": filename, "chunk_count": 0,
                    "file_size": file_size, "shared": False}

        adapter = _get_embedding_adapter()
        if adapter is None:
            raise ValueError("未配置embedding模型，请先在模型配置中添加embedding类型的模型")

        embeddings = adapter.embeddings([chunk["content"] for chunk in chunks])

        # 写入共享内容表
        conn.execute(
            "INSERT OR IGNORE INTO kb_content (content_hash, filename, file_size, chunk_count, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (c_hash, filename, file_size, len(chunks), created_at),
        )
        # 批量写入共享向量池
        conn.executemany(
            "INSERT OR IGNORE INTO kb_content_vectors (content_hash, chunk_index, content, vector)"
            " VALUES (?, ?, ?, ?)",
            [(c_hash, chunk["chunk_index"], chunk["content"], json.dumps(emb))
             for chunk, emb in zip(chunks, embeddings)],
        )

        # 插入用户引用
        doc_id = f"mu{user_id}_{uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO mu_knowledge_docs (id, user_id, filename, stored_name, file_size, chunk_count,"
            " content_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, user_id, filename, stored_name, file_size, len(chunks), c_hash, created_at),
        )
        conn.commit()
        logger.info(f"[mu-kb] user={user_id} 文件 {filename} 已入库 (hash={c_hash[:16]}..., {len(chunks)} chunks)")
        return {"doc_id": doc_id, "filename": filename, "chunk_count": len(chunks),
                "file_size": file_size, "shared": False}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def warmup() -> bool:
    """预热 embedding 模型（后台调用）：真正加载一次模型并缓存，避免首次搜索时长时间加载；返回是否成功"""
    adapter = _get_embedding_adapter()
    if adapter is None:
        return False
    try:
        adapter.embed_query("预热")
        return True
    except Exception as e:
        logger.debug(f"[mu-kb] warmup 失败: {e}")
        return False


def is_model_ready() -> bool:
    """embedding 模型是否已在内存中加载（本地 BGE 的 _model 已初始化）"""
    adapter = _get_embedding_adapter()
    if adapter is None:
        return False
    return getattr(adapter, "_model", None) is not None


def warmup_sync(timeout: int = 120) -> bool:
    """同步预热（阻塞）：有知识库文档的用户聊天时首次调用，之后秒级返回；返回是否成功"""
    if is_model_ready():
        return True
    return warmup()


def user_has_docs(user_id: int) -> bool:
    """用户是否已上传知识库文档（决定聊天时是否需要同步预热 embedding 模型）"""
    try:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM mu_knowledge_docs WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return bool(row and row["c"] > 0)
        finally:
            conn.close()
    except Exception as e:
        logger.debug(f"[mu-kb] user_has_docs 失败: {e}")
        return False


def _cosine(a: List[float], b: List[float]) -> float:
    """纯 Python 余弦相似度（避免额外依赖）"""
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def search(user_id: int, query: str, top_k: int = 5, threshold: float = 0.3) -> List[Dict]:
    """在该用户所有文档的共享向量池做余弦相似度检索，返回 [{filename, content, score}]

    流程：
    1. 查出该用户所有 content_hash（通过 mu_knowledge_docs）
    2. 从 kb_content_vectors 批量取出对应向量
    3. 逐条计算余弦相似度，返回 top_k
    """
    if not query:
        return []
    adapter = _get_embedding_adapter()
    if adapter is None:
        logger.warning("[mu-kb] 检索中止：未配置 embedding 模型")
        return []
    try:
        query_embedding = adapter.embed_query(query)
    except Exception as e:
        logger.error(f"[mu-kb] 查询向量化失败: {e}")
        return []

    conn = get_conn()
    try:
        # 1. 该用户的所有文档引用（含 filename 和 content_hash）
        docs = conn.execute(
            "SELECT id, filename, content_hash FROM mu_knowledge_docs WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        if not docs:
            return []

        # 2. 批量查共享向量池
        # content_hash -> filename（同一内容可能被多文档引用，取第一个即可）
        hash_to_name = {}
        for d in docs:
            h = d["content_hash"]
            if h and h not in hash_to_name:
                hash_to_name[h] = d["filename"] or "未知文档"
        hashes = [d["content_hash"] for d in docs if d["content_hash"]]
        if not hashes:
            # 兼容存量未迁移数据：回退到旧表 mu_knowledge_vectors（含 filename 列）
            rows = conn.execute(
                "SELECT v.content, v.vector, d.filename AS filename FROM mu_knowledge_vectors v"
                " LEFT JOIN mu_knowledge_docs d ON v.doc_id = d.id"
                " WHERE v.user_id = ?",
                (user_id,),
            ).fetchall()
        else:
            # 用 IN 查询（hash 数量 = 用户文档数，通常 < 100）；含 content_hash 列，无 filename
            placeholders = ",".join("?" * len(hashes))
            rows = conn.execute(
                f"SELECT v.content, v.vector, v.content_hash AS content_hash"
                f" FROM kb_content_vectors v"
                f" WHERE v.content_hash IN ({placeholders})",
                hashes,
            ).fetchall()

    finally:
        conn.close()

    def _row_col(row, key, default=None):
        """安全取 sqlite3.Row 的列：列不存在时返回 default（不抛 IndexError）"""
        try:
            return row[key]
        except Exception:
            return default

    scored = []
    for row in rows:
        try:
            vec = json.loads(row["vector"])
        except Exception:
            continue
        score = _cosine(query_embedding, vec)
        if score >= threshold:
            # 确定 filename：新表走 content_hash 映射，旧表直接取 filename 列
            rh = _row_col(row, "content_hash")
            filename = hash_to_name.get(rh) if rh else None
            if not filename:
                filename = _row_col(row, "filename") or "未知文档"
            scored.append((score, filename, row["content"] or ""))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"filename": fn, "content": content, "score": round(score, 4)}
            for score, fn, content in scored[:top_k]]


def list_documents(user_id: int) -> List[Dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, filename, file_size, chunk_count, created_at, content_hash"
            " FROM mu_knowledge_docs WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def delete_document(user_id: int, doc_id: str) -> Optional[int]:
    """删除用户文档引用（不删共享内容，其他用户可能还在用）

    返回删除的 chunk 数（用于前端展示）；文档不存在返回 None。
    共享内容 kb_content / kb_content_vectors 保留，由 GC 定期清理无引用孤儿。
    """
    conn = get_conn()
    try:
        doc = conn.execute(
            "SELECT id, chunk_count, content_hash FROM mu_knowledge_docs WHERE id = ? AND user_id = ?",
            (doc_id, user_id),
        ).fetchone()
        if not doc:
            return None
        conn.execute(
            "DELETE FROM mu_knowledge_docs WHERE id = ? AND user_id = ?",
            (doc_id, user_id),
        )
        # 兼容：若旧表还有该用户的向量（未迁移），一并清理
        conn.execute(
            "DELETE FROM mu_knowledge_vectors WHERE doc_id = ? AND user_id = ?",
            (doc_id, user_id),
        )
        conn.commit()
        return doc["chunk_count"]
    finally:
        conn.close()


def gc_orphaned_content() -> int:
    """清理无用户引用的孤儿共享内容（可由 cron 定期调用）

    返回删除的 content_hash 数量。
    """
    conn = get_conn()
    try:
        # 找出没有任何用户引用的 content_hash
        orphans = conn.execute(
            "SELECT c.content_hash FROM kb_content c"
            " WHERE NOT EXISTS ("
            "   SELECT 1 FROM mu_knowledge_docs d WHERE d.content_hash = c.content_hash"
            " )"
        ).fetchall()
        if not orphans:
            return 0
        hashes = [r["content_hash"] for r in orphans]
        placeholders = ",".join("?" * len(hashes))
        conn.execute(f"DELETE FROM kb_content_vectors WHERE content_hash IN ({placeholders})", hashes)
        conn.execute(f"DELETE FROM kb_content WHERE content_hash IN ({placeholders})", hashes)
        conn.commit()
        logger.info(f"[mu-kb] GC 清理孤儿内容 {len(hashes)} 个")
        return len(hashes)
    finally:
        conn.close()


def stats(user_id: int) -> Dict:
    conn = get_conn()
    try:
        documents = conn.execute(
            "SELECT COUNT(*) AS c FROM mu_knowledge_docs WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]
        # 该用户文档涉及的 chunk 总数（通过共享池统计）
        row = conn.execute(
            "SELECT COALESCE(SUM(d.chunk_count), 0) AS total"
            " FROM mu_knowledge_docs d WHERE d.user_id = ?", (user_id,)
        ).fetchone()
        chunks = row["total"]
    finally:
        conn.close()
    return {"documents": documents, "chunks": chunks}


def admin_all_users_knowledge() -> Dict:
    """管理员查看所有用户的知识库情况（含共享文档统计）

    返回:
    {
        "users": [
            {
                "user_id": int,
                "username": str,
                "display_name": str,
                "documents": int,
                "total_chunks": int,
                "shared_docs": int,       # 引用了共享内容（≥2用户）的文档数
                "docs": [{id, filename, file_size, chunk_count, content_hash, shared, shared_by}]
            }
        ],
        "summary": {
            "total_users": int,
            "users_with_docs": int,
            "total_documents": int,
            "total_unique_contents": int,   # kb_content 行数
            "total_shared_vectors": int,    # kb_content_vectors 行数
            "shared_content_list": [{content_hash, filename, ref_count, chunk_count}]
        }
    }
    """
    conn = get_conn()
    try:
        # 每个有文档的用户
        user_rows = conn.execute(
            "SELECT d.user_id, u.username, u.display_name,"
            " COUNT(*) AS documents,"
            " COALESCE(SUM(d.chunk_count), 0) AS total_chunks"
            " FROM mu_knowledge_docs d"
            " LEFT JOIN users u ON d.user_id = u.id"
            " GROUP BY d.user_id, u.username, u.display_name"
            " ORDER BY d.user_id"
        ).fetchall()

        # 共享内容引用计数（≥2 个用户引用 = 共享）
        shared_counts = {}
        for r in conn.execute(
            "SELECT content_hash, COUNT(DISTINCT user_id) AS ref_count"
            " FROM mu_knowledge_docs WHERE content_hash != ''"
            " GROUP BY content_hash HAVING ref_count >= 2"
        ).fetchall():
            shared_counts[r["content_hash"]] = r["ref_count"]

        users = []
        for ur in user_rows:
            docs = conn.execute(
                "SELECT id, filename, file_size, chunk_count, content_hash, created_at"
                " FROM mu_knowledge_docs WHERE user_id = ? ORDER BY created_at DESC",
                (ur["user_id"],),
            ).fetchall()
            doc_list = []
            shared_docs = 0
            for d in docs:
                is_shared = d["content_hash"] in shared_counts
                if is_shared:
                    shared_docs += 1
                doc_list.append({
                    "id": d["id"],
                    "filename": d["filename"],
                    "file_size": d["file_size"],
                    "chunk_count": d["chunk_count"],
                    "content_hash": d["content_hash"],
                    "created_at": d["created_at"],
                    "shared": is_shared,
                    "shared_by": shared_counts.get(d["content_hash"], 1),
                })
            users.append({
                "user_id": ur["user_id"],
                "username": ur["username"] or str(ur["user_id"]),
                "display_name": ur["display_name"] or "",
                "documents": ur["documents"],
                "total_chunks": ur["total_chunks"],
                "shared_docs": shared_docs,
                "docs": doc_list,
            })

        # 全局共享内容列表
        shared_content_list = []
        for ch, rc in shared_counts.items():
            row = conn.execute(
                "SELECT content_hash, filename, chunk_count FROM kb_content WHERE content_hash = ?",
                (ch,),
            ).fetchone()
            if row:
                shared_content_list.append({
                    "content_hash": row["content_hash"],
                    "filename": row["filename"],
                    "ref_count": rc,
                    "chunk_count": row["chunk_count"],
                })
        shared_content_list.sort(key=lambda x: x["ref_count"], reverse=True)

        # 汇总
        total_unique = conn.execute("SELECT COUNT(*) AS c FROM kb_content").fetchone()["c"]
        total_vectors = conn.execute("SELECT COUNT(*) AS c FROM kb_content_vectors").fetchone()["c"]

        return {
            "users": users,
            "summary": {
                "total_users": len(users),
                "users_with_docs": len(users),
                "total_documents": sum(u["documents"] for u in users),
                "total_unique_contents": total_unique,
                "total_shared_vectors": total_vectors,
                "shared_content_list": shared_content_list,
            },
        }
    finally:
        conn.close()


def admin_get_doc_file(doc_id) -> Optional[Dict]:
    """管理员取某知识库文档的原始文件信息，返回 {user_id, filename, stored_name}；
    文档不存在或未留存原文件（stored_name 为空）返回 None。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT user_id, filename, stored_name FROM mu_knowledge_docs WHERE id = ?",
            (doc_id,),
        ).fetchone()
        if not row or not row["stored_name"]:
            return None
        return {"user_id": row["user_id"], "filename": row["filename"] or "", "stored_name": row["stored_name"]}
    finally:
        conn.close()


def admin_get_doc_content(doc_id) -> Optional[Dict]:
    """管理员读取某知识库文档的提取文本（拼接各分块）。
    返回 {filename, file_size, content}；文档不存在返回 None。"""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT filename, file_size, content_hash FROM mu_knowledge_docs WHERE id = ?",
            (doc_id,),
        ).fetchone()
        if not row:
            return None
        c_hash = row["content_hash"] or ""
        content = ""
        if c_hash:
            chunks = conn.execute(
                "SELECT content FROM kb_content_vectors WHERE content_hash = ? ORDER BY chunk_index",
                (c_hash,),
            ).fetchall()
            content = "\n".join((c["content"] or "") for c in chunks)
        return {
            "filename": row["filename"] or "",
            "file_size": row["file_size"] or 0,
            "content": content,
        }
    finally:
        conn.close()
