# -*- coding: utf-8 -*-
"""多用户知识库 - Chroma 向量索引层（HNSW 余弦检索）

定位：
- SQLite（kb_content / kb_content_vectors）仍是内容寻址的**事实来源**，保存分块原文与向量；
- 本模块是**派生索引**：每个用户文档引用（mu_knowledge_docs 一行 = 一个 doc_id）的每个分块
  在 Chroma 里存一条记录，向量直接复用 SQLite 中已计算好的 embedding，**共享内容不重新向量化**。
- 检索走 HNSW 近似最近邻 + 元数据预过滤（user_id == 本人 OR is_public == 1），
  替代 knowledge_store 里 O(N) 的内存暴力余弦。

记录结构（collection: mu_kb_v1, cosine）：
  id       = f"{doc_id}#{chunk_index}"（doc_id 全局唯一）
  embedding= 复用 kb_content_vectors.vector
  document = 分块原文
  metadata = {user_id:int, is_public:int(0/1), doc_id:str, content_hash:str,
              chunk_index:int, filename:str}

容错：chromadb 未安装 / 初始化失败时 available() 返回 False，所有写入静默跳过、
检索返回 None，调用方回退到原暴力检索，保证知识库在任何环境下可用。

Windows 文件锁：全量重建采用「写新目录 → 重置客户端 → 目录改名切换 → 延迟删旧目录」，
不对正在被占用的目录做 rmtree。
"""
import json
import logging
import os
import shutil
import threading
import time
from typing import Dict, List, Optional

from lobster_mu.db import BASE_DIR, get_conn

logger = logging.getLogger(__name__)

COLLECTION_NAME = "mu_kb_v1"
# 全量重建用 A/B 双 collection：往非活动名灌数据，完成后切换指针再删旧活动库。
# 不用「新目录→改名」方案——chromadb rust 客户端在进程内持有目录锁，
# Windows 下对活跃目录 rename 会 WinError 5；同库 collection 切换无此问题，
# 且重建期间旧活动库始终完整可用。
REBUILD_COLLECTION_NAME = "mu_kb_v2"
INDEX_DIR = os.path.join(BASE_DIR, "data", "chroma_kb")
# 活动 collection 名指针（重建后可能是 v2，进程重启后据此打开；随 INDEX_DIR 派生以便测试隔离）
REBUILD_DIR = INDEX_DIR  # 兼容：不再使用独立目录，保留常量供测试 patch
# 重建后旧目录改名前缀，重启时尽力清理（Windows 下句柄可能延迟释放）
OLD_DIR_PREFIX = "chroma_kb_old_"

_UPSERT_BATCH = 500

_client = None
_collection = None
_init_lock = threading.Lock()
_write_lock = threading.RLock()
_disabled = False  # chromadb 不可用或初始化硬失败时置 True，避免反复尝试


def available() -> bool:
    """chromadb 是否可用（import + 取 collection 成功）"""
    if _disabled:
        return False
    try:
        return _get_collection() is not None
    except Exception:
        return False


def _cleanup_old_dirs() -> None:
    """清理上次重建残留的 chroma_kb_old_* 目录（句柄释放后才能删掉，删不掉就等下次）"""
    data_dir = os.path.dirname(INDEX_DIR)
    try:
        for name in os.listdir(data_dir):
            if name.startswith(OLD_DIR_PREFIX):
                shutil.rmtree(os.path.join(data_dir, name), ignore_errors=True)
    except Exception as e:
        logger.debug(f"[mu-kb-idx] 清理旧索引目录失败（可忽略）: {e}")


def _active_pointer_path() -> str:
    return os.path.join(os.path.dirname(INDEX_DIR), "chroma_kb_active.txt")


def _read_active_name() -> str:
    """读活动 collection 名指针；损坏/不存在返回主名"""
    try:
        with open(_active_pointer_path(), "r", encoding="utf-8") as f:
            name = f.read().strip()
            return name or COLLECTION_NAME
    except Exception:
        return COLLECTION_NAME


def _write_active_name(name: str) -> None:
    try:
        with open(_active_pointer_path(), "w", encoding="utf-8") as f:
            f.write(name)
    except Exception as e:
        logger.warning(f"[mu-kb-idx] 活动指针写入失败: {e}")


