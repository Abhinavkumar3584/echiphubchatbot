"""Load the clean pages from echiphub JSON files into the Qdrant vector database.

    python ingest.py            add new/changed pages, remove pages that are gone (fast: unchanged pages are skipped)
    python ingest.py --rebuild  start the database from zero (needed after changing EMBED_MODEL or data source)
    python ingest.py --dry      only show what would happen

Input:  echiphub/*.json   (written by:  python scraper_master.py)
Each page is cut into pieces of about CHUNK_WORDS words along its headings. Each piece starts with
"Page title > Heading > Sub-heading" so the bot knows where the text comes from.
"""
import glob, hashlib, json, os, re, sys, time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import config

BOILERPLATE = {
    "skip to content", "skip to main content", "go to the indico home page",
    "toggle navigation", "close menu", "open menu"
}

URL_KEYS = {
    "url", "action_url", "hub_url", "helpdesk_url", "category_url", "event_url",
    "service_url", "redirect_uri", "form_action", "server_action", "download_url",
    "manual_url", "read_more_cta", "link_url", "link", "icon", "image", "svg",
    "class", "style", "poster", "target_url"
}


def clean_text(s):
    if not isinstance(s, str):
        s = str(s)
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"\[\s*([^\]]*?)\s*\]\([^)]*\)", r"\1", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def clean_lines(items):
    out = []
    for line in items or []:
        s = clean_text(line).replace("\u200b", "")
        if not s or s.lower() in BOILERPLATE:
            continue
        out.append(s)
    return out


def normalize_url(url: str) -> str:
    if not url:
        return ""
    p = urlparse(url.strip())
    if not p.netloc:
        return url.strip()
    # Canonicalize SSO Keycloak transient login/registration endpoints
    if "sso.echiphub.in" in p.netloc:
        if any(x in p.path for x in ("registration", "authenticate", "openid-connect")):
            return "https://echiphub.in"
        return f"{p.scheme}://{p.netloc}"
    # Filter out transient tracking and auth query parameters
    bad_params = {"tab_id", "client_data", "session_code", "execution", "state", "response_type", "redirect_uri", "client_id"}
    qs = [(k, v) for k, v in parse_qsl(p.query) if k not in bad_params]
    query = urlencode(qs)
    path = p.path.rstrip("/") if p.path != "/" else "/"
    return urlunparse((p.scheme, p.netloc, path, p.params, query, ""))


def clean_title(title, url):
    t = (title or url).strip()
    for suff in [" - EdTech", " · NIELIT (Indico)", " - eChipHub Community", " - Community"]:
        if t.endswith(suff):
            t = t[:-len(suff)].strip()
    return t or url


def strip_links(md):
    """Markdown -> readable text for the embedding (link targets and images removed)."""
    t = clean_text(md)
    t = re.sub(r"[*_`#>|]+", " ", t)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def format_val_no_url(v, depth=0):
    if v is None:
        return ""
    if isinstance(v, (str, int, float, bool)):
        return clean_text(v)
    if isinstance(v, list):
        out = []
        for item in v:
            if isinstance(item, dict):
                parts = []
                for k, val in item.items():
                    if k.lower() in URL_KEYS or k.lower().endswith(("_url", "_uri", "_action")):
                        continue
                    fmt = format_val_no_url(val, depth + 1)
                    if fmt:
                        k_clean = k.replace("_", " ").title()
                        parts.append(f"{k_clean}: {fmt}")
                if parts:
                    out.append(", ".join(parts))
            elif isinstance(item, (str, int, float, bool)):
                s = clean_text(item)
                if s and s.lower() not in BOILERPLATE:
                    out.append(s)
        return "\n".join(f"- {x}" for x in out if x)
    if isinstance(v, dict):
        out = []
        for k, val in v.items():
            if k.lower() in URL_KEYS or k.lower().endswith(("_url", "_uri", "_action")):
                continue
            fmt = format_val_no_url(val, depth + 1)
            if fmt:
                k_clean = k.replace("_", " ").title()
                out.append(f"{k_clean}: {fmt}")
        return "\n".join(out)
    return ""


