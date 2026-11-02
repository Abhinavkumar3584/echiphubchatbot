"""eChipHub full extractor  -  one command does everything:

    python extract.py run          login -> find all URLs -> crawl -> website_tree.json -> one JSON per site

(run from the project folder:  python extractor/extract.py run)

Steps can also be run one by one (each continues where the last run stopped):
    python extract.py login        asks your ID + password, logs in to every site (Keycloak), saves the session
    python extract.py discover     STEP 1: finds every URL of every site -> output/website_tree.json (links only)
    python extract.py crawl        STEP 2: opens every URL (logged in, several at a time), extracts the content
    python extract.py build        STEP 3: cleans + sorts every page (keep / unwanted / duplicate / broken) and writes
                                   output/sites/<site>.json, output/pages/ and output/report/  (no internet needed)
    python extract.py report       the four groups per site, reasons, and the REQUIRED_URLS check

What is kept, removed, merged or reported as broken is decided by rules.py (edit that file, then run 'build').
Options: --fresh (start over)   --show (watch the browser)

Your password is only kept in memory while logging in. It is never written to disk.
output/session.json (the logged-in cookies) works like a password: delete it when you are finished.
"""
import asyncio, getpass, hashlib, json, os, re, shutil, sys, time
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

os.environ.setdefault("CRAWL4AI_NO_CLOUD_NOTICE", "1")
import httpx
from bs4 import BeautifulSoup

import cleaner
import rules

# =============================== SETTINGS ===============================
# One entry per website. "platform" lets the script use that platform's own page lists (fast + complete).
SITES = {
    "echiphub.in": {
        "platform": "wordpress",
        "start": ["https://echiphub.in/"],
        "login": "https://echiphub.in/",
        "js_wait": 2.0,
    },
    "events.echiphub.in": {
        "platform": "indico",
        "start": ["https://events.echiphub.in/"],
        "login": "https://events.echiphub.in/login/",
        "js_wait": 0.5,                       # server-rendered: no need to wait for JavaScript
    },
    "edx.echiphub.in": {
        "platform": "openedx",
        "start": ["https://edx.echiphub.in/", "https://edx.echiphub.in/courses"],
        "login": "https://edx.echiphub.in/login",
        "js_wait": 2.5,
    },
    "community.echiphub.in": {
        "platform": "discourse",
        "start": ["https://community.echiphub.in/"],
        "login": "https://community.echiphub.in/auth/oidc",
        "js_wait": 2.5,
    },
    "labs.echiphub.in": {
        "platform": "jupyterhub",
        "start": ["https://labs.echiphub.in/hub/home"],
        "login": "https://labs.echiphub.in/hub/login",
        "js_wait": 2.5,
    },
}
# Pages that MUST be in the result - the report checks each one by name. Add any page you care about.
REQUIRED_URLS = [
    "https://echiphub.in/",
    "https://echiphub.in/about",
    "https://echiphub.in/all-courses",
    "https://echiphub.in/workshops",
    "https://echiphub.in/contact",
    "https://community.echiphub.in/about",
    "https://community.echiphub.in/badges",
    "https://community.echiphub.in/guidelines",
    "https://events.echiphub.in/",
    "https://edx.echiphub.in/courses",
    "https://labs.echiphub.in/hub/home",
]
HERE = os.path.dirname(os.path.abspath(__file__))
EXTRA_URLS_FILE = os.path.join(HERE, "extra_urls.txt")   # optional: one URL per line (pages nothing links to)
SSO_HOST = "sso.echiphub.in"

# Links that are never opened, junk links and text removed from pages: see rules.py
FILE_EXT = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".zip", ".csv", ".txt",
            ".7z", ".rar", ".gz", ".tar", ".tgz")
FILE_PATTERNS = ("/attachments/",)
SKIP_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".mp4", ".mp3", ".ico", ".css", ".js", ".xml", ".json")

CONCURRENCY = 4          # pages opened at the same time (lower to 2 if the site starts refusing)
DELAY_SECONDS = 0.5      # pause per page per worker
RETRIES = 2              # extra tries for a failed page
MAX_PAGES = 3000         # safety limit
MAX_EVENT_ID = 400       # Indico: event numbers checked 1..this (fast check, no browser)
OUT = os.path.join(os.path.dirname(HERE), "output")   # <project>/output
# =========================================================================

SESSION = os.path.join(OUT, "session.json")
STATE = os.path.join(OUT, "state.json")
CACHE = os.path.join(OUT, "cache")
SHOW = "--show" in sys.argv
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# ----------------------------------------------------------------- helpers
def stripped_params(host):
    names = list(rules.STRIP_PARAMS.get("*", []))
    if host in SITES:
        names += rules.STRIP_PARAMS.get(SITES[host]["platform"], [])
    return {n.lower() for n in names}


def strip_query(query, host):
    drop = stripped_params(host)
    return urlencode([(k, v) for k, v in parse_qsl(query, keep_blank_values=True)
                      if k.lower() not in drop and not k.lower().startswith("utm_")])


