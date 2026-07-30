"""Web search tool — DuckDuckGo search."""

from actions.web_search import web_search as _web_search


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web using DuckDuckGo. Returns up-to-date information, news, or facts. Use this when you need current information beyond your training data.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (1-10, default 6)",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    ]


def web_search(query: str, max_results: int = 6) -> str:
    """Search the web using DuckDuckGo."""
    return _web_search(query, max_results)
