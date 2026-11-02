import os
import re
import json
import time
import hashlib
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ================= CONFIGURATION =================
EMAIL = "user-testing78@example.com"
PASSWORD = "Password@123"
OUTPUT_DIR = "echiphub"

# Sabhi 8 Targets exact user order me:
# Home -> EdX -> Events -> Workshops -> Helpdesk -> PDK -> Community -> Labs
TARGETS = [
    {
        "name": "Home",
        "url": "https://echiphub.in/",
        "label": "eChipHub Home",
        "output_file": os.path.join(OUTPUT_DIR, "home.json")
    },
    {
        "name": "EdX",
        "url": "https://edx.echiphub.in/",
        "label": "EdX Home",
        "output_file": os.path.join(OUTPUT_DIR, "edx.json")
    },
    {
        "name": "Events",
        "url": "https://events.echiphub.in/",
        "label": "Events Home",
        "output_file": os.path.join(OUTPUT_DIR, "events.json")
    },
    {
        "name": "Workshops",
        "url": "https://echiphub.in/workshops/",
        "label": "Workshops Home",
        "output_file": os.path.join(OUTPUT_DIR, "workshops.json")
    },
    {
        "name": "Helpdesk",
        "url": "https://helpdesk.echiphub.in/keycloaksso",
        "label": "Helpdesk Home",
        "output_file": os.path.join(OUTPUT_DIR, "helpdesk.json")
    },
    {
        "name": "PDK",
        "url": "https://verify.echiphub.in/",
        "label": "PDK Home",
        "output_file": os.path.join(OUTPUT_DIR, "pdk.json")
    },
    {
        "name": "Community",
        "url": "https://community.echiphub.in/auth/oidc?origin=https%3A%2F%2Fcommunity.echiphub.in%2F",
        "label": "Community Home",
        "output_file": os.path.join(OUTPUT_DIR, "community.json")
    },
    {
        "name": "Labs",
        "url": "https://echiphub.in/labs/",
        "label": "Labs Home",
        "output_file": os.path.join(OUTPUT_DIR, "labs.json")
    }
]

# Privacy aur Time-wasting rokne ke liye Blocked URL Patterns
BLOCKED_URL_PATTERNS = [
    "community.echiphub.in/u/",       # User profile pages block (Privacy + spam avoidance)
    "/u/test_78",
]

MAX_DEPTH = 2  
PAGE_DELAY = 2.5  

os.makedirs(OUTPUT_DIR, exist_ok=True)
# =================================================

visited_urls = set()
seen_content_hashes = set()

def format_duration(seconds):
    """Seconds ko clean 'Xm Ys' format me convert karta hai (sub-minute me decimal precision ke sath)"""
    if seconds < 60:
        return f"{round(seconds, 1)}s"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    else:
        return f"{m}m {s}s"

def normalize_url(url):
    """URL ko standardize karta hai (removes www, trailing slash, hash)"""
    if not url:
        return ""
    clean = url.split("#")[0].rstrip("/")
    clean = clean.replace("://www.", "://")
    return clean

def is_safe_url(url):
    """Logout links, static files, blocked patterns aur out-of-domain links ko block karta hai"""
    if not url or url.startswith("javascript:") or url.startswith("mailto:"):
        return False
    url_lower = url.lower()

    # Blocked URL patterns check (User profile privacy & time-wasting prevention)
    for pattern in BLOCKED_URL_PATTERNS:
        if pattern.lower() in url_lower:
            return False

    # Logout aur session-killing links
    if "logout" in url_lower or "wp-login.php" in url_lower or "sign-out" in url_lower:
        return False

    # Binary / Media downloads block
    if any(url_lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".zip", ".tar.gz", ".tgz", ".tar", ".gz", ".7z", ".iso", ".bin"]):
        return False

    parsed = urlparse(url)
    if "echiphub.in" not in parsed.netloc:
        return False
    return True

def scroll_page_top_to_bottom(page):
    """Page ko aaram se upar se neeche tak scroll karta hai taaki dynamic cards render ho jayein"""
    try:
        page.evaluate("""async () => {
            await new Promise((resolve) => {
                let totalHeight = 0;
                let distance = 350;
                let timer = setInterval(() => {
                    let scrollHeight = document.body.scrollHeight;
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 250);
            });
        }""")
        time.sleep(1.5)
        page.evaluate("window.scrollTo(0, 0);")
    except Exception:
        pass

