"""
Error Classifier — maps LLM API errors to typed reasons + recovery messages.

Pattern from hermes-agent/agent/error_classifier.py + billing_links.py.

Instead of raw HTTP error strings, callers get:
  - A typed FailoverReason enum (billing, rate_limit, auth, context_overflow, etc.)
  - A human-readable recovery message with a provider-specific billing URL

Usage in LLMClient::

    reason, message = classify_api_error(error_str, backend, base_url)
    if reason == FailoverReason.BILLING:
        return f"[Billing] {message}"
    elif reason == FailoverReason.RATE_LIMIT:
        # retry with backoff
    ...
"""

from __future__ import annotations

import re
from enum import Enum
from typing import NamedTuple


# ── Error reason taxonomy ────────────────────────────────────────────────────

class FailoverReason(str, Enum):
    """Typed classification of an LLM API error."""
    BILLING          = "billing"          # 402, credit exhausted, quota
    RATE_LIMIT       = "rate_limit"       # 429, too many requests
    AUTH             = "auth"             # 401, 403, invalid key
    CONTEXT_OVERFLOW = "context_overflow" # 413, context length exceeded
    MODEL_NOT_FOUND  = "model_not_found"  # 404, model not available
    SERVER_ERROR     = "server_error"     # 500, 502, 503, 504
    TIMEOUT          = "timeout"          # connect/read timeout
    UNKNOWN          = "unknown"          # anything else


class ClassifiedError(NamedTuple):
    reason: FailoverReason
    message: str           # user-facing recovery message
    is_retryable: bool     # True → caller should retry with backoff


# ── Provider billing URL table ───────────────────────────────────────────────
# Single source of truth: provider slug → (label, billing_url)
# Pattern from hermes-agent/agent/billing_links.py

_PROVIDER_BILLING: dict[str, tuple[str, str]] = {
    "openai":       ("OpenAI",       "https://platform.openai.com/settings/organization/billing"),
    "anthropic":    ("Anthropic",    "https://console.anthropic.com/settings/billing"),
    "groq":         ("Groq",         "https://console.groq.com/settings/billing"),
    "deepseek":     ("DeepSeek",     "https://platform.deepseek.com/top_up"),
    "mistral":      ("Mistral",      "https://console.mistral.ai/billing"),
    "openrouter":   ("OpenRouter",   "https://openrouter.ai/settings/credits"),
    "xai":          ("xAI",          "https://console.x.ai/team/default/billing"),
    "together":     ("Together AI",  "https://api.together.ai/settings/billing"),
    "fireworks":    ("Fireworks AI", "https://fireworks.ai/account/billing"),
    "cohere":       ("Cohere",       "https://dashboard.cohere.com/billing"),
    "perplexity":   ("Perplexity",   "https://www.perplexity.ai/settings/api"),
    "google":       ("Google AI",    "https://aistudio.google.com/app/billing"),
    "gemini":       ("Google AI",    "https://aistudio.google.com/app/billing"),
    "nvidia":       ("NVIDIA",       "https://build.nvidia.com/settings/billing"),
    "azure":        ("Azure OpenAI", "https://portal.azure.com/#blade/Microsoft_Azure_Billing/SubscriptionsBlade"),
}

# Base-URL host fragments → provider slug (fallback when slug is generic)
_HOST_TO_SLUG: list[tuple[str, str]] = [
    ("api.openai.com",                "openai"),
    ("api.anthropic.com",             "anthropic"),
    ("api.groq.com",                  "groq"),
    ("api.deepseek.com",              "deepseek"),
    ("api.mistral.ai",                "mistral"),
    ("openrouter.ai",                 "openrouter"),
    ("api.x.ai",                      "xai"),
    ("api.together.ai",               "together"),
    ("api.together.xyz",              "together"),
    ("fireworks.ai",                  "fireworks"),
    ("api.cohere.ai",                 "cohere"),
    ("api.perplexity.ai",             "perplexity"),
    ("generativelanguage.googleapis", "gemini"),
    ("azure.com",                     "azure"),
]


def _resolve_provider_slug(backend: str, base_url: str) -> str:
    """Best-effort resolution of a provider slug from backend name or base_url."""
    slug = (backend or "").strip().lower()
    # Direct match
    if slug in _PROVIDER_BILLING:
        return slug
    # Partial match on slug (e.g. "ollama-local" → no billing URL)
    for key in _PROVIDER_BILLING:
        if key in slug:
            return key
    # Fallback: match base_url host
    url_lower = (base_url or "").lower()
    for host_fragment, mapped_slug in _HOST_TO_SLUG:
        if host_fragment in url_lower:
            return mapped_slug
    return slug  # unknown


def _billing_message(slug: str, model: str, raw_error: str) -> str:
    """Compose a user-facing billing recovery message."""
    info = _PROVIDER_BILLING.get(slug)
    if info:
        label, url = info
        model_str = f" (model: {model})" if model else ""
        return (
            f"Your {label} account has run out of credits or reached its quota{model_str}. "
            f"Top up or upgrade at: {url}"
        )
    label = slug.replace("_", " ").replace("-", " ").title() or "your provider"
    return (
        f"Your {label} account has run out of credits or reached its quota. "
        f"Check your provider's billing dashboard. Raw error: {raw_error[:120]}"
    )


def _rate_limit_message(slug: str, raw_error: str) -> str:
    """Compose a user-facing rate-limit message."""
    info = _PROVIDER_BILLING.get(slug)
    label = info[0] if info else (slug.replace("_", " ").title() or "The provider")
    return (
        f"{label} rate limit reached. Raphael will retry automatically with backoff. "
        f"If this persists, check your plan limits."
    )


