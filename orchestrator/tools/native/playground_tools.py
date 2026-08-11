"""
Playground tools — Native schemas and handlers for Raphael Playground Studio.
"""

import logging
import threading
from PyQt6.QtCore import QTimer

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
    from controller.raphael_controller import get_controller_instance
    return get_controller_instance()


def _run_on_main_thread(fn):
    """Execute `fn()` synchronously on the main Qt GUI thread from any worker thread."""
    if threading.current_thread() is threading.main_thread():
        return fn()

    res = [None]
    err: list[Exception | None] = [None]
    evt = threading.Event()

    def runner():
        try:
            res[0] = fn()
        except Exception as e:
            err[0] = e
        finally:
            evt.set()

    QTimer.singleShot(0, runner)
    evt.wait(timeout=5.0)
    if err[0]:
        raise err[0]
    return res[0]


def render_playground_chart(chart_type: str, title: str, labels: list[str], values: list[float]) -> str:
    """Render a visual chart in the Raphael Playground window."""
    def _do():
        ctrl = _get_controller()
        if ctrl and hasattr(ctrl, "_window_manager"):
            win = ctrl._window_manager.show_playground()
            datasets = [{"data": values}]
            win.render_chart(chart_type, labels, datasets, title)
            return True
        return False

    success = _run_on_main_thread(_do)
    if success:
        return f"Rendered '{title}' ({chart_type} chart) in Raphael Playground Studio."
    return "Playground window manager unavailable."


def render_playground_diagram(mermaid_code: str, title: str = "Architecture Diagram") -> str:
    """Render a diagram in the Raphael Playground window."""
    def _do():
        ctrl = _get_controller()
        if ctrl and hasattr(ctrl, "_window_manager"):
            win = ctrl._window_manager.show_playground()
            win.render_diagram(mermaid_code, title)
            return True
        return False

    success = _run_on_main_thread(_do)
    if success:
        return f"Rendered diagram '{title}' in Raphael Playground Studio."
    return "Playground window manager unavailable."


def render_playground_html(html_code: str) -> str:
    """Render interactive HTML components in the Raphael Playground window."""
    def _do():
        ctrl = _get_controller()
        if ctrl and hasattr(ctrl, "_window_manager"):
            win = ctrl._window_manager.show_playground()
            win.render_html(html_code)
            return True
        return False

    success = _run_on_main_thread(_do)
    if success:
        return "Rendered custom HTML canvas in Raphael Playground Studio."
    return "Playground window manager unavailable."


def clear_playground() -> str:
    """Reset the Raphael Playground window canvas."""
    def _do():
        ctrl = _get_controller()
        if ctrl and hasattr(ctrl, "_window_manager"):
            win = ctrl._window_manager.show_playground()
            win.clear_playground()
            return True
        return False

    success = _run_on_main_thread(_do)
    if success:
        return "Cleared Raphael Playground Studio canvas."
    return "Playground window manager unavailable."
