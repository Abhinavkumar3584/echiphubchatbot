"""Load the clean pages from the extractor into the Qdrant vector database.

    python ingest.py            add new/changed pages, remove pages that are gone (fast: unchanged pages are skipped)
    python ingest.py --rebuild  start the database from zero (needed after changing EMBED_MODEL)
    python ingest.py --dry      only show what would happen

Input:  output/pages/<site>/*.json   (written by:  python extractor/extract.py run   or   ... build)
Each page is cut into pieces of about CHUNK_WORDS words along its headings. Each piece starts with
"Page title > Heading > Sub-heading" so the bot knows where the text comes from.
"""
import glob, hashlib, json, os, re, sys, time

import config


def strip_links(md):
    """Markdown -> readable text for the embedding (link targets and images removed)."""
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)
    t = re.sub(r"\[\s*([^\]]*?)\s*\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[*_`#>|]+", " ", t)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def sections_flat(sections, path=()):
    """[(heading path, text)] in reading order."""
    out = []
    for s in sections or []:
        h = (s.get("heading") or "").strip()
        here = path + ((h,) if h and h != "(introduction)" else ())
        text = (s.get("content") or "").strip()
        if text:
            out.append((here, text))
        out += sections_flat(s.get("children"), here)
    return out


def split_words(text, size, overlap):
    w = text.split()
    if len(w) <= size:
        return [text]
    step = max(1, size - overlap)
    return [" ".join(w[i:i + size]) for i in range(0, len(w), step) if w[i:i + size]][:200]


def chunk_page(doc):
    """Pieces of about CHUNK_WORDS words. Small neighbouring sections are packed together."""
    title = (doc.get("title") or doc["url"]).replace(" - EdTech", "").strip()
    parts = []
    for path, text in sections_flat(doc.get("sections")) or [((), doc.get("full_markdown", ""))]:
        label = " > ".join(strip_links(p) for p in path)[:300]
        room = max(60, config.CHUNK_WORDS - len(label.split()))
        for piece in split_words(text, room, config.CHUNK_OVERLAP):
            parts.append((label, piece))
    chunks, cur, cur_words = [], [], 0
    for label, piece in parts:
        n = len(strip_links(f"{label}\n{piece}").split())
        if cur and cur_words + n > config.CHUNK_WORDS:
            chunks.append(cur); cur, cur_words = [], 0
        cur.append((label, piece)); cur_words += n
    if cur:
        chunks.append(cur)
    out = []
    for group in chunks:
        md = "\n\n".join((f"## {l}\n{p}" if l else p) for l, p in group)
        plain = strip_links(md)
        if len(plain.split()) < config.MIN_CHUNK_WORDS:
            continue
        headings = [l for l, _ in group if l]
        out.append({"url": doc["url"], "title": title, "site": doc.get("site", ""),
                    "headings": headings[:6], "chunk": len(out),
                    "text": md,                                       # shown to the model (keeps links)
                    "embed_text": f"{title}\n{plain}"})               # used for the embeddings
    return out


def load_pages():
    docs = {}
    for path in sorted(glob.glob(os.path.join(config.PAGES_DIR, "**", "*.json"), recursive=True)):
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            print(f"  skipped {path}: {e}"); continue
        if d.get("approved", True) and d.get("url"):
            docs[d["url"]] = d
    return docs


META = os.path.join(os.path.dirname(config.QDRANT_PATH), "index_meta.json")


def main(rebuild=False, dry=False):
    import embeddings, vector_store as vs
    t0 = time.time()
    docs = load_pages()
    if not docs:
        sys.exit(f"No pages found in {config.PAGES_DIR}.\nRun the extractor first:  python extractor/extract.py run")
    print(f"{len(docs)} clean pages found in {config.PAGES_DIR}")

    meta = json.load(open(META)) if os.path.exists(META) else {}
    want_meta = {"embed_model": config.EMBED_MODEL, "sparse_model": config.SPARSE_MODEL,
                 "chunk_words": config.CHUNK_WORDS, "chunk_overlap": config.CHUNK_OVERLAP}
    if meta and meta != want_meta and not rebuild:
        print("Embedding model or chunk settings changed since the last load -> rebuilding everything.")
        rebuild = True
    try:
        if dry:
            stored = vs.pages() if vs.exists() and not rebuild else {}
        else:
            print("Loading the embedding models (the first time this downloads about 70 MB)...")
            dim = embeddings.dimension()
            if vs.exists() and not rebuild and vs.dense_size() != dim:
                print("Vector size changed -> rebuilding."); rebuild = True
            vs.create(dim, recreate=rebuild)
            stored = vs.pages()
    except vs.LockedError as e:
        sys.exit(str(e))

    added = updated = same = 0
    for url, d in docs.items():
        chunks = chunk_page(d)
        h = hashlib.sha256(json.dumps([c["text"] for c in chunks] + [d.get("title")]).encode()).hexdigest()[:16]
        if stored.get(url) == h or (not chunks and url not in stored):
            same += 1; continue
        kind = "UPDATE" if url in stored else "ADD   "
        print(f"  {'(dry) ' if dry else ''}{kind} {len(chunks):3} pieces  {url}")
        if dry:
            continue
        for c in chunks:
            c["page_hash"] = h
        if url in stored:
            vs.delete_page(url)
        if chunks:
            texts = [c.pop("embed_text") for c in chunks]
            vs.upsert(chunks, embeddings.dense_docs(texts), embeddings.sparse_docs(texts))
        added += url not in stored; updated += url in stored
    removed = [u for u in stored if u not in docs]
    for u in removed:
        print(f"  {'(dry) ' if dry else ''}REMOVE {u}")
        if not dry:
            vs.delete_page(u)
    if not dry:
        os.makedirs(os.path.dirname(META), exist_ok=True)
        json.dump(want_meta, open(META, "w"), indent=2)
    print(f"\nDone in {time.time() - t0:.0f}s: {added} added, {updated} updated, {len(removed)} removed, "
          f"{same} unchanged." + ("" if dry else f"  Database now holds {vs.count()} pieces of text."))
    vs.close()


if __name__ == "__main__":
    main(rebuild="--rebuild" in sys.argv, dry="--dry" in sys.argv)