def _auth_message(slug: str, raw_error: str) -> str:
    info = _PROVIDER_BILLING.get(slug)
    label = info[0] if info else (slug.replace("_", " ").title() or "The provider")
    return (
        f"{label} rejected the API key (authentication error). "
        f"Check your API key in Settings → Endpoints. Raw: {raw_error[:80]}"
    )


def _context_overflow_message(raw_error: str) -> str:
    return (
        "The request exceeded the model's context window. "
        "Raphael will try to compress the conversation and retry. "
        f"Details: {raw_error[:120]}"
    )


# ── Classification logic ─────────────────────────────────────────────────────

# Patterns checked against the lowercased error string
_BILLING_PATTERNS = re.compile(
    r"402|insufficient[_\s]credits?|credit[s]?\s*(exhausted|depleted|insufficient|limit|quota)"
    r"|quota.*exceeded|billing|payment required|exceeded.*limit|out of credits"
    r"|account.*balance|credits? required|upgrade.*plan|subscription.*expired"
    r"|payment_required|credits_exhausted|insufficient_quota"
)

_RATE_LIMIT_PATTERNS = re.compile(
    r"429|rate[_\s]limit|too many requests|requests? per (minute|second|hour|day)"
    r"|throttl(e|ing|ed)|slow down|retry[_\s]after|ratelimit"
)

_AUTH_PATTERNS = re.compile(
    r"401|403|unauthorized|authentication|invalid[_\s]api[_\s]key|api[_\s]key.*invalid"
    r"|incorrect[_\s]api[_\s]key|invalid[_\s]key|permission denied|forbidden"
    r"|access denied|no[_\s]auth|missing[_\s]auth|invalid[_\s]token"
)

_CONTEXT_PATTERNS = re.compile(
    r"413|context[_\s]length|maximum context|token[s]?\s*(limit|exceed|too long)"
    r"|too many tokens|input too long|prompt.*too long|context.*window.*exceeded"
    r"|string too long|max_tokens.*exceed|request too large|payload too large"
)

_MODEL_PATTERNS = re.compile(
    r"404|model.*not.*found|model.*not.*exist|no such model|invalid model"
    r"|model.*unavailable|model.*not.*support|does not exist"
)

_SERVER_PATTERNS = re.compile(
    r"500|502|503|504|internal server error|bad gateway|service unavailable"
    r"|gateway timeout|server error|overloaded|capacity"
)

_TIMEOUT_PATTERNS = re.compile(
    r"timed? out|timeout|connection.*reset|connection.*refused|connect.*error"
    r"|read timeout|write timeout|network error|eof|broken pipe"
)


def classify_api_error(
    error: str | Exception,
    backend: str = "",
    base_url: str = "",
    model: str = "",
) -> ClassifiedError:
    """Classify an LLM API error into a typed reason + recovery message.

    Args:
        error:    Exception or error string from the LLM client.
        backend:  Endpoint name (e.g. "groq", "openai", "ollama-local").
        base_url: Base URL of the endpoint (used as fallback for provider detection).
        model:    Model name involved, for display purposes.

    Returns:
        ClassifiedError(reason, message, is_retryable)
    """
    raw = str(error).strip()
    low = raw.lower()

    slug = _resolve_provider_slug(backend, base_url)

    # Check patterns in priority order
    if _BILLING_PATTERNS.search(low):
        return ClassifiedError(
            reason=FailoverReason.BILLING,
            message=_billing_message(slug, model, raw),
            is_retryable=False,
        )

    if _AUTH_PATTERNS.search(low):
        return ClassifiedError(
            reason=FailoverReason.AUTH,
            message=_auth_message(slug, raw),
            is_retryable=False,
        )

    if _RATE_LIMIT_PATTERNS.search(low):
        return ClassifiedError(
            reason=FailoverReason.RATE_LIMIT,
            message=_rate_limit_message(slug, raw),
            is_retryable=True,
        )

    if _CONTEXT_PATTERNS.search(low):
        return ClassifiedError(
            reason=FailoverReason.CONTEXT_OVERFLOW,
            message=_context_overflow_message(raw),
            is_retryable=True,
        )

    if _MODEL_PATTERNS.search(low):
        return ClassifiedError(
            reason=FailoverReason.MODEL_NOT_FOUND,
            message=f"Model '{model or 'unknown'}' was not found on {backend or 'the provider'}. Check your endpoint configuration.",
            is_retryable=False,
        )

    if _SERVER_PATTERNS.search(low):
        return ClassifiedError(
            reason=FailoverReason.SERVER_ERROR,
            message=f"The {backend or 'LLM'} server returned an error. Raphael will retry automatically.",
            is_retryable=True,
        )

    if _TIMEOUT_PATTERNS.search(low):
        return ClassifiedError(
            reason=FailoverReason.TIMEOUT,
            message=f"Request to {backend or 'the LLM'} timed out. Check that the endpoint is running and reachable.",
            is_retryable=True,
        )

    return ClassifiedError(
        reason=FailoverReason.UNKNOWN,
        message=f"[LLM Error — {backend or 'unknown'}]: {raw[:200]}",
        is_retryable=False,
    )


def format_error_for_user(classified: ClassifiedError) -> str:
    """Format a classified error as a user-facing response string."""
    icons = {
        FailoverReason.BILLING:          "💳",
        FailoverReason.RATE_LIMIT:       "⏱",
        FailoverReason.AUTH:             "🔑",
        FailoverReason.CONTEXT_OVERFLOW: "📄",
        FailoverReason.MODEL_NOT_FOUND:  "🔍",
        FailoverReason.SERVER_ERROR:     "⚠️",
        FailoverReason.TIMEOUT:          "🌐",
        FailoverReason.UNKNOWN:          "❌",
    }
    icon = icons.get(classified.reason, "❌")
    return f"{icon} {classified.message}"
