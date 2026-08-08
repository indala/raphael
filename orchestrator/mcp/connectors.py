"""
Pre-configured MCP Client Connectors — Built-in MCP server definitions.

Provides pre-configured client connectors for standard external MCP servers:
- Filesystem MCP (file operations & directory browsing)
- PostgreSQL MCP (database queries & schema inspection)
- GitHub MCP (repository issues, PRs, and code search)
- Memory MCP (graph memory store)
- Fetch MCP (web search & web page fetching)
"""

import json
import logging
from dataclasses import dataclass, field

import config

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


# Pre-configured popular MCP servers
STANDARD_MCP_SERVERS: dict[str, MCPServerConfig] = {
    "filesystem": MCPServerConfig(
        name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", str(config.PROJECT_ROOT)],
        enabled=False,
    ),
    "postgres": MCPServerConfig(
        name="postgres",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-postgres"],
        env={"POSTGRES_URL": getattr(config, "POSTGRES_URL", "")},
        enabled=False,
    ),
    "github": MCPServerConfig(
        name="github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": getattr(config, "GITHUB_TOKEN", "")},
        enabled=False,
    ),
    "memory": MCPServerConfig(
        name="memory",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-memory"],
        enabled=False,
    ),
    "fetch": MCPServerConfig(
        name="fetch",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-fetch"],
        enabled=False,
    ),
}


class MCPConnectorRegistry:
    """Registry for managing and discovering pre-configured external MCP connectors."""

    def __init__(self):
        self._servers: dict[str, MCPServerConfig] = dict(STANDARD_MCP_SERVERS)
        self._load_custom_configs()

    def _load_custom_configs(self):
        """Load user-defined MCP server configs from config (settings.toml)."""
        mcp_config_json = getattr(config, "MCP_SERVERS_JSON", "")
        if mcp_config_json:
            try:
                custom_dict = json.loads(mcp_config_json)
                for name, cfg in custom_dict.items():
                    self._servers[name] = MCPServerConfig(
                        name=name,
                        command=cfg.get("command", "npx"),
                        args=cfg.get("args", []),
                        env=cfg.get("env", {}),
                        enabled=cfg.get("enabled", True),
                    )
                logger.info("Loaded %d custom MCP server configs", len(custom_dict))
            except Exception as e:
                logger.warning("Failed to parse MCP_SERVERS_JSON: %s", e)

    def get_active_servers(self) -> list[MCPServerConfig]:
        """Return list of enabled MCP server configurations."""
        return [cfg for cfg in self._servers.values() if cfg.enabled]

    def register_server(self, config: MCPServerConfig):
        """Register a new MCP server connector at runtime."""
        self._servers[config.name] = config

    def list_all_servers(self) -> list[dict]:
        """List summary of registered MCP server configurations."""
        return [
            {
                "name": cfg.name,
                "command": cfg.command,
                "args": cfg.args,
                "enabled": cfg.enabled,
            }
            for cfg in self._servers.values()
        ]
