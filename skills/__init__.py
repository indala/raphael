"""
Skill definitions for Raphael's multi-agent system.

Each skill is a focused, reusable capability with a name, description,
and execute() method. Skills can use specific tools from the tool registry.
"""

import logging

logger = logging.getLogger(__name__)

_SKILL_REGISTRY: dict[str, Skill] = {}  # type: ignore[name-defined]


def register(skill_cls: type) -> type:
    """Decorator to register a skill class. Instantiates it on registration."""
    instance = skill_cls()
    _SKILL_REGISTRY[instance.name] = instance
    logger.debug("Skill registered: %s", instance.name)
    return skill_cls


def get_skill(name: str) -> Skill | None:  # type: ignore[name-defined]
    return _SKILL_REGISTRY.get(name)


def list_skills() -> list[str]:
    return list(_SKILL_REGISTRY.keys())


def discover_skills():
    """Lazy-import all skill modules to trigger registration."""
    import importlib
    import pkgutil

    import skills
    for m in pkgutil.iter_modules(skills.__path__, skills.__name__ + "."):
        if m.name != __name__:  # skip base_skill itself
            importlib.import_module(m.name)
