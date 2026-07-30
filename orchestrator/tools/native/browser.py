"""Browser control tool — Playwright multi-browser automation."""

from actions.browser_control import browser_control as _browser_control


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "browser_control",
                "description": "Control a web browser programmatically. Actions: navigate (go to URL), click (click element by CSS selector), fill (fill form field), screenshot (capture page), get_text (read page text), execute_js (run JavaScript), scroll (up/down), new_tab, close_tab, back, close_all. Supports Chrome, Firefox, Edge, Brave, Opera, Vivaldi. Auto-detects default browser.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["navigate", "click", "fill", "screenshot", "get_text", "get_html", "execute_js", "scroll", "new_tab", "close_tab", "back", "close_all"],
                            "description": "Action to perform",
                        },
                        "url": {
                            "type": "string",
                            "description": "URL to navigate to (for navigate/new_tab actions)",
                        },
                        "selector": {
                            "type": "string",
                            "description": "CSS selector (for click/fill/get_text actions)",
                        },
                        "text": {
                            "type": "string",
                            "description": "Text to fill into a form field (for fill action)",
                        },
                        "script": {
                            "type": "string",
                            "description": "JavaScript code to execute (for execute_js action)",
                        },
                        "browser": {
                            "type": "string",
                            "description": "Browser name: chrome, firefox, edge, brave, opera, vivaldi, chromium (auto-detected if omitted)",
                        },
                        "headless": {
                            "type": "boolean",
                            "description": "Run browser without visible window (default false)",
                        },
                        "full_page": {
                            "type": "boolean",
                            "description": "For screenshot action: capture the entire scrollable page (default false)",
                        },
                        "viewport_width": {
                            "type": "integer",
                            "description": "Width of the browser viewport in pixels (default 1280)",
                        },
                        "viewport_height": {
                            "type": "integer",
                            "description": "Height of the browser viewport in pixels (default 720)",
                        },
                        "user_agent": {
                            "type": "string",
                            "description": "Custom User-Agent header to use",
                        },
                    },
                    "required": ["action"],
                },
            },
        },
    ]


def browser_control(action: str, **kwargs) -> str:
    """Control a web browser programmatically."""
    return _browser_control(action, **kwargs)
