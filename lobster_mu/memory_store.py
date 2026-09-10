# -*- coding: utf-8 -*-
"""多用户龙虾Claw子项目 - 记忆存储（mu_memories，user_id 隔离；分词复用 MemoryManager.extract_keywords）"""
import json
from datetime import datetime

from lobster_mu.db import get_conn

# 仅为分词复用（该实例不用于存取，memory.db 不归 mu 管）
_kw_manager = None


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def extract_keywords(text: str, max_keywords: int = 8) -> list:
    global _kw_manager
    if _kw_manager is None:
        from memory import MemoryManager
        _kw_manager = MemoryManager()
    try:
        return _kw_manager.extract_keywords(text, max_keywords=max_keywords)
    except Exception:
        return []


def store(user_id: int, memory_type: str, content: str, keywords: list = None,
          session_id: str = None, weight: float = 1.0) -> int:
    """写入记忆；近似重复时累加权重（复用相似度思路简化为关键词重查）"""
    if memory_type not in ("short_term", "long_term"):
        raise ValueError("memory_type must be 'short_term' or 'long_term'")
    kw_str = json.dumps(keywords, ensure_ascii=False) if keywords else None
    # 查近似重复（同用户同类型，取最新一条内容相似者简化处理）
    conn = get_conn()
    try:
        existing = None
        kws = keywords or extract_keywords(content, max_keywords=5)
        for k in kws[:2]:
            rows = conn.execute(
                "SELECT id, content FROM mu_memories WHERE user_id = ? AND type = ?"
                " AND (content LIKE ? OR keywords LIKE ?) ORDER BY timestamp DESC LIMIT 1",
                (user_id, memory_type, f"%{k}%", f"%{k}%"),
            ).fetchall()
            for r in rows:
                if _similarity(content, r["content"]) >= 0.7:
                    existing = r["id"]
                    break
            if existing:
                break
        if existing:
            conn.execute(
                "UPDATE mu_memories SET weight = weight + ?, access_count = access_count + 1, timestamp = ?"
                " WHERE id = ?",
                (weight, _now(), existing),
            )
            conn.commit()
            return existing
        cur = conn.execute(
            "INSERT INTO mu_memories (user_id, type, content, keywords, session_id, weight, access_count, timestamp)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (user_id, memory_type, content, kw_str, session_id, weight, _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _similarity(text1: str, text2: str) -> float:
    if not text1 or not text2:
        return 0.0
    w1 = set(extract_keywords(text1, max_keywords=20)) | {w.lower() for w in text1.split() if len(w) > 1}
    w2 = set(extract_keywords(text2, max_keywords=20)) | {w.lower() for w in text2.split() if len(w) > 1}
    if not w1 or not w2:
        return 0.0
    inter = w1 & w2
    union = w1 | w2
    return len(inter) / len(union) if union else 0.0


def retrieve_by_keywords(user_id: int, keywords: list, memory_type: str = None, limit: int = 10) -> list:
    if not keywords:
        return []
    conn = get_conn()
    results = []
    try:
        per_kw = max(1, limit // max(1, len(keywords[:5])))
        for kw in keywords[:5]:
            sql = ("SELECT * FROM mu_memories WHERE user_id = ? AND (content LIKE ? OR keywords LIKE ?)")
            params = [user_id, f"%{kw}%", f"%{kw}%"]
            if memory_type:
                sql += " AND type = ?"
                params.append(memory_type)
            sql += " ORDER BY (weight * 0.7 + access_count * 0.3) DESC, timestamp DESC LIMIT ?"
            params.append(per_kw)
            for r in conn.execute(sql, params).fetchall():
                results.append(_row_to_dict(r))
        # 命中即累加访问计数
        ids = [r["id"] for r in results]
        if ids:
            conn.executemany(
                "UPDATE mu_memories SET access_count = access_count + 1, weight = weight + 0.1 WHERE id = ?",
                [(i,) for i in ids],
            )
            conn.commit()
    finally:
        conn.close()
    # 去重
    seen = set()
    unique = []
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            unique.append(r)
    return unique[:limit]


def _row_to_dict(r) -> dict:
    d = dict(r)
    try:
        d["keywords"] = json.loads(d["keywords"]) if d.get("keywords") else []
    except Exception:
        d["keywords"] = []
    return d


def list_memories(user_id: int, memory_type: str = None, limit: int = 100) -> list:
    conn = get_conn()
    try:
        sql = "SELECT * FROM mu_memories WHERE user_id = ?"
        params = [user_id]
        if memory_type:
            sql += " AND type = ?"
            params.append(memory_type)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        return [_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def add_memory(user_id: int, memory_type: str, content: str, session_id: str = None) -> int:
    return store(user_id, memory_type, content,
                 keywords=extract_keywords(content, max_keywords=8),
                 session_id=session_id, weight=1.0)


def delete_memory(user_id: int, memory_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM mu_memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def search_memories(user_id: int, query: str, memory_type: str = None, limit: int = 20) -> list:
    conn = get_conn()
    try:
        sql = "SELECT * FROM mu_memories WHERE user_id = ? AND (content LIKE ? OR keywords LIKE ?)"
        params = [user_id, f"%{query}%", f"%{query}%"]
        if memory_type:
            sql += " AND type = ?"
            params.append(memory_type)
        sql += " ORDER BY (weight * 0.7 + access_count * 0.3) DESC, timestamp DESC LIMIT ?"
        params.append(limit)
        results = [_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
    # 评分排序（复制原版 _score_results 逻辑）
    q_lower = query.lower()
    q_words = set(q_lower.split())
    for r in results:
        score = 0
        c_lower = r["content"].lower()
        if q_lower in c_lower:
            score += 5
        for w in q_words:
            if w and w in c_lower:
                score += 2
        for kw in r.get("keywords") or []:
            if kw.lower() in q_lower:
                score += 3
        r["score"] = score
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def clear_memories(user_id: int, memory_type: str = None) -> int:
    conn = get_conn()
    try:
        if memory_type:
            cur = conn.execute("DELETE FROM mu_memories WHERE user_id = ? AND type = ?", (user_id, memory_type))
        else:
            cur = conn.execute("DELETE FROM mu_memories WHERE user_id = ?", (user_id,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