# ================= TARGET SPECIFIC HANDLERS =================

def handle_edx_login(page):
    """
    EdX Specific Login:
    Navbar me 'Sign in' click karein -> apps.edx.echiphub.in/authn/login par 'Keycloak' click karein
    """
    if "edx" not in page.url.lower():
        return

    try:
        # Step 1: Agar edx.echiphub.in par navbar me 'Sign in' button hai
        if "apps.edx" not in page.url:
            nav_signin = page.locator("a:has-text('Sign in'), a:has-text('Log in'), button:has-text('Sign in')")
            if nav_signin.count() > 0 and nav_signin.first.is_visible():
                print("  [*] EdX: Clicking navbar 'Sign in'...")
                nav_signin.first.click()
                time.sleep(2)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass

        # Step 2: apps.edx.echiphub.in/authn/login par 'Or sign in with: Keycloak' button click karein
        keycloak_social_btn = page.locator("button:has-text('Keycloak'), a:has-text('Keycloak'), .social-auth-keycloak, [data-provider='keycloak']")
        if keycloak_social_btn.count() > 0 and keycloak_social_btn.first.is_visible():
            print("  [*] EdX: Clicking 'Or sign in with: Keycloak' button...")
            keycloak_social_btn.first.click()
            time.sleep(2)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass

        # Step 3: Agar Keycloak login prompt open hua toh credentials daalein
        handle_keycloak_login_if_present(page)

    except Exception as e:
        print(f"  [!] EdX login handler notice: {e}")

def handle_workshops_load_more(page):
    """
    Workshops Specific:
    'Live Workshops' aur 'Completed Workshops' ke 'Load More' buttons ko repeatedly click karke
    poora content DOM me load karta hai.
    """
    if "workshops" not in page.url.lower():
        return

    print("  [*] Workshops: Checking tabs and clicking 'Load More' buttons...")

    # 1. Tab switches (Live Workshops, Completed Workshops)
    tab_selectors = [
        "button:has-text('Live Workshops'), a:has-text('Live Workshops'), [data-tab*='live']",
        "button:has-text('Completed Workshops'), a:has-text('Completed Workshops'), [data-tab*='completed']"
    ]
    for tab_sel in tab_selectors:
        try:
            tab = page.locator(tab_sel)
            if tab.count() > 0 and tab.first.is_visible():
                tab.first.click()
                time.sleep(1.5)
        except Exception:
            pass

    # 2. 'Load More' loop
    load_more_selectors = [
        "button:has-text('Load More')",
        "a:has-text('Load More')",
        ".load-more-btn",
        ".load-more",
        "button:has-text('View More')",
        "a:has-text('View More')"
    ]
    max_clicks = 25
    click_count = 0

    while click_count < max_clicks:
        clicked = False
        for selector in load_more_selectors:
            try:
                btn = page.locator(selector)
                if btn.count() > 0:
                    for i in range(btn.count()):
                        target_btn = btn.nth(i)
                        if target_btn.is_visible() and target_btn.is_enabled():
                            btn_text = target_btn.inner_text().strip()
                            print(f"  [*] Workshops: Clicking '{btn_text}' (click #{click_count + 1})...")
                            target_btn.scroll_into_view_if_needed()
                            time.sleep(0.5)
                            target_btn.click()
                            clicked = True
                            click_count += 1
                            time.sleep(2)
                            break
                    if clicked:
                        break
            except Exception:
                pass

        if not clicked:
            if click_count > 0:
                print(f"  [*] Workshops: All items loaded (total clicks: {click_count}).")
            break

def handle_pdk_location_permission(page):
    """
    PDK Specific:
    Location prompt aane par automatically 'Share current location' button click karein
    """
    if "verify.echiphub.in" not in page.url.lower():
        return

    try:
        loc_btn = page.locator("button:has-text('Share current location'), a:has-text('Share current location'), .btn:has-text('Share current location')")
        if loc_btn.count() > 0 and loc_btn.first.is_visible():
            print("  [*] PDK: Clicking 'Share current location' button...")
            loc_btn.first.click()
            time.sleep(3)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            print("  [+] PDK: Location shared successfully!")
    except Exception:
        pass

