"""Finds the pieces of website text that answer a question."""
from dataclasses import dataclass

import config
import embeddings
import vector_store as vs


@dataclass
class Hit:
    url: str
    title: str
    text: str
    headings: list
    similarity: float      # 0..1 meaning similarity (BGE cosine)
    rank_score: float      # merged rank of meaning + keyword search


def search(question):
    qd = embeddings.dense_query(question)
    qs = embeddings.sparse_query(question)
    raw = vs.search(qd, qs, limit=config.TOP_K * 3, candidates=config.CANDIDATES)
    hits, per_page = [], {}
    for payload, rank, sim in raw:
        url = payload["url"]
        if per_page.get(url, 0) >= config.MAX_PER_PAGE:
            continue
        per_page[url] = per_page.get(url, 0) + 1
        hits.append(Hit(url, payload.get("title", ""), payload.get("text", ""), payload.get("headings", []), sim, rank))
        if len(hits) >= config.TOP_K:
            break
    return hits


def confident(hits):
    """True if at least one piece is similar enough to the question to answer from it."""
    return bool(hits) and max(h.similarity for h in hits) >= config.MIN_SCORE


def sources(hits):
    """Numbered sources, one number per page: [(n, title, url)]."""
    out, seen = [], {}
    for h in hits:
        if h.url not in seen:
            seen[h.url] = len(out) + 1
            out.append((seen[h.url], h.title, h.url))
    return out


def context_block(hits):
    """The text given to the model. Pieces of the same page share that page's number."""
    numbers = {url: n for n, _, url in sources(hits)}
    parts, used = [], 0
    for h in hits:
        block = f"[{numbers[h.url]}] {h.title} ({h.url})\n{h.text.strip()}"
        if used + len(block) > config.MAX_CONTEXT_CHARS and parts:
            break
        parts.append(block); used += len(block)
    return "\n\n---\n\n".join(parts)
