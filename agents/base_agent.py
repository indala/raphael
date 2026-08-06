"""
Base Agent ABC — routes tasks to skills.

An agent has:
- can_handle(query) → confidence 0.0-1.0 for intent routing
- run(query, llm, executor) → response string
- available_tools: list of tool names this agent may use ([] = all tools)

Agents now have evolution hooks (agent memory):
- _load_agent_memory(query) → injects learned context before execution
- _record_outcome(query, tools, outcome) → logs what happened
- _get_dynamic_confidence(query, base) → adjusts confidence from experience
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.core import LLMClient, ToolExecutor


class BaseAgent(ABC):
    """Abstract base for all agents."""

    name: str = ""
    description: str = ""
    available_tools: list[str] = []  # [] means ALL tools are available
    max_rounds: int = 8

    # Delegation tools made available to every agent automatically
    _DELEGATION_TOOLS = ["list_agents", "delegate_to_agent", "delegate_background", "check_task"]

    def __init_subclass__(cls, **kwargs):
        """Automatically inject delegation tools into every agent's available_tools."""
        super().__init_subclass__(**kwargs)
        if cls.available_tools is not None and len(cls.available_tools) > 0:
            for dt in cls._DELEGATION_TOOLS:
                if dt not in cls.available_tools:
                    cls.available_tools = [*cls.available_tools, dt]

    def can_handle(self, query: str) -> float:
        """
        LLM-based intent routing with description matching.

        When agent memory is empty (cold start), uses a lightweight LLM call
        to match the query against this agent's description. Returns confidence
        0.0-1.0 based on semantic similarity.

        Once memory accumulates, can_handle_evolved() adds memory-based adjustments.
        """
        # Check if agent has memory — if so, defer to evolved routing
        try:
            from memory.agent_memory import _load
            memory = _load()
            agent_data = memory.get(self.name, {})
            has_memory = bool(
                agent_data.get("interactions") or 
                agent_data.get("corrections") or 
                agent_data.get("rules")
            )
            if has_memory:
                # Memory exists — let can_handle_evolved() handle routing
                return 0.0
        except Exception:
            pass

        # Cold start — use LLM-based description matching
        if not self.description or not query:
            return 0.0

        try:
            from orchestrator.core import LLMClient
            client = LLMClient()
            
            prompt = (
                f"You are a routing classifier. Determine if this query matches the agent's capability.\n\n"
                f"Agent: {self.name}\n"
                f"Description: {self.description}\n\n"
                f"Query: {query}\n\n"
                "Output ONLY a confidence score 0.0-1.0 where:\n"
                "- 0.0-0.3: Not a match\n"
                "- 0.4-0.6: Possible match\n"
                "- 0.7-1.0: Strong match\n\n"
                "Output ONLY the number (e.g. '0.75'), no explanation."
            )
            
            messages = [{"role": "system", "content": prompt}]
            resp = client.chat(messages, tools=None, reason="agent_routing_seed")
            
            if resp and hasattr(resp, "content") and resp.content:
                score_text = resp.content.strip()
                score = float(score_text)
                return max(0.0, min(1.0, score))
        except Exception:
            pass
        
        return 0.0

    @abstractmethod
    def run(self, query: str, llm: LLMClient, executor: ToolExecutor) -> str:
        """Execute the task using available skills and tools. Returns response text."""
        ...

    # ──────────────────────────────────────────────
    #  Evolution Hooks
    # ──────────────────────────────────────────────

    def can_handle_evolved(self, query: str) -> float:
        """
        Dynamic can_handle — static baseline + memory-based adjustment.

        Returns confidence 0.0-1.0 incorporating what the agent
        has learned from past corrections and successful interactions.
        """
        base = self.can_handle(query)
        adjustment = self._get_confidence_adjustment(query)
        evolved = max(0.0, min(1.0, base + adjustment))
        if evolved != base:
            import logging
            logging.getLogger(__name__).debug(
                "'%s' confidence: %.2f base → %.2f evolved (adj=%.2f)",
                self.name, base, evolved, adjustment,
            )
        return evolved

    def _load_agent_memory(self, query: str) -> str:
        """
        Load relevant evolved context from agent memory.

        Injected into the agent's system prompt before execution
        so the agent benefits from past learnings.
        """
        try:
            from memory.agent_memory import get_context
            return get_context(self.name, query)
        except Exception:
            return ""

    def _record_outcome(
        self, query: str, tools_used: list[str], outcome: str = "completed"
    ):
        """Log this interaction to agent memory for future learning."""
        try:
            from memory.agent_memory import record_interaction
            record_interaction(self.name, query, tools_used, outcome)
        except Exception:
            pass

    def _get_confidence_adjustment(self, query: str) -> float:
        """
        Get memory-based confidence adjustment (-0.3 to +0.3).

        Override in subclasses to add agent-specific logic.
        """
        try:
            from memory.agent_memory import get_confidence_adjustment
            return get_confidence_adjustment(self.name, query)
        except Exception:
            return 0.0

    def _apply_correction(self, original_query: str, correction_text: str):
        """
        Process a user correction into a learned rule for this agent.
        """
        try:
            from memory.agent_memory import process_correction
            process_correction(self.name, original_query, correction_text)
        except Exception:
            pass

    # ──────────────────────────────────────────────
    #  Capabilities
    # ──────────────────────────────────────────────

    def get_capabilities(self) -> dict:
        """Return a description of this agent's capabilities for other agents."""
        return {
            "name": self.name,
            "description": self.description,
            "available_tools": list(self.available_tools) if self.available_tools else ["*"],
        }