def expand_discourse_sidebar_if_present(page):
    """
    Community Discourse Specific:
    Left sidebar ko check karein aur 'More' accordion ko click karke /about, /guidelines reveal karein
    """
    if "community.echiphub.in" not in page.url.lower():
        return

    try:
        # Sidebar toggle button agar band ho
        sidebar_toggle = page.locator("button.btn-sidebar-toggle, button.d-header-icons__sidebar-toggle")
        if sidebar_toggle.count() > 0 and sidebar_toggle.first.is_visible():
            if page.locator(".sidebar-wrapper, .d-sidebar").count() == 0 or not page.locator(".sidebar-wrapper, .d-sidebar").first.is_visible():
                print("  [*] Community: Opening hidden Discourse sidebar...")
                sidebar_toggle.first.click()
                time.sleep(1)

        # 'More' accordion expand karein
        more_selectors = [
            ".sidebar-section[data-section-name='more'] button",
            "button.sidebar-section-header-button:has-text('More')",
            ".sidebar-more-section button",
            "button:has-text('More')",
            "summary:has-text('More')"
        ]
        for sel in more_selectors:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                print("  [*] Community: Expanding 'More' accordion in sidebar...")
                loc.first.click()
                time.sleep(1)
                break
    except Exception:
        pass

def handle_keycloak_login_if_present(page):
    """Keycloak login form aane par automated credentials fill karein"""
    email_selector = "input#username, input[name='username'], input[type='email']"
    if page.locator(email_selector).count() > 0 and page.locator(email_selector).first.is_visible():
        print("[*] Keycloak SSO login detected, submitting credentials...")
        page.fill(email_selector, EMAIL)
        time.sleep(1)

        password_selector = "input#password, input[name='password'], input[type='password']"
        if page.locator(password_selector).count() == 0:
            page.locator("input#kc-login, button[type='submit']").click()
            time.sleep(2)

        page.fill(password_selector, PASSWORD)
        time.sleep(1)
        page.locator("input#kc-login, button[type='submit']").click()

        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        time.sleep(3)
        print("[+] Logged in successfully via Keycloak!")

def handle_potential_login_screens(page):
    """Subdomain OAuth / Login redirect buttons handle karein"""
    try:
        btn = page.locator("a[href*='oauth'], a[href*='login'], button#login_submit, a.btn:has-text('Sign in'), a:has-text('Login')")
        if btn.count() > 0 and ("login" in page.url.lower() or "auth" in page.url.lower()):
            btn.first.click()
            time.sleep(2)
    except Exception:
        pass

# ================= CONTENT STRUCTURING =================

def extract_raw_content_and_headings(soup):
    """Headings aur clean text extract karein"""
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    headings = {
        "h1": [h.get_text(strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)],
        "h2": [h.get_text(strip=True) for h in soup.find_all("h2") if h.get_text(strip=True)],
        "h3": [h.get_text(strip=True) for h in soup.find_all("h3") if h.get_text(strip=True)],
        "h4": [h.get_text(strip=True) for h in soup.find_all("h4") if h.get_text(strip=True)],
    }

    body = soup.body if soup.body else soup
    full_text = body.get_text(separator="\n", strip=True)
    return headings, full_text

def structure_into_sections(content, headings_dict):
    """Raw content ko clean heading-wise sections me divide karein (only heading, level, items)"""
    if not content:
        return []

    all_headings = []
    for level in ["h1", "h2", "h3", "h4"]:
        for h in headings_dict.get(level, []):
            clean_h = h.strip()
            if clean_h and clean_h not in [x[0] for x in all_headings]:
                all_headings.append((clean_h, level))

    lines = [l.strip() for l in content.split("\n") if l.strip()]

    positions = []
    matched_indices = set()
    for h_text, level in all_headings:
        for idx, line in enumerate(lines):
            if idx not in matched_indices and (line.lower() == h_text.lower() or h_text.lower() in line.lower()):
                positions.append((idx, h_text, level))
                matched_indices.add(idx)
                break

    positions.sort(key=lambda x: x[0])

    sections = []

    if not positions:
        sections.append({
            "heading": "General Content",
            "level": "body",
            "items": lines
        })
        return sections

    if positions[0][0] > 0:
        preamble = lines[:positions[0][0]]
        sections.append({
            "heading": "Overview / Header Info",
            "level": "intro",
            "items": preamble
        })

    for i in range(len(positions)):
        start_idx, h_text, level = positions[i]
        end_idx = positions[i + 1][0] if i + 1 < len(positions) else len(lines)

        sec_lines = lines[start_idx + 1:end_idx]

        sections.append({
            "heading": h_text,
            "level": level,
            "items": sec_lines
        })

    return sections