def sections_flat(sections, path=()):
    """Returns [(heading_path, text)] in reading order with strict hierarchy and zero URLs."""
    out = []
    for s in sections or []:
        if not isinstance(s, dict):
            continue

        stype = s.get("type", "")
        h = (s.get("heading") or s.get("section_name") or s.get("title") or "").strip()
        if h in ("Overview / Header Info", "(introduction)"):
            h = ""
        sec_path = path + ((h,) if h else ())

        # 1. Course Curriculum (Hierarchical: Overview + Sub-sections per module)
        if stype == "course_curriculum" and "modules" in s:
            tot_mods = s.get("total_modules", len(s["modules"]))
            tot_lessons = s.get("total_lessons", "")
            tot_labs = s.get("total_labs", "")

            # Overview chunk listing all modules clearly
            overview_lines = [
                f"Total Modules: {tot_mods}" + (f" | Total Lessons: {tot_lessons}" if tot_lessons else "") + (f" | Total Labs: {tot_labs}" if tot_labs else ""),
                "\nCourse Modules List:"
            ]
            for i, m in enumerate(s["modules"]):
                m_title = m.get("module_title") or f"Module {i+1}"
                cnt = m.get("items_count") or len(m.get("items", []))
                overview_lines.append(f"{i+1}. {m_title}" + (f" ({cnt} lessons/labs)" if cnt else ""))
            out.append((sec_path + ("Overview",), "\n".join(overview_lines)))

            # Individual module breakdowns
            for i, m in enumerate(s["modules"]):
                m_title = m.get("module_title") or f"Module {i+1}"
                m_status = m.get("status", "")
                m_lines = [f"Module: {m_title}" + (f" (Status: {m_status})" if m_status else "")]

                items = m.get("items", [])
                if items:
                    m_lines.append("Topics, Lessons and Labs:")
                    for it in items:
                        it_title = clean_text(it.get("title", ""))
                        it_type = it.get("type", "lesson")
                        it_stat = it.get("status", "")
                        badge = "[Lab]" if "lab" in it_type.lower() else "[Lecture]"
                        stat_str = f" - {it_stat}" if it_stat else ""
                        m_lines.append(f"- {badge} {it_title}{stat_str}")
                out.append((sec_path + (m_title,), "\n".join(m_lines)))
            continue

        # 2. FAQs list
        if stype == "faqs_list" and "faqs" in s:
            faq_lines = []
            for f in s["faqs"]:
                q = clean_text(f.get("question", ""))
                a = clean_text(f.get("answer", ""))
                if q and a:
                    faq_lines.append(f"Q: {q}\nA: {a}")
            if faq_lines:
                out.append((sec_path, "\n\n".join(faq_lines)))
            continue

        # 3. Workshops schedule & cards
        if ("workshops" in s and isinstance(s["workshops"], list)) or stype in ("workshop_schedule_table", "workshop_cards_grid"):
            ws_list = s.get("workshops", [])
            tab_name = s.get("tab_name") or s.get("status") or ""
            ws_lines = []
            if tab_name:
                ws_lines.append(f"Status / Tab: {tab_name}")
            for w in ws_list:
                if isinstance(w, dict):
                    w_title = clean_text(w.get("title") or w.get("workshop_title", ""))
                    w_centre = clean_text(w.get("centre") or w.get("conducted_by", ""))
                    w_dates = clean_text(w.get("dates") or w.get("date", ""))
                    w_stat = clean_text(w.get("status", ""))
                    parts = []
                    if w_title: parts.append(f"Workshop: {w_title}")
                    if w_centre: parts.append(f"Centre: {w_centre}")
                    if w_dates: parts.append(f"Dates: {w_dates}")
                    if w_stat: parts.append(f"Status: {w_stat}")
                    ws_lines.append("- " + " | ".join(parts))
                elif isinstance(w, str):
                    ws_lines.append(f"- {clean_text(w)}")
            if ws_lines:
                out.append((sec_path, "\n".join(ws_lines)))
            continue

        # 4. Courses lists (Foundation / Specialized)
        if stype in ("course_cards", "upcoming_course_cards") and "courses" in s:
            c_lines = []
            for c in s["courses"]:
                c_title = clean_text(c.get("title") or c.get("course_title", ""))
                c_desc = clean_text(c.get("description", ""))
                c_level = clean_text(c.get("level", ""))
                c_code = clean_text(c.get("code") or c.get("course_code", ""))
                parts = [c_title]
                if c_code: parts.append(f"Code: {c_code}")
                if c_level: parts.append(f"Level: {c_level}")
                line = " - ".join(parts)
                if c_desc: line += f"\n  Description: {c_desc}"
                c_lines.append(line)
            if c_lines:
                out.append((sec_path, "\n\n".join(c_lines)))
            continue

        # 5. Community groups
        if stype == "groups_directory" and "groups" in s:
            g_lines = []
            for g in s["groups"]:
                g_name = clean_text(g.get("group_name", ""))
                g_handle = clean_text(g.get("handle", ""))
                g_cnt = g.get("members_count", "")
                g_desc = clean_text(g.get("description", ""))
                line = f"- {g_name} ({g_handle})" + (f" | {g_cnt} members" if g_cnt else "")
                if g_desc: line += f"\n  {g_desc}"
                g_lines.append(line)
            if g_lines:
                out.append((sec_path, "\n".join(g_lines)))
            continue

        # 6. Community badges
        if stype == "badges_catalog" and "badges" in s:
            b_lines = []
            for b in s["badges"]:
                b_name = clean_text(b.get("badge_name", ""))
                b_desc = clean_text(b.get("description", ""))
                b_lines.append(f"- Badge: {b_name} - {b_desc}")
            if b_lines:
                out.append((sec_path, "\n".join(b_lines)))
            continue

        # 7. VM Packages
        if stype == "vm_packages_list" and "packages" in s:
            p_lines = []
            for pkg in s["packages"]:
                p_name = clean_text(pkg.get("package_name", ""))
                p_rec = " (Recommended)" if pkg.get("is_recommended") else ""
                p_desc = clean_text(pkg.get("description", ""))
                p_tools = clean_text(pkg.get("tools_available", ""))
                line = f"### Package: {p_name}{p_rec}\n{p_desc}"
                if p_tools: line += f"\nTools available: {p_tools}"
                p_lines.append(line)
            if p_lines:
                out.append((sec_path, "\n\n".join(p_lines)))
            continue

        # 8. Community Guidelines & Conduct Rules
        if (stype == "guidelines_list" or "guidelines" in s) and isinstance(s.get("guidelines"), list):
            gl = s["guidelines"]
            g_lines = [
                f"Total Rules & Conduct Guidelines: {len(gl)}",
                "\neChipHub Community Rules & Guidelines:"
            ]
            for i, rule in enumerate(gl):
                rtitle = clean_text(rule.get("title", f"Rule {i+1}"))
                rcontent = clean_text(rule.get("content", ""))
                first_sent = rcontent.split(".")[0].strip() if "." in rcontent else rcontent[:140]
                g_lines.append(f"{i+1}. {rtitle}: {first_sent}.")
            out.append((sec_path + ("Overview",), "\n".join(g_lines)))

            for i, rule in enumerate(gl):
                rtitle = clean_text(rule.get("title", f"Rule {i+1}"))
                rcontent = clean_text(rule.get("content", ""))
                out.append((sec_path + (rtitle,), f"### Guideline {i+1}: {rtitle}\n{rcontent}"))
            continue

        # 9. General section fallback (no URLs)
        parts = []
        main_text = s.get("content") or s.get("description") or s.get("headline") or s.get("statement") or s.get("vision") or s.get("text")
        if main_text and isinstance(main_text, str):
            cleaned = clean_text(main_text)
            if cleaned: parts.append(cleaned)

        if "items" in s and isinstance(s["items"], list):
            lines = clean_lines(s["items"])
            if lines: parts.append("\n".join(f"- {l}" for l in lines))

        skip_keys = {
            "section_name", "heading", "title", "type", "id", "content", "description",
            "headline", "statement", "vision", "text", "children", "items"
        }
        for k, v in s.items():
            if k in skip_keys or k.lower() in URL_KEYS or k.lower().endswith(("_url", "_uri", "_action")):
                continue
            if v is None or v == "" or v == [] or v == {}:
                continue
            fmt = format_val_no_url(v)
            if fmt:
                k_clean = k.replace("_", " ").title()
                parts.append(f"### {k_clean}\n{fmt}")

        body = "\n\n".join(parts).strip()
        if body:
            out.append((sec_path, body))

        if s.get("children"):
            out += sections_flat(s.get("children"), sec_path)

    return out


