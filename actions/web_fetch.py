"""
Web Fetch — fetch and extract readable text content from URLs.
Results are cached in-memory for 5 minutes to avoid re-downloading.

Tiered backends:
1. requests + html.parser (stdlib, fast)
2. BeautifulSoup4 (better text extraction if installed)
3. Playwright (JavaScript-rendered pages)
"""

import logging
import re
import time

from actions._web_cache import get as _cache_get, set as _cache_set

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 15
_MAX_TEXT_LENGTH = 8000  # Truncate to avoid blowing context
_FETCH_TTL = 300  # 5 minutes

# ── Content-mode presets ───────────────────────────────────────────
CONTENT_MODES = {
    "summary": 2_000,    # Short snippet — search results, quick lookups
    "article": 8_000,    # Full article — news, blog posts (default)
    "doc":     12_000,   # Documentation — API refs, guides, code examples
    "full":    16_000,   # Heavy content — research papers, specs
}


def _detect_content_mode(url: str) -> str:
    """Heuristic to guess content mode from URL structure."""
    url_lower = url.lower()
    # Documentation / code
    if any(d in url_lower for d in ["docs.", "/docs/", "/api/", "github.com",
                                      "readthedocs", "mdn.", "wiki.",
                                      "stackoverflow", "developer."]):
        return "doc"
    # Short-form / search
    if any(s in url_lower for s in ["google.com/search", "bing.com/search",
                                     "duckduckgo.com", "search."]):
        return "summary"
    # Full-length content
    if any(f in url_lower for f in ["arxiv.org", "research.", "pdf",
                                     "spec", "standard"]):
        return "full"
    return "article"


def _fetch_requests(url: str) -> str | None:
    """Fetch page content via httpx (fast async/sync HTTP) with requests fallback."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br, zstd",
    }
    try:
        import httpx
        with httpx.Client(follow_redirects=True, timeout=_REQUEST_TIMEOUT, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as me:
        logger.debug("httpx fetch failed (%s), trying requests fallback...", me)
        import requests
        resp = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT, allow_redirects=True)  # type: ignore[assignment]
        resp.raise_for_status()
        return resp.text


def _fetch_playwright(url: str) -> str | None:
    """Fetch page content via Playwright (handles JS-rendered pages)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("Playwright not available")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=_REQUEST_TIMEOUT * 1000)
            # Wait a bit for JS to render
            page.wait_for_timeout(2000)
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        logger.debug("Playwright fetch failed: %s", e)
        return None


def _extract_text_plain(html: str) -> str:
    """Extract text from HTML using stdlib html.parser."""
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self._text = []
            self._skip = False
            self._skip_tags = {"script", "style", "noscript", "svg", "iframe"}

        def handle_starttag(self, tag, attrs):
            if tag in self._skip_tags:
                self._skip = True

        def handle_endtag(self, tag):
            if tag in self._skip_tags:
                self._skip = False

        def handle_data(self, data):
            if not self._skip:
                stripped = data.strip()
                if stripped:
                    self._text.append(stripped)

        def result(self):
            return "\n".join(self._text)

    extractor = TextExtractor()
    extractor.feed(html)
    return extractor.result()  # type: ignore[no-any-return]


def _extract_text_soup(html: str) -> str:
    """Extract text from HTML using BeautifulSoup4 (better quality)."""
    try:
        import importlib
        BeautifulSoup = importlib.import_module("bs4").BeautifulSoup
    except ImportError:
        return None  # type: ignore[return-value]  # Signal fallback

    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "noscript", "svg", "iframe",
                     "nav", "header", "footer", "aside", "form"]):
        tag.decompose()

    # Try main/article first for better content
    main = soup.find("main") or soup.find("article") or soup.find("body") or soup
    text = main.get_text(separator="\n", strip=True)
    return text  # type: ignore[no-any-return]


def _clean_text(text: str) -> str:
    """Normalize whitespace and collapse repeated blank lines."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def web_fetch(url: str, max_length: int = _MAX_TEXT_LENGTH, content_mode: str = "auto") -> str:
    """
    Fetch a URL and extract readable text content.

    Tries requests + html.parser first, then BeautifulSoup if available,
    then Playwright for JS-heavy pages. Results cached for 5 minutes.

    Args:
        url: The URL to fetch.
        max_length: Maximum characters to return (default 8000).
        content_mode: Preset for max_length — "auto" (detect from URL),
                      "summary" (2k), "article" (8k), "doc" (12k), or "full" (16k).
                      Overrides max_length if set.

    Returns:
        Extracted text content or error message.
    """
    if content_mode in CONTENT_MODES:
        max_length = CONTENT_MODES[content_mode]
    elif content_mode == "auto":
        guessed = _detect_content_mode(url)
        max_length = CONTENT_MODES.get(guessed, max_length)

    if not url or not url.strip():
        return "Please provide a URL."

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Check cache
    cached = _cache_get(url)
    if cached is not None:
        logger.info("WebFetch: cache hit for %s", url)
        return cached

    logger.info("WebFetch: Fetching %s", url)
    start = time.time()

    # Tier 1: requests + fast extraction
    html = _fetch_requests(url)
    if html is None:
        return f"Failed to fetch {url}"

    # Try BeautifulSoup extraction first (better quality)
    text = _extract_text_soup(html)
    if text is None:
        # Fallback to stdlib html.parser
        text = _extract_text_plain(html)  # type: ignore[unreachable]

    # If extracted text is too short, might be JS-rendered — try Playwright
    if len(text) < 200:
        logger.info("WebFetch: Short text (%d chars), trying Playwright", len(text))
        js_html = _fetch_playwright(url)
        if js_html:
            js_text = _extract_text_soup(js_html)
            if js_text and len(js_text) > len(text):
                text = js_text

    text = _clean_text(text)
    elapsed = time.time() - start

    if not text:
        return f"Fetched {url} but no readable content found."

    # Truncate if needed
    if len(text) > max_length:
        text = text[:max_length] + f"\n\n[...truncated ({len(text) - max_length} more chars)]"

    _cache_set(url, text, _FETCH_TTL)
    logger.info("WebFetch: %d chars from %s in %.1fs (mode=%s)", len(text), url, elapsed, content_mode)
    return text


def _web_fetch_multi(urls: list[str], content_mode: str = "article",
                      max_concurrent: int = 5) -> str:
    """Fetch multiple URLs in parallel. Returns concatenated results."""
    import concurrent.futures

    if not urls:
        return "No URLs provided."

    urls = [u.strip() for u in urls if u.strip()]
    if len(urls) > max_concurrent:
        logger.warning("web_fetch_multi: limiting %d URLs to %d", len(urls), max_concurrent)
        urls = urls[:max_concurrent]

    results: list[tuple[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(urls)) as pool:
        future_map = {pool.submit(web_fetch, u, content_mode=content_mode): u for u in urls}
        for future in concurrent.futures.as_completed(future_map):
            url = future_map[future]
            try:
                text = future.result()
                results.append((url, text))
            except Exception as e:
                results.append((url, f"Error: {e}"))

    # Return in original order
    seen = set()
    parts = []
    for url in urls:
        matched = [r for r in results if r[0] == url and url not in seen]
        if matched:
            seen.add(url)
            text = matched[0][1]
            parts.append(f"--- {url} ({len(text)} chars) ---\n{text}")

    combined = "\n\n".join(parts)
    logger.info("WebFetchMulti: %d/%d URLs fetched, %d total chars (mode=%s)",
                len(parts), len(urls), len(combined), content_mode)
    return combined