def _get_collection():
    """取（惰性创建）持久化 Chroma collection；失败返回 None"""
    global _client, _collection, _disabled
    if _collection is not None:
        return _collection
    with _init_lock:
        if _collection is not None:
            return _collection
        try:
            import chromadb
        except Exception as e:
            logger.warning(f"[mu-kb-idx] chromadb 未安装，向量索引不可用，回退暴力检索: {e}")
            _disabled = True
            return None
        try:
            _cleanup_old_dirs()
            os.makedirs(INDEX_DIR, exist_ok=True)
            _client = chromadb.PersistentClient(path=INDEX_DIR)
            # 按指针打开上次活动 collection；若指针指向的库不存在（如目录被清）回退主名
            active_name = _read_active_name()
            existing = {c.name for c in _client.list_collections()}
            if active_name not in existing:
                active_name = COLLECTION_NAME
            _collection = _client.get_or_create_collection(
                name=active_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"[mu-kb-idx] Chroma 索引就绪: {INDEX_DIR} "
                        f"collection={active_name} (现有 {_collection.count()} 条)")
            return _collection
        except Exception as e:
            logger.error(f"[mu-kb-idx] Chroma 初始化失败，回退暴力检索: {e}")
            _disabled = True
            return None


def _chunk_id(doc_id: str, chunk_index: int) -> str:
    return f"{doc_id}#{chunk_index}"


def _meta(doc_id, user_id, is_public, content_hash, chunk_index, filename) -> Dict:
    # Chroma metadata 值仅支持 str/int/float/bool
    return {
        "user_id": int(user_id),
        "is_public": 1 if is_public else 0,
        "doc_id": str(doc_id),
        "content_hash": str(content_hash or ""),
        "chunk_index": int(chunk_index),
        "filename": str(filename or "未知文档")[:512],
    }


def upsert_doc(doc_id: str, user_id: int, is_public: bool, content_hash: str,
               filename: str, items: List[Dict]) -> bool:
    """写入/更新一个文档引用的全部分块。

    items: [{"chunk_index": int, "content": str, "vector": [float, ...]}]
    向量由调用方从 kb_content_vectors 复用（共享内容不重新 embedding）。
    """
    if not items:
        return True
    col = _get_collection()
    if col is None:
        return False
    try:
        with _write_lock:
            for start in range(0, len(items), _UPSERT_BATCH):
                batch = items[start:start + _UPSERT_BATCH]
                col.upsert(
                    ids=[_chunk_id(doc_id, it["chunk_index"]) for it in batch],
                    embeddings=[it["vector"] for it in batch],
                    documents=[it["content"] or "" for it in batch],
                    metadatas=[_meta(doc_id, user_id, is_public, content_hash,
                                     it["chunk_index"], filename) for it in batch],
                )
        return True
    except Exception as e:
        logger.error(f"[mu-kb-idx] upsert_doc 失败 doc={doc_id}: {e}")
        return False


def delete_doc(doc_id: str) -> bool:
    """删除某文档引用在索引中的全部分块"""
    col = _get_collection()
    if col is None:
        return False
    try:
        with _write_lock:
            col.delete(where={"doc_id": str(doc_id)})
        return True
    except Exception as e:
        logger.error(f"[mu-kb-idx] delete_doc 失败 doc={doc_id}: {e}")
        return False


def set_doc_public(doc_id: str, is_public: bool) -> bool:
    """翻转某文档引用全部分块的 is_public 元数据（保留向量不动）"""
    col = _get_collection()
    if col is None:
        return False
    try:
        with _write_lock:
            got = col.get(where={"doc_id": str(doc_id)}, include=["metadatas"])
            ids = got.get("ids") or []
            if not ids:
                return True
            metas = []
            for m in got.get("metadatas") or []:
                m = dict(m or {})
                m["is_public"] = 1 if is_public else 0
                metas.append(m)
            col.update(ids=ids, metadatas=metas)
        return True
    except Exception as e:
        logger.error(f"[mu-kb-idx] set_doc_public 失败 doc={doc_id}: {e}")
        return False


