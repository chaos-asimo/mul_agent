"""RAG retrieval logger module.

Provides a dedicated logger for the RAG knowledge base subsystem with
structured logging for easier debugging of retrieval failures.
"""
import logging
import time

# Create a dedicated logger for RAG retrieval
rag_logger = logging.getLogger("rag")
rag_logger.setLevel(logging.DEBUG)

# Only add handler if not already configured to avoid duplicates
if not rag_logger.handlers:
    # Console handler
    _console_handler = logging.StreamHandler()
    _console_handler.setLevel(logging.INFO)
    _formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)-7s %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    _console_handler.setFormatter(_formatter)
    rag_logger.addHandler(_console_handler)


def log_retrieval_start(query: str, top_k: int, threshold: float, source: str = "RAG") -> float:
    """Log the start of a retrieval operation.

    Args:
        query: The search query text.
        top_k: Maximum number of results to return.
        threshold: Minimum similarity score threshold.
        source: Source module name (e.g. "VectorStore", "KnowledgeBase").

    Returns:
        Start timestamp for elapsed time calculation.
    """
    start = time.time()
    rag_logger.info(
        f"[{source}] 开始检索 | "
        f"查询='{query[:80]}{'...' if len(query) > 80 else ''}' | "
        f"top_k={top_k} | threshold={threshold:.2f}"
    )
    return start


def log_retrieval_result(
    total_chunks: int,
    valid_chunks: int,
    passed_chunks: int,
    filtered_chunks: int,
    elapsed_ms: float,
    source: str = "RAG",
    results_preview: list = None,
):
    """Log the result of a retrieval operation.

    Args:
        total_chunks: Total chunks loaded from DB.
        valid_chunks: Chunks with valid embedding vectors.
        passed_chunks: Chunks that passed the threshold filter.
        filtered_chunks: Chunks filtered out by the threshold.
        elapsed_ms: Total elapsed time in milliseconds.
        source: Source module name.
        results_preview: Preview of top results (score, doc, chunk_id).
    """
    rag_logger.info(
        f"[{source}] 检索完成 | "
        f"总计块={total_chunks} | 有效块={valid_chunks} | "
        f"通过={passed_chunks} | 过滤={filtered_chunks} | "
        f"耗时={elapsed_ms:.1f}ms"
    )
    if results_preview:
        for r in results_preview:
            rag_logger.debug(
                f"[{source}] 命中 | "
                f"score={r.get('score', 0):.4f} | "
                f"doc={r.get('filename', '?')} | "
                f"chunk_id={r.get('chunk_id', '?')[:12]} | "
                f"content='{r.get('content', '')[:60]}...'"
            )


def log_embedding_status(text: str, dims: int, elapsed_ms: float, source: str = "RAG"):
    """Log embedding generation status.

    Args:
        text: Input text that was embedded.
        dims: Dimensionality of the generated vector.
        elapsed_ms: Time taken to generate the embedding.
        source: Source module name.
    """
    rag_logger.info(
        f"[{source}] 向量化完成 | "
        f"文本='{text[:50]}{'...' if len(text) > 50 else ''}' | "
        f"维度={dims} | 耗时={elapsed_ms:.1f}ms"
    )


def log_error(source: str, stage: str, error: Exception, context: str = ""):
    """Log an error during retrieval with context.

    Args:
        source: Source module name.
        stage: Stage where the error occurred (e.g. "embed_query", "cosine_search").
        error: The caught exception.
        context: Additional context description.
    """
    rag_logger.error(
        f"[{source}] 错误 | "
        f"阶段={stage} | "
        f"类型={type(error).__name__} | "
        f"详情={str(error)[:200]}"
        + (f" | 上下文={context}" if context else "")
    )


def log_debug(source: str, message: str):
    """Log a debug message.

    Args:
        source: Source module name.
        message: Debug message content.
    """
    rag_logger.debug(f"[{source}] {message}")