def split_words(text, size, overlap):
    w = text.split()
    if len(w) <= size:
        return [text]
    step = max(1, size - overlap)
    return [" ".join(w[i:i + size]) for i in range(0, len(w), step) if w[i:i + size]][:200]


def chunk_page(doc):
    """Pieces of about CHUNK_WORDS words. Small neighbouring sections are packed together."""
    title = clean_title(doc.get("title") or doc.get("page_title") or doc.get("name"), doc["url"])
    site = doc.get("site", "")
    parts = []
    flat = sections_flat(doc.get("sections")) or [((), doc.get("full_markdown", ""))]
    for path, text in flat:
        label = " > ".join(clean_text(p) for p in path if p)[:300]
        room = max(60, config.CHUNK_WORDS - len(label.split()))
        for piece in split_words(text, room, config.CHUNK_OVERLAP):
            parts.append((label, piece))
    chunks, cur, cur_words = [], [], 0
    for label, piece in parts:
        n = len(clean_text(f"{label}\n{piece}").split())
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
        out.append({"url": doc["url"], "title": title, "site": site,
                    "headings": headings[:6], "chunk": len(out),
                    "text": md,                                       # clean hierarchical text (zero URLs)
                    "embed_text": f"{title}\n{plain}"})               # used for the embeddings
    return out