def fetch_form(url):
    """The link as it will be opened: same as found (keeps the trailing slash) minus sort/share/tracking parts."""
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme, p.netloc, p.path, strip_query(p.query, p.netloc.lower().removeprefix("www.")), ""))


def canonical(url):
    p = urlsplit(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    query = strip_query(p.query, host)
    path = re.sub(r"/+$", "", p.path) or "/"
    path = re.sub(r"^(/event/\d+)/overview$", r"\1", path)          # Indico duplicate form
    path = re.sub(r"^(/t/[^/]+/\d+)/\d+$", r"\1", path)             # Discourse post-number form
    scheme = "https" if host.endswith("echiphub.in") else (p.scheme or "https")
    return urlunsplit((scheme, host, path, query, ""))


def host_of(url):
    return urlsplit(url).netloc.lower()


def base(host):
    """https://host (scheme taken from the site's first start URL)."""
    return f"{urlsplit(SITES[host]['start'][0]).scheme}://{host}"


def why_skip(url):
    u = url.lower()
    if u.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
        return "not a web page"
    if host_of(u) not in SITES:
        return "other website"
    if u.split("?")[0].endswith(SKIP_EXT):
        return "image/media/code file"
    b = cleaner.never_open(u)
    if b:
        return f"blocked ({b})"
    if re.search(r"^https?://[^/]+/g(/|$|\?)", u):          # Discourse group pages (member lists)
        return "blocked (/g)"
    return None


def is_file(url):
    u = url.lower().split("#")[0]
    return u.split("?")[0].endswith(FILE_EXT) or any(x in u for x in FILE_PATTERNS)


def looks_like_login(url, title="", text=""):
    u, t = (url or "").lower(), (title or "").lower()
    return (SSO_HOST in u or any(x in u for x in ("/login", "/signin", "wp-login", "/authn/"))
            or t.startswith(("sign in", "log in", "login")) or "sign in to your account" in (text or "").lower()[:600])


def short_error(text):
    text = (text or "failed").strip()
    m = re.search(r"(net::ERR_[A-Z_]+|Timeout \d+ms exceeded|timed? ?out|browser has (been closed|disconnected)|"
                  r"HTTP \d+)", text, re.I)
    if m:
        return m.group(1)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return (lines[-1] if lines else "failed")[:150]


def sections_from_markdown(md):
    root = {"heading": None, "level": 0, "content": "", "children": []}
    stack = [root]
    for line in md.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            level = len(m.group(1))
            node = {"heading": m.group(2).strip(), "level": level, "content": "", "children": []}
            while stack[-1]["level"] >= level:
                stack.pop()
            stack[-1]["children"].append(node)
            stack.append(node)
        else:
            stack[-1]["content"] += line + "\n"
    def clean(n):
        n["content"] = re.sub(r"\n{3,}", "\n\n", n["content"]).strip()
        for c in n["children"]:
            clean(c)
    clean(root)
    top = root["children"]
    if root["content"]:
        top = [{"heading": "(introduction)", "level": 1, "content": root["content"], "children": []}] + top
    return top


def load_json(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def cache_path(url):
    return os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest() + ".json")


def session_cookies():
    jar = httpx.Cookies()
    for c in load_json(SESSION, {}).get("cookies", []):
        try:
            jar.set(c["name"], c["value"], domain=c["domain"].lstrip("."), path=c.get("path", "/"))
        except Exception:
            pass
    return jar


# ================================================================= LOGIN
SSO_BUTTON = re.compile(r"(keycloak|single sign|\bsso\b|openid|oidc|sign in with|log ?in with)", re.I)
LOGIN_BUTTON = re.compile(r"^\s*(log ?in|sign ?in)\s*$", re.I)


def try_fill_form(page, user, pw):
    """Fill a visible username/password form (Keycloak or a site's own form). Returns True if submitted."""
    pw_box = page.locator("input[type=password]:visible")
    if pw_box.count() == 0:
        return False
    for sel in ["#username", "input[name=username]", "input[type=email]:visible", "input[name*=email]:visible",
                "input[name*=user]:visible", "#user_login", "input[name=emailOrUsername]", "input[type=text]:visible"]:
        box = page.locator(sel)
        if box.count() > 0:
            try:
                box.first.fill(user); break
            except Exception:
                continue
    pw_box.first.fill(pw)
    for sel in ["#kc-login", "#wp-submit", "button[type=submit]:visible", "input[type=submit]:visible"]:
        b = page.locator(sel)
        if b.count() > 0:
            try:
                b.first.click(); break
            except Exception:
                continue
    else:
        pw_box.first.press("Enter")
    page.wait_for_timeout(2000)
    page.wait_for_load_state("load", timeout=30000)
    if SSO_HOST in page.url and re.search(r"invalid (username|email|password)|incorrect", page.content(), re.I):
        raise SystemExit("\nLOGIN FAILED: Keycloak says the ID or password is wrong. Run the command again.")
    return True


def click_matching(page, pattern):
    for role in ("link", "button"):
        loc = page.get_by_role(role, name=pattern)
        if loc.count() > 0:
            try:
                loc.first.click(); page.wait_for_timeout(1500)
                page.wait_for_load_state("load", timeout=30000); return True
            except Exception:
                pass
    return False


def logged_in_signs(page):
    try:
        html = page.content().lower()
    except Exception:
        return False
    return any(x in html for x in ("logout", "log out", "sign out", "signout", "current-user", "my account",
                                   "my-account", "wpadminbar"))


def login():
    from playwright.sync_api import sync_playwright
    print("\nLog in once - the same Keycloak ID and password is used for every eChipHub site.")
    user = input("  Login ID (email / username): ").strip()
    pw = getpass.getpass("  Password (hidden while typing): ")
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=bool(os.environ.get("EXTRACT_HEADLESS_LOGIN")))
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        results = {}
        for host, site in SITES.items():
            print(f"\n  {host}: logging in...")
            try:
                page.goto(site["login"], timeout=60000)
                page.wait_for_load_state("load", timeout=30000)
                for _ in range(5):
                    if SSO_HOST in page.url and try_fill_form(page, user, pw):
                        continue                              # Keycloak form filled and sent
                    if not looks_like_login(page.url) and logged_in_signs(page):
                        break                                 # already logged in
                    if click_matching(page, SSO_BUTTON):
                        continue
                    if try_fill_form(page, user, pw):
                        continue
                    if click_matching(page, LOGIN_BUTTON):
                        continue
                    break
                if page.locator("#otp:visible, input[name=otp]:visible").count() > 0:
                    input("    A one-time code is needed: type it in the browser, then press Enter here... ")
                page.goto(site["start"][0], timeout=60000)
                page.wait_for_load_state("load", timeout=30000)
                results[host] = logged_in_signs(page)
            except Exception as e:
                print(f"    problem: {short_error(str(e))}")
                results[host] = False
            print(f"    {'OK - logged in' if results[host] else 'NOT SURE - please check this site in the browser'}")
        del pw
        if not all(results.values()):
            print("\nFor sites marked NOT SURE: in the Chrome window, open the site, click Login / Sign in,")
            print("finish logging in (Keycloak normally remembers you), and check you see your name.")
            input("Press Enter when done (or if the site has no login for you)... ")
        ctx.storage_state(path=SESSION)
        browser.close()
    print(f"\nSession saved ({SESSION}). Delete it when the extraction is finished.")


