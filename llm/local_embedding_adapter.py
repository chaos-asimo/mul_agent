"""Local embedding adapter using sentence-transformers.

Provides on-device embedding generation without calling external APIs.
Models are loaded lazily on first use and cached for subsequent calls.
"""
import os
import time
import threading
from typing import List, Dict, Optional

from .adapter_base import LLMAdapter, LLMResponse


# Set HuggingFace endpoint mirror for faster downloads in China
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


class LocalEmbeddingAdapter(LLMAdapter):
    """Local embedding adapter backed by sentence-transformers.

    The model is loaded lazily on the first ``embeddings()`` call and reused
    for the lifetime of the process.  Only the ``embeddings`` method is
    functional; ``chat`` and ``chat_stream`` raise ``NotImplementedError``
    because this adapter is purpose-built for vector generation.
    """

    _model_cache: Dict[str, object] = {}
    _lock = threading.Lock()
    # encode 推理串行锁：sentence-transformers / PyTorch 的 encode 非线程安全，
    # 多用户并发（FastAPI 线程池）同时对同一全局模型推理会抛异常或返回错误结果，
    # 导致知识库检索静默失败。推理很快，串行执行不影响体验但杜绝并发崩溃。
    _encode_lock = threading.Lock()

    def __init__(self, model_name: str = "BAAI/bge-base-zh-v1.5", **kwargs):
        super().__init__(
            api_key="local",
            model_name=model_name,
            api_url=""
        )
        self._model = None

    def _load_model(self):
        """Lazily load the sentence-transformers model (cached by model name)."""
        from rag.rag_logger import rag_logger, log_error, log_debug

        if self._model is not None:
            log_debug("LocalEmbedding", f"模型已加载: {self.model_name} (内存缓存)")
            return self._model

        cache_key = self.model_name
        if cache_key in LocalEmbeddingAdapter._model_cache:
            self._model = LocalEmbeddingAdapter._model_cache[cache_key]
            log_debug("LocalEmbedding", f"模型已加载: {self.model_name} (类缓存)")
            return self._model

        with LocalEmbeddingAdapter._lock:
            # Double-check after acquiring lock
            if cache_key in LocalEmbeddingAdapter._model_cache:
                self._model = LocalEmbeddingAdapter._model_cache[cache_key]
                log_debug("LocalEmbedding", f"模型已加载: {self.model_name} (锁内缓存)")
                return self._model

            load_start = time.time()
            rag_logger.info(f"[LocalEmbedding] 正在加载模型: {self.model_name}")
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                LocalEmbeddingAdapter._model_cache[cache_key] = self._model
                load_ms = (time.time() - load_start) * 1000
                # 获取模型信息用于日志
                model_info = ""
                try:
                    import numpy as np
                    test_vec = self._model.encode(["test"], convert_to_numpy=True)
                    dims = test_vec.shape[1] if len(test_vec.shape) > 1 else len(test_vec)
                    model_info = f", 向量维度={dims}"
                except Exception:
                    pass
                rag_logger.info(
                    f"[LocalEmbedding] 模型加载完成: {self.model_name} | "
                    f"耗时={load_ms:.1f}ms{model_info}"
                )
            except Exception as e:
                load_ms = (time.time() - load_start) * 1000
                log_error("LocalEmbedding", "_load_model", e,
                    f"model={self.model_name}, elapsed={load_ms:.1f}ms"
                )
                raise
            return self._model

    def embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts using the local model."""
        from rag.rag_logger import rag_logger, log_error, log_embedding_status, log_debug

        if not texts:
            log_debug("LocalEmbedding", "embeddings() 输入为空，返回空列表")
            return []

        embed_start = time.time()
        log_debug("LocalEmbedding", f"开始向量化: {len(texts)} 段文本")

        model = self._load_model()
        try:
            import numpy as np
            # sentence-transformers encode 非线程安全：多用户并发推理会抛异常。
            # 用全局串行锁保护所有 encode 调用（推理很快，串行不影响体验）。
            with LocalEmbeddingAdapter._encode_lock:
                # 分批编码：避免一次性对上千块文本推理长时间独占 CPU，
                # 批间短暂让出，降低上传知识库时对其它请求的 CPU 挤压。
                BATCH_SIZE = 64
                all_vecs = []
                for i in range(0, len(texts), BATCH_SIZE):
                    batch = texts[i:i + BATCH_SIZE]
                    vecs = model.encode(batch, convert_to_numpy=True,
                                        show_progress_bar=False, batch_size=32)
                    all_vecs.append(vecs)
                    if i + BATCH_SIZE < len(texts):
                        time.sleep(0.02)
            # 拼接在锁外做（纯 numpy，线程安全），缩短持锁时间
            embeddings = np.concatenate(all_vecs, axis=0) if len(all_vecs) > 1 else all_vecs[0]
            embed_ms = (time.time() - embed_start) * 1000

            # Convert numpy arrays to plain lists for JSON serialization
            if isinstance(embeddings, np.ndarray):
                result = embeddings.tolist()
                dims = embeddings.shape[1] if len(embeddings.shape) > 1 else len(embeddings)
            else:
                result = [list(e) if hasattr(e, 'tolist') else e for e in embeddings]
                dims = len(result[0]) if result else 0

            # 记录向量化结果
            log_embedding_status(
                text=texts[0][:50] if texts else "",
                dims=dims,
                elapsed_ms=embed_ms,
                source="LocalEmbedding"
            )
            log_debug("LocalEmbedding",
                f"向量化详情 | 文本数={len(texts)} | 维度={dims} | "
                f"耗时={embed_ms:.1f}ms | 前50字='{texts[0][:50] if texts else ''}'"
            )
            return result
        except Exception as e:
            embed_ms = (time.time() - embed_start) * 1000
            log_error("LocalEmbedding", "embeddings", e,
                f"texts_count={len(texts)}, elapsed={embed_ms:.1f}ms, model={self.model_name}"
            )
            raise

    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for a search query.

        Note: BGE v1.5 models do NOT require a query prefix (per official docs:
        "Instructions will not improve the performance"). Only original BGE v1
        models need the ``"为这个句子生成表示以用于检索相关文章："`` prefix.
        """
        from rag.rag_logger import rag_logger, log_error, log_debug

        if not text:
            log_debug("LocalEmbedding", "embed_query() 输入为空，返回空向量")
            return []

        query_start = time.time()
        log_debug("LocalEmbedding",
            f"开始查询向量化 | 模型={self.model_name} | 文本='{text[:80]}{'...' if len(text) > 80 else ''}'"
        )

        try:
            if "bge" in self.model_name.lower() and "v1.5" not in self.model_name.lower():
                prefixed = f"为这个句子生成表示以用于检索相关文章：{text}"
                result = self.embeddings([prefixed])[0]
            else:
                result = self.embeddings([text])[0]

            query_ms = (time.time() - query_start) * 1000
            rag_logger.info(
                f"[LocalEmbedding] 查询向量化完成 | "
                f"模型={self.model_name} | 耗时={query_ms:.1f}ms | "
                f"向量维度={len(result)} | "
                f"文本='{text[:50]}{'...' if len(text) > 50 else ''}'"
            )
            return result
        except Exception as e:
            query_ms = (time.time() - query_start) * 1000
            log_error("LocalEmbedding", "embed_query", e,
                f"model={self.model_name}, elapsed={query_ms:.1f}ms, text='{text[:50]}'"
            )
            raise

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> LLMResponse:
        raise NotImplementedError("LocalEmbeddingAdapter 不支持聊天功能")

    def chat_stream(self, messages: List[Dict[str, str]], **kwargs):
        raise NotImplementedError("LocalEmbeddingAdapter 不支持流式聊天")

    def count_tokens(self, text: str) -> int:
        """Rough token estimate using character count."""
        return len(text)