def collect_nodes(node, site, docs):
    if isinstance(node, list):
        for item in node:
            collect_nodes(item, site, docs)
        return
    if not isinstance(node, dict):
        return
    if "pages" in node and isinstance(node["pages"], list):
        for page in node["pages"]:
            collect_nodes(page, site, docs)
        return
    if not node.get("url"):
        return
    url = normalize_url(node["url"])
    if not url:
        return
    sections = node.get("sections") or []
    title = node.get("page_title") or node.get("name") or node.get("title") or ""
    # Avoid replacing main site page with empty SSO button placeholders
    is_sso_stub = node.get("id") in ("registration", "authenticate", "openedx-sso")
    if url not in docs:
        docs[url] = {
            "url": url,
            "title": title,
            "link_text": node.get("link_text", ""),
            "sections": sections,
            "site": site,
        }
    elif not is_sso_stub:
        existing_size = len(str(docs[url].get("sections", [])))
        new_size = len(str(sections))
        if new_size > existing_size:
            docs[url]["sections"] = sections
            if title:
                docs[url]["title"] = title
    for child in node.get("children", []):
        collect_nodes(child, site, docs)


def load_pages():
    docs = {}
    json_files = sorted(glob.glob(os.path.join(config.DATA_DIR, "**", "*.json"), recursive=True))
    for path in json_files:
        site = os.path.splitext(os.path.basename(path))[0]
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            print(f"  skipped {path}: {e}")
            continue
        collect_nodes(d, site, docs)
    return docs


META = os.path.join(os.path.dirname(config.QDRANT_PATH), "index_meta.json")


def main(rebuild=False, dry=False):
    import embeddings, vector_store as vs
    t0 = time.time()
    docs = load_pages()
    if not docs:
        sys.exit(f"No pages found in {config.DATA_DIR}.\nRun scraper first:  python scraper_master.py")
    print(f"{len(docs)} clean pages found in {config.DATA_DIR}")

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