# ================= CRAWL LOGIC =================

def crawl_nested(page, url, depth, link_text="Root"):
    """
    2-Layer Deduplication Crawler:
    - Layer 1: Redirected actual URL check
    - Layer 2: Content Hash check (fingerprint)
    """
    if not is_safe_url(url):
        print(f"{'  ' * depth}[*] [BLOCKED] Skipping blocked URL: {url}")
        return None

    norm_url = normalize_url(url)

    if norm_url in visited_urls:
        return None

    visited_urls.add(norm_url)
    indent = "  " * depth
    print(f"\n{indent}► [Depth {depth}] Opening: {url} ({link_text})")
    page_start_time = time.time()

    time.sleep(PAGE_DELAY)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(2)

        # Login checks
        handle_keycloak_login_if_present(page)
        handle_potential_login_screens(page)

        # Target specific login handlers
        handle_edx_login(page)
        handle_pdk_location_permission(page)

        # ---------------- LAYER 1: REDIRECT URL FILTER ----------------
        actual_url = normalize_url(page.url)
        if actual_url != norm_url and actual_url in visited_urls:
            print(f"{indent}  [*] [DEDUPLICATE - Layer 1] Redirected to already visited page ({actual_url}), skipping!")
            return None
        visited_urls.add(actual_url)

        # Target-specific page interactions
        handle_workshops_load_more(page)
        expand_discourse_sidebar_if_present(page)

        print(f"{indent}  [*] Scrolling & rendering full page...")
        scroll_page_top_to_bottom(page)

        html_content = page.content()
    except Exception as e:
        print(f"{indent}  [!] Error loading {url}: {e}")
        return None

    soup = BeautifulSoup(html_content, "lxml")
    page_title = soup.title.string.strip() if soup.title and soup.title.string else "Untitled"

    # Step A: Headings & Raw text
    headings, full_text = extract_raw_content_and_headings(soup)

    # Step B: Heading-wise sections
    structured_sections = structure_into_sections(full_text, headings)

    # ---------------- LAYER 2: CONTENT HASH FILTER ----------------
    page_fingerprint = "".join(item for sec in structured_sections for item in sec.get("items", []))
    if len(page_fingerprint.strip()) > 40:
        content_hash = hashlib.md5(page_fingerprint.encode("utf-8")).hexdigest()
        if content_hash in seen_content_hashes:
            print(f"{indent}  [*] [DEDUPLICATE - Layer 2] Content Hash matched another page, skipping exact duplicate!")
            return None
        seen_content_hashes.add(content_hash)

    page_duration = time.time() - page_start_time
    formatted_page_time = format_duration(page_duration)

    node = {
        "link_text": link_text,
        "url": actual_url,
        "title": page_title,
        "depth": depth,
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "time_taken": formatted_page_time,
        "headings": headings,
        "sections": structured_sections,
        "children": []
    }

    print(f"{indent}  [✓] Page scraped in {formatted_page_time}: {actual_url}")

    # Child links crawl karein
    if depth < MAX_DEPTH:
        child_links = []
        for a_tag in soup.find_all("a", href=True):
            abs_url = urljoin(url, a_tag["href"]).split("#")[0]
            txt = a_tag.get_text(strip=True) or "Link"
            norm_child = normalize_url(abs_url)

            # File download action buttons ko crawl mat karo
            if a_tag.has_attr("download") or "download pdk" in txt.lower():
                continue

            if is_safe_url(abs_url) and norm_child not in visited_urls:
                if not any(normalize_url(c["url"]) == norm_child for c in child_links):
                    child_links.append({"text": txt, "url": abs_url})

        for child in child_links:
            child_node = crawl_nested(page, child["url"], depth + 1, link_text=child["text"])
            if child_node:
                node["children"].append(child_node)

    return node

