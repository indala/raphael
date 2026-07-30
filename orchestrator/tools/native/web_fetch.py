"""Web fetch tool — fetch and extract readable text from URLs."""

from actions.web_fetch import _web_fetch_multi
from actions.web_fetch import web_fetch as _web_fetch


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description": "Fetch a URL and extract readable text content. Handles both static HTML and JavaScript-rendered pages. Use this after web_search to read full articles, documentation, or API responses.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to fetch (http:// or https://)",
                        },
                        "max_length": {
                            "type": "integer",
                            "description": "Maximum characters to return (default 8000). Use larger values (12000-16000) for documentation or code.",
                        },
                        "content_mode": {
                            "type": "string",
                            "enum": ["auto", "summary", "article", "doc", "full"],
                            "description": "Preset for content length: auto (detect from URL), summary (2k), article (8k), doc (12k), full (16k). Overrides max_length if provided.",
                        },
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_fetch_multi",
                "description": "Fetch multiple URLs in parallel. Use when you need content from several sources at once — faster than calling web_fetch repeatedly.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of URLs to fetch (2-5 recommended per batch)",
                        },
                        "content_mode": {
                            "type": "string",
                            "enum": ["auto", "summary", "article", "doc", "full"],
                            "description": "Content mode applied to all URLs (default: article)",
                        },
                    },
                    "required": ["urls"],
                },
            },
        },
    ]


def web_fetch(url: str, max_length: int = 8000, content_mode: str = "auto") -> str:
    """Fetch a URL and extract readable text content."""
    return _web_fetch(url, max_length, content_mode=content_mode)


def web_fetch_multi(urls: list[str], content_mode: str = "article") -> str:
    """Fetch multiple URLs in parallel. Returns concatenated results."""
    return _web_fetch_multi(urls, content_mode=content_mode)
