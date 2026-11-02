"""Cleaning + sorting engine (no internet needed).

classify(pages, ...) puts every page into one of four groups and returns the cleaned text of the kept ones:
    keep / unwanted / duplicate / broken      (see rules.py for what each rule does)
"""
import hashlib, re
from collections import Counter, defaultdict
from urllib.parse import urlsplit

import rules

LABELS = {"keep": "Real / useful", "unwanted": "Unwanted (removed)",
          "duplicate": "Duplicate (same content)", "broken": "Broken / inaccessible"}

LOREM = set("""lorem ipsum dolor sit amet consectetur adipiscing elit sed eiusmod tempor incididunt labore dolore
magna aliqua enim minim veniam quis nostrud exercitation ullamco laboris nisi aliquip commodo consequat duis aute
irure reprehenderit voluptate velit esse cillum fugiat nulla pariatur excepteur sint occaecat cupidatat proident
sunt culpa officia deserunt mollit anim vestibulum curabitur donec pellentesque porttitor quam vehicula elementum
dui rutrum congue leo eget malesuada nisl tempus convallis lectus sollicitudin molestie arcu erat accumsan
imperdiet aliquet posuere blandit ipsum orci porta dapibus praesent sapien massa egestas tortor risus cras
ultricies ligula dictum mauris tincidunt nibh pulvinar faucibus luctus ultrices cubilia curae auctor
ullamcorper voluptatem perferendis voluptate praesentium ducimus consequatur dignissimos tempora numquam
sapiente soluta architecto saepe""".split())


# ------------------------------------------------------------------ text helpers
def words(text):
    return re.findall(r"[A-Za-z0-9\u00C0-\uFFFF]+", text or "")


def plain(md):
    """Markdown -> plain words: link targets, images and markdown symbols removed."""
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md or "")
    t = re.sub(r"\]\([^)]*\)", "] ", t)
    t = re.sub(r"https?://\S+", " ", t)
    return re.sub(r"[#*_>|`\[\]\-]+", " ", t)


def fingerprint(md):
    """Same text = same fingerprint (link targets and markdown symbols are ignored)."""
    return hashlib.sha1(" ".join(words(plain(md).lower())).encode()).hexdigest()


def shingles(md, n=5):
    w = [x.lower() for x in words(plain(md))]
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))} if w else set()


def platform_patterns(platform):
    return rules.BOILERPLATE_PATTERNS.get("*", []) + rules.BOILERPLATE_PATTERNS.get(platform, [])


def remove_patterns(md, platform):
    for p in platform_patterns(platform):
        md = re.sub(p, "\n", md)
    return md


def dedupe_inside_page(md):
    """Text repeated on the same page (desktop + mobile copies, card front + back) is kept once."""
    out, seen, recent_headings = [], set(), []
    for line in md.splitlines():
        s = line.strip()
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            text = " ".join(words(plain(m.group(2)))).lower()
            if text and any(t == text and len(out) - i <= 6 for i, t in recent_headings):
                continue                                # same heading again a few lines later
            recent_headings.append((len(out), text))
            out.append(line)
            continue
        key = " ".join(words(plain(s))).lower()
        if len(key) >= 40 and not s.startswith("|"):
            if key in seen:
                continue
            seen.add(key)
        out.append(line)
    while out and (not out[-1].strip() or re.match(r"^#{1,6}\s", out[-1].strip())):
        out.pop()                                       # a heading left with nothing under it at the end
    md = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def blocks(md):
    """Split into sections (a heading + the text under it, up to the next heading)."""
    parts, cur = [], []
    for line in md.splitlines():
        if re.match(r"^#{1,6}\s", line.strip()) and cur:
            parts.append("\n".join(cur)); cur = []
        cur.append(line)
    if cur:
        parts.append("\n".join(cur))
    return [p for p in parts if p.strip()]


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ url helpers
def path_query(url):
    p = urlsplit(url)
    return (p.path or "/") + (f"?{p.query}" if p.query else "")


def never_open(url):
    u = url.lower()
    for b in rules.NEVER_OPEN:
        if b in u:
            return b
    return None


def action_free(url, canonical):
    """The same link without the query parts that trigger an action (add-to-cart=..), or None."""
    p = urlsplit(url)
    if not p.query:
        return None
    from urllib.parse import parse_qsl, urlencode, urlunsplit
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not never_open(f"{k}={v}")]
    rest = urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))
    return canonical(rest) if not never_open(rest) else None