def delete_by_content_hashes(hashes: List[str]) -> bool:
    """GC 用：按 content_hash 删除索引记录（调用时这些内容已无任何用户引用）"""
    if not hashes:
        return True
    col = _get_collection()
    if col is None:
        return False
    try:
        with _write_lock:
            # Chroma where 不支持单字段 IN 传超大列表，分批删
            for start in range(0, len(hashes), 200):
                batch = hashes[start:start + 200]
                if len(batch) == 1:
                    where = {"content_hash": batch[0]}
                else:
                    where = {"content_hash": {"$in": batch}}
                col.delete(where=where)
        return True
    except Exception as e:
        logger.error(f"[mu-kb-idx] delete_by_content_hashes 失败: {e}")
        return False


def query(user_id: int, query_embedding: List[float], top_k: int = 5,
          threshold: float = 0.3) -> Optional[List[Dict]]:
    """HNSW 检索该用户可见分块（本人私有 + 所有公共）。

    返回 [{filename, content, score(余弦相似度, 0~1)}]；索引不可用时返回 None 让调用方回退。
    """
    col = _get_collection()
    if col is None:
        return None
    try:
        res = col.query(
            query_embeddings=[query_embedding],
            n_results=max(int(top_k), 1),
            where={"$or": [{"user_id": int(user_id)}, {"is_public": 1}]},
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        logger.error(f"[mu-kb-idx] query 失败，调用方应回退: {e}")
        return None

    ids = (res.get("ids") or [[]])[0]
    if not ids:
        return []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        try:
            # cosine distance = 1 - cosine similarity；数值误差下夹到 [0,1]
            score = 1.0 - float(dist)
        except Exception:
            continue
        if score < threshold:
            continue
        out.append({
            "filename": (meta or {}).get("filename") or "未知文档",
            "content": doc or "",
            "score": round(max(0.0, min(1.0, score)), 4),
        })
    return out


def index_count() -> int:
    col = _get_collection()
    if col is None:
        return 0
    try:
        return int(col.count())
    except Exception:
        return 0


def _load_doc_vectors(conn, content_hash: str) -> Dict[int, List[float]]:
    """从共享向量池读出某内容全部分块的 {chunk_index: vector}"""
    rows = conn.execute(
        "SELECT chunk_index, vector FROM kb_content_vectors WHERE content_hash = ?",
        (content_hash,),
    ).fetchall()
    out = {}
    for r in rows:
        try:
            out[int(r["chunk_index"])] = json.loads(r["vector"])
        except Exception:
            continue
    return out


def sync_index() -> Dict:
    """增量同步：把 SQLite 有而 Chroma 没有的「文档引用 × 分块」补进索引。

    幂等，可在启动后台线程反复调用。返回 {added, docs, missing_docs, skipped_no_vector}。
    """
    col = _get_collection()
    if col is None:
        return {"available": False}
    added = 0
    docs_done = 0
    skipped_no_vector = 0
    try:
        with _write_lock:
            existing = set(col.get(include=[]).get("ids") or [])
        conn = get_conn()
        try:
            docs = conn.execute(
                "SELECT id, user_id, filename, content_hash, is_public, chunk_count"
                " FROM mu_knowledge_docs WHERE content_hash != '' ORDER BY created_at",
            ).fetchall()
            vec_cache: Dict[str, Dict[int, List[float]]] = {}
            content_cache: Dict[str, Dict[int, str]] = {}
            for d in docs:
                c_hash = d["content_hash"]
                if c_hash not in vec_cache:
                    rows = conn.execute(
                        "SELECT chunk_index, content, vector FROM kb_content_vectors"
                        " WHERE content_hash = ?",
                        (c_hash,),
                    ).fetchall()
                    vec_cache[c_hash] = {}
                    content_cache[c_hash] = {}
                    for r in rows:
                        content_cache[c_hash][int(r["chunk_index"])] = r["content"] or ""
                        try:
                            vec_cache[c_hash][int(r["chunk_index"])] = json.loads(r["vector"])
                        except Exception:
                            continue
                vecs = vec_cache[c_hash]
                if not vecs:
                    skipped_no_vector += 1
                    continue
                items = []
                for idx, vec in vecs.items():
                    if _chunk_id(d["id"], idx) in existing:
                        continue
                    items.append({"chunk_index": idx,
                                  "content": content_cache[c_hash].get(idx, ""),
                                  "vector": vec})
                if not items:
                    continue
                ok = upsert_doc(
                    d["id"], d["user_id"], bool(d["is_public"]), c_hash,
                    d["filename"], items,
                )
                if ok:
                    added += len(items)
                    docs_done += 1
                    for it in items:
                        existing.add(_chunk_id(d["id"], it["chunk_index"]))
        finally:
            conn.close()
        logger.info(f"[mu-kb-idx] 增量同步完成：补齐 {added} 条 / {docs_done} 个文档")
        return {"available": True, "added": added, "docs": docs_done,
                "skipped_no_vector": skipped_no_vector, "total": index_count()}
    except Exception as e:
        logger.error(f"[mu-kb-idx] 增量同步失败: {e}")
        return {"available": True, "error": str(e), "added": added}


def rebuild_index() -> Dict:
    """全量重建（同库双 collection 切换）：

    1. 删除可能残留的备用 collection，在同一 PersistentClient 下重建并灌满；
    2. 写锁内把活动指针切到新 collection，再删除旧 collection。
    全程不做 OS 目录改名（规避 Windows 下 rust 客户端目录锁导致的 WinError 5）；
    灌入失败时现网活动 collection 完全不受影响。
    """
    global _collection
    client = _client if _client is not None else None
    if client is None:
        col = _get_collection()
        if col is None:
            return {"success": False, "error": "chromadb 不可用"}
        client = _client

    started = time.time()
    active_name = getattr(_collection, "name", COLLECTION_NAME)
    target_name = REBUILD_COLLECTION_NAME if active_name == COLLECTION_NAME else COLLECTION_NAME
    conn = get_conn()
    try:
        docs = conn.execute(
            "SELECT id, user_id, filename, content_hash, is_public"
            " FROM mu_knowledge_docs WHERE content_hash != '' ORDER BY created_at",
        ).fetchall()

        # 1. 非活动 collection（A/B 交替）：旧活动库在重建期间继续完整服务
        try:
            client.delete_collection(target_name)
        except Exception:
            pass
        new_col = client.get_or_create_collection(
            name=target_name, metadata={"hnsw:space": "cosine"},
        )

        total = 0
        docs_done = 0
        batch_ids: List[str] = []
        batch_embs: List[List[float]] = []
        batch_docs: List[str] = []
        batch_metas: List[Dict] = []

        def _flush():
            nonlocal batch_ids, batch_embs, batch_docs, batch_metas
            if not batch_ids:
                return
            new_col.upsert(ids=batch_ids, embeddings=batch_embs,
                           documents=batch_docs, metadatas=batch_metas)
            batch_ids, batch_embs, batch_docs, batch_metas = [], [], [], []

        for d in docs:
            rows = conn.execute(
                "SELECT chunk_index, content, vector FROM kb_content_vectors"
                " WHERE content_hash = ? ORDER BY chunk_index",
                (d["content_hash"],),
            ).fetchall()
            for r in rows:
                try:
                    vec = json.loads(r["vector"])
                except Exception:
                    continue
                idx = int(r["chunk_index"])
                batch_ids.append(_chunk_id(d["id"], idx))
                batch_embs.append(vec)
                batch_docs.append(r["content"] or "")
                batch_metas.append(_meta(d["id"], d["user_id"], bool(d["is_public"]),
                                         d["content_hash"], idx, d["filename"]))
                total += 1
                if len(batch_ids) >= _UPSERT_BATCH:
                    _flush()
            docs_done += 1
        _flush()
    except Exception as e:
        logger.error(f"[mu-kb-idx] 全量重建灌库失败（现网索引未动）: {e}")
        try:
            client.delete_collection(target_name)
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # 2. 切换活动指针并删除旧 collection
    try:
        with _write_lock:
            _collection = new_col
            _write_active_name(target_name)
            # A/B 交替成功后才删旧活动库；同名（异常情况）不删
            if active_name != target_name:
                try:
                    client.delete_collection(active_name)
                except Exception as e:
                    logger.warning(f"[mu-kb-idx] 旧 collection 删除失败（不影响使用）: {e}")
        final_count = int(_collection.count())
        elapsed = round(time.time() - started, 1)
        logger.info(f"[mu-kb-idx] 全量重建完成: {final_count} 条 / {docs_done} 文档 / {elapsed}s")
        return {"success": True, "count": final_count, "docs": docs_done,
                "elapsed_sec": elapsed}
    except Exception as e:
        logger.error(f"[mu-kb-idx] 重建切换失败: {e}")
        return {"success": False, "error": f"切换失败: {e}"}
