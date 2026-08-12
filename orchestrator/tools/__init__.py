# ruff: noqa: E402
"""
Tool registry — collects schemas + functions from native and generated tool modules.

Native tools:  orchestrator/tools/native/  (human-written, never overwritten)
Generated tools: orchestrator/tools/generated/  (AI-created, can be freely updated)
"""

import contextlib
import importlib
import logging
import os
import pkgutil
from collections.abc import Callable

logger = logging.getLogger(__name__)

_TOOL_MODULES: list = []
_TOOL_MAP: dict[str, Callable] = {}
_filtered_schema_cache: dict[tuple[str, ...], list[dict]] = {}
_tools_initialized: bool = False
_tool_registry_version: int = 0

_NATIVE_MODULE_NAMES = [
    "memory", "clipboard", "system", "tts", "chart", "web", "files",
    "browser", "ui", "screen", "weather", "background_tools", "knowledge",
    "web_fetch", "delegation", "upstox", "playground_tools", "goals",
    "music", "music_player_tools", "email", "agent", "desktop", "audio", "power",
]


def _register(module):
    """Register a tool module — collects its schemas and tool functions."""
    if module not in _TOOL_MODULES:
        _TOOL_MODULES.append(module)
    for name in dir(module):
        obj = getattr(module, name)
        if callable(obj) and not name.startswith("_"):
            _TOOL_MAP[name] = obj


def _ensure_tools_loaded():
    """Lazily import native and generated production tool modules if not already loaded."""
    global _tools_initialized
    if _tools_initialized:
        return
    _tools_initialized = True

    # ── Native Tools ──
    for mod_name in _NATIVE_MODULE_NAMES:
        try:
            mod = importlib.import_module(f".native.{mod_name}", __name__)
            globals()[f"_mod_{mod_name}"] = mod
            _register(mod)
        except Exception as e:
            logger.warning("Native tool module '%s' failed to load: %s", mod_name, e)

    # ── Generated Tools ──
    try:
        from .generated import production as _gen_prod_pkg
        for _importer, _modname, _ispkg in pkgutil.iter_modules(
            _gen_prod_pkg.__path__, _gen_prod_pkg.__name__ + "."
        ):
            try:
                _mod = importlib.import_module(_modname)
                _register(_mod)
                logger.debug("Loaded generated tool: %s", _modname)
            except Exception as e:
                logger.warning("Generated tool '%s' failed to load: %s", _modname, e)
    except Exception as e:
        logger.warning("Generated production package search failed: %s", e)


# Check environment variable escape hatch
_EAGER_ENV = os.environ.get("RAPHAEL_EAGER_TOOLS", "").strip().lower()
if _EAGER_ENV in ("1", "true", "yes", "on"):
    _ensure_tools_loaded()


# ── MCP Tool Integration ──
_mcp_schemas: list[dict] | None = None
_mcp_tool_map: dict[str, Callable] | None = None
_mcp_manager = None


def _load_mcp_tools():
    """Fetch MCP tool schemas and functions from configured servers."""
    global _mcp_schemas, _mcp_tool_map, _mcp_manager
    if _mcp_schemas is not None:
        return
    try:
        from orchestrator.mcp.mcp_tools import MCPManager
        if _mcp_manager is None:
            _mcp_manager = MCPManager()
        _mcp_schemas = _mcp_manager.get_all_schemas()
        _mcp_tool_map = _mcp_manager.get_tool_map()
        if _mcp_schemas:
            logger.info("MCP: %d tool(s) loaded from server(s)", len(_mcp_schemas))
    except ImportError:
        _mcp_schemas = []
        _mcp_tool_map = {}
    except Exception as e:
        logger.warning("MCP tools failed to load: %s", e)
        _mcp_schemas = []
        _mcp_tool_map = {}


def reset_mcp_tools():
    """Close active connections and clear cached tools for reload."""
    global _mcp_schemas, _mcp_tool_map, _mcp_manager
    if _mcp_manager is not None:
        with contextlib.suppress(Exception):
            _mcp_manager.close()
        _mcp_manager = None
    _mcp_schemas = None
    _mcp_tool_map = None


# ── Parallel-safe tools ────────────────────────────────────────────
# Task 15: Expanded set of tools safe for parallel execution.
# These tools have no shared state or side effects that would cause
# race conditions when executed concurrently.
PARALLEL_SAFE_TOOLS: set[str] = {
    # Search & Web
    "web_search", "web_fetch", "web_fetch_multi",
    "get_weather",
    
    # File I/O (read-only operations)
    "process_file", "analyze_image", "read_file",
    "save_output",
    
    # Memory & Knowledge
    "recall_memory", "list_memories",
    "search_knowledge", "query_knowledge",
    
    # Screen & UI (read-only)
    "capture_screen", "desktop_snapshot_v2", "desktop_taskbar",
    "read_clipboard",
    "list_agents", "list_workflows",
    
    # Stock/Finance (read-only)
    "list_stocks", "get_stock_data",
    "get_current_song",
    
    # Goals & Tasks (read-only)
    "list_goals", "list_tasks",
    "check_task",
    
    # System Info (read-only)
    "desktop_processes", "desktop_system_info", "desktop_network",
    "desktop_environment",
    "service_list", "env_get",
    
    # Keyboard State (read-only)
    "key_is_pressed", "caps_lock_state", "num_lock_state",
    
    # Monitor Info (read-only)
    "monitor_get_dpi", "get_brightness",
    "recycle_bin_get",
    
    # Audio (read-only)
    "get_system_volume",
    
    # Music (read-only playlist/song data, not playback control)
    "list_local_songs",
    
    # Email (read-only)
    "read_inbox", "search_emails",
}


