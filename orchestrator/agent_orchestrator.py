"""
Agent Orchestrator — routes incoming requests to the best agent.

Uses intent detection (can_handle) to find the highest-confidence
agent for a given query. Now uses evolved confidence (memory-adjusted)
so agents improve routing decisions over time.

Task 13: Parallel agent evaluation with concurrency limiter
Task 14: Routing cache with SHA-256 keying for result memoization

Falls back to the default LLM loop if no agent exceeds the threshold.
"""

import hashlib
import logging
import os
from typing import TYPE_CHECKING
import concurrent.futures

if TYPE_CHECKING:
    from orchestrator.core import LLMClient, ToolExecutor

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.35
_agents_discovered = False

# Task 13: Concurrency limiter for parallel agent evaluation
# Bounded by min(len(agents), ROUTING_MAX_CONCURRENT, cpu_count, 8)
_ROUTING_MAX_CONCURRENT = min(3, os.cpu_count() or 1, 8)

# Task 14: Routing cache (namespace: "routing", key: sha256(query + version))
_routing_cache_enabled = True


def ensure_discovered():
    global _agents_discovered
    if not _agents_discovered:
        from agents import discover_agents
        discover_agents()
        _agents_discovered = True


def _get_routing_cache_key(query: str) -> str:
    """Generate SHA-256 cache key for routing result (Task 14).
    
    Key includes query normalization and agent registry version.
    """
    from orchestrator.cache_manager import get_cache_manager
    from agents import _AGENT_REGISTRY
    
    # Normalize query: strip whitespace, lowercase
    normalized = query.strip().lower()
    
    # Include registry version so cache auto-invalidates on agent reload
    registry_hash = hashlib.sha256(
        str(sorted(_AGENT_REGISTRY.keys())).encode()
    ).hexdigest()[:8]
    
    # SHA-256 of normalized query + registry hash
    cache_input = f"{normalized}|{registry_hash}"
    return hashlib.sha256(cache_input.encode()).hexdigest()


def select_agent(query: str) -> tuple[str, float] | None:
    """Find the best agent for a query using evolved (memory-adjusted) confidence.
    
    Task 13: Parallel evaluation of all agents with concurrency limit.
    Task 14: Result cached with SHA-256 key, invalidated on registry changes.
    """
    ensure_discovered()
    from agents import _AGENT_REGISTRY
    from orchestrator.cache_manager import get_cache_manager
    
    # Task 14: Check routing cache
    if _routing_cache_enabled:
        cache = get_cache_manager()
        cache_key = _get_routing_cache_key(query)
        cached_result = cache.get("routing", cache_key)
        if cached_result is not None:
            logger.debug("Routing cache hit for query (key=%s)", cache_key[:8])
            return cached_result

    best_name = None
    best_score = 0.0

    # Task 13: Parallel agent evaluation with concurrency limiter
    def _evaluate_agent(agent_item):
        """Evaluate a single agent's confidence."""
        name, agent = agent_item
        try:
            # Use evolved confidence that includes memory-based adjustments
            score = agent.can_handle_evolved(query)
            return name, score
        except Exception as e:
            logger.debug("Agent %s.can_handle_evolved failed: %s", name, e)
            return name, 0.0

    # Parallel evaluation bounded by concurrency limiter
    max_workers = min(len(_AGENT_REGISTRY), _ROUTING_MAX_CONCURRENT)
    if max_workers > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(_evaluate_agent, _AGENT_REGISTRY.items()))
            for name, score in results:
                if score > best_score:
                    best_score = score
                    best_name = name
    else:
        # Single agent or single-threaded fallback
        for name, agent in _AGENT_REGISTRY.items():
            _, score = _evaluate_agent((name, agent))
            if score > best_score:
                best_score = score
                best_name = name

    result = None
    if best_name and best_score >= _CONFIDENCE_THRESHOLD:
        result = (best_name, best_score)
        logger.info(
            "Agent routing: '%s' → %s (evolved confidence=%.2f, parallel eval)",
            query, best_name, best_score,
        )
    else:
        logger.info(
            "No agent matched query (best=%.2f, threshold=%.2f, parallel eval)",
            best_score, _CONFIDENCE_THRESHOLD,
        )

    # Task 14: Cache the result
    if _routing_cache_enabled and result is not None:
        cache = get_cache_manager()
        cache_key = _get_routing_cache_key(query)
        cache.set("routing", cache_key, result, ttl_seconds=3600)  # 1-hour TTL
    
    return result


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
