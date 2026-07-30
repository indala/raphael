"""
Agent definitions for Raphael's multi-agent system.

Each agent is a coordinator that routes tasks to skills. Agents use
intent detection (can_handle) to determine if they should take a request.
"""

import logging

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

_AGENT_REGISTRY: dict[str, BaseAgent] = {}


def register(agent_cls: type) -> type:
    """Decorator to register an agent class. Instantiates it on registration."""
    instance = agent_cls()
    _AGENT_REGISTRY[instance.name] = instance
    logger.debug("Agent registered: %s", instance.name)
    return agent_cls


def get_agent(name: str) -> BaseAgent | None:
    return _AGENT_REGISTRY.get(name)


def list_agents() -> list[str]:
    return list(_AGENT_REGISTRY.keys())


def list_agent_capabilities() -> list[dict]:
    """Return capabilities for all registered agents (for delegation)."""
    return [agent.get_capabilities() for agent in _AGENT_REGISTRY.values()]


def discover_agents():
    """Lazy-import all agent modules to trigger registration."""
    import importlib
    import pkgutil
    import agents
    for m in pkgutil.iter_modules(agents.__path__, agents.__name__ + "."):
        if m.name != __name__:  # skip base_agent itself
            importlib.import_module(m.name)