# ============================================================ DISCOVER
class State:
    """Every URL ever found: status, parent page (for the tree), how it was found."""
    def __init__(self, fresh=False):
        self.nodes = {} if fresh else load_json(STATE, {})
        for u, n in self.nodes.items():                 # rules.py may have changed since the last run
            reason = cleaner.unwanted_url(u)
            if n["status"] in ("new", "failed") and reason:
                n["status"], n["reason"] = "excluded", reason
            elif n["status"] == "excluded" and not reason:
                n["status"] = "new"; n.pop("reason", None)

    def add(self, url, parent=None, found_by="link", fetch=None):
        """Adds a new URL. Returns True only if it is new AND should be read (junk links are listed, not read)."""
        n = self.nodes.get(url)
        if n is None:
            reason = cleaner.unwanted_url(url)
            self.nodes[url] = {"status": "excluded" if reason else "new", "parent": parent, "found_by": found_by,
                               "title": "", "fetch": fetch_form(fetch or url)}
            if reason:
                self.nodes[url]["reason"] = reason
            return not reason
        if fetch and found_by == "link" and n["status"] == "new":
            n["fetch"] = fetch_form(fetch)              # open it the way the site itself links to it
        # prefer a real link parent over "found in a list" (gives a better tree), never create loops
        if parent and n["parent"] is None and n["found_by"] != "start" and not self.is_ancestor(url, parent):
            n["parent"], n["found_by"] = parent, "link"
        return False

    def is_ancestor(self, a, b):
        seen = set()
        while b and b not in seen:
            if b == a:
                return True
            seen.add(b); b = self.nodes.get(b, {}).get("parent")
        return False

    def save(self):
        save_json(STATE, self.nodes)


def sitemap_urls(client, host):
    found, todo, done = set(), [], set()
    try:
        r = client.get(f"{base(host)}/robots.txt")
        if r.status_code == 200:
            todo += [l.split(":", 1)[1].strip() for l in r.text.splitlines() if l.lower().startswith("sitemap:")]
    except Exception:
        pass
    todo += [f"{base(host)}/sitemap.xml", f"{base(host)}/wp-sitemap.xml", f"{base(host)}/sitemap_index.xml"]
    while todo and len(done) < 100:
        sm = todo.pop(0)
        if sm in done:
            continue
        done.add(sm)
        try:
            r = client.get(sm)
            if r.status_code != 200 or b"<" not in r.content[:200]:
                continue
            root = ET.fromstring(r.content)
            locs = [e.text.strip() for e in root.iter() if e.tag.endswith("loc") and e.text]
            if root.tag.endswith("sitemapindex"):
                todo += locs
            else:
                found.update(locs)
        except Exception:
            continue
    return found


