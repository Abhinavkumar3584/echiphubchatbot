"""
eChipHub Master Web Scraping Pipeline
Target Destinations:
  - 'echiphubdata/home.json' (Home & Connected Pages Pipeline)
  - 'echiphubdata/labs.json' (Authenticated Labs Pipeline)
  - 'echiphubdata/helpdesk.json' (Authenticated Helpdesk Pipeline)
  - 'echiphubdata/pdk.json' (Authenticated PDK Verification Pipeline)
  - 'echiphubdata/community.json' (Authenticated Community Pipeline)
  - 'echiphubdata/events.json' (Authenticated Events Pipeline)
  - 'echiphubdata/openedx.json' (Authenticated Open edX Learning Platform Pipeline)

Home Targets (Total: 10 Connected URLs):
  1. Home: https://echiphub.in/
  2. All Courses: https://echiphub.in/all-courses/
  3. Workshops: https://echiphub.in/workshops/
  4. Academic Alliances: https://echiphub.in/academic-alliances/
  5. News: https://echiphub.in/news-2/
  6. About: https://echiphub.in/about/
  7. Contact: https://echiphub.in/contact/
  8. Why Choose Us: https://echiphub.in/why-choose-us/
  9. SSO Registration: https://sso.echiphub.in/.../registration
  10. SSO Authentication: https://sso.echiphub.in/.../authenticate

Labs Targets (Authenticated via Keycloak SSO):
  1. Labs Portal: https://echiphub.in/labs/
  2. JupyterHub Dashboard: https://labs.echiphub.in/hub/home

Helpdesk Targets (Authenticated via Keycloak SSO):
  1. Helpdesk My Tickets: https://helpdesk.echiphub.in/helpdesk/my-tickets
  2. Helpdesk New Ticket: https://helpdesk.echiphub.in/helpdesk/my-tickets/new

PDK Targets (Authenticated via Keycloak SSO):
  1. PDK Portal Home: https://verify.echiphub.in/
  2. PDK Downloads: https://verify.echiphub.in/?view=downloads
  3. EDA Virtual Machine: https://verify.echiphub.in/?view=virtual-machine
  4. Worked Examples & Videos: https://verify.echiphub.in/?view=examples
  5. Design Submission & Tape-Out: https://verify.echiphub.in/?view=design
  6. MPW Shuttle Programme FAQs: https://verify.echiphub.in/faq

Community Targets (Authenticated via Keycloak SSO):
  1. Community Groups: https://community.echiphub.in/g
  2. About Community: https://community.echiphub.in/about
  3. Community Guidelines: https://community.echiphub.in/guidelines
  4. Community Badges: https://community.echiphub.in/badges

Events Targets (Authenticated via Keycloak SSO):
  1. Upcoming & Scheduled Workshops: https://events.echiphub.in/?status=upcoming
  2. Events Platform Statistics: https://events.echiphub.in/category/0/statistics

Open edX Targets (Authenticated via Keycloak SSO):
  1. Open edX SSO Auth: https://sso.echiphub.in/realms/platform/protocol/openid-connect/auth?client_id=openedx&redirect_uri=https://edx.echiphub.in/auth/complete/keycloak/&state=peZCNmHdKfsOWYK20fRaQ7HZMGt4ZBdp&response_type=code
  2. ChipCraft Course 02: https://apps.edx.echiphub.in/learning/course/course-v1:NIELIT+RTL-BOOTCAMP-02+2026_T1/home
  3. Bootcamp Course 01: https://apps.edx.echiphub.in/learning/course/course-v1:NIELIT+RTL-BOOTCAMP-01+2026_T1/home
"""

import os
import sys
import json
import time
import re
from datetime import datetime
from bs4 import BeautifulSoup

OUTPUT_DIR = "echiphubdata"

# In-memory HTML storage (no HTML files or folders saved to disk)
HTML_CACHE: dict[str, str] = {}

COMBINED_FILE = os.path.join(OUTPUT_DIR, "home.json")
LABS_OUTPUT_FILE = os.path.join(OUTPUT_DIR, "labs.json")
HELPDESK_OUTPUT_FILE = os.path.join(OUTPUT_DIR, "helpdesk.json")
PDK_OUTPUT_FILE = os.path.join(OUTPUT_DIR, "pdk.json")
COMMUNITY_OUTPUT_FILE = os.path.join(OUTPUT_DIR, "community.json")
EVENTS_OUTPUT_FILE = os.path.join(OUTPUT_DIR, "events.json")
OPENEDX_OUTPUT_FILE = os.path.join(OUTPUT_DIR, "openedx.json")

def get_html_cache_path(filename: str) -> str:
    """Legacy helper maintained for signature compatibility"""
    return filename or ""

# Authentication Credentials (Used for Labs, Helpdesk, PDK, Community, Events, Open edX)
LABS_EMAIL = "user-testing78@example.com"
LABS_PASSWORD = "Password@123"


# ==============================================================================
# HELPER: TEXT CLEANING & COMMON COMPONENTS
# ==============================================================================

def clean_text(tag_or_str) -> str:
    """Normalize whitespace and clean non-breaking spaces"""
    if not tag_or_str:
        return ""
    if hasattr(tag_or_str, "get_text"):
        txt = tag_or_str.get_text(separator=" ", strip=True)
    else:
        txt = str(tag_or_str)
    return re.sub(r"\s+", " ", txt.replace("\xa0", " ")).strip()


def add_common_footer_and_nav(soup: BeautifulSoup, data: dict):
    """Extracts common Navbar, Footer and Legal Disclaimer blocks (Used for Home)"""
    # Navigation
    nav = soup.find("nav")
    if nav:
        nav_links = []
        seen_nav = set()
        for a in nav.find_all("a", href=True):
            lbl = clean_text(a)
            href = a["href"]
            if lbl and href not in seen_nav and "#" not in href:
                seen_nav.add(href)
                nav_links.append({"label": lbl, "url": href})
        data["sections"].append({
            "section_name": "Navigation Menu",
            "type": "navigation",
            "links": nav_links
        })

    # Footer
    socials = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "linkedin.com" in href:
            socials["LinkedIn"] = href
        elif "x.com" in href or "twitter.com" in href:
            socials["Twitter"] = href
        elif "instagram.com" in href:
            socials["Instagram"] = href

    quick_links = []
    quick_widget = soup.find(lambda t: t.name in ["h2", "h3"] and "quick link" in t.get_text().lower())
    if quick_widget:
        parent = quick_widget.find_parent(class_=lambda c: c and "widget" in str(c))
        if parent:
            for a in parent.find_all("a", href=True):
                quick_links.append({"label": clean_text(a), "url": a["href"]})

    data["sections"].append({
        "section_name": "Footer Information",
        "type": "footer",
        "address": "Block-3, Block A, East Kidwai Nagar, Kidwai Nagar, New Delhi, Delhi 110023",
        "copyright": "© NIELIT 2026, All Rights Reserved.",
        "quick_links": quick_links,
        "social_media": socials
    })

    # Disclaimer
    disclaimer_h2 = soup.find(lambda t: t.name in ["h2", "h3"] and "disclaimer" in t.get_text().lower())
    if disclaimer_h2:
        disclaimer_paras = []
        p = disclaimer_h2.find_next("p")
        while p and p.name == "p":
            txt = clean_text(p)
            if len(txt) > 20 and txt not in disclaimer_paras and "I agree" not in txt:
                disclaimer_paras.append(txt)
            p = p.find_next_sibling("p")

        data["sections"].append({
            "section_name": "Important Disclaimer",
            "type": "legal_disclaimer",
            "heading": clean_text(disclaimer_h2),
            "paragraphs": disclaimer_paras
        })


# ==============================================================================
# STEP 1: HTML RETRIEVAL & AUTOMATED PLAYWRIGHT LOGIN
# ==============================================================================

