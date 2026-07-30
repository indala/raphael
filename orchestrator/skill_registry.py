"""
Skill Registry — discover, query, and execute skills.

Provides a unified interface for agents to discover skills,
check required tools, and execute them.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.core import LLMClient, ToolExecutor

logger = logging.getLogger(__name__)

_skills_discovered = False


def ensure_discovered():
    global _skills_discovered
    if not _skills_discovered:
        from skills import discover_skills
        discover_skills()
        _skills_discovered = True


def list_skills() -> list[dict]:
    """Return {name, description, required_tools} for all registered skills."""
    ensure_discovered()
    from skills import _SKILL_REGISTRY
    return [
        {"name": s.name, "description": s.description, "required_tools": s.required_tools}
        for s in _SKILL_REGISTRY.values()
    ]


def execute_skill(name: str, llm: LLMClient, executor: ToolExecutor, **kwargs) -> str:
    """Execute a skill by name with the given LLM and executor."""
    ensure_discovered()
    from skills import _SKILL_REGISTRY
    skill = _SKILL_REGISTRY.get(name)
    if skill is None:
        return f"Skill '{name}' not found."
    logger.info("Executing skill: %s", name)
    return skill.execute(llm=llm, executor=executor, **kwargs)  # type: ignore[no-any-return]
