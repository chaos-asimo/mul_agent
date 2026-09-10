# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - RAG 知识库（mu_knowledge_docs / mu_knowledge_vectors，user_id 隔离）

切块复用 rag.text_chunker.TextChunker（沿用原版默认参数 chunk_size=500/overlap=100），
embedding 调用方式照抄 rag/knowledge_base.py 的 _get_embedding_adapter，
向量以 JSON 数组存 SQLite（原版 rag/vector_store.py 同款存储格式），仅在本用户向量内检索。
"""
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


def _get_embedding_adapter():
    """照抄 KnowledgeBase._get_embedding_adapter：取第一个启用的 embedding 模型"""
    try:
        from models.model_manager import ModelManager
        from engine.agent_worker import create_embedding_adapter

        model_manager = ModelManager()
        for model_config in model_manager.get_all():
            if not getattr(model_config, "enabled", False):
                continue
            if getattr(model_config, "model_type", "") != "embedding":
                continue
            if not getattr(model_config, "api_key", ""):
                continue
            try:
                adapter = create_embedding_adapter(model_config)
                if adapter is not None:
                    return adapter
            except Exception as e:
                logger.error(f"[mu-kb] 创建 embedding adapter 失败: {e}")
                continue
    except Exception as e:
        logger.error(f"[mu-kb] 获取 embedding 模型失败: {e}")
    return None


def add_document(user_id: int, filename: str, file_size: int, content: str) -> Dict:
    """切块 + 向量化 + 入库（文档元数据存 mu_knowledge_docs，向量存 mu_knowledge_vectors）

    Raises:
        ValueError: 未配置 embedding 模型（与原版 KnowledgeBase 行为一致）
    """
    from rag.text_chunker import TextChunker

    doc_id = f"mu{user_id}_{uuid4().hex[:12]}"
    chunks = TextChunker().chunk(content or "")
    logger.info(f"[mu-kb] user={user_id} 文件 {filename} 分块完成，共 {len(chunks)} 块")

    created_at = _now()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO mu_knowledge_docs (id, user_id, filename, file_size, chunk_count,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, user_id, filename, file_size, 0, created_at),
        )
        conn.commit()
    finally:
        conn.close()

    if not chunks:
        return {"doc_id": doc_id, "filename": filename, "chunk_count": 0, "file_size": file_size}

    adapter = _get_embedding_adapter()
    if adapter is None:
        raise ValueError("未配置embedding模型，请先在模型配置中添加embedding类型的模型")

    try:
        embeddings = adapter.embeddings([chunk["content"] for chunk in chunks])
    except Exception as e:
        logger.error(f"[mu-kb] 生成 embedding 失败: {e}")
        raise

    conn = get_conn()
    try:
        for chunk, embedding in zip(chunks, embeddings):
            conn.execute(
                "INSERT INTO mu_knowledge_vectors (user_id, doc_id, chunk_index, content,"
                " vector, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, doc_id, chunk["chunk_index"], chunk["content"],
                 json.dumps(embedding), created_at),
            )
        conn.execute(
            "UPDATE mu_knowledge_docs SET chunk_count = ? WHERE id = ? AND user_id = ?",
            (len(chunks), doc_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()
    logger.info(f"[mu-kb] user={user_id} 文件 {filename} 已入库 (doc_id={doc_id})")
    return {"doc_id": doc_id, "filename": filename, "chunk_count": len(chunks),
            "file_size": file_size}


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
    """仅在该 user 的向量中做余弦相似度检索，返回 [{filename, content, score}]"""
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
        rows = conn.execute(
            "SELECT v.content, v.vector, d.filename FROM mu_knowledge_vectors v"
            " LEFT JOIN mu_knowledge_docs d ON v.doc_id = d.id"
            " WHERE v.user_id = ?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    scored = []
    for row in rows:
        try:
            vec = json.loads(row["vector"])
        except Exception:
            continue
        score = _cosine(query_embedding, vec)
        if score >= threshold:
            scored.append((score, row["filename"] or "未知文档", row["content"] or ""))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"filename": fn, "content": content, "score": round(score, 4)}
            for score, fn, content in scored[:top_k]]


def list_documents(user_id: int) -> List[Dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, filename, file_size, chunk_count, created_at"
            " FROM mu_knowledge_docs WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def delete_document(user_id: int, doc_id: str) -> Optional[int]:
    """删除文档并级联删向量，返回删除的分块数；文档不存在返回 None"""
    conn = get_conn()
    try:
        doc = conn.execute(
            "SELECT id FROM mu_knowledge_docs WHERE id = ? AND user_id = ?",
            (doc_id, user_id),
        ).fetchone()
        if not doc:
            return None
        cur = conn.execute(
            "DELETE FROM mu_knowledge_vectors WHERE doc_id = ? AND user_id = ?",
            (doc_id, user_id),
        )
        deleted = cur.rowcount
        conn.execute(
            "DELETE FROM mu_knowledge_docs WHERE id = ? AND user_id = ?",
            (doc_id, user_id),
        )
        conn.commit()
        return deleted
    finally:
        conn.close()


def stats(user_id: int) -> Dict:
    conn = get_conn()
    try:
        documents = conn.execute(
            "SELECT COUNT(*) AS c FROM mu_knowledge_docs WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]
        chunks = conn.execute(
            "SELECT COUNT(*) AS c FROM mu_knowledge_vectors WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]
    finally:
        conn.close()
    return {"documents": documents, "chunks": chunks}
