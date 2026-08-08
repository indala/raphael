"""
Playground tools — Native schemas and handlers for Raphael Playground Studio.
"""

import logging

logger = logging.getLogger(__name__)


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "render_playground_chart",
                "description": "Render a live visual chart card in the Raphael Playground Studio canvas.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chart_type": {
                            "type": "string",
                            "enum": ["bar", "line", "pie", "radar", "scatter"],
                            "description": "Chart visualization type",
                        },
                        "title": {
                            "type": "string",
                            "description": "Title of the chart card",
                        },
                        "labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Labels for the data items",
                        },
                        "values": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Numerical values for the data items",
                        },
                    },
                    "required": ["chart_type", "title", "labels", "values"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "render_playground_diagram",
                "description": "Render a system architecture or sequence diagram in the Raphael Playground Studio canvas.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mermaid_code": {
                            "type": "string",
                            "description": "Mermaid diagram specification code",
                        },
                        "title": {
                            "type": "string",
                            "description": "Diagram card title",
                        },
                    },
                    "required": ["mermaid_code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "render_playground_html",
                "description": "Render interactive custom HTML/CSS/JS components in the Raphael Playground Studio canvas.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "html_code": {
                            "type": "string",
                            "description": "Raw HTML/CSS snippet to render",
                        },
                    },
                    "required": ["html_code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "clear_playground",
                "description": "Clear and reset all rendered contents from the Raphael Playground Studio interactive canvas workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]


def _get_controller():
    from controller.window_manager import get_controller_instance
    return get_controller_instance()


def render_playground_chart(chart_type: str, title: str, labels: list[str], values: list[float]) -> str:
    """Render a visual chart in the Raphael Playground window."""
    ctrl = _get_controller()
    if ctrl and hasattr(ctrl, "_window_manager"):
        win = ctrl._window_manager.show_playground()
        datasets = [{"data": values}]
        win.render_chart(chart_type, labels, datasets, title)
        return f"Rendered '{title}' ({chart_type} chart) in Raphael Playground Studio."
    return "Playground window manager unavailable."


def render_playground_diagram(mermaid_code: str, title: str = "Architecture Diagram") -> str:
    """Render a diagram in the Raphael Playground window."""
    ctrl = _get_controller()
    if ctrl and hasattr(ctrl, "_window_manager"):
        win = ctrl._window_manager.show_playground()
        win.render_diagram(mermaid_code, title)
        return f"Rendered diagram '{title}' in Raphael Playground Studio."
    return "Playground window manager unavailable."


def render_playground_html(html_code: str) -> str:
    """Render interactive HTML components in the Raphael Playground window."""
    ctrl = _get_controller()
    if ctrl and hasattr(ctrl, "_window_manager"):
        win = ctrl._window_manager.show_playground()
        win.render_html(html_code)
        return "Rendered custom HTML canvas in Raphael Playground Studio."
    return "Playground window manager unavailable."


def clear_playground() -> str:
    """Reset the Raphael Playground window canvas."""
    ctrl = _get_controller()
    if ctrl and hasattr(ctrl, "_window_manager"):
        win = ctrl._window_manager.show_playground()
        win.clear_playground()
        return "Cleared Raphael Playground Studio canvas."
    return "Playground window manager unavailable."