def wordpress_urls(client, host):
    found = set()
    try:
        types = client.get(f"{base(host)}/wp-json/wp/v2/types").json()
    except Exception:
        return found
    bases = {t.get("rest_base") for t in (types.values() if isinstance(types, dict) else []) if t.get("rest_base")}
    bases -= {"media", "attachment", "wp_block", "wp_template", "wp_template_part", "wp_navigation",
              "wp_global_styles", "wp_font_family", "wp_font_face", "nav_menu_item", "menu-items"}
    for rb in sorted(bases):
        for page in range(1, 51):
            try:
                r = client.get(f"{base(host)}/wp-json/wp/v2/{rb}", params={"per_page": 100, "page": page, "_fields": "link"})
                items = r.json() if r.status_code == 200 else []
            except Exception:
                break
            if not isinstance(items, list) or not items:
                break
            found.update(i["link"] for i in items if isinstance(i, dict) and i.get("link"))
            if page >= int(r.headers.get("X-WP-TotalPages", page)):
                break
    return found


def discourse_urls(client, host):
    b = base(host)
    found = {f"{b}/{p}" for p in ("about", "badges", "faq", "guidelines", "tos", "privacy",
                                     "categories", "latest", "top")}
    try:
        cats = client.get(f"{b}/categories.json").json()["category_list"]["categories"]
        for c in cats:
            found.add(f"{b}/c/{c['slug']}/{c['id']}")
            for sub in c.get("subcategory_ids") or []:
                found.add(f"{b}/c/{sub}")
    except Exception:
        pass
    for page in range(0, 100):
        try:
            data = client.get(f"{b}/latest.json", params={"page": page}).json()
            topics = data["topic_list"]["topics"]
        except Exception:
            break
        if not topics:
            break
        found.update(f"{b}/t/{t['slug']}/{t['id']}" for t in topics)
        if not data["topic_list"].get("more_topics_url"):
            break
    return found


def indico_urls(client, host):
    b, found = base(host), set()
    try:
        data = client.get(f"{b}/export/categ/0.json", params={"from": "1900-01-01", "to": "2100-12-31"}).json()
        found.update(e["url"] for e in data.get("results", []) if e.get("url"))
    except Exception:
        pass
    async def probe():                               # check /event/1 .. /event/N quickly (no browser)
        sem = asyncio.Semaphore(10)
        async with httpx.AsyncClient(headers={"User-Agent": UA}, cookies=session_cookies(),
                                     timeout=20, follow_redirects=False) as ac:
            async def one(i):
                async with sem:
                    try:
                        r = await ac.get(f"{b}/event/{i}/")
                        if r.status_code in (200, 301, 302, 303, 307, 308, 401, 403):
                            found.add(f"{b}/event/{i}/")
                    except Exception:
                        pass
            await asyncio.gather(*(one(i) for i in range(1, MAX_EVENT_ID + 1)))
    asyncio.run(probe())
    return found


def openedx_urls(client, host):
    b, found = base(host), set()
    url = f"{b}/api/courses/v1/courses/?page_size=100"
    for _ in range(50):
        try:
            data = client.get(url).json()
        except Exception:
            break
        for c in data.get("results", []):
            cid = c.get("course_id") or c.get("id")
            if cid:
                found.add(f"{b}/courses/{cid}/about")
        url = (data.get("pagination") or {}).get("next") or data.get("next")
        if not url:
            break
    return found


PLATFORM_LISTS = {"wordpress": wordpress_urls, "discourse": discourse_urls,
                  "indico": indico_urls, "openedx": openedx_urls}


def seed(state):
    """Add every URL we can know WITHOUT following links: start pages, required pages, extra_urls.txt,
    sitemaps, and each platform's own list (WordPress API, Discourse lists, Indico events, edX courses)."""
    print("\nFinding URLs from every available source (fast, no browser):")
    for host, site in SITES.items():
        for u in site["start"]:
            state.add(canonical(u), None, "start", u)
    for u in REQUIRED_URLS:
        state.add(canonical(u), None, "required list", u)
    if os.path.exists(EXTRA_URLS_FILE):
        for line in open(EXTRA_URLS_FILE, encoding="utf-8"):
            if line.strip() and not line.startswith("#"):
                state.add(canonical(line.strip()), None, "extra_urls.txt", line.strip())
    with httpx.Client(headers={"User-Agent": UA}, cookies=session_cookies(), timeout=30, follow_redirects=True) as client:
        for host, site in SITES.items():
            for name, fn in (("sitemap", sitemap_urls), (f"{site['platform']} list", PLATFORM_LISTS.get(site["platform"]))):
                if not fn:
                    continue
                try:
                    urls = fn(client, host)
                except Exception as e:
                    print(f"  {host:24} {name:18} not available ({short_error(str(e))})"); continue
                new = 0
                for u in urls:
                    c = canonical(u)
                    if not why_skip(c) and state.add(c, None, name, u):
                        new += 1
                print(f"  {host:24} {name:18} {len(urls):5} URLs found ({new} new)")
    state.save()


