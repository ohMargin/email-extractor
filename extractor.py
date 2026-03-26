"""
Email extraction and official email scoring logic.
"""

import html as html_module
import logging
import re
import time
import random
from urllib.parse import urljoin, urlparse
from typing import Optional

import requests
import tldextract
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "qq.com", "163.com", "126.com", "sina.com", "sohu.com",
    "foxmail.com", "icloud.com", "live.com", "msn.com",
}

# 明确的非联系类服务域名（监控、CDN、基础设施等），直接排除
SERVICE_DOMAINS = {
    "sentry.io", "ingest.sentry.io",
    "amazonaws.com", "cloudfront.net", "fastly.net",
    "sendgrid.net", "mailchimp.com", "mailgun.org",
    "bounce.com", "noreply.com",
    "googlemail.com", "google.com",
    "facebook.com", "instagram.com", "twitter.com",
    "w3.org", "schema.org", "example.com",
}

# 明确排除的本地部分（无回复类）
NOREPLY_PREFIXES = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "bounce", "mailer-daemon", "postmaster",
}

OFFICIAL_PREFIXES = {
    "info", "contact", "admin", "hello", "support",
    "office", "mail", "service", "enquiry", "enquiries",
    "sales", "help", "team", "pr", "media", "press",
}

CONTACT_SUBPATHS = [
    "/contact", "/contact-us", "/contactus", "/contact_us",
    "/about", "/about-us", "/aboutus",
    "/reach-us", "/get-in-touch", "/connect",
    "/imprint", "/impressum",
]

