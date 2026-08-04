# ruff: noqa: E402
"""
Tool registry — collects schemas + functions from native and generated tool modules.

Native tools:  orchestrator/tools/native/  (human-written, never overwritten)
Generated tools: orchestrator/tools/generated/  (AI-created, can be freely updated)
"""

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

_TOOL_MODULES: list = []
_TOOL_MAP: dict[str, Callable] = {}


def _register(module):
    """Register a tool module — collects its schemas and tool functions."""
    _TOOL_MODULES.append(module)
    for name in dir(module):
        obj = getattr(module, name)
        if callable(obj) and not name.startswith("_"):
            _TOOL_MAP[name] = obj


# ── Native Tools (human-written, protected) ──
from .native import memory as _mod_memory

_register(_mod_memory)

from .native import clipboard as _mod_clipboard

_register(_mod_clipboard)

from .native import system as _mod_system

_register(_mod_system)

from .native import tts as _mod_tts

_register(_mod_tts)

from .native import chart as _mod_chart

_register(_mod_chart)

from .native import web as _mod_web

_register(_mod_web)

from .native import files as _mod_files

_register(_mod_files)

from .native import browser as _mod_browser

_register(_mod_browser)

from .native import ui as _mod_ui

_register(_mod_ui)

from .native import screen as _mod_screen

_register(_mod_screen)

from .native import weather as _mod_weather

_register(_mod_weather)

from .native import background_tools as _mod_bg

_register(_mod_bg)

from .native import knowledge as _mod_knowledge

_register(_mod_knowledge)

from .native import web_fetch as _mod_web_fetch

_register(_mod_web_fetch)

from .native import delegation as _mod_delegation

_register(_mod_delegation)

from .native import upstox as _mod_upstox

_register(_mod_upstox)

from .native import goals as _mod_goals

_register(_mod_goals)

from .native import music as _mod_music

_register(_mod_music)

from .native import music_player_tools as _mod_music_player

_register(_mod_music_player)

from .native import email as _mod_email

_register(_mod_email)

from .native import agent as _mod_agent

_register(_mod_agent)

from .native import desktop as _mod_desktop

_register(_mod_desktop)

from .native import audio as _mod_audio

_register(_mod_audio)

from .native import power as _mod_power

_register(_mod_power)

# ── Generated Tools (AI-created, dynamically loaded) ──
# Production tools are loaded; draft and archived are not (prevents conflicts)
import contextlib
import importlib
import pkgutil

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
# Tools with no side effects can run concurrently when the LLM requests
# multiple tool calls in one response. Others run sequentially.
PARALLEL_SAFE_TOOLS: set[str] = {
    "web_search", "web_fetch", "web_fetch_multi",
    "get_weather",
    "process_file", "analyze_image", "read_file",
    "recall_memory", "list_memories",
    "capture_screen", "read_clipboard",
    "list_agents", "list_workflows",
    "list_stocks", "get_stock_data",
    "get_current_song",
    "list_goals",
    "save_output",
    "service_list", "env_get",
    "key_is_pressed", "caps_lock_state", "num_lock_state",
    "monitor_get_dpi", "get_brightness",
    "recycle_bin_get",
}


def get_tool_schemas() -> list[dict]:
    """Return aggregated JSON schemas from all tool modules + MCP servers."""
    _load_mcp_tools()
    schemas = list(_mcp_schemas or [])
    for mod in _TOOL_MODULES:
        try:
            schemas.extend(mod.get_schemas())
        except Exception as e:
            logger.error("Failed to load schemas from %s: %s", mod.__name__, e)
    return schemas


def get_filtered_schemas(tool_names: list[str]) -> list[dict]:
    """Return schemas for specific tool names only.

    Used by agents to present only relevant tools to the LLM,
    reducing token usage and improving response focus.
    """
    all_schemas = get_tool_schemas()
    name_set = set(tool_names)
    return [s for s in all_schemas if s["function"]["name"] in name_set]


def get_tool_map() -> dict[str, Callable]:
    """Return the complete tool name → function map (native + generated + MCP)."""
    _load_mcp_tools()
    schema_names = {s["function"]["name"] for s in get_tool_schemas()}
    tool_map = {name: func for name, func in _TOOL_MAP.items() if name in schema_names}
    if _mcp_tool_map:
        tool_map.update(_mcp_tool_map)
    return tool_map


def is_generated_tool(name: str) -> bool:
    """Check if a tool is a generated (AI-created) tool in production."""
    from pathlib import Path
    prod_dir = Path(__file__).resolve().parent / "generated" / "production"
    return (prod_dir / f"{name}.py").exists()


def reload_tools():
    """Re-scan native and generated tool directories, re-import all modules.

    Used by the Tool Manager to pick up dynamically created tool modules.
    Clears cached modules and re-imports everything.
    """
    global _TOOL_MODULES, _TOOL_MAP
    _TOOL_MODULES = []
    _TOOL_MAP = {}
    import importlib
    import pkgutil

    import orchestrator.tools
    # Remove cached modules
    for m in list(orchestrator.tools.__dict__.keys()):
        if m.startswith("_mod_"):
            del orchestrator.tools.__dict__[m]
    # Re-import native modules
    for _importer, modname, _ispkg in pkgutil.iter_modules(
        orchestrator.tools.native.__path__, orchestrator.tools.native.__name__ + "."
    ):
        try:
            mod = importlib.import_module(modname)
            importlib.reload(mod)
            _TOOL_MODULES.append(mod)
            for name in dir(mod):
                obj = getattr(mod, name)
                if callable(obj) and not name.startswith("_"):
                    _TOOL_MAP[name] = obj
        except Exception as e:
            logger.warning("Tool reload skipped '%s': %s", modname, e)
    # Re-import generated production modules
    for _importer, modname, _ispkg in pkgutil.iter_modules(
        orchestrator.tools.generated.production.__path__,
        orchestrator.tools.generated.production.__name__ + "."
    ):
        try:
            mod = importlib.import_module(modname)
            importlib.reload(mod)
            _TOOL_MODULES.append(mod)
            for name in dir(mod):
                obj = getattr(mod, name)
                if callable(obj) and not name.startswith("_"):
                    _TOOL_MAP[name] = obj
        except Exception as e:
            logger.warning("Generated tool reload skipped '%s': %s", modname, e)


__all__ = [
    "get_filtered_schemas",
    "get_tool_map",
    "get_tool_schemas",
    "is_generated_tool",
    "reload_tools",
]
