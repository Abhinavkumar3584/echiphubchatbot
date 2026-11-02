"""FILTER RULES - the only file you need to edit to change what ends up in the clean data.

Every page found is put in exactly one of four groups:
    keep        Real / useful            -> goes into output/sites/*.json and output/pages/
    unwanted    Unwanted (removed)       -> demo content, templates, empty/test pages, account pages ...
    duplicate   Same content, other link -> only the best link of each group is kept
    broken      Broken / inaccessible    -> 404, failed to load, needs login, shows the home page instead

Rules 1-3 work on the LINK (before the page is opened, so time is saved and nothing is clicked by accident).
Rules 4-7 work on the CONTENT (after the page is read). Rule 8 decides which link wins among duplicates.
After changing anything here, run:  python extract.py build   (no internet needed, uses what was already read)
"""

# ---------------------------------------------------------------------------------------------------------
# 1. NEVER OPEN - links that do something (log out, add to cart, delete...) or show other people's data.
#    If any of these texts appears anywhere in the link (lower case), the link is never opened.
# ---------------------------------------------------------------------------------------------------------
NEVER_OPEN = [
    # session / admin
    "logout", "log-out", "logoff", "signout", "sign-out", "wp-admin", "wp-login", "/admin", "/manage",
    "/dashboard", "action=", "delete", "trash", "_wpnonce", "/edit", "preview=", "/settings", "/account",
    "/session/", "/auth/", "/login", "/signin", "/register", "/authn/", "next=", "/password",
    # shop actions (they CHANGE the cart of the logged-in user)
    "add-to-cart", "add_to_cart", "remove_item", "undo_item", "wc-ajax", "add_to_wishlist", "/cart", "/checkout",
    "/orders",
    # other people's personal data
    "/registrations", "/participants", "/surveys", "/abstracts/", "/members/", "/u/", "/users/", "/profile",
    "/my/", "/badges/",
    # endless / technical lists
    "/new-topic", "/new-message", ".ics", "/calendar", "/statistics", "period=", "view=", "/timetable/",
    "/category/0/", "replytocom=", "/feed", "/wp-json", "xmlrpc", "/search", "?page=", "&page=", "print=",
    "status=", "/tag/", "/tags/",
]

# ---------------------------------------------------------------------------------------------------------
# 2. REMOVED FROM LINKS - parts of a link that only sort, track or share. They are cut off, so
#    /shop?products-orderby=price and /shop become the same link and the page is read only once.
#    "*" = every site; otherwise the platform name from SITES in extract.py.
# ---------------------------------------------------------------------------------------------------------
STRIP_PARAMS = {
    "*": ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref"],
    "wordpress": ["products-order", "products-orderby", "orderby", "order", "product_view", "shop_view",
                  "per_page", "lang"],
    "discourse": ["u"],                        # ?u=<username> share links of the logged-in user
}

# ---------------------------------------------------------------------------------------------------------
# 3. UNWANTED LINKS - known junk, per website. Not opened; listed in the report as "unwanted" with the reason.
#    Each rule: (regular expression matched against the path + query, e.g. "/course/yoga?x=1", reason).
#    If you later publish REAL pages under one of these paths, delete that rule (or use ALWAYS_KEEP).
# ---------------------------------------------------------------------------------------------------------
UNWANTED_URLS = {
    "echiphub.in": [
        (r"[?&]elementor_library=",                       "Elementor builder template, not a page"),
        (r"^/elementor-hf/",                              "Elementor header/footer template"),
        (r"^/form(/|$)",                                  "form plugin record, not a page"),
        (r"[?&]post_type=",                               "internal WordPress record"),
        (r"^/navigation(-\d+)*/?$",                       "internal WordPress menu record"),
        (r"^/(lesson|quiz|section|mto-question)(/|$)",    "course-plugin demo item (opens the home page)"),
        (r"^/learn(/|$)",                                 "course-plugin player (blank page)"),
        (r"^/courses?(/|$)",                              "course-plugin demo course (guitar, yoga, ...)"),
        (r"^/course-category(/|$)",                       "course-plugin demo category"),
        (r"^/category/",                                  "blog category of theme demo posts"),
        (r"^/author/",                                    "author archive"),
        (r"^/(my-account|my-purchased-courses|customer-dashboard|customer-cabinet)(/|$)",
                                                          "account page (no public content)"),
        (r"^/my-course/?$",                               "template page with placeholder numbers"),
        (r"^/wp-content/",                                "uploaded file, not a page"),
    ],
    "events.echiphub.in": [],
    "community.echiphub.in": [],
    "edx.echiphub.in": [],
    "labs.echiphub.in": [],
}

# Links that are ALWAYS kept, even if rule 3 or the content rules say otherwise (still dropped if broken).
ALWAYS_KEEP = [
    # "https://echiphub.in/some-short-page",
]

# ---------------------------------------------------------------------------------------------------------
# 4. ACCESS - the chatbot answers anonymous visitors, so pages only visible after login are left out.
#    Set to False to keep login-only pages too.
# ---------------------------------------------------------------------------------------------------------
PUBLIC_ONLY = True

