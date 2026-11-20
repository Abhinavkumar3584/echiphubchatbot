"""Turns text into numbers (embeddings), locally on the CPU with FastEmbed (ONNX, no GPU).

dense  = BAAI/bge-small-en-v1.5 : meaning ("how do I join a workshop" ~ "registration for bootcamp")
sparse = Qdrant/bm25            : exact words (names, course codes, "SCL", "1.2 µm", city names)
Both are downloaded once (~70 MB) into data/models/ the first time they are used.
"""
import threading

import numpy as np

import config

_lock = threading.Lock()
_dense = _sparse = None


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
    return m / np.maximum(np.linalg.norm(m, axis=-1, keepdims=True), 1e-12)


def dense_docs(texts):
    return _normalize(list(_load()[0].embed(texts, batch_size=32)))


def dense_query(text):
    return _normalize(list(_load()[0].embed([config.QUERY_PREFIX + text]))[0])


def sparse_docs(texts):
    return [(e.indices.tolist(), e.values.tolist()) for e in _load()[1].embed(texts, batch_size=32)]


def sparse_query(text):
    e = next(iter(_load()[1].query_embed(text)))
    return e.indices.tolist(), e.values.tolist()


def dimension():
    from fastembed import TextEmbedding
    for m in TextEmbedding.list_supported_models():
        if m["model"].lower() == config.EMBED_MODEL.lower():
            return m["dim"]
    return len(dense_docs(["dimension check"])[0])


def warm_up():
    """Loads both models (downloads them the first time)."""
    dense_query("warm up")
    sparse_query("warm up")