REQUEST_TIMEOUT = 12  # seconds

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def _fetch_page(url: str, session: requests.Session) -> Optional[str]:
    """Fetch a single URL and return its HTML text, or None on failure."""
    try:
        resp = session.get(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        log.info("  GET %s -> %d (%d bytes)", url, resp.status_code, len(resp.content))
        if resp.status_code == 200:
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        else:
            log.info("  Skipping %s (status %d)", url, resp.status_code)
    except Exception as e:
        log.info("  Failed %s: %s", url, e)
    return None


def _decode_obfuscated(text: str) -> str:
    """
    Decode common email obfuscation techniques so the regex can find them.

    Handles:
    1. HTML entity encoding  — info&#64;example&#46;com  -> info@example.com
    2. [at] / (at) style     — info [at] example [dot] com -> info@example.com
    3. Unicode @-lookalike   — normalised by html.unescape already
    """
    # Step 1: decode HTML entities (&#64; -> @, &#46; -> ., &amp; etc.)
    text = html_module.unescape(text)

    # Step 2: decode [at] / (at) / " at " style obfuscation
    text = re.sub(r"\s*[\(\[]\s*at\s*[\)\]]\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+at\s+", "@", text, flags=re.IGNORECASE)

    # Step 3: decode [dot] / (dot) style
    text = re.sub(r"\s*[\(\[]\s*dot\s*[\)\]]\s*", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+dot\s+", ".", text, flags=re.IGNORECASE)

    return text


def _extract_jsonld_emails(html: str) -> set[str]:
    """
    Extract emails that appear as explicit "email" field values in JSON-LD
    structured data. These are the most authoritative source — the site owner
    deliberately published them as contact info.
    """
    import json

    jsonld_emails: set[str] = set()
    soup = BeautifulSoup(html, "lxml")

    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() == "email" and isinstance(v, str):
                    addr = v.strip().lower()
                    if EMAIL_REGEX.fullmatch(addr):
                        jsonld_emails.add(addr)
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            _walk(data)
        except Exception:
            pass

    return jsonld_emails


def _extract_emails_from_html(html: str) -> tuple[set[str], set[str]]:
    """
    Extract all email addresses from HTML source.

    Returns
    -------
    (all_emails, jsonld_emails)
      all_emails   : every email found by any strategy
      jsonld_emails: subset that came from JSON-LD "email" fields (highest trust)
    """
    emails: set[str] = set()

    def _add_all(text: str) -> None:
        for match in EMAIL_REGEX.findall(text):
            emails.add(match.lower())

    # Strategy 1: raw HTML text (plain @, JS blocks, inline JSON)
    _add_all(html)

    # Strategy 2 & 3: HTML entity + [at]/[dot] deobfuscation
    _add_all(_decode_obfuscated(html))

    soup = BeautifulSoup(html, "lxml")

    # Strategy 4: explicit mailto: links
    for tag in soup.find_all("a", href=True):
        href: str = tag["href"]
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?")[0].strip().lower()
            if EMAIL_REGEX.fullmatch(addr):
                emails.add(addr)

    # Strategy 5: JSON-LD "email" fields (authoritative)
    jsonld_emails = _extract_jsonld_emails(html)
    emails |= jsonld_emails

    return emails, jsonld_emails


def _get_main_domain(url: str) -> str:
    """Return the registered domain (e.g. 'example.com') from a URL."""
    ext = tldextract.extract(url)
    return f"{ext.domain}.{ext.suffix}".lower()


_HEX_HASH_RE = re.compile(r"^[0-9a-f]{16,}$")  # 16+ 位纯十六进制 = 系统哈希


def _is_junk_email(local: str, domain: str) -> bool:
    """Return True if this email is clearly a system/service address, not a contact."""
    # 已知服务域名
    for sd in SERVICE_DOMAINS:
        if domain == sd or domain.endswith("." + sd):
            return True
    # 无回复前缀
    if local in NOREPLY_PREFIXES:
        return True
    # 本地部分是哈希值（监控/事务型邮箱特征）
    if _HEX_HASH_RE.match(local):
        return True
    # 本地部分极长（>40 字符），通常是系统生成的
    if len(local) > 40:
        return True
    return False


def _score_email(
    email: str,
    main_domain: str,
    page_weights: dict[str, int],
    from_jsonld: bool = False,
) -> int:
    """
    Score an email address on how likely it is to be the official contact.

    Parameters
    ----------
    email        : the email address (lowercased)
    main_domain  : registered domain of the target site, e.g. 'example.com'
    page_weights : {email: cumulative_page_weight}
    from_jsonld  : True if found in a JSON-LD "email" field (highest trust)
    """
    local, _, domain = email.partition("@")

    # 系统/服务邮箱直接给极低分
    if _is_junk_email(local, domain):
        return -999

    score = 0

    # JSON-LD "email" 字段是网站主动声明的官方联系方式，给最高加分
    if from_jsonld:
        score += 80

    # Domain match
    if domain == main_domain or domain.endswith("." + main_domain):
        score += 50
    elif domain in FREE_EMAIL_DOMAINS:
        score -= 30

    # Official prefix
    if local in OFFICIAL_PREFIXES:
        score += 20

    # Page weight (contact/about pages score higher)
    score += page_weights.get(email, 0)

    return score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_emails_from_site(url: str) -> dict:
    """
    Crawl *url* and its common contact sub-pages, collect all emails,
    score each one, and return a structured result dict.

    Returns
    -------
    {
        "url": str,
        "status": "ok" | "error",
        "error": str | None,
        "official_email": str | None,
        "all_emails": [
            {"email": str, "score": int, "pages": [str, ...]},
            ...
        ],
    }
    """
    result: dict = {
        "url": url,
        "status": "ok",
        "error": None,
        "official_email": None,
        "all_emails": [],
    }

    # Normalise URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
        result["url"] = url

    main_domain = _get_main_domain(url)
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    # {email -> {page_url, ...}}
    email_pages: dict[str, set[str]] = {}
    # emails explicitly declared in JSON-LD "email" fields
    jsonld_email_set: set[str] = set()

    with requests.Session() as session:
        # Pages to visit: main URL + contact-like sub-paths
        pages_to_visit: list[tuple[str, int]] = [(url, 5)]  # (url, page_weight)
        for sub in CONTACT_SUBPATHS:
            pages_to_visit.append((urljoin(base, sub), 15))

        fetched_urls: set[str] = set()

        for page_url, page_weight in pages_to_visit:
            if page_url in fetched_urls:
                continue
            fetched_urls.add(page_url)

            html = _fetch_page(page_url, session)
            if not html:
                continue

            found, jsonld_found = _extract_emails_from_html(html)
            jsonld_email_set |= jsonld_found
            for em in found:
                email_pages.setdefault(em, set()).add(page_url)

            # Brief pause to be polite
            time.sleep(random.uniform(0.3, 0.8))

    if not email_pages:
        result["status"] = "ok"
        result["error"] = "No emails found on this site."
        return result

    # Build page_weights map: sum of page_weight for each page the email appeared on
    page_weight_map: dict[str, int] = {}
    for em, pages in email_pages.items():
        w = 0
        for pu in pages:
            is_contact = any(sub in pu.lower() for sub in CONTACT_SUBPATHS)
            w += 15 if is_contact else 5
        page_weight_map[em] = w

    # Score all emails
    scored = []
    for em, pages in email_pages.items():
        s = _score_email(
            em, main_domain, page_weight_map,
            from_jsonld=(em in jsonld_email_set),
        )
        scored.append({
            "email": em,
            "score": s,
            "pages": sorted(pages),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    result["all_emails"] = scored
    result["official_email"] = scored[0]["email"] if scored else None

    return result