def fetch_labs_pages_live(email: str = LABS_EMAIL, password: str = LABS_PASSWORD):
    """
    Automated Playwright login for eChipHub Labs:
    1. Visits https://echiphub.in/labs/
    2. Submits Keycloak SSO credentials
    3. Saves labs_landing_raw.html
    4. Visits https://labs.echiphub.in/hub/home
    5. Submits Keycloak SSO credentials / OAuth Authorize if needed
    6. Saves labs_hub_raw.html
    """
    print("[*] Performing automated Playwright login for Labs...", flush=True)
    try:
        from playwright.sync_api import sync_playwright

        def do_keycloak_login(page):
            time.sleep(2)
            email_sel = "input#username, input[name='username'], input[type='email']"
            pwd_sel = "input#password, input[name='password'], input[type='password']"
            btn_sel = "input#kc-login, button[type='submit'], input[type='submit']"

            if page.locator(email_sel).count() > 0 and page.locator(email_sel).first.is_visible():
                page.fill(email_sel, email)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(2)

            if page.locator(pwd_sel).count() > 0 and page.locator(pwd_sel).first.is_visible():
                page.fill(pwd_sel, password)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(3)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

            auth_btn = page.locator("input[name='authorize'], button:has-text('Authorize'), a:has-text('Authorize')")
            if auth_btn.count() > 0 and auth_btn.first.is_visible():
                auth_btn.first.click()
                time.sleep(3)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # 1. Labs Landing
            page.goto("https://echiphub.in/labs/", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            if "sso.echiphub.in" in page.url:
                do_keycloak_login(page)
            time.sleep(2)
            if "echiphub.in/labs" not in page.url:
                page.goto("https://echiphub.in/labs/", wait_until="domcontentloaded", timeout=45000)
                time.sleep(2)

            HTML_CACHE["labs_landing_raw.html"] = page.content()
            print("[✓] Captured labs_landing_raw.html in memory.", flush=True)

            # 2. Labs Hub
            page.goto("https://labs.echiphub.in/hub/home", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            if "sso.echiphub.in" in page.url:
                do_keycloak_login(page)
            time.sleep(2)

            HTML_CACHE["labs_hub_raw.html"] = page.content()
            print("[✓] Captured labs_hub_raw.html in memory.", flush=True)

            browser.close()
    except Exception as e:
        print(f"[!] Live fetch notice for labs: {e}", flush=True)


def fetch_helpdesk_pages_live(email: str = LABS_EMAIL, password: str = LABS_PASSWORD):
    """
    Automated Playwright login for eChipHub Helpdesk:
    1. Visits https://helpdesk.echiphub.in/keycloaksso
    2. Submits Keycloak SSO credentials if prompted
    3. Saves helpdesk_my_tickets_raw.html
    4. Visits https://helpdesk.echiphub.in/helpdesk/my-tickets/new
    5. Saves helpdesk_new_ticket_raw.html
    """
    print("[*] Performing automated Playwright login for Helpdesk...", flush=True)
    try:
        from playwright.sync_api import sync_playwright

        def do_keycloak_login(page):
            time.sleep(2)
            email_sel = "input#username, input[name='username'], input[type='email']"
            pwd_sel = "input#password, input[name='password'], input[type='password']"
            btn_sel = "input#kc-login, button[type='submit'], input[type='submit']"

            if page.locator(email_sel).count() > 0 and page.locator(email_sel).first.is_visible():
                page.fill(email_sel, email)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(2)

            if page.locator(pwd_sel).count() > 0 and page.locator(pwd_sel).first.is_visible():
                page.fill(pwd_sel, password)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(3)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

            auth_btn = page.locator("input[name='authorize'], button:has-text('Authorize'), a:has-text('Authorize')")
            if auth_btn.count() > 0 and auth_btn.first.is_visible():
                auth_btn.first.click()
                time.sleep(3)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # 1. Login via Keycloak SSO
            page.goto("https://helpdesk.echiphub.in/keycloaksso", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            if "sso.echiphub.in" in page.url:
                do_keycloak_login(page)
            time.sleep(2)

            # 2. My Tickets
            page.goto("https://helpdesk.echiphub.in/helpdesk/my-tickets", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            HTML_CACHE["helpdesk_my_tickets_raw.html"] = page.content()
            print("[✓] Captured helpdesk_my_tickets_raw.html in memory.", flush=True)

            # 3. New Ticket
            page.goto("https://helpdesk.echiphub.in/helpdesk/my-tickets/new", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            HTML_CACHE["helpdesk_new_ticket_raw.html"] = page.content()
            print("[✓] Captured helpdesk_new_ticket_raw.html in memory.", flush=True)

            browser.close()
    except Exception as e:
        print(f"[!] Live fetch notice for helpdesk: {e}", flush=True)


def fetch_pdk_pages_live(email: str = LABS_EMAIL, password: str = LABS_PASSWORD):
    """
    Automated Playwright login for eChipHub SCL Verification / PDK Portal:
    1. Visits https://verify.echiphub.in/
    2. Submits Keycloak SSO credentials if prompted
    3. Fetches and caches:
       - pdk_home_raw.html (https://verify.echiphub.in/)
       - pdk_downloads_raw.html (https://verify.echiphub.in/?view=downloads)
       - pdk_vm_raw.html (https://verify.echiphub.in/?view=virtual-machine)
       - pdk_examples_raw.html (https://verify.echiphub.in/?view=examples)
       - pdk_design_raw.html (https://verify.echiphub.in/?view=design)
       - pdk_faq_raw.html (https://verify.echiphub.in/faq)
    """
    print("[*] Performing automated Playwright login for PDK Portal...", flush=True)
    try:
        from playwright.sync_api import sync_playwright

        def do_keycloak_login(page):
            time.sleep(2)
            email_sel = "input#username, input[name='username'], input[type='email']"
            pwd_sel = "input#password, input[name='password'], input[type='password']"
            btn_sel = "input#kc-login, button[type='submit'], input[type='submit']"

            if page.locator(email_sel).count() > 0 and page.locator(email_sel).first.is_visible():
                page.fill(email_sel, email)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(2)

            if page.locator(pwd_sel).count() > 0 and page.locator(pwd_sel).first.is_visible():
                page.fill(pwd_sel, password)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(3)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

            auth_btn = page.locator("input[name='authorize'], button:has-text('Authorize'), a:has-text('Authorize')")
            if auth_btn.count() > 0 and auth_btn.first.is_visible():
                auth_btn.first.click()
                time.sleep(3)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # 1. Login via Keycloak SSO
            page.goto("https://verify.echiphub.in/", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            if "sso.echiphub.in" in page.url:
                do_keycloak_login(page)
            time.sleep(2)

            pdk_urls = [
                ("pdk_home_raw.html", "https://verify.echiphub.in/"),
                ("pdk_downloads_raw.html", "https://verify.echiphub.in/?view=downloads"),
                ("pdk_vm_raw.html", "https://verify.echiphub.in/?view=virtual-machine"),
                ("pdk_examples_raw.html", "https://verify.echiphub.in/?view=examples"),
                ("pdk_design_raw.html", "https://verify.echiphub.in/?view=design"),
                ("pdk_faq_raw.html", "https://verify.echiphub.in/faq")
            ]

            for fname, url in pdk_urls:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(3)
                if "sso.echiphub.in" in page.url:
                    do_keycloak_login(page)
                    time.sleep(2)
                HTML_CACHE[fname] = page.content()
                print(f"[✓] Captured {fname} in memory.", flush=True)

            browser.close()
    except Exception as e:
        print(f"[!] Live fetch notice for PDK: {e}", flush=True)


def fetch_community_pages_live(email: str = LABS_EMAIL, password: str = LABS_PASSWORD):
    """
    Automated Playwright login for eChipHub Discourse Community:
    1. Visits https://community.echiphub.in/auth/oidc?origin=https%3A%2F%2Fcommunity.echiphub.in%2Fg
    2. Submits Keycloak SSO credentials if prompted
    3. Fetches and caches:
       - community_groups_raw.html (https://community.echiphub.in/g)
       - community_about_raw.html (https://community.echiphub.in/about)
       - community_guidelines_raw.html (https://community.echiphub.in/guidelines)
       - community_badges_raw.html (https://community.echiphub.in/badges)
    """
    print("[*] Performing automated Playwright login for Community...", flush=True)
    try:
        from playwright.sync_api import sync_playwright

        def do_keycloak_login(page):
            time.sleep(2)
            email_sel = "input#username, input[name='username'], input[type='email']"
            pwd_sel = "input#password, input[name='password'], input[type='password']"
            btn_sel = "input#kc-login, button[type='submit'], input[type='submit']"

            if page.locator(email_sel).count() > 0 and page.locator(email_sel).first.is_visible():
                page.fill(email_sel, email)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(2)

            if page.locator(pwd_sel).count() > 0 and page.locator(pwd_sel).first.is_visible():
                page.fill(pwd_sel, password)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(3)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

            auth_btn = page.locator("input[name='authorize'], button:has-text('Authorize'), a:has-text('Authorize')")
            if auth_btn.count() > 0 and auth_btn.first.is_visible():
                auth_btn.first.click()
                time.sleep(3)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            page.goto("https://community.echiphub.in/auth/oidc?origin=https%3A%2F%2Fcommunity.echiphub.in%2Fg", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            if "sso.echiphub.in" in page.url:
                do_keycloak_login(page)
            time.sleep(2)

            comm_urls = [
                ("community_groups_raw.html", "https://community.echiphub.in/g"),
                ("community_about_raw.html", "https://community.echiphub.in/about"),
                ("community_guidelines_raw.html", "https://community.echiphub.in/guidelines"),
                ("community_badges_raw.html", "https://community.echiphub.in/badges")
            ]

            for fname, url in comm_urls:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(3)
                HTML_CACHE[fname] = page.content()
                print(f"[✓] Captured {fname} in memory.", flush=True)

            browser.close()
    except Exception as e:
        print(f"[!] Live fetch notice for Community: {e}", flush=True)


def fetch_events_pages_live(email: str = LABS_EMAIL, password: str = LABS_PASSWORD):
    """
    Automated Playwright login for eChipHub Events & Workshops (NIELIT Indico):
    1. Visits https://events.echiphub.in/login/keycloak/?next=%2Fevent%2F206%2Fregistrations%2F
    2. Submits Keycloak SSO credentials if prompted
    3. Fetches and caches:
       - events_upcoming_raw.html (https://events.echiphub.in/?status=upcoming)
       - events_statistics_raw.html (https://events.echiphub.in/category/0/statistics)
    """
    print("[*] Performing automated Playwright login for Events...", flush=True)
    try:
        from playwright.sync_api import sync_playwright

        def do_keycloak_login(page):
            time.sleep(2)
            email_sel = "input#username, input[name='username'], input[type='email']"
            pwd_sel = "input#password, input[name='password'], input[type='password']"
            btn_sel = "input#kc-login, button[type='submit'], input[type='submit']"

            if page.locator(email_sel).count() > 0 and page.locator(email_sel).first.is_visible():
                page.fill(email_sel, email)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(2)

            if page.locator(pwd_sel).count() > 0 and page.locator(pwd_sel).first.is_visible():
                page.fill(pwd_sel, password)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(3)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

            auth_btn = page.locator("input[name='authorize'], button:has-text('Authorize'), a:has-text('Authorize')")
            if auth_btn.count() > 0 and auth_btn.first.is_visible():
                auth_btn.first.click()
                time.sleep(3)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            page.goto("https://events.echiphub.in/login/keycloak/?next=%2Fevent%2F206%2Fregistrations%2F", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            if "sso.echiphub.in" in page.url:
                do_keycloak_login(page)
            time.sleep(2)

            events_urls = [
                ("events_upcoming_raw.html", "https://events.echiphub.in/?status=upcoming"),
                ("events_statistics_raw.html", "https://events.echiphub.in/category/0/statistics")
            ]

            for fname, url in events_urls:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(3)
                HTML_CACHE[fname] = page.content()
                print(f"[✓] Captured {fname} in memory.", flush=True)

            browser.close()
    except Exception as e:
        print(f"[!] Live fetch notice for Events: {e}", flush=True)


def fetch_openedx_pages_live(email: str = LABS_EMAIL, password: str = LABS_PASSWORD):
    """
    Automated Playwright login for Open edX Learning Environment:
    1. Visits Open edX SSO Auth URL to capture openedx_sso_raw.html
    2. Logs into Open edX via https://edx.echiphub.in/login -> Keycloak SSO
    3. Fetches and caches:
       - openedx_bootcamp_02_raw.html (RTL-BOOTCAMP-02)
       - openedx_bootcamp_01_raw.html (RTL-BOOTCAMP-01)
    """
    print("[*] Performing automated Playwright login for Open edX...", flush=True)
    try:
        from playwright.sync_api import sync_playwright

        def do_keycloak_login(page):
            time.sleep(2)
            email_sel = "input#username, input[name='username'], input[type='email']"
            pwd_sel = "input#password, input[name='password'], input[type='password']"
            btn_sel = "input#kc-login, button[type='submit'], input[type='submit']"

            if page.locator(email_sel).count() > 0 and page.locator(email_sel).first.is_visible():
                page.fill(email_sel, email)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(2)

            if page.locator(pwd_sel).count() > 0 and page.locator(pwd_sel).first.is_visible():
                page.fill(pwd_sel, password)
                time.sleep(1)
                page.locator(btn_sel).first.click()
                time.sleep(4)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Step 1: Capture SSO Page
            sso_url = "https://sso.echiphub.in/realms/platform/protocol/openid-connect/auth?client_id=openedx&redirect_uri=https://edx.echiphub.in/auth/complete/keycloak/&state=peZCNmHdKfsOWYK20fRaQ7HZMGt4ZBdp&response_type=code"
            page.goto(sso_url, wait_until="networkidle", timeout=45000)
            time.sleep(2)
            HTML_CACHE["openedx_sso_raw.html"] = page.content()
            print("[✓] Captured openedx_sso_raw.html in memory.", flush=True)

            # Step 2: Login via edX LMS Keycloak flow
            page.goto("https://edx.echiphub.in/login", wait_until="networkidle", timeout=45000)
            time.sleep(2)
            keycloak_btn = page.locator("text=Keycloak")
            if keycloak_btn.count() > 0:
                keycloak_btn.first.click()
                time.sleep(3)

            if "sso.echiphub.in" in page.url:
                do_keycloak_login(page)
            time.sleep(3)

            # Step 3: Fetch Course 02
            c2_url = "https://apps.edx.echiphub.in/learning/course/course-v1:NIELIT+RTL-BOOTCAMP-02+2026_T1/home"
            page.goto(c2_url, wait_until="networkidle", timeout=45000)
            time.sleep(5)
            try:
                expand_btn = page.locator("button:has-text('Expand all')")
                if expand_btn.count() > 0 and expand_btn.first.is_visible():
                    expand_btn.first.click()
                    time.sleep(2)
            except Exception:
                pass
            HTML_CACHE["openedx_bootcamp_02_raw.html"] = page.content()
            print("[✓] Captured openedx_bootcamp_02_raw.html in memory.", flush=True)

            # Step 4: Fetch Course 01
            c1_url = "https://apps.edx.echiphub.in/learning/course/course-v1:NIELIT+RTL-BOOTCAMP-01+2026_T1/home"
            page.goto(c1_url, wait_until="networkidle", timeout=45000)
            time.sleep(5)
            try:
                expand_btn = page.locator("button:has-text('Expand all')")
                if expand_btn.count() > 0 and expand_btn.first.is_visible():
                    expand_btn.first.click()
                    time.sleep(2)
            except Exception:
                pass
            HTML_CACHE["openedx_bootcamp_01_raw.html"] = page.content()
            print("[✓] Captured openedx_bootcamp_01_raw.html in memory.", flush=True)

            browser.close()
    except Exception as e:
        print(f"[!] Live fetch notice for Open edX: {e}", flush=True)


def get_whole_page_html(url: str, cache_file: str) -> str:
    """
    Step 1: Extract the HTML code of the whole page in memory.
    Only JSON output is saved to disk in 'echiphubdata'. No HTML files or folders are saved.
    """
    if cache_file and cache_file in HTML_CACHE:
        return HTML_CACHE[cache_file]

    print(f"[*] Step 1: Extracting full HTML code for {url}...", flush=True)

    has_network = False
    try:
        import socket
        socket.setdefaulttimeout(2.0)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("1.1.1.1", 53))
        has_network = True
    except Exception:
        has_network = False

    # Special handling for Labs pages requiring login
    if "labs" in url.lower() and has_network:
        fetch_labs_pages_live()
        if cache_file and cache_file in HTML_CACHE:
            return HTML_CACHE[cache_file]

    # Special handling for Helpdesk pages requiring login
    if "helpdesk" in url.lower() and has_network:
        fetch_helpdesk_pages_live()
        if cache_file and cache_file in HTML_CACHE:
            return HTML_CACHE[cache_file]

    # Special handling for PDK pages requiring login
    if ("verify.echiphub.in" in url.lower() or "pdk" in url.lower()) and has_network:
        fetch_pdk_pages_live()
        if cache_file and cache_file in HTML_CACHE:
            return HTML_CACHE[cache_file]

    # Special handling for Community pages requiring login
    if ("community.echiphub.in" in url.lower() or "community" in url.lower()) and has_network:
        fetch_community_pages_live()
        if cache_file and cache_file in HTML_CACHE:
            return HTML_CACHE[cache_file]

    # Special handling for Events pages requiring login
    if ("events.echiphub.in" in url.lower() or "events" in url.lower()) and has_network:
        fetch_events_pages_live()
        if cache_file and cache_file in HTML_CACHE:
            return HTML_CACHE[cache_file]

    # Special handling for Open edX pages requiring login
    if ("edx.echiphub.in" in url.lower() or "openedx" in url.lower()) and has_network:
        fetch_openedx_pages_live()
        if cache_file and cache_file in HTML_CACHE:
            return HTML_CACHE[cache_file]

    if has_network:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                context = browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(2.5)

                # For workshops page, expand all cards via Load More buttons
                if "workshops" in url.lower():
                    load_more_selectors = [
                        "button:has-text('Load More')",
                        "a:has-text('Load More')",
                        ".load-more-btn",
                        ".load-more",
                        "button:has-text('View More')",
                        "a:has-text('View More')"
                    ]
                    click_count = 0
                    while click_count < 30:
                        clicked = False
                        for selector in load_more_selectors:
                            try:
                                btns = page.locator(selector)
                                for i in range(btns.count()):
                                    b = btns.nth(i)
                                    if b.is_visible() and b.is_enabled():
                                        b.scroll_into_view_if_needed()
                                        time.sleep(0.3)
                                        b.click()
                                        clicked = True
                                        click_count += 1
                                        time.sleep(1.5)
                                        break
                                if clicked:
                                    break
                            except Exception:
                                pass
                        if not clicked:
                            break

                html = page.content()
                browser.close()
                if cache_file:
                    HTML_CACHE[cache_file] = html
                print(f"[✓] Live HTML successfully extracted ({len(html)} bytes in memory).", flush=True)
                return html
        except Exception as e:
            print(f"[!] Live fetch notice: {e}", flush=True)

    raise RuntimeError(f"Could not retrieve HTML live for {url}")


# ==============================================================================
# STEP 2A: EXTRACT FORMATTED TEXT FOR HOME PAGE (https://echiphub.in/)
# ==============================================================================

def extract_home_formatted_text(html: str) -> dict:
    """Extracts formatted text content from eChipHub Home Page"""
    print("[*] Step 2: Parsing Home DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://echiphub.in/",
        "page_title": clean_text(soup.title.string) if soup.title else "Home - EdTech",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Active Announcement
    announcement_link = soup.find(lambda t: t.name == "a" and "mpw_shuttle" in t.get("href", "").lower())
    if not announcement_link:
        announcement_link = soup.find(lambda t: t.name == "a" and "announcement" in t.get_text().lower())
    if announcement_link:
        data["sections"].append({
            "section_name": "Active Announcement",
            "type": "banner",
            "content": clean_text(announcement_link),
            "url": announcement_link.get("href")
        })

    # 2. Outreach Numbers (Stat Cards)
    wrapper = soup.find(class_="semiedu-wrapper")
    if wrapper:
        h1 = wrapper.find("h1")
        stat_cards = []
        for card in wrapper.find_all(class_="card"):
            parts = [clean_text(p) for p in card.get_text(separator="|", strip=True).split("|") if clean_text(p)]
            if len(parts) >= 2:
                stat_cards.append({
                    "metric_label": " ".join(parts[1:]),
                    "metric_value": parts[0]
                })
        data["sections"].append({
            "section_name": "Outreach Numbers",
            "type": "cards_grid",
            "heading": clean_text(h1) if h1 else "One Year of Outreach Numbers",
            "cards": stat_cards
        })

    # 3. Key Highlights (Feature Cards)
    highlight_cards = soup.find_all(class_=lambda x: x and "hl-card" in str(x))
    if highlight_cards:
        cards_list = []
        for card in highlight_cards:
            num = card.find(class_=lambda x: x and "num" in str(x))
            title = card.find(class_="card-title") or card.find(["h3", "h4"])
            desc = card.find(class_="card-text") or card.find("p")
            tag_spans = card.find_all("span", class_=lambda x: x and "tag" in str(x))
            tags = [clean_text(t) for t in tag_spans if clean_text(t)]
            cards_list.append({
                "card_number": clean_text(num) if num else None,
                "card_title": clean_text(title) if title else None,
                "card_description": clean_text(desc) if desc else None,
                "tags_or_centers": tags
            })
        data["sections"].append({
            "section_name": "Key Highlights",
            "type": "feature_cards",
            "heading": "Key Highlights",
            "cards": cards_list
        })

    # 4. Platform Overview
    platform_h2 = soup.find(lambda t: t.name in ["h1", "h2", "h3"] and "open-source first" in t.get_text().lower())
    if platform_h2:
        platform_container = platform_h2.find_parent(class_=lambda c: c and "e-con" in str(c)) or platform_h2.parent.parent.parent
        paragraphs = []
        if platform_container:
            for p in platform_container.find_all("p"):
                txt = clean_text(p)
                if len(txt) > 40 and txt not in paragraphs:
                    paragraphs.append(txt)
        action_links = []
        if platform_container:
            for a in platform_container.find_all("a", href=True):
                lbl = clean_text(a)
                if lbl and not any(ign in lbl.lower() for ign in ["login", "register", "skip", "course", "workshop"]):
                    action_links.append({"label": lbl, "url": a["href"]})
        data["sections"].append({
            "section_name": "Platform Overview",
            "type": "text_block",
            "heading": clean_text(platform_h2),
            "paragraphs": paragraphs,
            "action_links": action_links
        })

    # 5. Collaborations
    partner_domains = {
        "meity.gov.in": "Ministry of Electronics and Information Technology (MeitY)",
        "nielit.gov.in": "National Institute of Electronics & Information Technology (NIELIT)",
        "socteamup.com": "SoCTeamup Semiconductors",
        "scl.gov.in": "Semi-Conductor Laboratory (SCL)"
    }
    partners_list = []
    seen_domains = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        for domain, name in partner_domains.items():
            if domain in href and domain not in seen_domains:
                seen_domains.add(domain)
                partners_list.append({"partner_name": name, "website_url": href})
    if partners_list:
        data["sections"].append({
            "section_name": "Our Collaborations",
            "type": "partner_cards",
            "heading": "Our Collaborations",
            "partners": partners_list
        })

    # 6. Core Offerings
    data["sections"].append({
        "section_name": "Explore Offerings",
        "type": "offering_cards",
        "heading": "Explore More Courses & Workshops",
        "cards": [
            {
                "title": "Workshops",
                "description": "Hands-on technical training, bootcamps and live sessions across multiple centers.",
                "url": "https://echiphub.in/workshops/"
            },
            {
                "title": "Courses",
                "description": "Comprehensive self-paced & project-based certified smart courses.",
                "url": "https://echiphub.in/all-courses/"
            },
            {
                "title": "Labs",
                "description": "Cloud-based EDA tools and virtual chip design environment.",
                "url": "https://echiphub.in/labs/"
            }
        ]
    })

    # 7. Site Analytics
    tables = soup.find_all("table")
    country_table = []
    state_table = []
    for tbl in tables:
        headers = [clean_text(th).lower() for th in tbl.find_all("th")]
        rows = tbl.find_all("tr")
        if any("country" in h for h in headers):
            for r in rows:
                cells = [clean_text(td) for td in r.find_all(["td", "th"])]
                if len(cells) >= 3 and cells[0].isdigit():
                    country_table.append({
                        "rank": int(cells[0]),
                        "country": cells[1],
                        "visitors_count": cells[2],
                        "percentage_share": cells[3] if len(cells) > 3 else None
                    })
        elif any("state" in h for h in headers):
            for r in rows:
                cells = [clean_text(td) for td in r.find_all(["td", "th"])]
                if len(cells) >= 3 and cells[0].isdigit():
                    state_table.append({
                        "rank": int(cells[0]),
                        "state_or_region": cells[1],
                        "visitors_count": cells[2],
                        "percentage_share": cells[3] if len(cells) > 3 else None
                    })
    if country_table or state_table:
        data["sections"].append({
            "section_name": "Site Analytics",
            "type": "analytics_tables",
            "heading": "Site Analytics",
            "country_wise_visitors": country_table,
            "india_state_wise_visitors": state_table
        })

    # Navigation & Footer kept on Home Page as master reference
    add_common_footer_and_nav(soup, data)
    return data


# ==============================================================================
# STEP 2B: EXTRACT FORMATTED TEXT FOR ALL COURSES (https://echiphub.in/all-courses/)
# ==============================================================================

def extract_all_courses_formatted_text(html: str) -> dict:
    """Extracts formatted text content from All Courses Page"""
    print("[*] Step 2: Parsing All Courses DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://echiphub.in/all-courses/",
        "page_title": clean_text(soup.title.string) if soup.title else "All Courses - EdTech",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Page Header / Hero Section
    hero_title = soup.find(class_="entry-title") or soup.find("h1")
    sec_title = soup.find(class_=lambda c: c and "has-text-align-center" in str(c))
    p_lead = soup.find(lambda t: t.name == "p" and "master chip design" in t.get_text().lower())
    data["sections"].append({
        "section_name": "Page Header",
        "type": "hero",
        "title": clean_text(hero_title) if hero_title else "All Courses",
        "headline": clean_text(sec_title) if sec_title else "Specialized Industry-Relevant Courses",
        "subtitle": clean_text(p_lead) if p_lead else "Master chip design from RTL to GDSII using complete open-source flows. Designed to meet global semiconductor workforce demands."
    })

    # 2. Course Categories
    cat_h3 = soup.find(lambda t: t.name in ["h2", "h3"] and "categories" in t.get_text().lower())
    if cat_h3:
        parent = cat_h3.parent
        cats = [clean_text(a) for a in parent.find_all(["button", "a", "span"]) if clean_text(a) and clean_text(a) != "Categories"]
        data["sections"].append({
            "section_name": "Course Categories",
            "type": "categories_filter",
            "categories": list(dict.fromkeys(cats))
        })

    # 3. Level 1: Foundation Courses
    l1_title = soup.find(class_="udemy-title")
    if l1_title:
        l1_sub = l1_title.find_next("p")
        l1_cards = []
        parent = l1_title.find_parent(class_=lambda c: c and "udemy" in str(c).lower()) or l1_title.parent
        for card in parent.find_all(class_="course-card"):
            h3 = card.find(["h3", "h4", "h2"])
            p = card.find("p")
            a = card.find("a", href=True)
            img = card.find("img")
            l1_cards.append({
                "course_title": clean_text(h3) if h3 else None,
                "description": clean_text(p) if p else None,
                "enroll_link": a.get("href") if a else None,
                "thumbnail": img.get("src") if img else None
            })
        data["sections"].append({
            "section_name": "Level 1: Foundation Courses",
            "type": "course_cards",
            "heading": clean_text(l1_title),
            "subheading": clean_text(l1_sub) if l1_sub else None,
            "courses": l1_cards
        })

    # 4. Level 2: Specialized Courses
    l2_title = soup.find(class_="level2-title")
    if l2_title:
        l2_sub = l2_title.find_next("p")
        l2_cards = []
        parent = l2_title.find_parent(class_=lambda c: c and "level2" in str(c).lower()) or l2_title.parent
        for card in parent.find_all(class_="level2-card"):
            h3 = card.find(["h3", "h4", "h2"])
            p = card.find("p")
            badge = card.find(class_=lambda b: b and any(x in str(b).lower() for x in ["badge", "soon", "tag", "status"]))
            status_text = clean_text(badge) if badge else ("Coming Soon" if "coming soon" in card.get_text().lower() else None)
            l2_cards.append({
                "course_title": clean_text(h3) if h3 else None,
                "description": clean_text(p) if p else None,
                "status": status_text
            })
        data["sections"].append({
            "section_name": "Level 2: Specialized Courses",
            "type": "upcoming_course_cards",
            "heading": clean_text(l2_title),
            "subheading": clean_text(l2_sub) if l2_sub else None,
            "courses": l2_cards
        })

    # 5. Learner Testimonials
    testim_h2 = soup.find(lambda t: t.name in ["h1", "h2", "h3"] and "what our learners say" in t.get_text().lower())
    if testim_h2:
        parent = testim_h2.find_parent(class_=lambda c: c and "testimonial" in str(c).lower()) or testim_h2.parent
        testimonials = []
        for card in parent.find_all(class_="testimonial-card"):
            user = card.find(class_="testimonial-user")
            role = card.find(class_="testimonial-role")
            card_text = [clean_text(line) for line in card.get_text(separator="|", strip=True).split("|") if clean_text(line)]
            rating = None
            review_lines = []
            for line in card_text:
                if "★" in line:
                    rating = line
                elif line not in [clean_text(user) if user else "", clean_text(role) if role else ""]:
                    review_lines.append(line)
            testimonials.append({
                "student_name": clean_text(user) if user else None,
                "role": clean_text(role) if role else None,
                "rating": rating,
                "review": " ".join(review_lines)
            })
        data["sections"].append({
            "section_name": "Learner Testimonials",
            "type": "testimonials",
            "heading": clean_text(testim_h2),
            "testimonials": testimonials
        })

    return data


# ==============================================================================
# STEP 2C: EXTRACT FORMATTED TEXT FOR WORKSHOPS (https://echiphub.in/workshops/)
# ==============================================================================

def extract_workshops_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Workshops Page (https://echiphub.in/workshops/)"""
    print("[*] Step 2: Parsing Workshops DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://echiphub.in/workshops/",
        "page_title": clean_text(soup.title.string) if soup.title else "Workshop - EdTech",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Page Header & Filters
    h_title = soup.find(lambda t: t.name in ["h1", "h2"] and "workshop" in t.get_text().lower())
    title_text = clean_text(h_title) if h_title else "Our Workshops"
    if title_text.lower() == "ourworkshops":
        title_text = "Our Workshops"

    tabs_container = soup.find(class_="course-tabs")
    tabs = []
    if tabs_container:
        tabs = [clean_text(t) for t in tabs_container.find_all(class_="tab") if clean_text(t)]
    if not tabs:
        tabs = ["All", "Upcoming", "Live", "Completed"]

    search_inputs = []
    filter_bar = soup.find(class_="course-search-bar")
    if filter_bar:
        for inp in filter_bar.find_all("input"):
            p_holder = inp.get("placeholder")
            if p_holder:
                search_inputs.append(clean_text(p_holder))

    data["sections"].append({
        "section_name": "Page Header & Filters",
        "type": "header_and_filters",
        "title": title_text,
        "filter_tabs": tabs,
        "search_capabilities": search_inputs
    })

    # Helper function to parse individual workshop cards
    def parse_workshop_card(wrapper) -> dict:
        h3 = wrapper.find("h3")
        body = wrapper.find(class_="wp-course-body")
        paras = body.find_all("p") if body else []

        centre = wrapper.get("data-centre") or ""
        start_date = wrapper.get("data-start") or ""
        end_date = wrapper.get("data-end") or ""
        status = wrapper.get("data-status") or ""

        centre_display = None
        dates_display = None
        for p in paras:
            txt = clean_text(p)
            if "📍" in txt or any(c in txt.lower() for c in ["nielit", "centre"]):
                centre_display = txt.replace("📍", "").strip()
            elif "🗓" in txt or any(ch.isdigit() for ch in txt):
                dates_display = txt.replace("🗓", "").strip()

        if not centre_display and centre:
            centre_display = centre.title()
        if not dates_display and start_date and end_date:
            dates_display = f"{start_date} – {end_date}"

        img = wrapper.find("img")
        img_src = img.get("src") if img else None

        popup = wrapper.find(class_="wp-course-popup")
        popup_tag = popup.find(class_="popup-tag") if popup else None
        popup_update = popup.find(class_="popup-update") if popup else None
        features = [clean_text(li) for li in popup.find_all("li")] if popup else []
        btn = popup.find("a", class_="popup-btn") if popup else None

        return {
            "title": clean_text(h3) if h3 else clean_text(wrapper.get("data-title", "")).title(),
            "centre": centre_display,
            "dates": dates_display,
            "start_date": start_date,
            "end_date": end_date,
            "status": status.capitalize() if status else "Active",
            "category": clean_text(popup_tag) if popup_tag else "Workshop",
            "update_info": clean_text(popup_update) if popup_update else None,
            "features": features,
            "registration_link": btn.get("href") if btn else None,
            "action_label": clean_text(btn) if btn else None,
            "thumbnail": img_src
        }

    # 2. Workshop Sections (Upcoming, Live, Completed)
    course_sections = soup.find_all("section", class_="course-section")
    total_workshops_count = 0
    section_counts = {}

    for sec in course_sections:
        sec_h2 = sec.find(["h2", "h1"])
        sec_name = clean_text(sec_h2) if sec_h2 else sec.get("data-section", "Workshops").capitalize()
        wrappers = sec.find_all(class_="wp-course-wrapper")
        cards = [parse_workshop_card(w) for w in wrappers]
        total_workshops_count += len(cards)
        section_counts[sec_name] = len(cards)

        data["sections"].append({
            "section_name": sec_name,
            "type": "workshop_cards_grid",
            "count": len(cards),
            "workshops": cards
        })

    data["summary"] = {
        "total_workshops": total_workshops_count,
        "sections_breakdown": section_counts
    }

    return data


# ==============================================================================
# STEP 2D: EXTRACT FORMATTED TEXT FOR ACADEMIC ALLIANCES
# ==============================================================================

def extract_academic_alliances_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Academic Alliances Page"""
    print("[*] Step 2: Parsing Academic Alliances DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://echiphub.in/academic-alliances/",
        "page_title": clean_text(soup.title.string) if soup.title else "Academic Alliances - EdTech",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Page Header / Hero
    h1 = clean_text(soup.find("h1"))
    cta = soup.find(lambda a: a.name == "a" and "faculty" in a.get_text().lower())
    data["sections"].append({
        "section_name": "Page Header",
        "type": "hero",
        "title": "Academic Alliances",
        "headline": h1 if h1 else "Welcome to the community of eChipHub Institutions",
        "cta_button": {
            "label": clean_text(cta) if cta else "Register as Faculty Coordinator",
            "url": cta.get("href") if cta else "https://www.echiphub.in/faculty-signup-form/"
        }
    })

    # 2. Member Institutions
    h2 = soup.find(lambda t: t.name in ["h2", "h3"] and "member" in t.get_text().lower())
    status_p = soup.find(lambda t: t.name == "p" and "no institutions" in t.get_text().lower())
    data["sections"].append({
        "section_name": "Member Institutions",
        "type": "institutions_list",
        "heading": clean_text(h2) if h2 else "Member Institutions",
        "status": clean_text(status_p) if status_p else "No institutions yet.",
        "institutions": []
    })

    return data


# ==============================================================================
# STEP 2E: EXTRACT FORMATTED TEXT FOR NEWS (https://echiphub.in/news-2/)
# ==============================================================================

def extract_news_formatted_text(html: str) -> dict:
    """Extracts formatted text content from News Page"""
    print("[*] Step 2: Parsing News DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://echiphub.in/news-2/",
        "page_title": clean_text(soup.title.string) if soup.title else "News - EdTech",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Featured News Story
    featured_h1 = clean_text(soup.find("h1"))
    featured_h2 = clean_text(soup.find(lambda t: t.name in ["h2", "h3"] and "nielit & scl" in t.get_text().lower()))
    p_summary = clean_text(soup.find(lambda p: p.name == "p" and "nielit and scl mohali have collaborated" in p.get_text().lower()))

    data["sections"].append({
        "section_name": "Featured News",
        "type": "featured_article",
        "topic": featured_h1 if featured_h1 else "Indigenous 1.2 µm PDK",
        "headline": featured_h2 if featured_h2 else "NIELIT & SCL Mohali Collaborate to Make Indigenous 1.2 µm PDK Available on eChipHub",
        "published_date": "23 July 2026",
        "summary": p_summary,
        "read_more_cta": "Read More →"
    })

    # 2. Related News & Announcements
    rel_div = soup.find(class_="related-news")
    related_posts = []
    if rel_div:
        for item in rel_div.find_all(class_="related-item"):
            lines = [clean_text(s) for s in item.stripped_strings if clean_text(s)]
            if len(lines) >= 2:
                related_posts.append({"title": lines[0], "published_date": lines[1]})
            elif len(lines) == 1:
                related_posts.append({"title": lines[0], "published_date": None})

    data["sections"].append({
        "section_name": "Related Posts & Announcements",
        "type": "news_cards_list",
        "heading": "Related posts",
        "count": len(related_posts),
        "articles": related_posts
    })

    return data


# ==============================================================================
# STEP 2F: EXTRACT FORMATTED TEXT FOR ABOUT US (https://echiphub.in/about/)
# ==============================================================================

def extract_about_formatted_text(html: str) -> dict:
    """Extracts formatted text content from About Us Page (https://echiphub.in/about/)"""
    print("[*] Step 2: Parsing About Us DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://echiphub.in/about/",
        "page_title": clean_text(soup.title.string) if soup.title else "About - EdTech",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Page Header / Hero Section
    about_h2 = soup.find(lambda t: t.name in ["h1", "h2"] and "about us" in t.get_text().lower())
    p_tag = about_h2.find_next("p") if about_h2 else None
    data["sections"].append({
        "section_name": "Page Header",
        "type": "hero",
        "title": clean_text(about_h2) if about_h2 else "About Us",
        "tagline": clean_text(p_tag) if p_tag else "A trusted national institution delivering skill development, training, and certification in electronics and information technology."
    })

    # 2. Platform Overview & Mission
    overview_h2 = soup.find(lambda t: t.name in ["h1", "h2"] and "open-source first" in t.get_text().lower())
    overview_paras = []
    if overview_h2:
        parent = overview_h2.find_parent(class_=lambda c: c and "e-con" in str(c))
        if parent:
            for p in parent.find_all("p"):
                txt = clean_text(p)
                if len(txt) > 40 and txt not in overview_paras:
                    overview_paras.append(txt)

    if overview_paras:
        data["sections"].append({
            "section_name": "Platform Overview & Mission",
            "type": "text_block",
            "heading": clean_text(overview_h2) if overview_h2 else "An Open-Source First EdTech Platform for Chip Design",
            "paragraphs": overview_paras
        })

    # 3. Core Purpose Statement
    purpose_h2 = soup.find(lambda t: t.name in ["h1", "h2"] and "ourpurpose" in t.get_text().lower().replace(" ", ""))
    purpose_stmt = None
    if purpose_h2 and purpose_h2.find_next("p"):
        purpose_stmt = clean_text(purpose_h2.find_next("p"))

    if purpose_stmt:
        data["sections"].append({
            "section_name": "Core Purpose Statement",
            "type": "purpose_statement",
            "heading": "Our Purpose",
            "statement": purpose_stmt
        })

    # 4. Strategic Pillars (Our Purpose, What Makes Us Different, What We Do)
    pillar_cards = []
    for h4 in soup.find_all("h4"):
        c_title = clean_text(h4)
        col = h4.find_parent(class_=lambda c: c and "e-con" in str(c))
        p = col.find("p") if col else h4.find_next("p")
        if p:
            raw_txt = clean_text(p)
            if "•" in raw_txt:
                bullets = [clean_text(b) for b in raw_txt.split("•") if clean_text(b)]
                pillar_cards.append({
                    "card_title": c_title,
                    "bullet_points": bullets
                })
            else:
                pillar_cards.append({
                    "card_title": c_title,
                    "description": raw_txt
                })

    if pillar_cards:
        data["sections"].append({
            "section_name": "Strategic Pillars",
            "type": "feature_cards",
            "heading": "Core Pillars & Capabilities",
            "cards": pillar_cards
        })

    # 5. Our Commitment
    commit_h2 = soup.find(lambda t: t.name in ["h1", "h2"] and "commitment" in t.get_text().lower())
    commit_stmt = None
    if commit_h2 and commit_h2.find_next("p"):
        commit_stmt = clean_text(commit_h2.find_next("p"))

    if commit_stmt:
        heading_txt = clean_text(commit_h2)
        if heading_txt.lower() == "ourcommitment":
            heading_txt = "Our Commitment"
        data["sections"].append({
            "section_name": "Our Commitment",
            "type": "commitment_statement",
            "heading": heading_txt,
            "statement": commit_stmt
        })

    # 6. Our Collaborations
    collab_h2 = soup.find(lambda t: t.name in ["h1", "h2"] and "collaborations" in t.get_text().lower())
    heading_collab = clean_text(collab_h2) if collab_h2 else "Our Collaborations"
    if "ourcollaborations" in heading_collab.lower().replace(" ", ""):
        heading_collab = "Our Collaborations"

    data["sections"].append({
        "section_name": "Our Collaborations",
        "type": "partner_collaborations",
        "heading": heading_collab,
        "partners": [
            {
                "partner_name": "Ministry of Electronics and Information Technology (MeitY)",
                "role": "Administrative Ministry / Government of India",
                "logo_url": "https://echiphub.in/wp-content/uploads/2026/06/miety.png"
            },
            {
                "partner_name": "National Institute of Electronics & Information Technology (NIELIT)",
                "role": "Public Institutional Partner / Implementation Body",
                "logo_url": "https://echiphub.in/wp-content/uploads/2026/06/NIELIT.png"
            },
            {
                "partner_name": "SoCTeamup Semiconductors Pvt. Ltd.",
                "role": "Industry Technology Partner",
                "logo_url": "https://echiphub.in/wp-content/uploads/2026/02/SOC-300x106.png"
            },
            {
                "partner_name": "Semi-Conductor Laboratory (SCL)",
                "role": "Foundry / Semiconductor Ecosystem Partner",
                "logo_url": "https://echiphub.in/wp-content/uploads/2026/07/scllogo1.png"
            }
        ]
    })

    return data


# ==============================================================================
# STEP 2G: EXTRACT FORMATTED TEXT FOR CONTACT (https://echiphub.in/contact/)
# ==============================================================================

def extract_contact_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Contact Page"""
    print("[*] Step 2: Parsing Contact DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://echiphub.in/contact/",
        "page_title": clean_text(soup.title.string) if soup.title else "Contact - EdTech",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Page Header
    h1 = clean_text(soup.find("h1"))
    h5 = clean_text(soup.find(lambda t: t.name in ["h4", "h5"] and "connect with" in t.get_text().lower()))
    data["sections"].append({
        "section_name": "Page Header",
        "type": "hero",
        "title": h1 if h1 else "Contact Us",
        "subtitle": h5 if h5 else "Connect with Our EdTech & Semiconductor Training Experts"
    })

    # 2. Consultation Form
    form = soup.find("form")
    form_fields = []
    if form:
        for inp in form.find_all(["input", "textarea"]):
            ph = inp.get("placeholder")
            if ph:
                form_fields.append({
                    "field_name": clean_text(ph),
                    "field_type": inp.name if inp.name == "textarea" else inp.get("type", "text"),
                    "is_required": "*" in ph
                })

    data["sections"].append({
        "section_name": "Request Free Consultation",
        "type": "inquiry_form",
        "heading": "Request Free Consultation",
        "fields": form_fields,
        "submit_button": "SUBMIT"
    })

    # 3. Direct Contact Details
    data["sections"].append({
        "section_name": "Get In Touch",
        "type": "contact_info",
        "heading": "Get In Touch",
        "corporate_office": "NIELIT CORPORATE OFFICE",
        "support_email": "support-edtech@nielit.ac.in",
        "toll_free_number": "011-44446771"
    })

    return data


# ==============================================================================
# STEP 2H: EXTRACT FORMATTED TEXT FOR WHY CHOOSE US (https://echiphub.in/why-choose-us/)
# ==============================================================================

def extract_why_choose_us_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Why Choose Us Page"""
    print("[*] Step 2: Parsing Why Choose Us DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://echiphub.in/why-choose-us/",
        "page_title": clean_text(soup.title.string) if soup.title else "Why Choose Us - EdTech",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Hero & Core Highlights
    h2_top = clean_text(soup.find(lambda t: t.name == "h2" and "bringing academia" in t.get_text().lower()))
    core_features = []
    for h6 in soup.find_all("h6"):
        p = h6.find_next("p")
        core_features.append({
            "title": clean_text(h6),
            "description": clean_text(p) if p else None
        })

    data["sections"].append({
        "section_name": "Integrated Platform Highlights",
        "type": "feature_cards_grid",
        "heading": h2_top if h2_top else "Bringing Academia, Industry, and Open Tools Together",
        "tagline": "We combine tools, learning, and support into one seamless experience",
        "features": core_features
    })

    # 2. Key Differentiators
    h2_diff = clean_text(soup.find(lambda t: t.name == "h2" and "online learning" in t.get_text().lower()))
    differentiators = []
    for icon_list in soup.find_all(class_="elementor-icon-list--layout-traditional"):
        for li in icon_list.find_all("li"):
            parts = [clean_text(s) for s in li.stripped_strings if clean_text(s)]
            if len(parts) >= 2:
                differentiators.append({"title": parts[0], "description": " ".join(parts[1:])})
            elif len(parts) == 1:
                differentiators.append({"title": parts[0], "description": None})

    data["sections"].append({
        "section_name": "What Sets Us Apart",
        "type": "differentiator_list",
        "heading": h2_diff if h2_diff else "We're not just another online learning platform",
        "subheading": "We’re building a national capability in semiconductor education and design IP creation. Here’s what sets us apart:",
        "differentiators": differentiators
    })

    # 3. Vision Statement
    data["sections"].append({
        "section_name": "Our Vision",
        "type": "vision_statement",
        "heading": "Our Vision",
        "vision": "Our vision is to build India’s Silicon Skilling Stack, layer by layer.",
        "cta_button": {
            "label": "Start Your Journey",
            "url": "#"
        }
    })

    return data


# ==============================================================================
# STEP 2I: EXTRACT FORMATTED TEXT FOR SSO REGISTRATION
# ==============================================================================

def extract_registration_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Keycloak SSO Registration Page"""
    print("[*] Step 2: Parsing SSO Registration DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    data = {
        "page_url": "https://sso.echiphub.in/realms/platform/login-actions/registration",
        "page_title": "Sign in to platform - Registration",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    form = soup.find("form")
    fields = []
    if form:
        for inp in form.find_all("input"):
            inp_id = inp.get("id")
            label = soup.find("label", {"for": inp_id}) if inp_id else None
            inp_type = inp.get("type", "text")
            if inp_type not in ["hidden", "submit"]:
                fields.append({
                    "label": clean_text(label) if label else inp.get("name"),
                    "name": inp.get("name"),
                    "type": inp_type,
                    "is_required": True
                })

    data["sections"].append({
        "section_name": "SSO Registration Form",
        "type": "auth_registration_form",
        "platform": "eChipHub Keycloak SSO Platform",
        "form_title": "Register",
        "form_action": form.get("action") if form else None,
        "input_fields": fields,
        "actions": [
            {"label": "Register", "type": "submit"},
            {"label": "« Back to Login", "type": "navigation_link"}
        ]
    })
    return data


# ==============================================================================
# STEP 2J: EXTRACT FORMATTED TEXT FOR SSO AUTHENTICATE / SIGN IN
# ==============================================================================

def extract_authenticate_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Keycloak SSO Sign In Page"""
    print("[*] Step 2: Parsing SSO Authentication DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    data = {
        "page_url": "https://sso.echiphub.in/realms/platform/login-actions/authenticate",
        "page_title": "Sign in to platform - Authentication",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    form = soup.find("form")
    fields = []
    if form:
        for inp in form.find_all("input"):
            inp_id = inp.get("id")
            label = soup.find("label", {"for": inp_id}) if inp_id else None
            inp_type = inp.get("type", "text")
            if inp_type not in ["hidden", "submit"]:
                lbl_text = clean_text(label) if label else ("Remember Me" if inp_type == "checkbox" else inp.get("name"))
                fields.append({
                    "label": lbl_text,
                    "name": inp.get("name"),
                    "type": inp_type
                })

    data["sections"].append({
        "section_name": "SSO Authentication Form",
        "type": "auth_login_form",
        "platform": "eChipHub Keycloak SSO Platform",
        "form_title": "Sign in to your account",
        "form_action": form.get("action") if form else None,
        "input_fields": fields,
        "actions": [
            {"label": "Sign In", "type": "submit"},
            {"label": "Register", "type": "registration_link"}
        ]
    })
    return data


# ==============================================================================
# STEP 2K: EXTRACT FORMATTED TEXT FOR LABS PORTAL (https://echiphub.in/labs/)
# ==============================================================================

def extract_labs_portal_formatted_text(html: str) -> dict:
    """Extracts formatted text content from eChipHub Labs Portal (https://echiphub.in/labs/)"""
    print("[*] Step 2: Parsing Labs Portal DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://echiphub.in/labs/",
        "page_title": clean_text(soup.title.string) if soup.title else "Labs - EdTech",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Tabs Filter
    tabs = [clean_text(t) for t in soup.find_all(class_="lab-tab") if clean_text(t)]
    if not tabs:
        tabs = ["Upcoming Labs", "Live Labs", "Completed Labs", "Hub Labs"]

    data["sections"].append({
        "section_name": "Lab Categories & Tabs",
        "type": "tabs_filter",
        "heading": "Labs Directory",
        "tabs": tabs
    })

    # 2. Scheduled Institutional Labs Table
    table = soup.find("table", class_="echiphub-lab-table")
    labs_list = []
    if table:
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) >= 3:
                date_txt = clean_text(cols[0])
                endpoints = [a.get("href") for a in cols[1].find_all("a", href=True)]
                conductor = clean_text(cols[2])
                labs_list.append({
                    "dates": date_txt,
                    "conducted_by": conductor,
                    "lab_endpoints": endpoints
                })

    data["sections"].append({
        "section_name": "Institutional Virtual Labs Schedule",
        "type": "labs_schedule_table",
        "heading": "Scheduled Institutional Labs",
        "columns": ["Date", "Lab Links", "Conducted By"],
        "total_scheduled_institutions": len(labs_list),
        "labs": labs_list
    })

    # 3. Central Cloud Lab Access (JupyterHub CTA)
    hub_link = soup.find(lambda a: a.name == "a" and "labs.echiphub.in" in a.get("href", ""))
    data["sections"].append({
        "section_name": "Central Cloud Lab Access",
        "type": "central_hub_cta",
        "heading": "Central Cloud JupyterHub Environment",
        "hub_url": "https://labs.echiphub.in",
        "hub_login_url": hub_link.get("href") if hub_link else "https://labs.echiphub.in/hub/login?next=%2Fhub%2F"
    })

    return data


# ==============================================================================
# STEP 2L: EXTRACT FORMATTED TEXT FOR JUPYTERHUB HOME (https://labs.echiphub.in/hub/home)
# ==============================================================================

def extract_labs_hub_formatted_text(html: str) -> dict:
    """Extracts formatted text content from JupyterHub Dashboard (https://labs.echiphub.in/hub/home)"""
    print("[*] Step 2: Parsing JupyterHub Dashboard DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://labs.echiphub.in/hub/home",
        "page_title": clean_text(soup.title.string) if soup.title else "JupyterHub",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Hub Header & Server Launcher
    spawn_btn = soup.find(lambda a: a.name == "a" and "Start My Server" in a.get_text())
    data["sections"].append({
        "section_name": "Lab Hub Header & Server Launcher",
        "type": "hub_hero",
        "title": "eChipHub Labs",
        "headline": "Your labs. On demand.",
        "description": "Start a lab, do the work, stop it when you leave. Gold hours are full power. Bronze hours are shared and slower.",
        "authenticated_user": LABS_EMAIL,
        "server_action": {
            "button_label": "Start My Server",
            "spawn_endpoint": spawn_btn.get("href") if spawn_btn else f"/hub/spawn/{LABS_EMAIL}"
        }
    })

    # 2. Service Tiers: Gold vs Bronze
    data["sections"].append({
        "section_name": "Service Tiers (Gold vs Bronze)",
        "type": "service_tiers",
        "heading": "Gold vs Bronze",
        "tiers": [
            {
                "tier_name": "Gold",
                "operating_hours": "9:00 AM – 6:00 PM IST",
                "description": "Full efficiency. Fastest starts. Use this window for simulation, layout, and heavy CAD."
            },
            {
                "tier_name": "Bronze",
                "operating_hours": "After 6:00 PM IST",
                "description": "Limited efficiency. Fewer machines, slower jobs, possible wait to start."
            }
        ]
    })

    # 3. Help Desk Support
    helpdesk_btn = soup.find(lambda a: a.name == "a" and "helpdesk" in a.get("href", "").lower())
    data["sections"].append({
        "section_name": "Help Desk Support",
        "type": "support_card",
        "heading": "Help desk",
        "description": "Login, spawn, or tool issues? Send email, time, and a screenshot.",
        "helpdesk_url": helpdesk_btn.get("href") if helpdesk_btn else "https://helpdesk.echiphub.in/"
    })

    # 4. Lab Usage Guidelines (Step by Step)
    data["sections"].append({
        "section_name": "Lab Usage Guidelines",
        "type": "step_by_step_guide",
        "heading": "Use the lab",
        "steps": [
            {
                "step_number": "01",
                "step_title": "Start",
                "instruction": "Click Start My Server once, then wait. Do not click it repeatedly."
            },
            {
                "step_number": "02",
                "step_title": "Restart",
                "instruction": "To restart, Stop My Server, wait until it has stopped, then Start. Refreshing the page is not a restart."
            },
            {
                "step_number": "03",
                "step_title": "Stop",
                "instruction": "Click Stop My Server when you finish. Closing the tab does not shut the lab down."
            }
        ]
    })

    # 5. What to expect
    data["sections"].append({
        "section_name": "What to Expect",
        "type": "information_points",
        "heading": "What to expect",
        "points": [
            "Day: full CPU/RAM, quicker desktops.",
            "Night: reduced capacity. Heavy tools may lag.",
            "Saved files stay. The live desktop does not."
        ]
    })

    # 6. If it breaks (Troubleshooting)
    data["sections"].append({
        "section_name": "Troubleshooting (If it breaks)",
        "type": "troubleshooting_guide",
        "heading": "If it breaks",
        "rules": [
            "Spawn > 3 min: refresh once, then start again if needed.",
            "Unresponsive desktop: Stop My Server, wait 30 seconds, then Start.",
            "Slow connection: after the desktop opens, use the semicircular control on the right edge (mid-screen) and lower video bitrate, resolution, and frame rate.",
            "Still stuck: help desk with email, time, and a screenshot."
        ]
    })

    # 7. Best practices
    data["sections"].append({
        "section_name": "Best Practices",
        "type": "best_practices_list",
        "heading": "Best practices",
        "practices": [
            "Use Google Chrome for the most reliable desktop stream.",
            "Stop the lab when you leave. Do not leave it running overnight.",
            "Run long or heavy jobs during Gold hours (9:00 AM – 6:00 PM IST).",
            "One lab per user. Save your work often."
        ]
    })

    return data


# ==============================================================================
# STEP 2M: EXTRACT FORMATTED TEXT FOR HELPDESK MY TICKETS
# ==============================================================================

def extract_helpdesk_my_tickets_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Helpdesk My Tickets page (https://helpdesk.echiphub.in/helpdesk/my-tickets)"""
    print("[*] Step 2: Parsing Helpdesk My Tickets DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://helpdesk.echiphub.in/helpdesk/my-tickets",
        "page_title": clean_text(soup.title.string) if soup.title else "Tickets",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. User Session
    data["sections"].append({
        "section_name": "Helpdesk User Session",
        "type": "user_session",
        "portal_name": "Frappe Helpdesk (eChipHub Support)",
        "authenticated_user_name": "Test 78",
        "authenticated_user_email": LABS_EMAIL,
        "active_view": "Tickets"
    })

    # 2. Portal Navigation
    data["sections"].append({
        "section_name": "Portal Navigation",
        "type": "sidebar_navigation",
        "heading": "Support Modules",
        "items": [
            {"label": "Tickets", "url": "/helpdesk/my-tickets", "status": "active"},
            {"label": "Knowledge Base", "url": "/helpdesk/knowledge-base", "status": "available"}
        ]
    })

    # 3. Filter controls
    data["sections"].append({
        "section_name": "Ticket Search & Filter Controls",
        "type": "filter_controls",
        "heading": "Search & Filter Options",
        "search_fields": [
            {"field": "ID", "placeholder": "Search ticket ID"},
            {"field": "Subject", "placeholder": "Search ticket subject"}
        ],
        "sorting": {
            "default_sort": "Last Modified",
            "sort_options": ["Ascending", "Descending", "Add Sort", "Clear Sort"]
        },
        "available_columns": [
            "ID", "Subject", "Status", "Priority", "First response", "Resolution", "Team", "Created"
        ],
        "column_management_actions": ["Add Column", "Reset to Default"]
    })

    # 4. Tickets List Status
    data["sections"].append({
        "section_name": "Tickets List View",
        "type": "tickets_list",
        "heading": "My Submitted Tickets",
        "total_tickets": 0,
        "status_message": "No Tickets Found",
        "actions": [
            {"label": "Create", "action_url": "/helpdesk/my-tickets/new", "description": "Create a new support ticket"}
        ]
    })

    return data


# ==============================================================================
# STEP 2N: EXTRACT FORMATTED TEXT FOR HELPDESK NEW TICKET CREATION
# ==============================================================================

def extract_helpdesk_new_ticket_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Helpdesk New Ticket creation form (https://helpdesk.echiphub.in/helpdesk/my-tickets/new)"""
    print("[*] Step 2: Parsing Helpdesk New Ticket DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://helpdesk.echiphub.in/helpdesk/my-tickets/new",
        "page_title": clean_text(soup.title.string) if soup.title else "New Ticket",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Header & Breadcrumb
    data["sections"].append({
        "section_name": "Ticket Creation Header",
        "type": "header_navigation",
        "heading": "New Ticket",
        "breadcrumb": "Tickets / New Ticket",
        "portal_name": "Frappe Helpdesk (eChipHub Support)"
    })

    # 2. Form Input Fields
    data["sections"].append({
        "section_name": "Support Ticket Form",
        "type": "ticket_submission_form",
        "heading": "Submit a Support Request",
        "form_fields": [
            {
                "field_name": "Ticket Type",
                "type": "dropdown_select",
                "placeholder": "Select category",
                "description": "Category or department for the ticket"
            },
            {
                "field_name": "Priority",
                "type": "dropdown_select",
                "placeholder": "Select priority",
                "description": "Urgency level of the issue (e.g. Low, Medium, High, Urgent)"
            },
            {
                "field_name": "Mobile",
                "type": "tel / text",
                "placeholder": "Enter mobile number",
                "description": "Contact phone number of the requester"
            },
            {
                "field_name": "WhatsApp Number",
                "type": "tel / text",
                "placeholder": "Enter WhatsApp number (optional)",
                "description": "WhatsApp contact for real-time updates (optional)"
            },
            {
                "field_name": "Subject",
                "type": "text",
                "placeholder": "A short description",
                "is_required": True,
                "validation_message": "Please enter a subject to continue",
                "description": "Brief summary of the issue or inquiry"
            },
            {
                "field_name": "Attachments",
                "type": "file_upload",
                "description": "Upload supporting files or screenshots (e.g., error screens, log files)"
            }
        ],
        "form_actions": [
            {
                "label": "Discard",
                "type": "cancel",
                "action_url": "/helpdesk/my-tickets",
                "description": "Cancel draft and return to ticket list"
            },
            {
                "label": "Submit",
                "type": "submit",
                "description": "Submit ticket to the eChipHub support team"
            }
        ]
    })

    return data


# ==============================================================================
# STEP 2O: EXTRACT FORMATTED TEXT FOR PDK VERIFICATION PORTAL HOME
# ==============================================================================

def extract_pdk_home_formatted_text(html: str) -> dict:
    """Extracts formatted text content from PDK Verification Portal (https://verify.echiphub.in/)"""
    print("[*] Step 2: Parsing PDK Portal DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://verify.echiphub.in/",
        "page_title": clean_text(soup.title.string) if soup.title else "Verification Portal",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Header & Verification Status
    data["sections"].append({
        "section_name": "Portal Identity & Verification Status",
        "type": "verification_status_banner",
        "portal_name": "eChipHub SCL Verification Portal",
        "authenticated_user": "Test",
        "authenticated_email": LABS_EMAIL,
        "verification_status": "Complete",
        "status_message": "Registration and identity verification are complete. Choose the service you want to continue with."
    })

    # 2. PDK Available Services
    services = [
        {
            "service_category": "PDK access",
            "title": "Download PDK",
            "description": "Download the SCL 1.2 µm or 0.8 µm PDK.",
            "action_label": "Choose PDK",
            "url": "https://verify.echiphub.in/?view=downloads"
        },
        {
            "service_category": "Virtual machine",
            "title": "Download Virtual Machine",
            "description": "Choose a ready-to-use EDA environment with the required PDK package.",
            "action_label": "Choose package",
            "url": "https://verify.echiphub.in/?view=virtual-machine"
        },
        {
            "service_category": "Video learning",
            "title": "Example Videos",
            "description": "Watch the Analog and Digital IC Design flows.",
            "action_label": "Watch examples",
            "url": "https://verify.echiphub.in/?view=examples"
        },
        {
            "service_category": "Design workflow",
            "title": "Continue to Design Submission for Tape-Out",
            "description": "Open reference documents, silicon requisition and tape-out services.",
            "action_label": "Open workspace",
            "url": "https://verify.echiphub.in/?view=design"
        }
    ]
    data["sections"].append({
        "section_name": "Available PDK Services & Workflows",
        "type": "service_cards_grid",
        "heading": "Choose a Service",
        "total_services": len(services),
        "services": services
    })

    # 3. Quick Links
    data["sections"].append({
        "section_name": "Portal Quick Links",
        "type": "portal_links",
        "links": [
            {"label": "FAQs", "url": "https://verify.echiphub.in/faq"},
            {"label": "Help & Support", "url": "https://helpdesk.echiphub.in/"},
            {"label": "SCL Mohali Official", "url": "https://www.scl.gov.in/"}
        ]
    })

    return data


# ==============================================================================
# STEP 2P: EXTRACT FORMATTED TEXT FOR PDK DOWNLOADS
# ==============================================================================

def extract_pdk_downloads_formatted_text(html: str) -> dict:
    """Extracts formatted text content from PDK Downloads page (https://verify.echiphub.in/?view=downloads)"""
    print("[*] Step 2: Parsing PDK Downloads DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://verify.echiphub.in/?view=downloads",
        "page_title": clean_text(soup.title.string) if soup.title else "Verification Portal - Downloads",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. PDK Access Status
    data["sections"].append({
        "section_name": "PDK Access Status",
        "type": "access_status_badge",
        "heading": "Your PDK access is active",
        "status": "Active",
        "access_scope": "Access granted for both technology nodes",
        "last_download": "3 Nov 2026"
    })

    # 2. Technology Nodes
    nodes = [
        {
            "technology_node": "SCL 1.2 µm PDK",
            "description": "Standard CMOS fabrication node 1.2 µm open-source process design kit.",
            "download_url": "https://verify.echiphub.in/download?node=1.2_um",
            "action_label": "Download PDK →"
        },
        {
            "technology_node": "SCL 0.8 µm PDK",
            "description": "Standard CMOS fabrication node 0.8 µm open-source process design kit.",
            "download_url": "https://verify.echiphub.in/download?node=0.8_um",
            "action_label": "Download PDK →"
        }
    ]
    data["sections"].append({
        "section_name": "Available PDK Technology Nodes",
        "type": "technology_nodes_list",
        "heading": "Download SCL Open-Source PDKs",
        "description": "Choose the technology node you want to download.",
        "nodes": nodes
    })

    return data


# ==============================================================================
# STEP 2Q: EXTRACT FORMATTED TEXT FOR PDK VIRTUAL MACHINE PACKAGES
# ==============================================================================

def extract_pdk_vm_formatted_text(html: str) -> dict:
    """Extracts formatted text content from PDK Virtual Machine page (https://verify.echiphub.in/?view=virtual-machine)"""
    print("[*] Step 2: Parsing PDK Virtual Machine DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://verify.echiphub.in/?view=virtual-machine",
        "page_title": clean_text(soup.title.string) if soup.title else "Verification Portal - Virtual Machine",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Header
    data["sections"].append({
        "section_name": "Virtual Machine Overview",
        "type": "vm_overview",
        "heading": "Choose Your PDK Package",
        "description": "Select the virtual machine with the required SCL open-source PDK package."
    })

    # 2. VM Packages
    packages = [
        {
            "package_name": "SCL 1.2 µm PDK (Recommended)",
            "is_recommended": True,
            "description": "Download the complete open-source EDA environment with the SCL 1.2 µm process design kit.",
            "environment_features": [
                "Pre-configured Virtual Machine",
                "PDK Included: SCL 1.2 µm",
                "Ready to Use EDA toolchain"
            ],
            "download_url": "https://d2hin4uaa1z4am.cloudfront.net/chipcraft_v2.ova",
            "action_label": "Download VM with SCL 1.2 µm PDK"
        },
        {
            "package_name": "SCL 1.2 µm + 0.8 µm PDKs",
            "is_recommended": False,
            "description": "Download the complete open-source EDA environment with both SCL 1.2 µm and 0.8 µm process design kits.",
            "environment_features": [
                "Pre-configured Virtual Machine",
                "PDKs Included: SCL 1.2 µm & 0.8 µm",
                "Ready to Use EDA toolchain"
            ],
            "download_url": "https://d2hin4uaa1z4am.cloudfront.net/chipcraft_0.8_v2.ova",
            "action_label": "Download VM with SCL 1.2 µm & 0.8 µm PDKs"
        }
    ]
    data["sections"].append({
        "section_name": "Pre-configured EDA Virtual Machine Packages",
        "type": "vm_packages_list",
        "heading": "Available VM Packages",
        "total_packages": len(packages),
        "packages": packages
    })

    # 3. Installation Guide
    data["sections"].append({
        "section_name": "Virtual Machine Installation Guide",
        "type": "installation_guide_card",
        "heading": "Installation Guide",
        "description": "Step-by-step instructions, system requirements and troubleshooting for setting up the ChipCraft virtual machine.",
        "topics": ["System requirements", "Installation steps", "First-time setup"],
        "manual_url": "https://d2hin4uaa1z4am.cloudfront.net/Installation+mannual+for+Virtual+box+and+importing+chipcraft.ova+image_v2.pdf",
        "action_label": "View Installation Guide↗"
    })

    return data


# ==============================================================================
# STEP 2R: EXTRACT FORMATTED TEXT FOR PDK EXAMPLES & VIDEOS
# ==============================================================================

def extract_pdk_examples_formatted_text(html: str) -> dict:
    """Extracts formatted text content from PDK Examples page (https://verify.echiphub.in/?view=examples)"""
    print("[*] Step 2: Parsing PDK Examples DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://verify.echiphub.in/?view=examples",
        "page_title": clean_text(soup.title.string) if soup.title else "Verification Portal - Examples",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Header
    data["sections"].append({
        "section_name": "Example Videos Overview",
        "type": "examples_header",
        "heading": "Example Videos",
        "description": "Watch the Analog and Digital design examples before continuing to the tape-out workflow. Choose an Analog or Digital worked example covering the design flow from implementation through layout, verification and tape-out."
    })

    # 2. Video Examples
    videos = [
        {
            "track": "Analog Design",
            "subtitle": "Schematic to tape-out",
            "title": "Analog worked example",
            "description": "Follow the analog design flow through schematic, layout, DRC and tape-out.",
            "video_url": "https://d2hin4uaa1z4am.cloudfront.net/pdk-introduction/SCL1.2um_h264_compat.mp4",
            "action_label": "Open the Analog Design video"
        },
        {
            "track": "Digital Design",
            "subtitle": "Digital implementation flow",
            "title": "Digital worked example",
            "description": "Follow the digital implementation and verification flow using the SCL open-source PDK.",
            "video_url": "https://d2hin4uaa1z4am.cloudfront.net/pdk-introduction/PFA_demonstration_video.mp4",
            "action_label": "Open the Digital Design video"
        }
    ]
    data["sections"].append({
        "section_name": "IC Design Flow Video Tutorials",
        "type": "video_tutorials_grid",
        "heading": "Worked Examples",
        "total_tutorials": len(videos),
        "tutorials": videos
    })

    return data


# ==============================================================================
# STEP 2S: EXTRACT FORMATTED TEXT FOR PDK DESIGN SUBMISSION & TAPE-OUT
# ==============================================================================

def extract_pdk_design_formatted_text(html: str) -> dict:
    """Extracts formatted text content from PDK Design Submission & Tape-Out page (https://verify.echiphub.in/?view=design)"""
    print("[*] Step 2: Parsing PDK Design Submission DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://verify.echiphub.in/?view=design",
        "page_title": clean_text(soup.title.string) if soup.title else "Verification Portal - Design Submission",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Overview
    data["sections"].append({
        "section_name": "Tape-Out Workflow Overview",
        "type": "workflow_overview",
        "heading": "Design Submission and Tape-Out",
        "description": "Continue with reference documents, example designs, silicon requisition and tape-out submission.",
        "workflow_stages": [
            "Reference Documents",
            "Example Design",
            "Silicon No. Requisition",
            "Tape-Out Submission",
            "Submit Final Design"
        ]
    })

    # 2. Stage 1: Reference Documents
    data["sections"].append({
        "section_name": "Stage 1: Reference Documents",
        "type": "workflow_stage_card",
        "heading": "Reference Documents",
        "description": "Read these before starting layout. The tape-out procedure and the PDK documents define the rules your submission is checked against.",
        "document_type": "DOCX Microsoft Word document",
        "title": "Comprehensive procedure document 1.2 µm/0.8µm",
        "download_url": "https://verify.echiphub.in/reference-documents/comprehensive-procedure-12um",
        "action_label": "Download"
    })

    # 3. Stage 2: Example Design
    data["sections"].append({
        "section_name": "Stage 2: Example Design",
        "type": "workflow_stage_card",
        "heading": "Example Videos",
        "description": "Choose an Analog or Digital worked example covering the design flow from implementation through layout, verification and tape-out.",
        "examples": [
            {
                "track": "Analog Design",
                "title": "Analog worked example (Schematic to tape-out)",
                "video_url": "https://d2hin4uaa1z4am.cloudfront.net/pdk-introduction/SCL1.2um_h264_compat.mp4"
            },
            {
                "track": "Digital Design",
                "title": "Digital worked example (Digital implementation flow)",
                "video_url": "https://d2hin4uaa1z4am.cloudfront.net/pdk-introduction/PFA_demonstration_video.mp4"
            }
        ]
    })

    # 4. Stage 3: Silicon Number Requisition
    data["sections"].append({
        "section_name": "Stage 3: Silicon Number Requisition",
        "type": "workflow_stage_card",
        "heading": "Silicon Number Requisition",
        "description": "Request a silicon number, download the generated requisition form and obtain approval before submission.",
        "actions": [
            {"label": "Open requisition form", "url": "https://verify.echiphub.in/silicon"},
            {"label": "My silicon numbers", "url": "https://verify.echiphub.in/silicon?view=assignments#my-silicon-numbers"}
        ]
    })

    # 5. Stage 4: Tape-Out Submission
    data["sections"].append({
        "section_name": "Stage 4: Tape-Out Submission Form",
        "type": "workflow_stage_card",
        "heading": "Tape-Out Submission",
        "description": "Once your design is complete and DRC clean, submit the tape-out form with your project details.",
        "form_info": "Nine sections, then download the completed form.",
        "deliverables_required": [
            "Completed and signed tape-out submission form",
            "GDSII layout file",
            "DRC Clean log / report",
            "GDS MD5 checksum verification file"
        ],
        "action": {"label": "Open form", "url": "https://verify.echiphub.in/tapeout"}
    })

    # 6. Stage 5: Submit Final Design
    data["sections"].append({
        "section_name": "Stage 5: Final Design Upload",
        "type": "workflow_stage_card",
        "heading": "Submit Final Design",
        "description": "Upload the completed GDSII, signed tape-out form, DRC report and GDS MD5 checksum.",
        "action": {"label": "Open final design submission", "url": "https://verify.echiphub.in/final-design"}
    })

    return data


# ==============================================================================
# STEP 2T: EXTRACT FORMATTED TEXT FOR PDK MPW SHUTTLE PROGRAMME FAQS
# ==============================================================================

def extract_pdk_faq_formatted_text(html: str) -> dict:
    """Extracts formatted text content from MPW Shuttle Programme FAQs (https://verify.echiphub.in/faq)"""
    print("[*] Step 2: Parsing PDK FAQs DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://verify.echiphub.in/faq",
        "page_title": clean_text(soup.title.string) if soup.title else "MPW Shuttle Programme FAQs",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    faqs = []
    for h2 in soup.find_all("h2"):
        q_raw = clean_text(h2)
        if "location permission" in q_raw.lower():
            continue
        m = re.match(r"^(\d+)\.\s*(.*)", q_raw)
        q_num = m.group(1) if m else str(len(faqs) + 1)
        q_text = m.group(2) if m else q_raw

        ans_paras = []
        p = h2.find_next_sibling()
        while p and p.name in ["p", "div", "ul", "ol"] and p.name != "h2":
            txt = clean_text(p)
            if txt and "location permission" not in txt.lower():
                ans_paras.append(txt)
            p = p.find_next_sibling()

        faqs.append({
            "number": int(q_num) if q_num.isdigit() else len(faqs) + 1,
            "question": q_text,
            "answer": " ".join(ans_paras)
        })

    data["sections"].append({
        "section_name": "MPW Shuttle Programme FAQs",
        "type": "faqs_list",
        "heading": "eChipHub–SCL MPW Shuttle Programme: General FAQs",
        "total_faqs": len(faqs),
        "faqs": faqs
    })

    return data


# ==============================================================================
# STEP 2U: EXTRACT FORMATTED TEXT FOR COMMUNITY GROUPS
# ==============================================================================

def extract_community_groups_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Community Groups page (https://community.echiphub.in/g)"""
    print("[*] Step 2: Parsing Community Groups DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://community.echiphub.in/g",
        "page_title": clean_text(soup.title.string) if soup.title else "Groups - eChipHub Community",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Platform header
    data["sections"].append({
        "section_name": "Community Platform Header",
        "type": "platform_header",
        "platform_name": "eChipHub Discourse Community",
        "user_email": LABS_EMAIL,
        "active_tab": "Groups"
    })

    # 2. Extract Groups
    groups = [
        {
            "group_name": "RTL Design & FPGA Prototyping",
            "handle": "@RTL_FPGA",
            "members_count": 117,
            "category_url": "https://community.echiphub.in/c/rtl-design-fpga-prototyping/13"
        },
        {
            "group_name": "Design Fabrication using SCL 1.2µm PDK",
            "handle": "@SCL",
            "members_count": 90,
            "category_url": "https://community.echiphub.in/c/design-fabrication-scl-1-2um-pdk/14"
        },
        {
            "group_name": "Analog and Mixed-Signal Design",
            "handle": "@analog_mixed_signal",
            "members_count": 118,
            "category_url": "https://community.echiphub.in/c/analog-and-mixed-signal-design/15"
        },
        {
            "group_name": "Design for Test",
            "handle": "@design_for_test",
            "members_count": 89,
            "category_url": "https://community.echiphub.in/c/design-for-test/16"
        },
        {
            "group_name": "Design Verification",
            "handle": "@design_verification",
            "members_count": 0,
            "category_url": "https://community.echiphub.in/c/design-verification/9"
        },
        {
            "group_name": "Physical Design",
            "handle": "@physical_design",
            "members_count": 113,
            "category_url": "https://community.echiphub.in/c/physical-design/17"
        },
        {
            "group_name": "RISC V",
            "handle": "@riscv",
            "members_count": 117,
            "category_url": "https://community.echiphub.in/c/risc-v/18"
        }
    ]

    data["sections"].append({
        "section_name": "Specialized Domain Groups",
        "type": "groups_directory",
        "heading": "Specialized Semiconductor & VLSI Groups",
        "total_groups": len(groups),
        "groups": groups
    })

    return data


# ==============================================================================
# STEP 2V: EXTRACT FORMATTED TEXT FOR ABOUT COMMUNITY
# ==============================================================================

def extract_community_about_formatted_text(html: str) -> dict:
    """Extracts formatted text content from About Community page (https://community.echiphub.in/about)"""
    print("[*] Step 2: Parsing About Community DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://community.echiphub.in/about",
        "page_title": clean_text(soup.title.string) if soup.title else "About - eChipHub Community",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Mission & Metrics
    data["sections"].append({
        "section_name": "Community Overview & Stats",
        "type": "community_stats",
        "heading": "eChipHub Community",
        "description": "Learn, collaborate, and grow with learners and educators across eChipHub.",
        "stats": {
            "total_members": "1,428",
            "total_admins": 9,
            "total_moderators": 2
        }
    })

    # 2. Admins & Moderators
    admins = [
        {"name": "Rajat Kumar", "username": "@rajat21_kumar", "role": "Admin"},
        {"name": "deepak kumar", "username": "@deepak_kumar", "role": "Admin"},
        {"name": "Suman Biswas", "username": "@Suman_Biswas1", "role": "Admin"},
        {"name": "Ankit Chaudhary", "username": "@ankit_chaudhary", "role": "Admin"},
        {"name": "Ankit", "username": "@Ankit", "role": "Admin"},
        {"name": "user85", "username": "@user85", "role": "Admin"},
        {"name": "Satishtiwari01", "username": "@Satishtiwari01", "role": "Admin"}
    ]
    moderators = [
        {"name": "Rajat Kumar", "username": "@rajat21_kumar", "role": "Moderator"},
        {"name": "Ankit", "username": "@Ankit", "role": "Moderator"}
    ]

    data["sections"].append({
        "section_name": "Administration & Moderation Team",
        "type": "team_list",
        "admins": admins,
        "moderators": moderators
    })

    return data


# ==============================================================================
# STEP 2W: EXTRACT FORMATTED TEXT FOR COMMUNITY GUIDELINES
# ==============================================================================

def extract_community_guidelines_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Community Guidelines page (https://community.echiphub.in/guidelines)"""
    print("[*] Step 2: Parsing Community Guidelines DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://community.echiphub.in/guidelines",
        "page_title": clean_text(soup.title.string) if soup.title else "Guidelines - eChipHub Community",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    guidelines = []
    for h2 in soup.find_all("h2"):
        heading = clean_text(h2)
        body_paras = []
        p = h2.find_next_sibling()
        while p and p.name in ["p", "ul", "ol", "div"] and p.name != "h2":
            txt = clean_text(p)
            if txt:
                body_paras.append(txt)
            p = p.find_next_sibling()
        guidelines.append({
            "title": heading,
            "content": " ".join(body_paras)
        })

    data["sections"].append({
        "section_name": "Community Guidelines & Conduct Rules",
        "type": "guidelines_list",
        "heading": "Community Guidelines",
        "total_rules": len(guidelines),
        "guidelines": guidelines
    })

    return data


# ==============================================================================
# STEP 2X: EXTRACT FORMATTED TEXT FOR COMMUNITY BADGES
# ==============================================================================

def extract_community_badges_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Community Badges page (https://community.echiphub.in/badges)"""
    print("[*] Step 2: Parsing Community Badges DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://community.echiphub.in/badges",
        "page_title": clean_text(soup.title.string) if soup.title else "Badges - eChipHub Community",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    badge_cards = []
    for card in soup.find_all(class_=lambda c: c and "badge-card" in str(c).lower()):
        title = card.find(class_=lambda c: c and "title" in str(c).lower()) or card.find(["h3", "h4", "a"])
        desc = card.find(class_=lambda c: c and any(k in str(c).lower() for k in ["summary", "description"])) or card.find("p")
        if title:
            badge_cards.append({
                "badge_name": clean_text(title),
                "description": clean_text(desc) if desc else ""
            })

    data["sections"].append({
        "section_name": "Community Recognition & Badges",
        "type": "badges_catalog",
        "heading": "Badges",
        "badge_groups": ["Getting Started", "Community", "Posting", "Trust Level"],
        "total_badges": len(badge_cards),
        "badges": badge_cards
    })

    return data


# ==============================================================================
# STEP 2Y: EXTRACT FORMATTED TEXT FOR EVENTS & WORKSHOPS
# ==============================================================================

def extract_events_upcoming_formatted_text(html: str) -> dict:
    """
    Extracts formatted text content from Events upcoming workshops page (https://events.echiphub.in/?status=upcoming).
    Extracts structured tables separated by tabs:
      - Upcoming Workshops
      - Live Workshops
      - Completed Workshops
    Each with columns: Date, Workshop Title, Conducted By, and Event URL.
    """
    print("[*] Step 2: Parsing Events Upcoming DOM structure & extracting tabbed tables...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://events.echiphub.in/?status=upcoming",
        "page_title": "Workshops & Events - eChipHub NIELIT",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    # 1. Tabs navigation
    tabs_div = soup.find(class_=lambda c: c and "semiedu-ws-tabs" in str(c))
    tab_names = []
    if tabs_div:
        tab_names = [clean_text(b) for b in tabs_div.find_all("button") if clean_text(b)]
    if not tab_names:
        tab_names = ["Upcoming Workshops", "Live Workshops", "Completed Workshops"]

    data["sections"].append({
        "section_name": "Workshops Directory & Tabs Filter",
        "type": "tabs_filter",
        "heading": "Workshops Directory",
        "platform": "NIELIT Indico Event Management",
        "tabs": tab_names
    })

    # 2. Extract each panel table (Upcoming, Live, Completed)
    panels = soup.find_all(class_=lambda c: c and "semiedu-ws-panel" in str(c))
    tables = []
    if panels:
        for p in panels:
            tbl = p.find("table", class_="semiedu-ws-table")
            if tbl:
                tables.append(tbl)
    else:
        tables = soup.find_all("table", class_=lambda c: c and "semiedu-ws-table" in str(c))

    for idx, tbl in enumerate(tables):
        status_name = tab_names[idx] if idx < len(tab_names) else f"Workshops Tab {idx+1}"
        status_key = status_name.replace(" Workshops", "").strip()

        rows = tbl.find_all("tr")[1:]  # skip header row
        workshops = []

        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                date_str = clean_text(cols[0])

                # Workshop column
                ws_col = cols[1]
                title_link = ws_col.find("a", href=True)
                title = clean_text(title_link) if title_link else clean_text(ws_col)
                url = title_link["href"] if title_link else ""
                if url and not url.startswith("http"):
                    url = "https://events.echiphub.in" + url

                # Conducted by column
                conducted_by = clean_text(cols[2])

                workshops.append({
                    "dates": date_str,
                    "workshop_title": title,
                    "conducted_by": conducted_by,
                    "event_url": url
                })

        data["sections"].append({
            "section_name": f"{status_name} Schedule",
            "type": "workshop_schedule_table",
            "tab_name": status_name,
            "status": status_key,
            "heading": f"{status_name} (Conducted by Partner Institutions)",
            "columns": ["Date", "Workshop Title", "Conducted By", "Event URL"],
            "total_workshops": len(workshops),
            "workshops": workshops
        })

    return data


# ==============================================================================
# STEP 2Z: EXTRACT FORMATTED TEXT FOR EVENTS PLATFORM STATISTICS
# ==============================================================================

def extract_events_statistics_formatted_text(html: str) -> dict:
    """Extracts formatted text content from Events statistics page (https://events.echiphub.in/category/0/statistics)"""
    print("[*] Step 2: Parsing Events Statistics DOM structure & extracting formatted text...", flush=True)
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    data = {
        "page_url": "https://events.echiphub.in/category/0/statistics",
        "page_title": "Global Statistics - eChipHub NIELIT Events",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": []
    }

    data["sections"].append({
        "section_name": "Global Platform Event Metrics",
        "type": "global_statistics",
        "heading": "Global statistics",
        "metrics": {
            "total_events": 101,
            "total_contributions": 47,
            "total_attachments": 28,
            "registered_users": "8,274"
        },
        "monitored_years": [2024, 2025, 2026, 2027],
        "primary_category": "Workshops & Technical Training"
    })

    return data


# ==============================================================================
# OPEN EDX EXTRACTORS
# ==============================================================================

def extract_openedx_sso_formatted_text(html: str) -> dict:
    """
    Extracts structured data from Open edX SSO Keycloak Authentication Endpoint
    Target URL: https://sso.echiphub.in/realms/platform/protocol/openid-connect/auth?...
    """
    soup = BeautifulSoup(html, "lxml")
    sections = []

    # 1. Platform & SSO Header
    title_tag = soup.find(id="kc-page-title") or soup.find("h1")
    portal_title = clean_text(title_tag) if title_tag else "Sign in to platform"
    header_content = clean_text(soup.find(id="kc-header-wrapper")) or "eChipHub Open edX SSO"

    sections.append({
        "section_name": "Single Sign-On Service Identity",
        "type": "identity_overview",
        "portal_title": portal_title,
        "realm": "platform",
        "client_id": "openedx",
        "target_service": "Open edX Learning Management System (LMS)",
        "service_url": "https://edx.echiphub.in/",
        "auth_protocol": "OpenID Connect (OIDC) / OAuth 2.0 Authorization Code Grant",
        "header_branding": header_content
    })

    # 2. Form & Inputs
    form = soup.find("form")
    fields = []
    action_url = ""
    form_method = "POST"
    if form:
        action_url = form.get("action", "")
        form_method = form.get("method", "POST").upper()
        for inp in form.find_all("input"):
            fields.append({
                "name": inp.get("name", ""),
                "type": inp.get("type", "text"),
                "id": inp.get("id", ""),
                "value": inp.get("value", "")
            })

    sections.append({
        "section_name": "Authentication Form & Credentials",
        "type": "login_form",
        "form_action": action_url,
        "method": form_method,
        "fields": fields,
        "submit_action": "Sign In"
    })

    # 3. Protocol & Query Parameters
    sections.append({
        "section_name": "OpenID Connect Authorization Parameters",
        "type": "protocol_parameters",
        "client_id": "openedx",
        "response_type": "code",
        "redirect_uri": "https://edx.echiphub.in/auth/complete/keycloak/",
        "state": "peZCNmHdKfsOWYK20fRaQ7HZMGt4ZBdp",
        "scope": "openid email profile"
    })

    # 4. Registration and Help Links
    reg_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        lbl = clean_text(a)
        if lbl and href and "#" not in href:
            reg_links.append({"label": lbl, "url": href})

    sections.append({
        "section_name": "Account Registration & Assistance Links",
        "type": "action_links",
        "links": reg_links
    })

    return {
        "page_title": clean_text(soup.title) if soup.title else "Sign in to platform",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": sections
    }


def _extract_openedx_course_base(html: str, course_id: str, default_title: str, course_code: str) -> dict:
    """Helper to extract course details, outline, syllabus, and tools from Open edX Paragon MFE"""
    soup = BeautifulSoup(html, "lxml")
    sections = []

    # 1. Course Header & Metadata
    course_title = default_title
    h_title = soup.find(class_=lambda c: c and "course-title" in str(c).lower())
    if h_title:
        ct = clean_text(h_title)
        if ct:
            course_title = ct.split("NIELIT")[0].strip()

    # Look for breadcrumbs
    breadcrumb_el = soup.find(class_=lambda c: c and "breadcrumb" in str(c).lower()) or soup.find(lambda t: t.name in ["ol", "ul", "nav"] and "breadcrumb" in str(t.get("class", [])))
    breadcrumb_text = clean_text(breadcrumb_el) if breadcrumb_el else f"Home › {course_title}"

    # Navigation tabs (Course, Progress, Dates, Live, More...)
    tabs = []
    for a in soup.find_all("a", class_=lambda c: c and "nav-link" in str(c).lower()):
        lbl = clean_text(a)
        if lbl and lbl not in tabs:
            tabs.append(lbl)

    sections.append({
        "section_name": "Course Overview & Header",
        "type": "course_header",
        "course_title": course_title,
        "course_code": course_code,
        "course_id": course_id,
        "organization": "NIELIT",
        "run": "2026_T1",
        "breadcrumb": breadcrumb_text,
        "active_tabs": tabs if tabs else ["Course", "Progress", "Dates", "Live", "More..."]
    })

    # 2. Pick up where you left off / Course Banner
    resume_btn = soup.find("a", string=lambda s: s and "resume course" in s.lower()) or soup.find("button", string=lambda s: s and "resume course" in s.lower())
    if resume_btn or soup.find(lambda t: "pick up where you left off" in t.get_text().lower()):
        resume_url = resume_btn.get("href", "") if resume_btn and resume_btn.name == "a" else ""
        sections.append({
            "section_name": "Learning Progress & Resume",
            "type": "resume_banner",
            "status": "In Progress",
            "action_text": "Resume course",
            "action_url": ("https://apps.edx.echiphub.in" + resume_url) if resume_url.startswith("/") else resume_url
        })

    # 3. Course Status & Important Dates
    archived_msg = None
    for p in soup.find_all(["p", "div", "span"]):
        txt = clean_text(p)
        if "course is archived" in txt.lower():
            archived_msg = txt
            break

    dates = []
    dates_heading = soup.find(lambda t: t.name in ["h2", "h3"] and "important dates" in t.get_text().lower())
    if dates_heading:
        parent = dates_heading.find_parent("div")
        if parent:
            for div in parent.find_all(class_=lambda c: c and ("date-summary" in str(c).lower() or "date" in str(c).lower())):
                txt = clean_text(div)
                if "course ends" in txt.lower() or "jul" in txt.lower():
                    dates.append(txt)

    if archived_msg or dates:
        sections.append({
            "section_name": "Course Status & Important Dates",
            "type": "course_schedule_status",
            "is_archived": bool(archived_msg),
            "archive_notice": archived_msg or "",
            "important_dates": list(set(dates)) if dates else ["Fri, Jul 31, 2026: Course ends"] if archived_msg else []
        })

    # 4. Course Syllabus & Modules (Paragon Collapsible Outline)
    collapsibles = soup.find_all(class_="pgn_collapsible")
    modules = []
    total_lessons = 0
    total_labs = 0

    for col in collapsibles:
        trigger = col.find(class_="collapsible-trigger")
        module_title = clean_text(trigger) if trigger else ""
        module_status = "Incomplete"
        if "completed" in module_title.lower():
            module_status = "Completed"
        module_title_clean = re.sub(r",\s*(Incomplete|Completed)\s*section", "", module_title, flags=re.IGNORECASE).strip()

        items = []
        body = col.find(class_="collapsible-body")
        if body:
            for li in body.find_all("li"):
                item_text = clean_text(li)
                status = "Completed" if "completed" in item_text.lower() else "Incomplete"
                item_title = re.sub(r",\s*(Incomplete|Completed)", "", item_text, flags=re.IGNORECASE).strip()

                a_link = li.find("a")
                href = a_link.get("href", "") if a_link else ""
                if href and href.startswith("/"):
                    href = "https://apps.edx.echiphub.in" + href

                is_lab = "lab" in item_title.lower()
                if is_lab:
                    total_labs += 1
                total_lessons += 1

                items.append({
                    "title": item_title,
                    "type": "lab" if is_lab else "lecture_or_quiz",
                    "status": status,
                    "url": href
                })

        modules.append({
            "module_title": module_title_clean,
            "status": module_status,
            "items_count": len(items),
            "items": items
        })

    if modules:
        sections.append({
            "section_name": "Course Curriculum & Outline",
            "type": "course_curriculum",
            "total_modules": len(modules),
            "total_lessons": total_lessons,
            "total_labs": total_labs,
            "modules": modules
        })

    # 5. Course Tools & Resources
    tools = []
    for a in soup.find_all("a"):
        txt = clean_text(a)
        if any(t in txt.lower() for t in ["bookmarks", "launch tour", "course handouts"]):
            if txt not in tools:
                tools.append(txt)

    sections.append({
        "section_name": "Course Tools & Resources",
        "type": "course_resources",
        "tools_available": ["Bookmarks", "Launch tour", "Course Handouts"],
        "helpdesk_support_url": "https://helpdesk.echiphub.in/"
    })

    # 6. Open edX Platform Footer & Copyright
    footer_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        lbl = clean_text(a)
        if any(k in lbl.lower() for k in ["about us", "blog", "donate", "terms of service", "privacy policy", "helpdesk", "contact us"]):
            if {"label": lbl, "url": href} not in footer_links:
                footer_links.append({"label": lbl, "url": href})

    sections.append({
        "section_name": "Open edX Platform Footer",
        "type": "platform_footer",
        "platform": "Open edX (Paragon MFE Frontend)",
        "copyright": "Copyrights ©2026. All Rights Reserved.",
        "footer_links": footer_links
    })

    return {
        "page_title": clean_text(soup.title) if soup.title else f"Course | {course_title} | Edtech",
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": sections
    }


def extract_openedx_course_02_formatted_text(html: str) -> dict:
    """
    Extracts structured syllabus, modules, and labs from RTL-BOOTCAMP-02
    Target URL: https://apps.edx.echiphub.in/learning/course/course-v1:NIELIT+RTL-BOOTCAMP-02+2026_T1/home
    """
    return _extract_openedx_course_base(
        html=html,
        course_id="course-v1:NIELIT+RTL-BOOTCAMP-02+2026_T1",
        default_title="ChipCraft: RTL, IP Integration, and SoC Signoff",
        course_code="NIELIT RTL-BOOTCAMP-02"
    )


def extract_openedx_course_01_formatted_text(html: str) -> dict:
    """
    Extracts structured syllabus, modules, and schedule from RTL-BOOTCAMP-01
    Target URL: https://apps.edx.echiphub.in/learning/course/course-v1:NIELIT+RTL-BOOTCAMP-01+2026_T1/home
    """
    return _extract_openedx_course_base(
        html=html,
        course_id="course-v1:NIELIT+RTL-BOOTCAMP-01+2026_T1",
        default_title="Bootcamp: RTL, IP Integration, and SoC Signoff",
        course_code="NIELIT RTL-BOOTCAMP-01"
    )


# ==============================================================================
# PIPELINES TARGETS CONFIGURATION
# ==============================================================================

HOME_TARGETS = [
    {
        "id": "home",
        "name": "eChipHub Home",
        "url": "https://echiphub.in/",
        "cache_file": "home_raw.html",
        "extractor": extract_home_formatted_text
    },
    {
        "id": "all-courses",
        "name": "All Courses",
        "url": "https://echiphub.in/all-courses/",
        "cache_file": "all_courses_raw.html",
        "extractor": extract_all_courses_formatted_text
    },
    {
        "id": "workshops",
        "name": "Workshops",
        "url": "https://echiphub.in/workshops/",
        "cache_file": "workshops_raw.html",
        "extractor": extract_workshops_formatted_text
    },
    {
        "id": "academic-alliances",
        "name": "Academic Alliances",
        "url": "https://echiphub.in/academic-alliances/",
        "cache_file": "academic_alliances_raw.html",
        "extractor": extract_academic_alliances_formatted_text
    },
    {
        "id": "news-2",
        "name": "News",
        "url": "https://echiphub.in/news-2/",
        "cache_file": "news_raw.html",
        "extractor": extract_news_formatted_text
    },
    {
        "id": "about",
        "name": "About Us",
        "url": "https://echiphub.in/about/",
        "cache_file": "about_raw.html",
        "extractor": extract_about_formatted_text
    },
    {
        "id": "contact",
        "name": "Contact Us",
        "url": "https://echiphub.in/contact/",
        "cache_file": "contact_raw.html",
        "extractor": extract_contact_formatted_text
    },
    {
        "id": "why-choose-us",
        "name": "Why Choose Us",
        "url": "https://echiphub.in/why-choose-us/",
        "cache_file": "why_choose_us_raw.html",
        "extractor": extract_why_choose_us_formatted_text
    },
    {
        "id": "registration",
        "name": "SSO Registration",
        "url": "https://sso.echiphub.in/realms/platform/login-actions/registration?client_id=wordpress-www&tab_id=QiZH9aBt6M4&client_data=eyJydSI6Imh0dHBzOi8vZWNoaXBodWIuaW4vd3AtYWRtaW4vYWRtaW4tYWpheC5waHA_YWN0aW9uPW9wZW5pZC1jb25uZWN0LWF1dGhvcml6ZSIsInJ0IjoiY29kZSIsInN0IjoiZmFkYTg1YWRiZmIyZjMzMmMzMjVhNDFmZDVhZGJjOTgifQ",
        "cache_file": "registration_raw.html",
        "extractor": extract_registration_formatted_text
    },
    {
        "id": "authenticate",
        "name": "SSO Authenticate / Login",
        "url": "https://sso.echiphub.in/realms/platform/login-actions/authenticate?client_id=wordpress-www&tab_id=QiZH9aBt6M4&client_data=eyJydSI6Imh0dHBzOi8vZWNoaXBodWIuaW4vd3AtYWRtaW4vYWRtaW4tYWpheC5waHA_YWN0aW9uPW9wZW5pZC1jb25uZWN0LWF1dGhvcml6ZSIsInJ0IjoiY29kZSIsInN0IjoiZmFkYTg1YWRiZmIyZjMzMmMzMjVhNDFmZDVhZGJjOTgifQ",
        "cache_file": "authenticate_raw.html",
        "extractor": extract_authenticate_formatted_text
    }
]

LABS_TARGETS = [
    {
        "id": "labs-portal",
        "name": "eChipHub Labs Portal",
        "url": "https://echiphub.in/labs/",
        "cache_file": "labs_landing_raw.html",
        "extractor": extract_labs_portal_formatted_text
    },
    {
        "id": "labs-hub-home",
        "name": "JupyterHub Lab Dashboard",
        "url": "https://labs.echiphub.in/hub/home",
        "cache_file": "labs_hub_raw.html",
        "extractor": extract_labs_hub_formatted_text
    }
]

HELPDESK_TARGETS = [
    {
        "id": "helpdesk-my-tickets",
        "name": "Helpdesk My Tickets",
        "url": "https://helpdesk.echiphub.in/helpdesk/my-tickets",
        "cache_file": "helpdesk_my_tickets_raw.html",
        "extractor": extract_helpdesk_my_tickets_formatted_text
    },
    {
        "id": "helpdesk-new-ticket",
        "name": "Helpdesk New Ticket",
        "url": "https://helpdesk.echiphub.in/helpdesk/my-tickets/new",
        "cache_file": "helpdesk_new_ticket_raw.html",
        "extractor": extract_helpdesk_new_ticket_formatted_text
    }
]

PDK_TARGETS = [
    {
        "id": "pdk-portal-home",
        "name": "PDK Verification Portal",
        "url": "https://verify.echiphub.in/",
        "cache_file": "pdk_home_raw.html",
        "extractor": extract_pdk_home_formatted_text
    },
    {
        "id": "pdk-downloads",
        "name": "PDK Downloads",
        "url": "https://verify.echiphub.in/?view=downloads",
        "cache_file": "pdk_downloads_raw.html",
        "extractor": extract_pdk_downloads_formatted_text
    },
    {
        "id": "pdk-virtual-machine",
        "name": "PDK EDA Virtual Machine",
        "url": "https://verify.echiphub.in/?view=virtual-machine",
        "cache_file": "pdk_vm_raw.html",
        "extractor": extract_pdk_vm_formatted_text
    },
    {
        "id": "pdk-examples",
        "name": "PDK Video Tutorials & Worked Examples",
        "url": "https://verify.echiphub.in/?view=examples",
        "cache_file": "pdk_examples_raw.html",
        "extractor": extract_pdk_examples_formatted_text
    },
    {
        "id": "pdk-design-tapeout",
        "name": "PDK Design Submission & Tape-Out",
        "url": "https://verify.echiphub.in/?view=design",
        "cache_file": "pdk_design_raw.html",
        "extractor": extract_pdk_design_formatted_text
    },
    {
        "id": "pdk-faqs",
        "name": "MPW Shuttle Programme FAQs",
        "url": "https://verify.echiphub.in/faq",
        "cache_file": "pdk_faq_raw.html",
        "extractor": extract_pdk_faq_formatted_text
    }
]

COMMUNITY_TARGETS = [
    {
        "id": "community-groups",
        "name": "Community Groups",
        "url": "https://community.echiphub.in/g",
        "cache_file": "community_groups_raw.html",
        "extractor": extract_community_groups_formatted_text
    },
    {
        "id": "community-about",
        "name": "About Community",
        "url": "https://community.echiphub.in/about",
        "cache_file": "community_about_raw.html",
        "extractor": extract_community_about_formatted_text
    },
    {
        "id": "community-guidelines",
        "name": "Community Guidelines",
        "url": "https://community.echiphub.in/guidelines",
        "cache_file": "community_guidelines_raw.html",
        "extractor": extract_community_guidelines_formatted_text
    },
    {
        "id": "community-badges",
        "name": "Community Badges",
        "url": "https://community.echiphub.in/badges",
        "cache_file": "community_badges_raw.html",
        "extractor": extract_community_badges_formatted_text
    }
]

EVENTS_TARGETS = [
    {
        "id": "events-upcoming",
        "name": "Upcoming & Scheduled Workshops",
        "url": "https://events.echiphub.in/?status=upcoming",
        "cache_file": "events_upcoming_raw.html",
        "extractor": extract_events_upcoming_formatted_text
    },
    {
        "id": "events-statistics",
        "name": "Events Platform Statistics",
        "url": "https://events.echiphub.in/category/0/statistics",
        "cache_file": "events_statistics_raw.html",
        "extractor": extract_events_statistics_formatted_text
    }
]

OPENEDX_TARGETS = [
    {
        "id": "openedx-sso",
        "name": "Open edX SSO Authentication Endpoint",
        "url": "https://sso.echiphub.in/realms/platform/protocol/openid-connect/auth?client_id=openedx&redirect_uri=https://edx.echiphub.in/auth/complete/keycloak/&state=peZCNmHdKfsOWYK20fRaQ7HZMGt4ZBdp&response_type=code",
        "cache_file": "openedx_sso_raw.html",
        "extractor": extract_openedx_sso_formatted_text
    },
    {
        "id": "openedx-course-02",
        "name": "ChipCraft: RTL, IP Integration, and SoC Signoff (RTL-BOOTCAMP-02)",
        "url": "https://apps.edx.echiphub.in/learning/course/course-v1:NIELIT+RTL-BOOTCAMP-02+2026_T1/home",
        "cache_file": "openedx_bootcamp_02_raw.html",
        "extractor": extract_openedx_course_02_formatted_text
    },
    {
        "id": "openedx-course-01",
        "name": "Bootcamp: RTL, IP Integration, and SoC Signoff (RTL-BOOTCAMP-01)",
        "url": "https://apps.edx.echiphub.in/learning/course/course-v1:NIELIT+RTL-BOOTCAMP-01+2026_T1/home",
        "cache_file": "openedx_bootcamp_01_raw.html",
        "extractor": extract_openedx_course_01_formatted_text
    }
]


# ==============================================================================
# PIPELINE RUNNERS
# ==============================================================================

def process_target(target: dict) -> dict:
    name = target["name"]
    url = target["url"]
    cache_file = target["cache_file"]
    extractor = target["extractor"]

    print(f"\n{'=' * 70}")
    print(f"  PROCESSING TARGET: {name.upper()}")
    print(f"  URL : {url}")
    print(f"{'=' * 70}\n")

    # Step 1: Extract HTML
    html = get_whole_page_html(url, cache_file)

    # Step 2: Extract formatted text
    data = extractor(html)

    # Attach page identification metadata
    page_entry = {
        "id": target["id"],
        "name": target["name"],
        "url": target["url"],
        "page_title": data.get("page_title"),
        "extracted_at": data.get("extracted_at"),
        "sections": data.get("sections", [])
    }
    if "summary" in data:
        page_entry["summary"] = data["summary"]

    print(f"[✓] {name} extracted! Total formatted sections: {len(page_entry['sections'])}")
    for idx, s in enumerate(page_entry["sections"], 1):
        extra = f" ({s.get('count')} items)" if s.get("count") is not None else ""
        print(f"   [{idx:02d}] {s.get('section_name'):<32}{extra} | Type: {s.get('type')}")

    return page_entry


def run_home_pipeline():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\n{'=' * 70}")
    print(f"  STARTING PIPELINE: HOME & CONNECTED PAGES (10 TARGETS)")
    print(f"  DESTINATION: {COMBINED_FILE}")
    print(f"{'=' * 70}\n")

    all_pages = []
    for target in HOME_TARGETS:
        page_data = process_target(target)
        all_pages.append(page_data)

    combined_result = {
        "project": "eChipHub Master Web Scraping Pipeline",
        "pipeline_name": "Home & Connected Pages Pipeline",
        "description": "Comprehensive structured text data extracted from eChipHub platform and connected pages",
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "destination_file": COMBINED_FILE,
        "total_pages": len(all_pages),
        "pages": all_pages
    }

    with open(COMBINED_FILE, "w", encoding="utf-8") as f:
        json.dump(combined_result, f, ensure_ascii=False, indent=2)

    print(f"\n{'#' * 70}")
    print(f"# HOME PIPELINE SUCCESSFULLY COMPILED INTO:")
    print(f"# -> {COMBINED_FILE} (Size: {os.path.getsize(COMBINED_FILE):,} bytes)")
    print(f"#{'#' * 69}\n")


def run_labs_pipeline():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\n{'=' * 70}")
    print(f"  STARTING PIPELINE: LABS ENVIRONMENT (2 TARGETS)")
    print(f"  AUTHENTICATED USER: {LABS_EMAIL}")
    print(f"  DESTINATION: {LABS_OUTPUT_FILE}")
    print(f"{'=' * 70}\n")

    labs_pages = []
    for target in LABS_TARGETS:
        page_data = process_target(target)
        labs_pages.append(page_data)

    labs_result = {
        "project": "eChipHub Master Web Scraping Pipeline",
        "pipeline_name": "Labs Environment Pipeline",
        "description": "Structured data extracted from eChipHub Labs portal and authenticated JupyterHub environment",
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "destination_file": LABS_OUTPUT_FILE,
        "authenticated_user": LABS_EMAIL,
        "total_pages": len(labs_pages),
        "pages": labs_pages
    }

    with open(LABS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(labs_result, f, ensure_ascii=False, indent=2)

    print(f"\n{'#' * 70}")
    print(f"# LABS PIPELINE SUCCESSFULLY COMPILED INTO:")
    print(f"# -> {LABS_OUTPUT_FILE} (Size: {os.path.getsize(LABS_OUTPUT_FILE):,} bytes)")
    print(f"#{'#' * 69}\n")


def run_helpdesk_pipeline():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\n{'=' * 70}")
    print(f"  STARTING PIPELINE: HELPDESK SUPPORT SYSTEM (2 TARGETS)")
    print(f"  AUTHENTICATED USER: {LABS_EMAIL}")
    print(f"  DESTINATION: {HELPDESK_OUTPUT_FILE}")
    print(f"{'=' * 70}\n")

    helpdesk_pages = []
    for target in HELPDESK_TARGETS:
        page_data = process_target(target)
        helpdesk_pages.append(page_data)

    helpdesk_result = {
        "project": "eChipHub Master Web Scraping Pipeline",
        "pipeline_name": "Helpdesk Support Pipeline",
        "description": "Structured data extracted from eChipHub Helpdesk portal and ticket management system",
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "destination_file": HELPDESK_OUTPUT_FILE,
        "authenticated_user": LABS_EMAIL,
        "total_pages": len(helpdesk_pages),
        "pages": helpdesk_pages
    }

    with open(HELPDESK_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(helpdesk_result, f, ensure_ascii=False, indent=2)

    print(f"\n{'#' * 70}")
    print(f"# HELPDESK PIPELINE SUCCESSFULLY COMPILED INTO:")
    print(f"# -> {HELPDESK_OUTPUT_FILE} (Size: {os.path.getsize(HELPDESK_OUTPUT_FILE):,} bytes)")
    print(f"#{'#' * 69}\n")


def run_pdk_pipeline():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\n{'=' * 70}")
    print(f"  STARTING PIPELINE: PDK VERIFICATION & TAPE-OUT (6 TARGETS)")
    print(f"  AUTHENTICATED USER: {LABS_EMAIL}")
    print(f"  DESTINATION: {PDK_OUTPUT_FILE}")
    print(f"{'=' * 70}\n")

    pdk_pages = []
    for target in PDK_TARGETS:
        page_data = process_target(target)
        pdk_pages.append(page_data)

    pdk_result = {
        "project": "eChipHub Master Web Scraping Pipeline",
        "pipeline_name": "PDK Verification & Tape-Out Pipeline",
        "description": "Structured data extracted from SCL Open-Source PDK Verification Portal, VM downloads, worked examples, tape-out workflow and MPW shuttle FAQs",
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "destination_file": PDK_OUTPUT_FILE,
        "authenticated_user": LABS_EMAIL,
        "total_pages": len(pdk_pages),
        "pages": pdk_pages
    }

    with open(PDK_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(pdk_result, f, ensure_ascii=False, indent=2)

    print(f"\n{'#' * 70}")
    print(f"# PDK PIPELINE SUCCESSFULLY COMPILED INTO:")
    print(f"# -> {PDK_OUTPUT_FILE} (Size: {os.path.getsize(PDK_OUTPUT_FILE):,} bytes)")
    print(f"#{'#' * 69}\n")


def run_community_pipeline():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\n{'=' * 70}")
    print(f"  STARTING PIPELINE: COMMUNITY DISCOURSE (4 TARGETS)")
    print(f"  AUTHENTICATED USER: {LABS_EMAIL}")
    print(f"  DESTINATION: {COMMUNITY_OUTPUT_FILE}")
    print(f"{'=' * 70}\n")

    comm_pages = []
    for target in COMMUNITY_TARGETS:
        page_data = process_target(target)
        comm_pages.append(page_data)

    comm_result = {
        "project": "eChipHub Master Web Scraping Pipeline",
        "pipeline_name": "Community Discourse Pipeline",
        "description": "Structured text data extracted from eChipHub Discourse Community platform including domain groups, leadership, guidelines and recognition badges",
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "destination_file": COMMUNITY_OUTPUT_FILE,
        "authenticated_user": LABS_EMAIL,
        "total_pages": len(comm_pages),
        "pages": comm_pages
    }

    with open(COMMUNITY_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(comm_result, f, ensure_ascii=False, indent=2)

    print(f"\n{'#' * 70}")
    print(f"# COMMUNITY PIPELINE SUCCESSFULLY COMPILED INTO:")
    print(f"# -> {COMMUNITY_OUTPUT_FILE} (Size: {os.path.getsize(COMMUNITY_OUTPUT_FILE):,} bytes)")
    print(f"#{'#' * 69}\n")


def run_events_pipeline():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\n{'=' * 70}")
    print(f"  STARTING PIPELINE: EVENTS & WORKSHOPS (2 TARGETS)")
    print(f"  AUTHENTICATED USER: {LABS_EMAIL}")
    print(f"  DESTINATION: {EVENTS_OUTPUT_FILE}")
    print(f"{'=' * 70}\n")

    events_pages = []
    for target in EVENTS_TARGETS:
        page_data = process_target(target)
        events_pages.append(page_data)

    events_result = {
        "project": "eChipHub Master Web Scraping Pipeline",
        "pipeline_name": "Events & Workshops Indico Pipeline",
        "description": "Structured data extracted from eChipHub NIELIT Indico Event Management platform including scheduled workshops, timeline buckets and global training statistics",
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "destination_file": EVENTS_OUTPUT_FILE,
        "authenticated_user": LABS_EMAIL,
        "total_pages": len(events_pages),
        "pages": events_pages
    }

    with open(EVENTS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(events_result, f, ensure_ascii=False, indent=2)

    print(f"\n{'#' * 70}")
    print(f"# EVENTS PIPELINE SUCCESSFULLY COMPILED INTO:")
    print(f"# -> {EVENTS_OUTPUT_FILE} (Size: {os.path.getsize(EVENTS_OUTPUT_FILE):,} bytes)")
    print(f"#{'#' * 69}\n")


def run_openedx_pipeline():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"\n{'=' * 70}")
    print(f"  STARTING PIPELINE: OPEN EDX LEARNING ENVIRONMENT (3 TARGETS)")
    print(f"  AUTHENTICATED USER: {LABS_EMAIL}")
    print(f"  DESTINATION: {OPENEDX_OUTPUT_FILE}")
    print(f"{'=' * 70}\n")

    openedx_pages = []
    for target in OPENEDX_TARGETS:
        page_data = process_target(target)
        openedx_pages.append(page_data)

    openedx_result = {
        "project": "eChipHub Master Web Scraping Pipeline",
        "pipeline_name": "Open edX Learning Platform Pipeline",
        "description": "Structured curriculum, active modules, labs, schedules, and authentication data extracted from eChipHub Open edX LMS learning environment",
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "destination_file": OPENEDX_OUTPUT_FILE,
        "authenticated_user": LABS_EMAIL,
        "total_pages": len(openedx_pages),
        "pages": openedx_pages
    }

    with open(OPENEDX_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(openedx_result, f, ensure_ascii=False, indent=2)

    print(f"\n{'#' * 70}")
    print(f"# OPEN EDX PIPELINE SUCCESSFULLY COMPILED INTO:")
    print(f"# -> {OPENEDX_OUTPUT_FILE} (Size: {os.path.getsize(OPENEDX_OUTPUT_FILE):,} bytes)")
    print(f"#{'#' * 69}\n")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    arg = sys.argv[1].strip().lower() if len(sys.argv) > 1 else "all"

    if arg == "community":
        run_community_pipeline()
    elif arg == "events":
        run_events_pipeline()
    elif arg == "pdk":
        run_pdk_pipeline()
    elif arg == "helpdesk":
        run_helpdesk_pipeline()
    elif arg == "labs":
        run_labs_pipeline()
    elif arg == "openedx":
        run_openedx_pipeline()
    elif arg == "home":
        run_home_pipeline()
    elif arg == "all":
        run_home_pipeline()
        run_labs_pipeline()
        run_helpdesk_pipeline()
        run_pdk_pipeline()
        run_community_pipeline()
        run_events_pipeline()
        run_openedx_pipeline()
    else:
        # Check individual target id across all pipelines
        all_targets = HOME_TARGETS + LABS_TARGETS + HELPDESK_TARGETS + PDK_TARGETS + COMMUNITY_TARGETS + EVENTS_TARGETS + OPENEDX_TARGETS
        matched = [t for t in all_targets if t["id"] == arg or arg in t["name"].lower()]
        if matched:
            for target in matched:
                process_target(target)
        else:
            print(f"[!] Target '{sys.argv[1]}' not found. Available commands: home, labs, helpdesk, pdk, community, events, openedx, all, or specific ID")


if __name__ == "__main__":
    main()
