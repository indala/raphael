"""Simple hook-based plugin system.

Plugins can hook into key points in the orchestrator lifecycle:
tool execution, LLM requests/responses, startup, and shutdown.
"""

import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_plugins: list[Plugin] = []


class Plugin:
    """Base class for all plugins. Override the hook methods you need."""

    name: str = ""
    manifest: dict = {}

    def on_startup(self):
        """Called once when the app starts."""

    def on_shutdown(self):
        """Called once when the app shuts down."""

    def on_tool_execute(self, _tool_name: str, _args: dict, _result: str) -> str | None:
        """Called after every tool execution. Return modified result or None."""
        return None

    def on_event(self, event: str, data: dict):
        """Called for every event bus event. Override to subscribe to system events."""

    def on_llm_request(self, messages: list[dict]) -> list[dict]:
        """Called before an LLM request. Return modified messages or originals."""
        return messages

    def on_llm_response(self, response: dict) -> dict:
        """Called after an LLM response. Return modified response or original."""
        return response


# ── Registry ──


def register(plugin: Plugin):
    """Register a plugin instance."""
    _plugins.append(plugin)
    # Auto-subscribe plugin.on_event to all event bus events
    if hasattr(plugin, "on_event") and plugin.on_event.__func__ is not Plugin.on_event:  # type: ignore[union-attr,attr-defined]
        from orchestrator.event_bus import EventBus
        EventBus().subscribe("*", plugin.on_event)
    logger.info("Plugin registered: %s", plugin.name or type(plugin).__name__)


def get_hooks(hook_name: str) -> list:
    """Return a list of callables for a given hook name across all plugins."""
    hooks = []
    for p in _plugins:
        fn = getattr(p, hook_name, None)
        if fn is not None:
            hooks.append(fn)
    return hooks


def get_all() -> list[Plugin]:
    """Return all registered plugins."""
    return list(_plugins)


def discover_and_register():
    """Auto-discover plugins from the plugins/ directory and register them."""
    import json
    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    if not plugins_dir.is_dir():
        logger.debug("Plugins directory not found: %s", plugins_dir)
        return

    # 1. Discover python module plugins
    for f in sorted(plugins_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        mod_name = f"plugins.{f.stem}"
        try:
            mod = importlib.import_module(mod_name)
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
                    instance = obj()
                    # Load optional manifest if plugin.json exists alongside
                    manifest_file = plugins_dir / f"{f.stem}.json"
                    if manifest_file.exists():
                        try:
                            meta = json.loads(manifest_file.read_text(encoding="utf-8"))
                            if not meta.get("enabled", True):
                                logger.info("Plugin '%s' disabled in manifest — skipping", instance.name or f.stem)
                                continue
                            instance.manifest = meta
                        except Exception as me:
                            logger.warning("Failed to parse manifest for %s: %s", f.stem, me)
                    register(instance)
        except Exception as e:
            logger.error("Failed to load plugin %s: %s", mod_name, e)


def startup():
    """Call on_startup on all registered plugins."""
    for p in _plugins:
        try:
            p.on_startup()
        except Exception as e:
            logger.error("Plugin on_startup failed (%s): %s", p.name, e)


def shutdown():
    """Call on_shutdown on all registered plugins."""
    for p in _plugins:
        try:
            p.on_shutdown()
        except Exception as e:
            logger.error("Plugin on_shutdown failed (%s): %s", p.name, e)