# =============================================================== CRAWL
async def crawl(state, max_rounds=3, concurrency=None):
    concurrency = concurrency or CONCURRENCY
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    os.makedirs(CACHE, exist_ok=True)
    session = SESSION if os.path.exists(SESSION) else None
    if not session:
        print("\n(no login session - only public pages will be read. Run 'python extract.py login' first.)")
    browser = BrowserConfig(headless=not SHOW, storage_state=session, viewport_width=1440, viewport_height=900, verbose=False)
    run_cfg = {h: CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        markdown_generator=DefaultMarkdownGenerator(options={"ignore_images": True, "body_width": 0}),
        excluded_tags=["nav", "footer", "header", "script", "style", "noscript", "select", "form"],
        excluded_selector="#wpadminbar, .admin-bar, .skip-link",
        remove_overlay_elements=True, wait_until="load", delay_before_return_html=s.get("js_wait", 2.0),
        page_timeout=60000, verbose=False) for h, s in SITES.items()}

    queue = asyncio.Queue()
    for url, n in state.nodes.items():
        if n["status"] in ("new", "failed") and not why_skip(url) and not why_skip(n.get("fetch") or url):
            queue.put_nowait(url)
    total = {"done": 0, "fails_in_row": 0}
    pause = asyncio.Event(); pause.set()
    print(f"\nCrawling {queue.qsize()} URLs with {concurrency} browser tabs at once (new links are added as they are found)...")
    t0 = time.time()

    async with AsyncWebCrawler(config=browser) as crawler:
        async def handle(url):
            node = state.nodes[url]
            target = node.get("fetch") or url
            r, err, code = None, "", 0
            for attempt in range(RETRIES + 1):
                await pause.wait()
                try:
                    r = await crawler.arun(target, config=run_cfg.get(host_of(url), next(iter(run_cfg.values()))))
                    code = r.status_code or 0
                    # Crawl4AI marks small pages as "blocked"; we judge by status code and HTML ourselves
                    if code in (404, 410) or (r.html and code < 400):
                        break
                    err = f"HTTP {code}" if code >= 400 else short_error(r.error_message)
                except Exception as e:
                    err, r, code = short_error(f"{e}"), None, 0
                if attempt < RETRIES:
                    await asyncio.sleep(3 * (attempt + 1))
            if r is not None and code in (404, 410):
                node["status"] = "not found (404)"
                return
            if r is None or not r.html or code >= 400:
                node["status"], node["error"] = "failed", err or "no page returned"
                total["fails_in_row"] += 1
                print(f"  FAILED  {url}  ->  {node['error']}")
                if total["fails_in_row"] >= 8 and pause.is_set():
                    print("\n  Many failures in a row - the server may be limiting us. Pausing 90 seconds...\n")
                    pause.clear(); state.save(); await asyncio.sleep(90); total["fails_in_row"] = 0; pause.set()
                return
            total["fails_in_row"] = 0

            final = r.redirected_url or target
            title = ((r.metadata or {}).get("title") or "").strip()
            md = (r.markdown.raw_markdown if r.markdown is not None and hasattr(r.markdown, "raw_markdown")
                  else str(r.markdown or "")).strip()
            if not md:                                   # fallback: plain text from the HTML
                soup = BeautifulSoup(r.html, "html.parser")
                for t in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                    t.decompose()
                md = soup.get_text("\n", strip=True)
                if not title and soup.title:
                    title = soup.title.get_text(strip=True)
            same_site, other_sites, files = [], [], []
            for a in BeautifulSoup(r.html or "", "html.parser").find_all("a", href=True):
                absu = urljoin(final, a["href"].strip())
                if is_file(absu):
                    files.append({"url": absu.split("#")[0], "text": a.get_text(" ", strip=True)[:120]}); continue
                c = canonical(absu)
                reason = why_skip(c) or (why_skip(absu.split("#")[0]) if host_of(absu).removeprefix("www.") in SITES
                                         else None)
                if reason == "other website" and not c.startswith(("mailto", "tel", "javascript")):
                    other_sites.append(c); continue
                if reason:
                    continue
                if c != url:
                    same_site.append(c)
                    if state.add(c, url, "link", absu.split("#")[0]):
                        queue.put_nowait(c)
            if looks_like_login(final, title, md):
                node["status"], node["title"] = "needs login", title
                print(f"   LOGIN  {url}"); return
            node["title"] = title
            if len(md.split()) < 5:
                node["status"] = "no text"; return
            save_json(cache_path(url), {
                "url": url, "final_url": canonical(final), "status_code": code, "title": title,
                "description": (r.metadata or {}).get("description"),
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "markdown": md, "links": sorted(set(same_site)), "other_site_links": sorted(set(other_sites)),
                "files": list({f["url"]: f for f in files}.values())})
            node["status"], node["cache"] = "ok", cache_path(url)
            total["done"] += 1
            if total["done"] % 25 == 0:
                state.save()
                print(f"  ... {total['done']} pages read, {queue.qsize()} waiting, {(time.time() - t0) / 60:.1f} min")
            print(f"  OK  {url}  ({len(md.split())} words)")

        async def worker():
            while True:
                url = await queue.get()
                try:
                    if total["done"] < MAX_PAGES and state.nodes[url]["status"] in ("new", "failed"):
                        await handle(url)
                        await asyncio.sleep(DELAY_SECONDS)
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
        await queue.join()
        for w in workers:
            w.cancel()
    state.save()
    failed = [u for u, n in state.nodes.items() if n["status"] == "failed"]
    print(f"\nRead {total['done']} pages in {(time.time() - t0) / 60:.1f} min. Failed: {len(failed)}")
    if failed and max_rounds > 1:
        print("Trying the failed pages once more, slowly (one at a time)...")
        await crawl(state, max_rounds - 1, concurrency=1)


