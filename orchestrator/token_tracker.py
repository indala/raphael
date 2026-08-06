"""
Token and Cost Tracker — per-session LLM usage monitoring.

Pattern from hermes-agent/agent/billing_usage.py.

Tracks:
  - Prompt tokens (input) and completion tokens (output) per LLM call
  - Estimated dollar cost using a provider + model cost table
  - Session totals (tokens + cost) with a formatted summary

Cost table covers common models at current public pricing (per 1M tokens):
  OpenAI, Anthropic, Groq, Google, Mistral, DeepSeek, Ollama (free).

Usage::

    tracker = get_tracker()                    # global singleton
    tracker.record(response, backend, model)   # call after each LLM response
    print(tracker.format_summary())            # at session end or on demand

get_session_cost() is exposed as a tool the LLM can call.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# ── Cost table ───────────────────────────────────────────────────────────────
# USD per 1 million tokens (input, output).
# Ollama and other local models are free ($0).
# Update when pricing changes — these are reference values.

_COST_TABLE: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o":                    (2.50,  10.00),
    "gpt-4o-mini":               (0.15,   0.60),
    "gpt-4-turbo":               (10.00, 30.00),
    "gpt-4":                     (30.00, 60.00),
    "gpt-3.5-turbo":             (0.50,  1.50),
    "o1":                        (15.00, 60.00),
    "o1-mini":                   (3.00,  12.00),
    "o3-mini":                   (1.10,   4.40),

    # Anthropic
    "claude-3-5-sonnet":         (3.00,  15.00),
    "claude-3-5-haiku":          (0.80,   4.00),
    "claude-3-opus":             (15.00, 75.00),
    "claude-3-sonnet":           (3.00,  15.00),
    "claude-3-haiku":            (0.25,   1.25),

    # Groq (hosted inference, very cheap)
    "llama-3.1-70b-versatile":   (0.59,  0.79),
    "llama-3.1-8b-instant":      (0.05,  0.08),
    "llama3-70b-8192":           (0.59,  0.79),
    "llama3-8b-8192":            (0.05,  0.08),
    "mixtral-8x7b-32768":        (0.24,  0.24),
    "gemma2-9b-it":              (0.20,  0.20),

    # Google
    "gemini-1.5-pro":            (1.25,  5.00),
    "gemini-1.5-flash":          (0.075, 0.30),
    "gemini-2.0-flash":          (0.10,  0.40),
    "gemini-2.5-pro":            (1.25,  10.00),
    "gemini-2.5-flash":          (0.15,  0.60),

    # Mistral
    "mistral-large":             (3.00,  9.00),
    "mistral-small":             (0.20,  0.60),
    "codestral":                 (0.20,  0.60),

    # DeepSeek
    "deepseek-chat":             (0.07,  1.10),
    "deepseek-coder":            (0.07,  1.10),
    "deepseek-reasoner":         (0.55,  2.19),

    # xAI
    "grok-2":                    (2.00,  10.00),
    "grok-beta":                 (5.00,  15.00),

    # Together AI
    "meta-llama/llama-3.1-70b-instruct": (0.88, 0.88),
    "meta-llama/llama-3.1-8b-instruct":  (0.18, 0.18),

    # Ollama / local — always free
    "ollama":                    (0.0, 0.0),
    "local":                     (0.0, 0.0),
}

# Backend slug → cost override when model name isn't in the table
_BACKEND_FREE: frozenset[str] = frozenset({
    "ollama", "ollama-local", "ollama-cloud", "vllm", "lmstudio",
    "mlx", "llamacpp", "local",
})


def _lookup_cost(model: str, backend: str) -> tuple[float, float]:
    """Return (input_cost_per_1m, output_cost_per_1m) for a model.

    Match strategy:
    1. Exact model name match
    2. Model name prefix match (handles version suffixes like -20250101)
    3. Backend is a known free/local backend → (0, 0)
    4. Unknown → (0, 0) with a debug log
    """
    if backend.lower() in _BACKEND_FREE:
        return (0.0, 0.0)

    model_lower = model.lower().strip()

    # Exact match
    if model_lower in _COST_TABLE:
        return _COST_TABLE[model_lower]

    # Prefix match (longest prefix wins)
    best_key = ""
    for key in _COST_TABLE:
        if model_lower.startswith(key) and len(key) > len(best_key):
            best_key = key
    if best_key:
        return _COST_TABLE[best_key]

    logger.debug("token_tracker: no cost entry for model='%s' backend='%s'", model, backend)
    return (0.0, 0.0)


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class TokenUsage:
    """Token counts for a single LLM call."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    backend: str = ""
    reason: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class SessionUsage:
    """Accumulated token and cost totals for the current session."""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    call_count: int = 0
    session_start: datetime = field(default_factory=datetime.now)
    records: list[TokenUsage] = field(default_factory=list)

    def add(self, usage: TokenUsage) -> None:
        self.total_prompt_tokens    += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens           += usage.total_tokens
        self.total_cost_usd         += usage.cost_usd
        self.call_count             += 1
        self.records.append(usage)
        # Keep only last 200 records to avoid unbounded growth
        if len(self.records) > 200:
            self.records = self.records[-200:]