# ---------------------------------------------------------------------------------------------------------
# 5. TEXT REMOVED FROM EVERY PAGE (menus, pop-ups, cart panels ...). Regular expressions, per platform.
#    On top of this, any block of text found on most pages of a site is removed automatically (rule 7).
# ---------------------------------------------------------------------------------------------------------
BOILERPLATE_PATTERNS = {
    "*": [
        r"(?m)^\s*\[?\s*Skip to (main )?content\s*\]?(\([^)]*\))?\s*$",
        r"(?m)^\s*(\[\s*\]\([^)]*\)\s*)+$",                                          # empty links (icons)
    ],
    "wordpress": [
        r"(?s)#{1,6}\s*Important Disclaimer\s*\n.*?\bI agree\b[^\n]*",                 # lab disclaimer pop-up
        r"(?s)Review My Order\s*0?\s*Subtotal\s*Taxes & shipping calculated at checkout\s*"
        r"(\[\s*Checkout\s*\]\([^)]*\))?\s*0?",                                          # mini-cart panel
        r"(?m)^.*has been added to your cart\..*$",
        r"(?m)^\s*Your browser does not support the video tag\.\s*$",
        r"(?m)^\s*Select View:\s*$",
        r"(?s)#{1,6}\s*Related products\b.*?(?=\n#{1,2}\s|\Z)",                       # shop: other products
        r"\[\s*Add to cart\s*\]\([^)]*\)",
        r"(?m)^\s*\*?\s*\[\s*(Description|Reviews \(\d+\)|Additional information)\s*\]\([^)]*#tab-[^)]*\)\s*$",
        r"(?m)^\s*There are no reviews yet\.\s*$",
        r"(?m)^\s*Be the first to review .*$",
    ],
    "indico": [
        r"(?s)#{1,6}\s*Choose timezone\s*\n.*?\[Back to eChipHub\]\([^)]*\)\s*",       # timezone/language/menu
        r"(?m)^\*?\s*A \*\*(lecture|meeting|conference)\*\* is .*$",
        r"(?m)^\*\*Features\*\* :.*$",
        r"(?m)^\s*\[ Create (lecture|meeting|conference) \]\([^)]*\)\s*$",
        r"(?m)^\s*(PrintPDFFull screenDetailed viewFilter|Updating the timetable\.\.\.)\s*$",
        r"(?m)^\|\s*Filter options\s*\|.*$",
        r"(?m)^\s*AllUpcomingLiveCompleted\s*$",
    ],
    "discourse": [
        r"(?m)^\s*You have selected \*\*0\*\* posts\.\s*$",
        r"(?m)^\s*\[\s*(select all|cancel selecting)\s*\]\([^)]*\)\s*$",
        r"(?m)^\s*Share Bookmark Mark unread\s*$",
        r"(?m)^\s*Reply\s*$",
        r"(?m)^\s*Normal\s+You will be notified.*$",
        r"(?s)#{1,6}\s*(New & Unread Topics|Suggested Topics|Related Topics).*",       # lists at the end
        r"(?m)^#{1,6}\s*Want to read more\?.*$",
        r'(?m)^\s*\[\s*\d+[smhdwy]\s*\]\([^)]*"Post date"\)\s*$',                  # "[ 14d ](...)" post age
        r"(?m)^\s*\[\s*\d*\s*\]\([^)]*/u/[^)]*\)\s*$",                                  # avatar links
        r"(?m)^\s*\d+ views?\s*$",
    ],
    "openedx": [],
}

# A page that shows the site's home page instead of its own content is broken ("soft 404").
# Only for platforms that do this for missing pages (WordPress). On Discourse, /categories = home is normal.
SOFT_404_PLATFORMS = ["wordpress"]

# ---------------------------------------------------------------------------------------------------------
# 6. CONTENT RULES - a page is "unwanted" if, after cleaning, it ...
# ---------------------------------------------------------------------------------------------------------
MIN_WORDS = 20                 # ... has fewer words than this (empty / almost empty page)
LOREM_SHARE = 0.03             # ... is more than 3% Lorem-ipsum words (theme demo text)
PLACEHOLDER_PHRASES = [        # ... contains one of these (default/sample content)
    "Welcome to WordPress. This is your first post",
    "This is an example page",
    "Hi, this is a comment.",
]
TEST_TITLE = r"^\s*(test|testing|demo|dummy|sample)\b"    # ... has a title starting with one of these words
EMPTY_PLACEHOLDERS = [         # ... says it has nothing yet AND has fewer than EMPTY_PLACEHOLDER_WORDS words
    "There are no materials yet",
    "No institutions yet",
]
EMPTY_PLACEHOLDER_WORDS = 60

# ---------------------------------------------------------------------------------------------------------
# 7. AUTOMATIC BOILERPLATE - a section or line that appears on at least this share of a site's pages
#    is site-wide decoration (menus, footers, pop-ups) and is removed from every page of that site.
# ---------------------------------------------------------------------------------------------------------
AUTO_BOILERPLATE_SHARE = 0.5
AUTO_BOILERPLATE_MIN_PAGES = 6     # only for sites with at least this many pages
AUTO_BOILERPLATE_MIN_CHARS = 15    # shorter lines are left alone

# ---------------------------------------------------------------------------------------------------------
# 8. DUPLICATES - pages whose cleaned text is the same (link targets ignored), or at least this similar,
#    are one page. The link kept is: in REQUIRED_URLS > a start page > no "?" > fewest "/" > shortest.
# ---------------------------------------------------------------------------------------------------------
NEAR_DUPLICATE = 0.90
