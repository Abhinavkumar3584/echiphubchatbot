"""Turns text into numbers (embeddings), locally on the CPU with FastEmbed (ONNX, no PyTorch, no GPU).

dense  = BAAI/bge-small-en-v1.5 : meaning ("how do I join a workshop" ~ "registration for bootcamp")
sparse = Qdrant/bm25            : exact words (names, course codes, "SCL", "1.2 µm", city names)
The models are downloaded once (~70 MB) into data/models/ the first time they are used.
"""
import threading

import numpy as np

import config

_lock = threading.Lock()
_dense = None
_sparse = None


def _load():
    global _dense, _sparse
    with _lock:
        if _dense is None:
            from fastembed import SparseTextEmbedding, TextEmbedding
            _dense = TextEmbedding(config.EMBED_MODEL, cache_dir=config.MODEL_DIR)
            _sparse = SparseTextEmbedding(config.SPARSE_MODEL, cache_dir=config.MODEL_DIR)
    return _dense, _sparse


def _normalize(m):
    m = np.asarray(m, dtype=np.float32)
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.maximum(n, 1e-12)


def dense_docs(texts):
    dense, _ = _load()
    return _normalize(list(dense.embed(texts, batch_size=32)))


def dense_query(text):
    dense, _ = _load()
    return _normalize(list(dense.embed([config.QUERY_PREFIX + text]))[0])


def sparse_docs(texts):
    _, sparse = _load()
    return [(e.indices.tolist(), e.values.tolist()) for e in sparse.embed(texts, batch_size=32)]


def sparse_query(text):
    _, sparse = _load()
    e = next(iter(sparse.query_embed(text)))
    return e.indices.tolist(), e.values.tolist()


def dimension():
    from fastembed import TextEmbedding
    for m in TextEmbedding.list_supported_models():
        if m["model"].lower() == config.EMBED_MODEL.lower():
            return m["dim"]
    return len(dense_docs(["dimension check"])[0])


def warm_up():
    """Load both models (downloads them the first time)."""
    dense_query("warm up"); sparse_query("warm up")