def normalize_tool_schema(schema: object) -> dict | None:
    if not isinstance(schema, dict):
        return None
    if schema.get("type") == "function" and isinstance(schema.get("function"), dict):
        schema = schema["function"]
        if not isinstance(schema, dict):
            return None
    name = schema.get("name", "")
    if not name or not isinstance(name, str):
        return None
    return schema  # type: ignore[return-value]


def get_tool_schemas() -> list[dict]:
    """Return aggregated JSON schemas from all tool modules + MCP servers."""
    _ensure_tools_loaded()
    _load_mcp_tools()
    schemas = list(_mcp_schemas or [])
    for mod in _TOOL_MODULES:
        try:
            raw_schemas = mod.get_schemas()
            for raw in raw_schemas:
                func = raw.get("function") if isinstance(raw, dict) else None
                if func is not None:
                    if normalize_tool_schema(func) is None:
                        logger.warning(
                            "Skipping malformed schema from %s (missing 'name'): %s",
                            mod.__name__, str(raw)[:120],
                        )
                        continue
                    schemas.append(raw)
                else:
                    if normalize_tool_schema(raw) is None:
                        logger.warning(
                            "Skipping malformed bare schema from %s: %s",
                            mod.__name__, str(raw)[:120],
                        )
                        continue
                    schemas.append({"type": "function", "function": raw})
        except Exception as e:
            logger.error("Failed to load schemas from %s: %s", getattr(mod, "__name__", str(mod)), e)
    return schemas


def get_filtered_schemas(tool_names: list[str]) -> list[dict]:
    """Return schemas for specific tool names only, using a computed cache."""
    cache_key = tuple(sorted(tool_names))
    if cache_key in _filtered_schema_cache:
        return list(_filtered_schema_cache[cache_key])

    all_schemas = get_tool_schemas()
    name_set = set(tool_names)
    filtered = [s for s in all_schemas if s["function"]["name"] in name_set]
    _filtered_schema_cache[cache_key] = filtered
    return list(filtered)


def get_tool_map() -> dict[str, Callable]:
    """Return the complete tool name → function map (native + generated + MCP)."""
    _ensure_tools_loaded()
    _load_mcp_tools()
    schema_names = {s["function"]["name"] for s in get_tool_schemas()}
    tool_map = {name: func for name, func in _TOOL_MAP.items() if name in schema_names}
    if _mcp_tool_map:
        tool_map.update(_mcp_tool_map)
    return tool_map


def invalidate_tool_cache():
    """Clear schema caches and tool map state."""
    global _tools_initialized, _filtered_schema_cache, _TOOL_MODULES, _TOOL_MAP
    _filtered_schema_cache.clear()
    _TOOL_MODULES.clear()
    _TOOL_MAP.clear()
    _tools_initialized = False
    reset_mcp_tools()


def is_generated_tool(name: str) -> bool:
    """Check if a tool is a generated (AI-created) tool in production."""
    from pathlib import Path
    prod_dir = Path(__file__).resolve().parent / "generated" / "production"
    return (prod_dir / f"{name}.py").exists()


def reload_tools():
    """Re-scan native and generated tool directories, re-import all modules."""
    global _tool_registry_version
    invalidate_tool_cache()
    _tool_registry_version += 1  # Bump version on reload
    _ensure_tools_loaded()


def get_tool_registry_version() -> int:
    """Get the current tool registry version (Task 9).
    
    Used by CacheManager to invalidate caches when tools are reloaded.
    Increments each time reload_tools() is called.
    """
    return _tool_registry_version


def __getattr__(name: str):
    """Module-level attribute lookup to allow accessing loaded tool functions or native module references."""
    _ensure_tools_loaded()
    if name.startswith("_mod_"):
        mod_name = name[5:]
        if mod_name in _NATIVE_MODULE_NAMES:
            return importlib.import_module(f".native.{mod_name}", __name__)
    if name in _TOOL_MAP:
        return _TOOL_MAP[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "get_filtered_schemas",
    "get_tool_map",
    "get_tool_registry_version",
    "get_tool_schemas",
    "invalidate_tool_cache",
    "is_generated_tool",
    "normalize_tool_schema",
    "reload_tools",
]

