import sqlite3, json, os, time
import numpy as np


class VectorStore:
    """SQLite-based vector storage engine for RAG."""

    def __init__(self, db_path=None):
        """Initialize the vector store, creating the DB file and tables if needed.

        Args:
            db_path: Optional path to the SQLite database file. Defaults to
                ``<package>/../data/rag_vectors.db``.
        """
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'rag_vectors.db')
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._create_tables()

    def _create_tables(self):
        """Create the documents and chunks tables along with their indexes."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT,
                file_size INTEGER,
                chunk_count INTEGER,
                uploaded_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                doc_id TEXT,
                chunk_index INTEGER,
                content TEXT,
                embedding TEXT,
                metadata TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents(uploaded_at)')
        conn.commit()
        conn.close()

    def add_document(self, doc_id, filename, file_size, chunks):
        """Insert document metadata and all of its chunks.

        Args:
            doc_id: Unique identifier for the document.
            filename: Original file name.
            file_size: Size of the source file in bytes.
            chunks: List of chunk dicts. Each chunk must contain ``chunk_id``,
                ``chunk_index``, ``content``, ``embedding`` (list of floats) and
                ``metadata`` (dict).

        Returns:
            True on success, False on failure.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            from datetime import datetime
            uploaded_at = datetime.now().isoformat()
            cursor.execute('''
                INSERT INTO documents (id, filename, file_size, chunk_count, uploaded_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (doc_id, filename, file_size, len(chunks), uploaded_at))
            for chunk in chunks:
                embedding_json = json.dumps(chunk['embedding'])
                metadata_json = json.dumps(chunk.get('metadata', {}))
                cursor.execute('''
                    INSERT INTO chunks (id, doc_id, chunk_index, content, embedding, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    chunk['chunk_id'],
                    doc_id,
                    chunk['chunk_index'],
                    chunk['content'],
                    embedding_json,
                    metadata_json,
                ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[VectorStore] add_document error: {e}")
            try:
                conn.close()
            except Exception:
                pass
            return False

    def delete_document(self, doc_id):
        """Delete a document and all of its chunks.

        Args:
            doc_id: Unique identifier of the document to delete.

        Returns:
            The number of deleted chunks. Returns 0 if nothing was deleted or
            an error occurred.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM chunks WHERE doc_id = ?', (doc_id,))
            deleted_chunks = cursor.rowcount
            cursor.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
            conn.commit()
            conn.close()
            return deleted_chunks
        except Exception as e:
            print(f"[VectorStore] delete_document error: {e}")
            try:
                conn.close()
            except Exception:
                pass
            return 0

    def search(self, query_embedding, top_k=5, threshold=0.3):
        """Search for the most similar chunks using cosine similarity.

        All embeddings are loaded from SQLite, converted to a numpy matrix and
        compared against the query embedding in a single batched operation.

        Args:
            query_embedding: List of floats representing the query vector.
            top_k: Maximum number of results to return.
            threshold: Minimum cosine similarity score for a result to be kept.

        Returns:
            List of result dicts sorted by descending score. Each dict has
            ``chunk_id``, ``doc_id``, ``content``, ``score``, ``metadata`` and
            ``filename``.
        """
        from .rag_logger import rag_logger, log_retrieval_result, log_error, log_debug
        
        search_start = time.time()
        total_chunks = 0
        valid_chunks = 0
        passed_count = 0
        filtered_count = 0
        skipped_zero_norm = 0
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT chunks.id, chunks.doc_id, chunks.content, chunks.embedding, chunks.metadata, documents.filename
                FROM chunks
                LEFT JOIN documents ON chunks.doc_id = documents.id
            ''')
            rows = cursor.fetchall()
            conn.close()

            total_chunks = len(rows)
            log_debug("VectorStore", f"加载分块数据: {total_chunks} 条记录")
            
            if not rows:
                rag_logger.info(f"[VectorStore] 知识库为空，返回 0 条结果")
                return []

            embeddings = []
            valid_rows = []
            for idx, row in enumerate(rows):
                try:
                    emb = json.loads(row[3]) if row[3] else []
                    if not emb:
                        log_debug("VectorStore", f"分块 {idx} ({row[0][:12]}): 嵌入向量为空，跳过")
                        continue
                    embeddings.append(emb)
                    valid_rows.append(row)
                except (json.JSONDecodeError, TypeError) as e:
                    log_debug("VectorStore", f"分块 {idx} ({row[0][:12]}): 嵌入JSON解析失败: {e}")
                    continue

            valid_chunks = len(embeddings)
            rag_logger.info(
                f"[VectorStore] 加载完成 | 总分块={total_chunks} | 有效嵌入={valid_chunks} | "
                f"跳过空嵌入={total_chunks - valid_chunks}"
            )
            
            if not embeddings:
                rag_logger.warning("[VectorStore] 无有效嵌入向量，无法进行相似度检索")
                return []

            matrix = np.array(embeddings, dtype=np.float64)
            query_vec = np.array(query_embedding, dtype=np.float64)
            
            log_debug("VectorStore", f"矩阵形状={matrix.shape}, 查询向量维度={query_vec.shape[0]}")

            # Avoid division by zero for zero vectors / empty rows
            matrix_norms = np.linalg.norm(matrix, axis=1)
            query_norm = np.linalg.norm(query_vec)
            
            rag_logger.debug(
                f"[VectorStore] 向量范数 | 矩阵最小值={matrix_norms.min():.6f} | "
                f"最大值={matrix_norms.max():.6f} | 查询向量={query_norm:.6f}"
            )

            scores = np.zeros(valid_chunks, dtype=np.float64)
            valid = (matrix_norms > 0) & (query_norm > 0)
            
            if not query_norm > 0:
                skipped_zero_norm = valid_chunks
                rag_logger.warning(f"[VectorStore] 查询向量范数为零，跳过 {skipped_zero_norm} 个分块")
            elif not valid.any():
                rag_logger.warning(f"[VectorStore] 无有效分块可计算相似度（所有向量范数为零）")
            else:
                skipped_zero_norm = valid_chunks - valid.sum()
                if skipped_zero_norm > 0:
                    log_debug("VectorStore", f"跳过 {skipped_zero_norm} 个零范数分块")
                
                valid_matrix = matrix[valid]
                normalized_matrix = valid_matrix / matrix_norms[valid][:, None]
                normalized_query = query_vec / query_norm
                valid_scores = normalized_matrix.dot(normalized_query)
                scores[valid] = valid_scores

            results = []
            for idx, row in enumerate(valid_rows):
                score = float(scores[idx])
                if score < threshold:
                    filtered_count += 1
                    log_debug("VectorStore", 
                        f"分块 {idx} ({row[0][:12]}): score={score:.4f} < threshold={threshold:.2f} | 过滤"
                    )
                    continue
                passed_count += 1
                try:
                    metadata = json.loads(row[4]) if row[4] else {}
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
                results.append({
                    'chunk_id': row[0],
                    'doc_id': row[1],
                    'content': row[2],
                    'score': score,
                    'metadata': metadata,
                    'filename': row[5],
                })
                log_debug("VectorStore", 
                    f"分块 {idx} ({row[0][:12]}): score={score:.4f} >= threshold={threshold:.2f} | 命中"
                )

            results.sort(key=lambda x: x['score'], reverse=True)
            final_results = results[:top_k]
            
            elapsed_ms = (time.time() - search_start) * 1000
            
            # Build result preview for logging
            results_preview = []
            for r in final_results:
                results_preview.append({
                    'score': r['score'],
                    'filename': r.get('filename', '?'),
                    'chunk_id': r.get('chunk_id', '?'),
                    'content': r.get('content', '')[:60],
                })
            
            log_retrieval_result(
                total_chunks=total_chunks,
                valid_chunks=valid_chunks,
                passed_chunks=passed_count,
                filtered_chunks=filtered_count,
                elapsed_ms=elapsed_ms,
                source="VectorStore",
                results_preview=results_preview,
            )
            
            # Log detailed breakdown of filtered vs passed
            rag_logger.debug(
                f"[VectorStore] 检索详情 | "
                f"通过分块={passed_count} | 过滤分块={filtered_count} | "
                f"零范数跳过={skipped_zero_norm} | "
                f"Top-{top_k}结果={len(final_results)}"
            )
            
            return final_results
        except Exception as e:
            log_error("VectorStore", "cosine_search", e, 
                f"total={total_chunks}, valid={valid_chunks}, threshold={threshold}, top_k={top_k}"
            )
            try:
                conn.close()
            except Exception:
                pass
            return []

    def list_documents(self):
        """Return all documents ordered by upload time (newest first).

        Returns:
            List of dicts with ``id``, ``filename``, ``file_size``,
            ``chunk_count`` and ``uploaded_at``. Returns an empty list on error.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, filename, file_size, chunk_count, uploaded_at
                FROM documents
                ORDER BY uploaded_at DESC
            ''')
            rows = cursor.fetchall()
            conn.close()
            return [
                {
                    'id': row[0],
                    'filename': row[1],
                    'file_size': row[2],
                    'chunk_count': row[3],
                    'uploaded_at': row[4],
                }
                for row in rows
            ]
        except Exception as e:
            print(f"[VectorStore] list_documents error: {e}")
            try:
                conn.close()
            except Exception:
                pass
            return []

    def get_document(self, doc_id):
        """Return metadata for a single document.

        Args:
            doc_id: Unique identifier of the document.

        Returns:
            Dict with ``id``, ``filename``, ``file_size``, ``chunk_count`` and
            ``uploaded_at``, or None if not found / on error.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, filename, file_size, chunk_count, uploaded_at
                FROM documents
                WHERE id = ?
            ''', (doc_id,))
            row = cursor.fetchone()
            conn.close()
            if row is None:
                return None
            return {
                'id': row[0],
                'filename': row[1],
                'file_size': row[2],
                'chunk_count': row[3],
                'uploaded_at': row[4],
            }
        except Exception as e:
            print(f"[VectorStore] get_document error: {e}")
            try:
                conn.close()
            except Exception:
                pass
            return None

    def get_stats(self):
        """Return aggregate statistics about the store.

        Returns:
            Dict with ``total_documents``, ``total_chunks`` and
            ``db_size_bytes``. On error the counts default to 0.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM documents')
            total_documents = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM chunks')
            total_chunks = cursor.fetchone()[0]
            conn.close()
            db_size_bytes = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            return {
                'total_documents': total_documents,
                'total_chunks': total_chunks,
                'db_size_bytes': db_size_bytes,
            }
        except Exception as e:
            print(f"[VectorStore] get_stats error: {e}")
            try:
                conn.close()
            except Exception:
                pass
            return {
                'total_documents': 0,
                'total_chunks': 0,
                'db_size_bytes': 0,
            }
