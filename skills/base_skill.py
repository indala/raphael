"""
Base Skill ABC — a focused, reusable capability.

A skill is a named capability with a description and an execute() method.
Skills receive the LLMClient and ToolExecutor and can call tools to
accomplish their task.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.core import LLMClient, ToolExecutor


class Skill(ABC):
    """Abstract base for all skills."""

    name: str = ""
    description: str = ""
    required_tools: list[str] = []

    @abstractmethod
    def execute(self, llm: LLMClient, executor: ToolExecutor, **kwargs) -> str:
        ...
