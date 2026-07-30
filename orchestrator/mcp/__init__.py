"""
MCP (Model Context Protocol) support for Raphael.

Provides:
- ``MCPManager`` — manages configured MCP server connections
- ``MCPToolAdapter`` — bridges MCP tools to Raphael's tool format
- ``MCPServerConnection`` — low-level stdio subprocess connection

Tools from MCP servers are prefixed ``mcp_<server>_<tool>`` and auto-register
in the main tool registry alongside native tools.
"""

from .client import MCPServerConnection
from .mcp_tools import MCPManager, MCPToolAdapter

__all__ = ["MCPManager", "MCPServerConnection", "MCPToolAdapter"]