def save_json(data, output_file):
    """Final output file save karein"""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[✓] Saved structured JSON -> {output_file}")

# ================= MAIN ORCHESTRATOR =================

def main():
    total_start_time = time.time()
    timing_records = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        # 1440x900 viewport + Geolocation permission (for PDK SCL India access)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            permissions=["geolocation"],
            geolocation={"latitude": 28.6139, "longitude": 77.2090} # New Delhi, India
        )
        page = context.new_page()

        # 1. Download event cancel karein (Zero disk files)
        page.on("download", lambda download: (
            print(f"  [*] Blocked file download: {download.suggested_filename}"),
            download.cancel()
        ))

        # 2. Binary archive requests network-level abort
        def block_binary_requests(route, request):
            url_lower = request.url.lower()
            if any(url_lower.endswith(ext) for ext in [".tar.gz", ".tgz", ".zip", ".tar", ".gz", ".7z", ".iso", ".bin"]):
                route.abort()
                return
            route.continue_()

        page.route("**/*", block_binary_requests)

        print(f"\n{'#' * 70}")
        print(f"# eChipHub Master Scraping Pipeline (Total Targets: {len(TARGETS)})")
        print(f"# Sequence: {' -> '.join(t['name'] for t in TARGETS)}")
        print(f"{'#' * 70}")

        for index, target in enumerate(TARGETS, 1):
            target_name = target["name"]
            target_url = target["url"]
            target_label = target["label"]
            output_file = target["output_file"]

            print(f"\n{'=' * 65}")
            print(f"[*] [{index}/{len(TARGETS)}] STARTING TASK: {target_name.upper()}")
            print(f"[*] Target URL : {target_url}")
            print(f"[*] Destination: {output_file}")
            print(f"{'=' * 65}")

            task_start_time = time.time()

            # Target ke liye visited cache reset karein taaki har task independent rahe
            visited_urls.clear()
            seen_content_hashes.clear()

            print(f"[*] Navigating to: {target_url}")
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"  [!] Navigation notice: {e}")
            time.sleep(2)

            # Keycloak SSO Login
            handle_keycloak_login_if_present(page)

            # Target specific login
            if target_name == "EdX":
                handle_edx_login(page)
            elif target_name == "PDK":
                handle_pdk_location_permission(page)

            # Crawl
            print(f"[+] Crawling {target_name}...")
            root_data = crawl_nested(page, target_url, depth=0, link_text=target_label)

            if root_data:
                save_json(root_data, output_file)
                status = "SUCCESS"
            else:
                print(f"[!] Warning: No data returned for {target_name}")
                status = "EMPTY / SKIPPED"

            task_duration = time.time() - task_start_time
            timing_records.append({
                "target": target_name,
                "file": output_file,
                "duration": format_duration(task_duration),
                "status": status
            })

            print(f"[*] Completed {target_name} in {format_duration(task_duration)}")
            time.sleep(2)

        browser.close()

    total_duration = time.time() - total_start_time

    # ================= FINAL TIMING SUMMARY DASHBOARD =================
    print(f"\n\n{'#' * 75}")
    print(f"#              ECHIPHUB MASTER PIPELINE TIMING DASHBOARD             #")
    print(f"{'#' * 75}")
    print(f"{'Target Name':<15} | {'Status':<15} | {'Duration':<12} | {'Output File'}")
    print(f"{'-' * 15}-+-{'-' * 15}-+-{'-' * 12}-+-{'-' * 25}")

    for rec in timing_records:
        print(f"{rec['target']:<15} | {rec['status']:<15} | {rec['duration']:<12} | {rec['file']}")

    print(f"{'-' * 75}")
    print(f"Total Execution Time (Home to Labs): {format_duration(total_duration)} ({round(total_duration, 1)} seconds)")
    print(f"{'#' * 75}\n")

if __name__ == "__main__":
    main()