def unwanted_url(url):
    """Reason if the link matches an UNWANTED_URLS rule of its site, else None."""
    if url in rules.ALWAYS_KEEP:
        return None
    host = urlsplit(url).netloc.lower()
    pq = path_query(url)
    for pattern, reason in rules.UNWANTED_URLS.get(host, []):
        if re.search(pattern, pq, re.I):
            return reason
    return None


def rank(u, required, found_by):
    p = urlsplit(u)
    return (u not in required, found_by.get(u) != "start",
            bool(p.query), p.path.rstrip("/").count("/"), len(u), u)


def canonical_choice(urls, required, found_by):
    return min(urls, key=lambda u: rank(u, required, found_by))


# ------------------------------------------------------------------ main entry
def classify(pages, platform_of, home_of, required, canonical, looks_like_login):
    """pages: {url: {"status", "title", "access", "found_by", "reason"?, "error"?, "cache": {...} or None}}
    Returns ({url: {"category", "reason", "duplicate_of"?, "clean_md"?, "words_raw"?, "words_clean"?}},
             removed_boilerplate {host: [(text, pages)]})"""
    required = {canonical(u) for u in required}
    found_by = {u: p.get("found_by") for u, p in pages.items()}
    out = {}

    def put(u, cat, reason, **extra):
        out[u] = {"category": cat, "reason": reason, **extra}

    # ---- A. decisions from the crawl status and the link itself
    candidates = []
    for u, p in pages.items():
        st, cache = p.get("status", ""), p.get("cache")
        keep_forced = u in rules.ALWAYS_KEEP
        if st == "excluded":
            put(u, "unwanted", f"{p.get('reason', 'unwanted link')} (not opened)")
        elif never_open(u):
            base = action_free(u, canonical)
            if base and base != u and base in pages:
                put(u, "duplicate", f"action link ({never_open(u)}) to the same page - must not be opened",
                    duplicate_of=base)
            else:
                put(u, "unwanted", f"action link ({never_open(u)}) - must not be opened")
        elif canonical(u) != u and canonical(u) in pages:
            put(u, "duplicate", "same page; the link only adds a sort/share/tracking option",
                duplicate_of=canonical(u))
        elif unwanted_url(u) and not keep_forced:
            put(u, "unwanted", unwanted_url(u))
        elif st == "new":
            put(u, "pending", "not read yet - run 'python extract.py crawl'")
        elif st.startswith("not found"):
            put(u, "broken", "page not found (404)")
        elif st == "failed":
            put(u, "broken", f"could not be loaded ({p.get('error', 'error')})")
        elif st == "needs login":
            put(u, "broken", "opens the login page even when logged in")
        elif st == "no text":
            put(u, "unwanted", "no readable text (empty page or file)")
        elif not cache:
            put(u, "pending", "saved text is missing - run 'python extract.py crawl'")
        else:
            final = canonical(cache.get("final_url") or u)
            if final != u and looks_like_login(cache.get("final_url") or ""):
                put(u, "broken", "redirects to the login page")
            elif final != u and final in pages and pages[final].get("status") == "ok":
                put(u, "duplicate", "redirects to another page", duplicate_of=final)
            elif rules.PUBLIC_ONLY and p.get("access") == "login" and not keep_forced:
                put(u, "unwanted", "only visible after login (the chatbot is public)")
            else:
                candidates.append(u)

    # ---- B. clean the text: fixed patterns, then automatic site-wide boilerplate
    host = lambda u: urlsplit(u).netloc.lower()
    stage1 = {}
    for u in candidates:
        md = pages[u]["cache"].get("markdown", "")
        stage1[u] = remove_patterns(md, platform_of(host(u)))

    removed = {}
    by_host = defaultdict(list)
    for u in candidates:
        by_host[host(u)].append(u)
    stage2 = {}
    for h, urls in by_host.items():
        distinct = {}                                   # count each distinct page once (copies don't vote twice)
        for u in urls:
            distinct.setdefault(fingerprint(stage1[u]), u)
        n = len(distinct)
        drop_blocks, drop_lines = set(), set()
        if n >= rules.AUTO_BOILERPLATE_MIN_PAGES:
            bc, lc = Counter(), Counter()
            for u in distinct.values():
                bs = {norm(b) for b in blocks(stage1[u]) if len(norm(b)) >= rules.AUTO_BOILERPLATE_MIN_CHARS}
                ls = {norm(l) for l in stage1[u].splitlines()
                      if len(norm(l)) >= rules.AUTO_BOILERPLATE_MIN_CHARS and not norm(l).startswith("#")}
                bc.update(bs); lc.update(ls)
            limit = max(2, rules.AUTO_BOILERPLATE_SHARE * n)
            drop_blocks = {b for b, c in bc.items() if c >= limit}
            drop_lines = {l for l, c in lc.items() if c >= limit}
            removed[h] = sorted([(b, bc[b]) for b in drop_blocks] + [(l, lc[l]) for l in drop_lines],
                                key=lambda x: -x[1])
        for u in urls:
            kept = [b for b in blocks(stage1[u]) if norm(b) not in drop_blocks]
            text = "\n".join(l for l in "\n".join(kept).splitlines() if norm(l) not in drop_lines)
            stage2[u] = dedupe_inside_page(text)

    # ---- C. content rules
    alive = []
    homes = {h: canonical(home_of(h)) for h in by_host}
    home_sh = {h: shingles(stage2[hu]) for h, hu in homes.items() if hu in stage2}
    for u in candidates:
        md, title = stage2[u], pages[u].get("title") or ""
        w = words(plain(md))
        info = {"clean_md": md, "words_raw": len(words(plain(pages[u]["cache"].get("markdown", "")))),
                "words_clean": len(w)}
        forced = u in rules.ALWAYS_KEEP
        lorem = sum(1 for x in w if x.lower() in LOREM) / max(1, len(w))
        h = host(u)
        if u != homes.get(h) and h in home_sh and platform_of(h) in rules.SOFT_404_PLATFORMS \
                and jaccard(shingles(md), home_sh[h]) >= rules.NEAR_DUPLICATE:
            put(u, "broken", "shows the home page instead of its own content (soft 404)", **info)
        elif forced:
            alive.append(u); out[u] = {"category": "keep", "reason": "in ALWAYS_KEEP", **info}
        elif lorem > rules.LOREM_SHARE:
            put(u, "unwanted", f"placeholder Lorem-ipsum text ({lorem:.0%} filler words)", **info)
        elif any(x.lower() in md.lower() for x in rules.PLACEHOLDER_PHRASES):
            put(u, "unwanted", "default sample content of the website software", **info)
        elif re.search(rules.TEST_TITLE, title, re.I):
            put(u, "unwanted", f"test/demo page (title: {title[:60]})", **info)
        elif len(w) < rules.EMPTY_PLACEHOLDER_WORDS and any(x.lower() in md.lower()
                                                            for x in rules.EMPTY_PLACEHOLDERS):
            ph = next(x for x in rules.EMPTY_PLACEHOLDERS if x.lower() in md.lower())
            put(u, "unwanted", f"placeholder - no content yet (\"{ph}\")", **info)
        elif len(w) < rules.MIN_WORDS:
            put(u, "unwanted", f"empty or almost empty page ({len(w)} words after cleaning)", **info)
        else:
            alive.append(u); out[u] = {"category": "keep", "reason": "", **info}

    # ---- D. duplicates among what is left (exact, then near-identical)
    groups = defaultdict(list)
    for u in alive:
        groups[(host(u), fingerprint(out[u]["clean_md"]))].append(u)
    reps = []
    for (_, _), urls in groups.items():
        best = canonical_choice(urls, required, found_by)
        reps.append(best)
        for u in urls:
            if u != best:
                out[u].update(category="duplicate", reason="identical text", duplicate_of=best)
    sh = {u: shingles(out[u]["clean_md"]) for u in reps}
    reps.sort(key=lambda u: rank(u, required, found_by))
    winners = []
    for u in reps:
        match = None
        for wv in winners:
            if host(wv) == host(u) and abs(len(sh[wv]) - len(sh[u])) <= 0.2 * max(len(sh[wv]), len(sh[u]), 1) \
                    and jaccard(sh[u], sh[wv]) >= rules.NEAR_DUPLICATE:
                match = wv; break
        if match:
            best = canonical_choice([u, match], required, found_by)
            other = u if best == match else match
            if best != match:                          # the new one is the better link: swap
                winners[winners.index(match)] = best
            out[other].update(category="duplicate", reason="nearly identical text", duplicate_of=best)
            for x, d in out.items():                   # re-point anything that pointed to the loser
                if d.get("duplicate_of") == other:
                    d["duplicate_of"] = best
        else:
            winners.append(u)
    for d in out.values():
        if d["category"] != "keep":
            d.pop("clean_md", None)
    return out, removed


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
