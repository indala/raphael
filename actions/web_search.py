"""
Web Search — DuckDuckGo primary search.
No API keys required. Returns formatted results that the LLM can process.
Results are cached in-memory for 2 minutes to avoid redundant queries.
"""

import logging

from actions._web_cache import get as _cache_get, set as _cache_set

logger = logging.getLogger(__name__)

_SEARCH_TTL = 120  # 2 minutes


def _ddg_search(query: str, max_results: int = 6) -> list[dict]:
    """Search DuckDuckGo and return structured results."""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # type: ignore[assignment]
        except ImportError:
            raise ImportError(
                "DuckDuckGo search library not installed. "
                "Run: pip install ddgs"
            )

    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "url": r.get("href", ""),
            })
    return results


def _format_results(query: str, results: list[dict]) -> str:
    """Format search results as readable text."""
    if not results:
        return f"No search results found for: {query}"

    lines = [f"Search results for: {query}\n"]
    for i, r in enumerate(results, 1):
        if r.get("title"):
            lines.append(f"{i}. {r['title']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        if r.get("url"):
            lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def web_search(query: str, max_results: int = 6) -> str:
    """
    Search the web using DuckDuckGo.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default 6).

    Returns:
        Formatted search results as a string.
    """
    if not query or not query.strip():
        return "Please provide a search query."

    query = query.strip()
    cache_key = f"search:{query}:{max_results}"

    # Check cache
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info("WebSearch: cache hit for '%s'", query)
        return cached

    logger.info("WebSearch: Searching: %s", query)

    try:
        results = _ddg_search(query, max_results=max_results)
        formatted = _format_results(query, results)
        _cache_set(cache_key, formatted, _SEARCH_TTL)
        logger.info("WebSearch: %d result(s) found.", len(results))
        return formatted
    except ImportError as e:
        return f"Search unavailable: {e}"
    except Exception as e:
        return f"Search failed: {e}"