# ── Tracker ───────────────────────────────────────────────────────────────────

class TokenTracker:
    """Thread-safe per-session token and cost tracker."""

    def __init__(self):
        self._lock = threading.Lock()
        self._session = SessionUsage()

    def record(
        self,
        response: Any,
        backend: str = "",
        model: str = "",
        reason: str = "",
    ) -> TokenUsage | None:
        """Extract usage from an LLM response and record it.

        Handles both OpenAI SDK response objects (``response.usage``) and
        plain dict responses. Silently returns None if no usage data is
        available (streaming responses don't always include usage).
        """
        usage_obj = None

        # OpenAI SDK response
        if hasattr(response, "usage") and response.usage:
            usage_obj = response.usage

        # Dict-shaped usage (some OpenAI-compat wrappers)
        elif isinstance(response, dict) and "usage" in response:
            usage_obj = response["usage"]

        if usage_obj is None:
            return None

        # Extract token counts (handle both object and dict forms)
        def _get(obj, key: str, default: int = 0) -> int:
            if isinstance(obj, dict):
                return int(obj.get(key, default))
            return int(getattr(obj, key, default))

        prompt_tokens     = _get(usage_obj, "prompt_tokens")
        completion_tokens = _get(usage_obj, "completion_tokens")
        total_tokens      = _get(usage_obj, "total_tokens") or (prompt_tokens + completion_tokens)

        # Calculate cost
        in_rate, out_rate = _lookup_cost(model, backend)
        cost_usd = (
            (prompt_tokens     / 1_000_000) * in_rate
            + (completion_tokens / 1_000_000) * out_rate
        )

        token_usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            model=model,
            backend=backend,
            reason=reason,
        )

        with self._lock:
            self._session.add(token_usage)

        if cost_usd > 0:
            logger.debug(
                "token_tracker: %s/%s prompt=%d completion=%d cost=$%.6f",
                backend, model, prompt_tokens, completion_tokens, cost_usd,
            )

        return token_usage

    def get_session(self) -> SessionUsage:
        """Return a snapshot of the current session usage."""
        with self._lock:
            return self._session

    def reset_session(self) -> None:
        """Reset session counters (call at session start)."""
        with self._lock:
            self._session = SessionUsage()

    def format_summary(self, verbose: bool = False) -> str:
        """Return a formatted session usage summary."""
        with self._lock:
            s = self._session

        if s.call_count == 0:
            return "No LLM calls recorded this session."

        duration = datetime.now() - s.session_start
        hours, rem = divmod(int(duration.total_seconds()), 3600)
        minutes = rem // 60
        duration_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"

        lines = [
            f"📊 Session Usage ({duration_str})",
            f"  Calls:      {s.call_count}",
            f"  Tokens:     {s.total_tokens:,} "
            f"({s.total_prompt_tokens:,} in + {s.total_completion_tokens:,} out)",
        ]

        if s.total_cost_usd > 0:
            lines.append(f"  Est. cost:  ${s.total_cost_usd:.4f} USD")
        else:
            lines.append("  Est. cost:  $0.00 (local/free model)")

        if verbose and s.records:
            lines.append("\n  Recent calls:")
            for r in s.records[-5:]:
                cost_str = f"  ${r.cost_usd:.5f}" if r.cost_usd else ""
                lines.append(
                    f"    {r.backend}/{r.model} — {r.total_tokens:,} tokens{cost_str} [{r.reason}]"
                )

        return "\n".join(lines)


# ── Global singleton ──────────────────────────────────────────────────────────

_tracker: TokenTracker | None = None
_tracker_lock = threading.Lock()


def get_tracker() -> TokenTracker:
    """Return the global TokenTracker singleton."""
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = TokenTracker()
    return _tracker


def get_session_cost() -> str:
    """Tool-callable: return current session token usage and cost summary."""
    return get_tracker().format_summary(verbose=True)
