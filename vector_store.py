"""Qdrant vector database.

QDRANT_URL empty -> Qdrant runs locally inside this program and stores files in data/qdrant.
QDRANT_URL set   -> connects to an external Qdrant server.
Each piece of text is stored with two vectors: "dense" (meaning, BGE) and "bm25" (exact words).
Search runs both and merges the two result lists (Reciprocal Rank Fusion).
"""
import uuid

import numpy as np
from qdrant_client import QdrantClient, models

import config

DENSE, SPARSE = "dense", "bm25"
_client = None


class LockedError(RuntimeError):
    pass


def client():
    global _client
    if _client is None:
        if config.QDRANT_URL:
            _client = QdrantClient(url=config.QDRANT_URL, api_key=config.QDRANT_API_KEY or None, timeout=30)
        else:
            qpath = config.QDRANT_PATH
            # On serverless (Vercel / AWS Lambda), the deployment directory is read-only.
            if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
                import shutil
                tmp_qpath = os.path.join("/tmp", "qdrant")
                if not os.path.exists(tmp_qpath) and os.path.exists(qpath):
                    try:
                        shutil.copytree(qpath, tmp_qpath, ignore=shutil.ignore_patterns("*.lock"))
                    except Exception:
                        pass
                if os.path.exists(tmp_qpath):
                    qpath = tmp_qpath
            try:
                _client = QdrantClient(path=qpath)
            except Exception as e:                       # local mode: only one program at a time
                if "already accessed" in str(e) or "lock" in str(e).lower():
                    raise LockedError(
                        "The local Qdrant database is in use by another program (probably the running chatbot).\n"
                        "Stop the chatbot first, or use a Qdrant server (set QDRANT_URL, see README).") from e
                raise
    return _client


def close():
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None


def exists():
    return client().collection_exists(config.COLLECTION)


def create(dim, recreate=False):
    c = client()
    if recreate and c.collection_exists(config.COLLECTION):
        c.delete_collection(config.COLLECTION)
    if not c.collection_exists(config.COLLECTION):
        c.create_collection(
            config.COLLECTION,
            vectors_config={DENSE: models.VectorParams(size=dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)})
        if config.QDRANT_URL:                           # payload index (server mode) for fast delete-by-page
            c.create_payload_index(config.COLLECTION, "url", models.PayloadSchemaType.KEYWORD)


def dense_size():
    info = client().get_collection(config.COLLECTION)
    v = info.config.params.vectors
    return v[DENSE].size if isinstance(v, dict) else v.size


def point_id(url, i):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{url}#{i}"))


def upsert(chunks, dense, sparse):
    pts = [models.PointStruct(
        id=point_id(ch["url"], ch["chunk"]),
        vector={DENSE: dense[i].tolist(), SPARSE: models.SparseVector(indices=sparse[i][0], values=sparse[i][1])},
        payload=ch) for i, ch in enumerate(chunks)]
    for i in range(0, len(pts), 128):
        client().upsert(config.COLLECTION, points=pts[i:i + 128], wait=True)


def delete_page(url):
    client().delete(config.COLLECTION, points_selector=models.FilterSelector(filter=models.Filter(
        must=[models.FieldCondition(key="url", match=models.MatchValue(value=url))])), wait=True)


def pages():
    """{url: page_hash} of everything stored."""
    out, offset = {}, None
    while True:
        pts, offset = client().scroll(config.COLLECTION, limit=512, offset=offset,
                                      with_payload=["url", "page_hash"], with_vectors=False)
        for p in pts:
            out[p.payload["url"]] = p.payload.get("page_hash")
        if offset is None:
            return out


def count():
    return client().count(config.COLLECTION, exact=True).count if exists() else 0


def search(qdense, qsparse, limit, candidates):
    """Hybrid search. Returns [(payload, fused_rank_score, dense_similarity)] best first."""
    res = client().query_points(
        config.COLLECTION,
        prefetch=[models.Prefetch(query=qdense.tolist(), using=DENSE, limit=candidates),
                  models.Prefetch(query=models.SparseVector(indices=qsparse[0], values=qsparse[1]),
                                  using=SPARSE, limit=candidates)],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=limit, with_payload=True, with_vectors=[DENSE])
    out = []
    for p in res.points:
        v = p.vector.get(DENSE) if isinstance(p.vector, dict) else p.vector
        sim = float(np.dot(qdense, np.asarray(v, dtype=np.float32) / max(np.linalg.norm(v), 1e-12))) if v else 0.0
        out.append((p.payload, float(p.score), sim))
    return out