# ========================================================== ACCESS CHECK
def check_access(state):
    """Which pages can anyone see? Opens each page WITHOUT login (fast, no browser)."""
    ok_pages = [u for u, n in state.nodes.items() if n["status"] == "ok"]
    print(f"\nChecking which of the {len(ok_pages)} pages are public (without login)...")
    async def run():
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=25, follow_redirects=True) as ac:
            home_ok = {}
            for h in SITES:
                try:
                    home_ok[h] = (await ac.get(f"{base(h)}/")).status_code == 200
                except Exception:
                    home_ok[h] = False
            async def one(u):
                async with sem:
                    if not home_ok.get(host_of(u)):
                        state.nodes[u]["access"] = "unknown (site blocks simple checks)"; return
                    try:
                        r = await ac.get(u)
                        if r.status_code in (401, 403) or looks_like_login(str(r.url), "", r.text[:3000]):
                            state.nodes[u]["access"] = "login"
                        elif r.status_code == 200:
                            state.nodes[u]["access"] = "public"
                        else:
                            state.nodes[u]["access"] = f"unknown (HTTP {r.status_code})"
                    except Exception:
                        state.nodes[u]["access"] = "unknown"
            await asyncio.gather(*(one(u) for u in ok_pages))
    asyncio.run(run())
    state.save()


# =============================================================== BUILD
REPORT_DIR = os.path.join(OUT, "report")
PAGES_DIR = os.path.join(OUT, "pages")
ORDER = ["keep", "unwanted", "duplicate", "broken", "pending"]


def read_cache(url, node):
    for path in (node.get("cache"), cache_path(url)):
        if path:
            path = path.replace("\\", os.sep).replace("/", os.sep)
            if os.path.exists(path):
                return load_json(path, None)
    return None


def page_file_name(url):
    p = urlsplit(url)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", (p.path + ("-" + p.query if p.query else "")).strip("/")).strip("-")
    return f"{(slug or 'home')[:80]}-{hashlib.sha1(url.encode()).hexdigest()[:8]}.json"


