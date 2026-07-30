"""
Agent Evolution Memory — lets agents learn, adapt, and improve over time.

Each agent has a persistent namespace storing:
- corrections: user corrections extracted into behavioral rules
- interactions: log of queries handled, tools used, outcomes
- rules: derived behavioral guidelines that evolve with use

All read/write operations are LLM-powered so the system evolves
its understanding without hardcoded schema changes.

Data flow:
  Before execution: get_context() → inject learned rules into agent prompt
  After execution:  record_interaction() → log what happened
  On correction:    process_correction() → extract rule from user feedback
  Background:       consolidate() → merge/clean/prune rules
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

import config

AGENT_MEMORY_PATH = config.ROAMING_DIR / "memory" / "agent_evolution.json"

_MAX_INTERACTIONS = 50  # ring buffer per agent


# ──────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────


def _load() -> dict:
    """Load agent memory from disk. Returns empty dict on error."""
    if not AGENT_MEMORY_PATH.exists():
        return {}
    try:
        text = AGENT_MEMORY_PATH.read_text(encoding="utf-8").strip()
        if not text:
            return {}
        return json.loads(text)  # type: ignore[no-any-return]
    except Exception as e:
        logger.warning("Could not parse agent memory JSON (%s) — initializing empty memory structure", e)
        return {}


def _save(data: dict):
    """Atomically save agent memory to disk."""
    AGENT_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = AGENT_MEMORY_PATH.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp_path.replace(AGENT_MEMORY_PATH)


def _ensure_agent(memory: dict, agent_name: str) -> dict:
    """Ensure an agent namespace exists with default structure."""
    if agent_name not in memory:
        memory[agent_name] = {
            "interactions": [],
            "corrections": [],
            "rules": [],
        }
    ns = memory[agent_name]
    ns.setdefault("interactions", [])
    ns.setdefault("corrections", [])
    ns.setdefault("rules", [])
    return ns  # type: ignore[no-any-return]


def _call_llm(system_prompt: str, reason: str = "agent_evolution") -> str:
    """Stateless LLM call — pure text, no tools, fresh client."""
    try:
        from orchestrator.core import LLMClient
        client = LLMClient()
        messages = [{"role": "system", "content": system_prompt}]
        resp = client.chat(messages, reason=reason)
        if resp and resp.content:  # type: ignore[attr-defined]
            return resp.content.strip()  # type: ignore[attr-defined,no-any-return]
    except Exception as e:
        logger.debug("Agent memory LLM call failed: %s", e)
    return ""


def _extract_json(text: str):
    """Strip markdown fences and extract JSON from LLM output."""
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


# ──────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────


def get_context(agent_name: str, query: str) -> str:
    """
    Get relevant evolved context for an agent facing a query.

    Uses LLM to select which past rules and corrections apply
    to the current query. Returns formatted text or empty string.
    """
    memory = _load()
    agent_data = _ensure_agent(memory, agent_name)
    corrections = agent_data.get("corrections", [])
    rules = agent_data.get("rules", [])

    if not corrections and not rules:
        return ""

    prompt = (
        f"You are the Evolution Engine for the '{agent_name}' agent. "
        "Select relevant past learnings that apply to the current query.\n\n"
        f"Known behavioral rules:\n{json.dumps(rules, indent=2)}\n\n"
        f"Past corrections:\n{json.dumps(corrections, indent=2)}\n\n"
        f"Current query: '{query}'\n\n"
        "Output ONLY the rules and corrections relevant to this specific query. "
        "Format as concise behavioral instructions the agent should follow. "
        "If nothing is relevant, output 'None'."
    )

    result = _call_llm(prompt, reason="get_context")
    if not result or result.strip().lower() == "none":
        return ""

    return (
        f"[Agent Evolution Memory — learned behavior for '{agent_name}']\n"
        f"{result}\n"
    )


def record_interaction(
    agent_name: str,
    query: str,
    tools_used: list[str],
    outcome: str = "completed",
):
    """Log an agent interaction for pattern learning."""
    memory = _load()
    agent_data = _ensure_agent(memory, agent_name)
    interactions = agent_data["interactions"]

    interactions.append({
        "query": query[:200],
        "tools_used": tools_used,
        "outcome": outcome,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })

    # Ring buffer — keep most recent
    if len(interactions) > _MAX_INTERACTIONS:
        interactions[:] = interactions[-_MAX_INTERACTIONS:]

    _save(memory)
    logger.debug("Recorded interaction for '%s': %s", agent_name, outcome)


def process_correction(agent_name: str, original_query: str, correction_text: str):
    """
    Process a user correction into a behavioral rule.

    Uses LLM to understand the correction and extract
    a specific rule the agent should follow in the future.
    """
    prompt = (
        f"You are the Evolution Engine for the '{agent_name}' agent.\n\n"
        f"The user's original query was: '{original_query}'\n"
        f"The user is now correcting or teaching: '{correction_text}'\n\n"
        "Extract a specific behavioral rule the agent should follow in the future.\n"
        "Output a JSON object with exactly these fields:\n"
        '{"rule": "<specific instruction for the agent>", '
        '"condition": "<when this applies — query pattern>", '
        '"source": "correction"}\n\n'
        'If the correction is NOT about agent behavior, output: null\n'
        "Output ONLY valid JSON, no explanation."
    )

    result = _call_llm(prompt, reason="process_correction")
    if not result:
        return

    try:
        text = _extract_json(result)
        rule_data = json.loads(text)
        if rule_data is None:
            return

        memory = _load()
        agent_data = _ensure_agent(memory, agent_name)

        # Append the correction
        agent_data["corrections"].append({
            "query": original_query[:200],
            "correction": correction_text[:500],
            "rule": rule_data.get("rule", ""),
            "condition": rule_data.get("condition", ""),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

        # Add the extracted rule
        agent_data["rules"].append({
            "rule": rule_data.get("rule", ""),
            "condition": rule_data.get("condition", ""),
            "source": "correction",
        })

        _save(memory)
        logger.info(
            "Agent '%s' learned rule from correction: %s",
            agent_name, rule_data.get("rule", ""),
        )
    except Exception as e:
        logger.error("Failed to process correction for '%s': %s", agent_name, e)


def get_confidence_adjustment(agent_name: str, query: str) -> float:
    """
    Returns a confidence adjustment (-0.3 to +0.3) based on past experience.

    Positive means the agent has succeeded on similar queries before.
    Negative means corrections or failures suggest lower confidence.
    """
    memory = _load()
    agent_data = _ensure_agent(memory, agent_name)
    rules = agent_data.get("rules", [])
    interactions = agent_data.get("interactions", [])

    if not rules and not interactions:
        return 0.0

    prompt = (
        f"You are the confidence adjuster for the '{agent_name}' agent.\n\n"
        f"Behavioral rules for this agent:\n{json.dumps(rules, indent=2)}\n\n"
        f"Recent interactions:\n{json.dumps(interactions[-10:], indent=2)}\n\n"
        f"Current query: '{query}'\n\n"
        "Should this agent's confidence be adjusted for this query?\n"
        "- Past success with similar queries: boost 0.1 to 0.3\n"
        "- Corrections suggest not handling this: reduce -0.3 to -0.1\n"
        "- No strong signal: 0.0\n"
        "Output ONLY a number between -0.3 and 0.3, e.g. '0.15' or '-0.2' or '0.0'"
    )

    result = _call_llm(prompt, reason="confidence_adjustment")
    if not result:
        return 0.0

    try:
        adj = float(result.strip())
        return max(-0.3, min(0.3, adj))
    except ValueError:
        return 0.0


def consolidate():
    """
    Background consolidation: review interactions, merge duplicate rules,
    prune outdated corrections, detect emerging patterns.

    Called periodically during idle time or after significant interaction counts.
    """
    memory = _load()
    if not memory:
        return

    for agent_name, agent_data in memory.items():
        rules = agent_data.get("rules", [])
        corrections = agent_data.get("corrections", [])
        interactions = agent_data.get("interactions", [])

        # Skip agents with little data
        if len(rules) < 3 and len(corrections) < 3:
            continue

        prompt = (
            f"You are the consolidation engine for the '{agent_name}' agent.\n\n"
            f"Current behavioral rules:\n{json.dumps(rules, indent=2)}\n\n"
            f"Correction history:\n{json.dumps(corrections, indent=2)}\n\n"
            f"Recent interactions:\n{json.dumps(interactions[-20:], indent=2)}\n\n"
            "Review and consolidate:\n"
            "1. Merge duplicate or overlapping rules\n"
            "2. Remove rules contradicted by newer corrections\n"
            "3. Identify any emerging patterns from interactions\n"
            "4. Keep rules concise and actionable\n\n"
            "Output a JSON array of consolidated rule objects. "
            'Each object must have: "rule", "condition", "source".\n'
            "Example: [{\"rule\": \"...\", \"condition\": \"...\", \"source\": \"correction\"}]\n"
            "If no rules remain, output: []\n"
            "Output ONLY the JSON array."
        )

        result = _call_llm(prompt, reason="consolidate")
        if not result:
            continue

        try:
            text = _extract_json(result)
            # Find JSON array in the output
            start = text.index("[")
            end = text.rindex("]") + 1
            consolidated = json.loads(text[start:end])
            if isinstance(consolidated, list):
                agent_data["rules"] = consolidated
                logger.info(
                    "Consolidated '%s' rules → %d rules",
                    agent_name, len(consolidated),
                )
        except (ValueError, json.JSONDecodeError) as e:
            logger.debug("Consolidation parse failed for '%s': %s", agent_name, e)

    _save(memory)


def get_interaction_summary(agent_name: str) -> str:
    """Get a short summary of agent activity for monitoring/debugging."""
    memory = _load()
    agent_data = _ensure_agent(memory, agent_name)
    rules = agent_data.get("rules", [])
    interactions = agent_data.get("interactions", [])
    corrections = agent_data.get("corrections", [])

    return (
        f"Agent '{agent_name}': "
        f"{len(interactions)} interactions, "
        f"{len(corrections)} corrections, "
        f"{len(rules)} active rules"
    )
