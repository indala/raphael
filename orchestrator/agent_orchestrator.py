"""
Agent Orchestrator — routes incoming requests to the best agent.

Uses intent detection (can_handle) to find the highest-confidence
agent for a given query. Now uses evolved confidence (memory-adjusted)
so agents improve routing decisions over time.

Falls back to the default LLM loop if no agent exceeds the threshold.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.core import LLMClient, ToolExecutor

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.35
_agents_discovered = False


def ensure_discovered():
    global _agents_discovered
    if not _agents_discovered:
        from agents import discover_agents
        discover_agents()
        _agents_discovered = True


def select_agent(query: str) -> tuple[str, float] | None:
    """Find the best agent for a query using evolved (memory-adjusted) confidence."""
    ensure_discovered()
    from agents import _AGENT_REGISTRY

    best_name = None
    best_score = 0.0

    for name, agent in _AGENT_REGISTRY.items():
        try:
            # Use evolved confidence that includes memory-based adjustments
            score = agent.can_handle_evolved(query)
            if score > best_score:
                best_score = score
                best_name = name
        except Exception as e:
            logger.debug("Agent %s.can_handle_evolved failed: %s", name, e)

    if best_name and best_score >= _CONFIDENCE_THRESHOLD:
        logger.info(
            "Agent routing: '%s' → %s (evolved confidence=%.2f)",
            query, best_name, best_score,
        )
        return best_name, best_score

    logger.info(
        "No agent matched query (best=%.2f, threshold=%.2f)",
        best_score, _CONFIDENCE_THRESHOLD,
    )
    return None


def route_to_agent(
    query: str, _llm: LLMClient, executor: ToolExecutor
) -> tuple[str | None, str | None]:
    """
    Route query to the best agent.

    Creates a per-agent LLM client (with the agent's assigned model)
    rather than reusing the caller's LLM client.

    Returns (agent_name, response).
    - agent_name: the agent that handled it (None if no agent matched)
    - response: the agent's response (None if no agent matched)
    """
    from orchestrator.agent_models import create_agent_llm

    selected = select_agent(query)
    if selected is None:
        return None, None

    agent_name, _ = selected
    from agents import _AGENT_REGISTRY

    agent = _AGENT_REGISTRY[agent_name]
    logger.info("Routing '%s' → agent '%s'", query, agent_name)

    try:
        # Create an LLM client tailored to this agent and query
        agent_llm = create_agent_llm(agent_name, query=query)
        response = agent.run(query=query, llm=agent_llm, executor=executor)
        return agent_name, response
    except Exception as e:
        logger.error("Agent '%s' execution failed: %s", agent_name, e)
        return agent_name, None


def process_correction_for_agent(
    agent_name: str, original_query: str, correction_text: str
):
    """
    Process user correction for the last-used agent.
    Must be called when a follow-up user message is a correction.
    """
    logger.info("Processing correction for agent '%s'", agent_name)
    from agents import _AGENT_REGISTRY
    agent = _AGENT_REGISTRY.get(agent_name)
    if agent is None:
        return
    agent._apply_correction(original_query, correction_text)
