"""
MCP Client — manages Model Context Protocol server subprocess connections.

Each MCP server runs as a subprocess (stdio transport). The client
manages its lifecycle and exposes list_tools / call_tool.

Architecture insp®ired by Zero's internal/mcp/ pattern:
  - Server spawned on first use (lazy)
  - Health-checked via send_ping
  - Auto-restarted on connection failure
"""

import logging
import time
from contextlib import AsyncExitStack, suppress
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

logger = logging.getLogger(__name__)


class MCPServerConnection:
    """
    Manages a single MCP server subprocess.

    Wraps MCP SDK's stdio_client + ClientSession with lifecycle
    management, health checks, and error recovery.
    """

    def __init__(self, name: str, command: str, args: list[str] | None = None,
                 env: dict[str, str] | None = None, cwd: str | None = None):
        self.name = name
        self._params = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
            cwd=cwd,
        )
        self._exit_stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._stdio: Any | None = None
        self._write: Any | None = None
        self._initialized = False
        self._last_ping = 0.0

    # ── Connection Management ────────────────────────────────────────

    async def initialize(self) -> bool:
        """Connect and initialize the MCP server. Returns True on success."""
        try:
            transport = await self._exit_stack.enter_async_context(
                stdio_client(self._params)
            )
            self._stdio, self._write = transport
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(self._stdio, self._write)
            )
            await self._session.initialize()
            self._initialized = True
            self._last_ping = time.time()
            logger.info("MCP server '%s' initialized", self.name)
            return True
        except Exception as e:
            logger.warning("MCP server '%s' init failed: %s", self.name, e)
            await self._cleanup()
            return False

    async def health(self) -> bool:
        """Check if the server is alive via ping."""
        if not self._session or not self._initialized:
            return False
        try:
            await self._session.send_ping()
            self._last_ping = time.time()
            return True
        except Exception:
            return False

    async def list_tools(self) -> list[dict]:
        """Return the list of tools from the server."""
        if not self._session or not self._initialized:
            raise ConnectionError(f"MCP server '{self.name}' not initialized")
        try:
            result = await self._session.list_tools()
            tools = []
            for tool in result.tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema,
                })
            return tools
        except Exception as e:
            logger.error("Failed to list tools from '%s': %s", self.name, e)
            raise

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Call a tool on the server and return the text result."""
        if not self._session or not self._initialized:
            raise ConnectionError(f"MCP server '{self.name}' not initialized")
        try:
            result: CallToolResult = await self._session.call_tool(name, arguments)
            # Extract text from content list
            parts = []
            for content in result.content:
                if isinstance(content, TextContent):
                    parts.append(content.text)
                else:
                    parts.append(str(content))
            text = "\n".join(parts)
            if result.isError:
                logger.error("MCP tool '%s' on '%s' returned error: %s",
                             name, self.name, text)
                raise RuntimeError(f"MCP tool error: {text}")
            return text
        except Exception as e:
            if not isinstance(e, RuntimeError):
                logger.error("MCP tool '%s' call failed on '%s': %s",
                             name, self.name, e)
                raise
            raise

    async def close(self):
        """Clean up the connection."""
        await self._cleanup()

    async def _cleanup(self):
        with suppress(Exception):
            await self._exit_stack.aclose()
        self._session = None
        self._stdio = None
        self._write = None
        self._initialized = False

    def __del__(self):
        # Best-effort cleanup for garbage collection
        if hasattr(self, '_exit_stack') and self._exit_stack:
            try:
                import asyncio
                with suppress(RuntimeError):
                    asyncio.get_running_loop()
                # Don't close from non-async context — will be cleaned
                # up by the MCPClient manager
            except Exception:
                pass
