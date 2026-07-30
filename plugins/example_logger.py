"""Example plugin — logs every tool execution to the debug log."""

import logging

from orchestrator.plugin import Plugin

logger = logging.getLogger(__name__)


class ToolLoggerPlugin(Plugin):
    name = "tool_logger"

    def on_tool_execute(self, tool_name: str, args: dict, result: str) -> None:
        logger.debug("Tool executed: %s(%s) => %s", tool_name, args, result[:200])
