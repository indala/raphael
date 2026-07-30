"""
MCP Tool Bridge — adapts MCP server tools to Raphael's tool format.

Each MCP server exposes tools via JSON-RPC. This bridge converts them
to Raphael's OpenAI function-calling schema format, with ``mcp_<server>_``
prefixes to avoid naming conflicts.

Tool function naming convention::

    mcp_<server_name>_<tool_name>

This makes them indistinguishable from native tools at the registry level.
"""

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable
from typing import Any

from .client import MCPServerConnection

_bg_loop: asyncio.AbstractEventLoop | None = None
_bg_thread: threading.Thread | None = None
_bg_lock = threading.Lock()


def _get_background_loop() -> asyncio.AbstractEventLoop:
    global _bg_loop, _bg_thread
    with _bg_lock:
        if _bg_loop is None:
            _bg_loop = asyncio.new_event_loop()
            def run_loop(loop):
                asyncio.set_event_loop(loop)
                loop.run_forever()
            _bg_thread = threading.Thread(target=run_loop, args=(_bg_loop,), daemon=True)
            _bg_thread.start()
        return _bg_loop


def run_async(coro) -> Any:
    """Run a coroutine synchronously on the persistent background event loop."""
    loop = _get_background_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


logger = logging.getLogger(__name__)


# ── Schema prefix ──────────────────────────────────────────────────────
PREFIX_SEPARATOR = "_"


def _prefix(server_name: str, tool_name: str) -> str:
    """Build the prefixed tool name, e.g. ``mcp_filesystem_read_file``."""
    return f"mcp_{server_name}{PREFIX_SEPARATOR}{tool_name}"


class MCPToolAdapter:
    """
    Adapts a single MCP server's tools for Raphael's tool registry.

    An adapter instance represents one MCP server. It provides:

    - ``get_schemas()`` — OpenAI JSON schema for each tool
    - ``execute(prefixed_name, args)`` — dispatches to the right tool
    """

    def __init__(self, server_name: str, connection: MCPServerConnection):
        self.server_name = server_name
        self._connection = connection
        self._tools: list[dict] = []
        self._initialized = False
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self.server_name

    # ── Schema Building ──────────────────────────────────────────────

    def get_schemas(self) -> list[dict]:
        """
        Return OpenAI function-calling schemas for all tools from this server.

        Called from the tool registry layer. Results are cached after first
        successful list_tools() call.
        """
        if not self._initialized:
            self._refresh_tools()
        if not self._tools:
            return []

        schemas = []
        for tool in self._tools:
            prefixed_name = _prefix(self.server_name, tool["name"])
            schemas.append({
                "type": "function",
                "function": {
                    "name": prefixed_name,
                    "description": tool.get("description", ""),
                    "parameters": self._adapt_schema(
                        tool.get("inputSchema", {"type": "object", "properties": {}})
                    ),
                },
            })
        return schemas

    def get_tool_map(self) -> dict[str, Callable]:
        """Return ``{prefixed_name: callable}`` for each tool."""
        if not self._initialized:
            self._refresh_tools()

        tool_map = {}
        for tool in self._tools:
            prefixed_name = _prefix(self.server_name, tool["name"])
            target_name = tool["name"]
            tool_map[prefixed_name] = self._make_executor(target_name)
        return tool_map

    def health(self) -> bool:
        """Check if the underlying server connection is healthy."""
        try:
            return run_async(self._connection.health())  # type: ignore[no-any-return]
        except Exception:
            return False

    # ── Internal ─────────────────────────────────────────────────────

    def _refresh_tools(self):
        """Fetch tool list from the MCP server (runs once)."""
        with self._lock:
            if self._initialized:
                return
            try:
                # Initialize if needed
                if not getattr(self._connection, '_initialized', True):
                    ok = run_async(self._connection.initialize())
                    if not ok:
                        logger.warning("MCP server '%s' not available", self.server_name)
                        self._tools = []
                        self._initialized = True
                        return

                tools_raw = run_async(self._connection.list_tools())
                self._tools = tools_raw
                self._initialized = True
                logger.info("MCP server '%s': %d tools loaded",
                            self.server_name, len(self._tools))
            except Exception as e:
                logger.warning("Failed to load tools from '%s': %s",
                               self.server_name, e)
                self._tools = []
                self._initialized = True

    def _make_executor(self, tool_name: str) -> Callable:
        """Create a sync callable that invokes the MCP tool via asyncio."""

        def execute(**kwargs) -> str:
            try:
                return run_async(self._connection.call_tool(tool_name, kwargs))  # type: ignore[no-any-return]
            except Exception as e:
                logger.error("MCP tool %s/%s failed: %s",
                             self.server_name, tool_name, e)
                return f"Error: {e}"

        execute.__name__ = _prefix(self.server_name, tool_name)
        execute.__qualname__ = execute.__name__
        return execute

    @staticmethod
    def _adapt_schema(input_schema: dict) -> dict:
        """Ensure the schema has the required OpenAI function-calling format."""
        if not input_schema:
            return {"type": "object", "properties": {}}
        if "type" not in input_schema:
            input_schema["type"] = "object"
        if "properties" not in input_schema:
            input_schema["properties"] = {}
        return input_schema


# ── Top-Level Manager ──────────────────────────────────────────────────

class MCPManager:
    """
    Manages all configured MCP servers and their tool adapters.

    Reads ``config.MCP_SERVERS`` and creates a connection + adapter
    for each server. Provides aggregated schemas and tool maps for
    integration with Raphael's tool registry.
    """

    def __init__(self):
        self._adapters: list[MCPToolAdapter] = []
        self._initialized = False

    def initialize(self):
        """Read config and create adapters for all configured servers."""
        if self._initialized:
            return

        try:
            import config
            servers = getattr(config, "MCP_SERVERS", [])
        except (ImportError, AttributeError):
            servers = []

        if not servers:
            logger.debug("No MCP servers configured")
            self._initialized = True
            return

        for server_cfg in servers:
            name = server_cfg.get("name", "unknown")
            command = server_cfg.get("command", "")
            args = server_cfg.get("args", [])
            env = server_cfg.get("env", None)
            cwd = server_cfg.get("cwd", None)

            if not command:
                logger.warning("MCP server '%s' has no command, skipping", name)
                continue

            connection = MCPServerConnection(
                name=name, command=command, args=args, env=env, cwd=cwd,
            )
            adapter = MCPToolAdapter(name, connection)
            self._adapters.append(adapter)

        self._initialized = True
        logger.info("MCP: %d server(s) configured", len(self._adapters))

    def get_all_schemas(self) -> list[dict]:
        """Aggregate schemas from all configured MCP servers."""
        self.initialize()
        all_schemas = []
        for adapter in self._adapters:
            all_schemas.extend(adapter.get_schemas())
        return all_schemas

    def get_tool_map(self) -> dict[str, Callable]:
        """Aggregate tool maps from all configured MCP servers."""
        self.initialize()
        tool_map: dict[str, Callable] = {}
        for adapter in self._adapters:
            tool_map.update(adapter.get_tool_map())
        return tool_map

    def close(self):
        """Close all MCP server connections."""
        for adapter in self._adapters:
            with contextlib.suppress(Exception):
                run_async(adapter._connection.close())
        self._adapters.clear()
        self._initialized = False

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, *args):
        self.close()
