# -*- coding: utf-8 -*-
"""对存量知识库文档重新计算 content_hash（用当前 extract_text 逻辑），
使内容相同的文档统一 hash 从而共享。

背景：早期版本入库时 hash 算法与当前不一致（旧版可能用原始字节 hash），
导致内容相同的文档 hash 不同、未共享。本脚本用当前 extract_text 重算文本 hash 并统一。

用法:
    python rehash_kb.py [--dry-run]

安全：幂等，已一致的不重复处理；支持 --dry-run 预览。
"""
import sys
import os
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lobster_mu import db
from lobster_mu.paths import uploads_dir
from lobster_mu.upload_service import extract_text

DRY = "--dry-run" in sys.argv


def main():
    db.init_db()
    conn = db.get_conn()
    try:
        docs = conn.execute(
            "SELECT d.id, d.user_id, d.filename, d.file_size, d.content_hash, d.chunk_count"
            " FROM mu_knowledge_docs d WHERE d.content_hash != ''"
        ).fetchall()
    finally:
        conn.close()

    print(f"文档总数: {len(docs)}")
    changed = []  # (doc_id, uid, fname, old_hash_full, new_hash_full, file_size, chunk_count)

    for d in docs:
        uid = d["user_id"]
        fname = d["filename"]
        fsize = d["file_size"]
        old_hash = d["content_hash"]

        # 在 uploads_dir(uid) 里找对应文件（原始文件名可能带时间戳，按 size + 后缀匹配）
        updir = uploads_dir(uid)
        target = None
        if os.path.isdir(updir):
            ext_orig = os.path.splitext(fname)[1].lower()
            base_orig = os.path.splitext(fname)[0]
            for f in os.listdir(updir):
                fp = os.path.join(updir, f)
                if not os.path.isfile(fp):
                    continue
                if os.path.getsize(fp) != fsize:
                    continue
                if f.endswith(ext_orig) and (base_orig in f or f.endswith(ext_orig)):
                    target = fp
                    break
            if not target:
                # 兜底：任意 size 匹配
                for f in os.listdir(updir):
                    fp = os.path.join(updir, f)
                    if os.path.isfile(fp) and os.path.getsize(fp) == fsize:
                        target = fp
                        break
        if not target:
            print(f"  [跳过] user{uid} {fname}: 找不到对应上传文件（size={fsize}）")
            continue

        ext = os.path.splitext(target)[1].lower()
        try:
            with open(target, "rb") as fh:
                raw = fh.read()
            text = extract_text(target, ext, raw=raw)
        except Exception as e:
            print(f"  [错误] user{uid} {fname}: {e}")
            continue

        new_hash = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
        if new_hash != old_hash:
            changed.append((d["id"], uid, fname, old_hash, new_hash, fsize, d["chunk_count"]))
            print(f"  [变更] user{uid} {fname}: {old_hash[:16]}... -> {new_hash[:16]}...")
        else:
            print(f"  [一致] user{uid} {fname}: {old_hash[:16]}...")

    print("\n" + "=" * 50)
    print(f"需变更: {len(changed)} 篇")

    if DRY:
        print("[DRY-RUN] 未写入数据库")
        return

    if not changed:
        print("无需变更，退出")
        return

    conn = db.get_conn()
    try:
        for doc_id, uid, fname, old_hash, new_hash, fsize, chunk_count in changed:
            # 1. 若新 hash 的 kb_content 不存在，且旧 hash 有向量 → 把旧向量改名到新 hash
            exist = conn.execute(
                "SELECT content_hash, chunk_count FROM kb_content WHERE content_hash = ?",
                (new_hash,),
            ).fetchone()
            if not exist:
                old_vec = conn.execute(
                    "SELECT COUNT(*) c FROM kb_content_vectors WHERE content_hash = ?",
                    (old_hash,),
                ).fetchone()["c"]
                if old_vec > 0:
                    # 向量改名（旧 hash 的向量就是这份内容的向量）
                    conn.execute(
                        "UPDATE kb_content_vectors SET content_hash = ? WHERE content_hash = ?",
                        (new_hash, old_hash),
                    )
                    # kb_content 也改名
                    conn.execute(
                        "INSERT OR IGNORE INTO kb_content (content_hash, filename, file_size, chunk_count, created_at)"
                        " SELECT ?, filename, file_size, chunk_count, created_at FROM kb_content WHERE content_hash = ?",
                        (new_hash, old_hash),
                    )
                    conn.execute("DELETE FROM kb_content WHERE content_hash = ?", (old_hash,))
                # 更新文档引用
                conn.execute(
                    "UPDATE mu_knowledge_docs SET content_hash = ? WHERE id = ?",
                    (new_hash, doc_id),
                )
            else:
                # 新 hash 已存在（其他文档已用该 hash）→ 只更新引用，旧向量留给 GC
                conn.execute(
                    "UPDATE mu_knowledge_docs SET content_hash = ? WHERE id = ?",
                    (new_hash, doc_id),
                )
        conn.commit()
        print("已写入数据库")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # 2. GC 清理孤儿内容（被改名/重复的旧 hash）
    from lobster_mu import knowledge_store
    n = knowledge_store.gc_orphaned_content()
    print(f"GC 清理孤儿内容: {n} 个")
    print("完成")


if __name__ == "__main__":
    main()