def build(state, with_content):
    """Sorts every page into keep / unwanted / duplicate / broken and writes:
       output/website_tree.json           every URL of every site, with its group and the reason
       output/sites/<site>.json           ONLY the kept pages: cleaned text, sections, tree   (with_content)
       output/pages/<site>/<page>.json    one file per kept page, ready for the chatbot's load_knowledge.py
       output/report/filter_report.csv    every URL with group + reason (open in Excel)
       output/report/filter_report.json   the same + summary + boilerplate that was removed"""
    nodes = state.nodes
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pages = {}
    for u, n in nodes.items():
        if host_of(u) not in SITES:
            continue
        pages[u] = dict(n, cache=read_cache(u, n) if n["status"] == "ok" else None)

    decision, removed = cleaner.classify(
        pages, platform_of=lambda h: SITES.get(h, {}).get("platform", ""),
        home_of=lambda h: f"{base(h)}/", required=REQUIRED_URLS, canonical=canonical,
        looks_like_login=looks_like_login)
    keep = {u for u, d in decision.items() if d["category"] == "keep"}

    def kept_parent(u):
        """Nearest page above this one that is kept (duplicates hang under the page they copy)."""
        seen, p = set(), nodes.get(u, {}).get("parent")
        while p and p not in seen:
            seen.add(p)
            d = decision.get(p, {})
            if p in keep and p != u:
                return p
            if d.get("duplicate_of") in keep and d["duplicate_of"] != u:
                return d["duplicate_of"]
            p = nodes.get(p, {}).get("parent")
        return None

    # ---------- website_tree.json: every URL, with its group
    children = {}
    for u, n in nodes.items():
        children.setdefault(n.get("parent"), []).append(u)

    def tree_node(u, seen):
        d, n = decision.get(u, {}), nodes[u]
        out = {"url": u, "title": n.get("title", ""), "group": cleaner.LABELS.get(d.get("category"), d.get("category")),
               "found_by": n.get("found_by")}
        if d.get("reason"):
            out["reason"] = d["reason"]
        if d.get("duplicate_of"):
            out["duplicate_of"] = d["duplicate_of"]
        if n.get("access"):
            out["access"] = n["access"]
        kids = [k for k in sorted(children.get(u, [])) if host_of(k) == host_of(u) and k in decision and k not in seen]
        seen.update(kids)
        out["children"] = [tree_node(k, seen) for k in kids]
        return out

    def count(tree):
        return sum(1 + count(t["children"]) for t in tree)

    combined = {"generated_at": now, "groups": cleaner.LABELS, "sites": {}, "cross_site_links": []}
    for host in SITES:
        tops = [u for u in decision if host_of(u) == host
                and (not nodes[u].get("parent") or host_of(nodes[u]["parent"]) != host
                     or nodes[u]["parent"] not in decision)]
        home = canonical(f"{base(host)}/")
        tops.sort(key=lambda u: (u != home, u))
        seen = set(tops)
        tree = [tree_node(u, seen) for u in tops]
        combined["sites"][host] = {"pages": count(tree), "tree": tree}
    pairs = set()
    for u in keep:
        for l in (pages[u]["cache"] or {}).get("links", []):
            l = canonical(l)
            l = decision.get(l, {}).get("duplicate_of") or l
            if host_of(l) != host_of(u) and l in keep:
                pairs.add((u, l))
    combined["cross_site_links"] = [{"from": a, "to": b} for a, b in sorted(pairs)]
    save_json(os.path.join(OUT, "website_tree.json"), combined)
    print(f"\nwrote {OUT}/website_tree.json  (every URL with its group)")

    # ---------- report files (always)
    os.makedirs(REPORT_DIR, exist_ok=True)
    rows = []
    for u, d in decision.items():
        n = nodes[u]
        rows.append({"site": host_of(u), "group": d["category"], "group_label": cleaner.LABELS.get(d["category"], d["category"]),
                     "reason": d.get("reason", ""), "url": u, "duplicate_of": d.get("duplicate_of", ""),
                     "title": n.get("title", ""), "words_before": d.get("words_raw", ""),
                     "words_after": d.get("words_clean", ""), "access": n.get("access", ""),
                     "found_by": n.get("found_by", "")})
    site_order = {h: i for i, h in enumerate(SITES)}
    rows.sort(key=lambda r: (site_order.get(r["site"], 99), ORDER.index(r["group"]) if r["group"] in ORDER else 9,
                             r["reason"], r["url"]))
    import csv
    with open(os.path.join(REPORT_DIR, "filter_report.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["url"])
        w.writeheader(); w.writerows(rows)
    summary = {h: {g: sum(1 for r in rows if r["site"] == h and r["group"] == g) for g in ORDER} for h in SITES}
    save_json(os.path.join(REPORT_DIR, "filter_report.json"),
              {"generated_at": now, "groups": cleaner.LABELS, "summary": summary, "pages": rows,
               "boilerplate_removed": {h: [{"text": t[:300], "on_pages": c} for t, c in v] for h, v in removed.items()}})
    with open(os.path.join(REPORT_DIR, "boilerplate_removed.txt"), "w", encoding="utf-8") as f:
        f.write("Text found on most pages of a site and removed from every page (check nothing important is here).\n")
        for h, v in removed.items():
            f.write(f"\n===== {h}: {len(v)} blocks/lines =====\n")
            for t, c in v:
                f.write(f"\n--- on {c} pages ---\n{t[:600]}\n")
    print(f"wrote {REPORT_DIR}/filter_report.csv, filter_report.json, boilerplate_removed.txt")

    if not with_content:
        return
    # ---------- clean data: output/sites/<site>.json (kept pages only, as a tree) + output/pages/
    shutil.rmtree(PAGES_DIR, ignore_errors=True)
    kept_children = {}
    for u in keep:
        kept_children.setdefault(kept_parent(u), []).append(u)

    def page_json(u):
        c, n, d = pages[u]["cache"], nodes[u], decision[u]
        md = d["clean_md"]
        links = set()
        for l in c.get("links", []):
            l = canonical(l)
            l = decision.get(l, {}).get("duplicate_of") or l
            if l in keep and l != u:
                links.add(l)
        also = sorted(x for x, dx in decision.items() if dx.get("duplicate_of") == u)
        return {"url": u, "title": n.get("title", ""), "description": c.get("description"),
                "access": n.get("access", "unknown"), "fetched_at": c.get("fetched_at"),
                "word_count": len(md.split()), "also_found_at": also,
                "sections": sections_from_markdown(md), "full_markdown": md, "files": c.get("files", []),
                "links": sorted(l for l in links if host_of(l) == host_of(u)),
                "links_to_other_echiphub_sites": sorted(l for l in links if host_of(l) != host_of(u)),
                "external_links": c.get("other_site_links", [])}

    def kept_tree(u, placed):
        placed.add(u)
        d = page_json(u)
        kids = [k for k in sorted(kept_children.get(u, [])) if host_of(k) == host_of(u) and k not in placed]
        placed.update(kids)
        d["children"] = [kept_tree(k, placed) for k in kids]
        return d

    for host in SITES:
        mine = [u for u in keep if host_of(u) == host]
        tops = [u for u in mine if kept_parent(u) is None or host_of(kept_parent(u)) != host]
        home = canonical(f"{base(host)}/")
        tops.sort(key=lambda u: (u != home, u))
        placed = set(tops)
        tree = [kept_tree(u, placed) for u in tops]
        for u in sorted(set(mine) - placed):            # safety net: a page in a loop is never lost
            if u not in placed:
                placed.add(u); tree.append(kept_tree(u, placed))
        save_json(os.path.join(OUT, "sites", f"{host}.json"),
                  {"site": host, "platform": SITES[host]["platform"], "generated_at": now,
                   "pages": count(tree), "note": "only real/useful pages; see output/report/ for what was left out",
                   "tree": tree})
        for u in [x for x in keep if host_of(x) == host]:
            doc = page_json(u)
            doc.update(site=host, approved=True)
            save_json(os.path.join(PAGES_DIR, host, page_file_name(u)), doc)
        print(f"wrote {OUT}/sites/{host}.json and {PAGES_DIR}/{host}/  ({len([x for x in keep if host_of(x) == host])} pages)")


# ============================================================== REPORT
def report(state):
    path = os.path.join(REPORT_DIR, "filter_report.json")
    data = load_json(path, None)
    if not data:
        print("No report yet - run 'python extract.py build' first."); return
    rows = data["pages"]
    print("\n================ REPORT ================")
    print(f"\n{'site':24} {'real/useful':>12} {'unwanted':>9} {'duplicate':>10} {'broken':>7} {'not read':>9}")
    for h, c in data["summary"].items():
        print(f"{h:24} {c['keep']:>12} {c['unwanted']:>9} {c['duplicate']:>10} {c['broken']:>7} {c['pending']:>9}")
    for g in ("unwanted", "duplicate", "broken", "pending"):
        mine = [r for r in rows if r["group"] == g]
        if not mine:
            continue
        reasons = {}
        for r in mine:
            key = re.sub(r"\s+", " ", re.sub(r"\(.*?\)|\d+", "", r["reason"])).strip(" -") or r["reason"]
            reasons[key] = reasons.get(key, 0) + 1
        print(f"\n{cleaner.LABELS.get(g, 'Not read yet')} - {len(mine)} links:")
        for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"   {v:4}  {k}")
    broken = [r for r in rows if r["group"] == "broken"]
    if broken:
        print("\nBroken links (tell the website owner):")
        for r in broken[:40]:
            print(f"   {r['url']}   ->  {r['reason']}")
        if len(broken) > 40:
            print(f"   ... and {len(broken) - 40} more in output/report/filter_report.csv")
    print("\nREQUIRED_URLS check:")
    by_url = {r["url"]: r for r in rows}
    missing = 0
    for u in REQUIRED_URLS:
        c = canonical(u); r = by_url.get(c)
        if r and r["group"] == "keep":
            print(f"   OK       {c}")
        elif r and r["group"] == "duplicate" and by_url.get(r["duplicate_of"], {}).get("group") == "keep":
            print(f"   OK       {c}   (kept as {r['duplicate_of']})")
        else:
            missing += 1
            print(f"   MISSING  {c}   ({(r['group'] + ': ' + r['reason']) if r else 'not found'})")
    print(f"\n{'All required pages are in the clean data.' if not missing else f'{missing} required pages are missing - see above.'}")
    print("Clean data:  output/sites/<site>.json   and   output/pages/<site>/*.json  (for load_knowledge.py)")
    print("Details:     output/report/filter_report.csv  (every link, its group and the reason)")


# ================================================================ MAIN
def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in ("run", "login", "discover", "crawl", "build", "report"):
        print(__doc__); return
    fresh = "--fresh" in sys.argv
    if fresh:
        for p in (STATE, os.path.join(OUT, "website_tree.json")):
            if os.path.exists(p): os.remove(p)
        for d in (CACHE, os.path.join(OUT, "sites"), REPORT_DIR, PAGES_DIR):
            shutil.rmtree(d, ignore_errors=True)
    if cmd in ("run", "login"):
        if cmd == "login" or not os.path.exists(SESSION) or input("Use the saved login session? [Y/n] ").strip().lower() == "n":
            login()
        if cmd == "login":
            return
    state = State()
    if cmd in ("run", "discover"):
        seed(state); build(state, with_content=False)
        print("STEP 1 done: every URL found so far is listed in output/website_tree.json")
        if cmd == "discover":
            return
    if cmd in ("run", "crawl"):
        if not state.nodes:
            seed(state)
        asyncio.run(crawl(state))
        check_access(state)
    if cmd in ("run", "crawl", "build"):
        build(state, with_content=True)
    report(state)


if __name__ == "__main__":
    main()
