"""
Health Check — lightweight endpoint ping to verify model reachability.

After saving an endpoint, call ``ping_endpoint()`` to send a minimal chat
completion and confirm the primary model responds correctly.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_PING_TIMEOUT_SECS = 15
_DISCOVERY_TIMEOUT_SECS = 6
_PING_PROMPT = "Respond with exactly one word: ok"


class PingResult:
    """Outcome of a single endpoint ping."""

    def __init__(self, ok: bool, model: str, latency_ms: int = 0, error: str = ""):
        self.ok = ok
        self.model = model
        self.latency_ms = latency_ms
        self.error = error

    @property
    def summary(self) -> str:
        if self.ok:
            return f"✅  {self.model}  responded  OK  ({self.latency_ms}ms)"
        return f"❌  {self.model}  —  {self.error}"


def ping_endpoint(
    base_url: str,
    api_key: str,
    model: str,
    timeout: int = _PING_TIMEOUT_SECS,
) -> PingResult:
    """Send a single-turn chat completion to verify the endpoint works.

    Args:
        base_url: Full base URL of the endpoint (e.g. ``https://api.openai.com/v1``).
        api_key: API key or bearer token.
        model: Model identifier to test.
        timeout: Request timeout in seconds.

    Returns:
        A PingResult with ``ok=True`` on success or ``ok=False`` with an error message.
    """
    if not base_url or not model:
        return PingResult(False, model, error="Base URL or model is empty — skipping")

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": _PING_PROMPT}],
        "max_tokens": 4,
        "temperature": 0,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = int((time.monotonic() - start) * 1000)
            data = json.loads(resp.read().decode("utf-8"))
            reply = (
                (data.get("choices") or [{}])[0]
                .get("message") or {}
            ).get("content") or ""
            reply = reply.strip().lower()
            if reply and "ok" in reply:
                return PingResult(True, model, elapsed)
            logger.debug("Ping reply unexpected: %r", reply)
            return PingResult(False, model, error=f"Unexpected response: {reply[:80]}")
    except urllib.error.HTTPError as exc:
        detail = ""
        with contextlib.suppress(Exception):
            detail = exc.read().decode("utf-8", errors="replace")[:200]
        msg = f"HTTP {exc.code}"
        if detail:
            msg += f": {detail}"
        return PingResult(False, model, error=msg)
    except urllib.error.URLError as exc:
        return PingResult(False, model, error=f"Connection failed: {exc.reason}")
    except TimeoutError:
        return PingResult(False, model, error=f"Timed out after {timeout}s")
    except Exception as exc:
        logger.exception("Ping failed unexpectedly")
        return PingResult(False, model, error=str(exc))


def discover_models(
    base_url: str,
    api_key: str = "",
    timeout: int = _DISCOVERY_TIMEOUT_SECS,
) -> list[str]:
    """Fetch available model IDs from an OpenAI-compatible ``/v1/models`` endpoint.

    Used for providers whose model roster changes dynamically (Ollama, Groq,
    OpenRouter, LM Studio, etc.). Returns an empty list on failure.

    Args:
        base_url: Base URL of the API endpoint.
        api_key: Optional bearer token.
        timeout: Request timeout in seconds.

    Returns:
        Sorted list of model ``id`` strings, or ``[]`` on error.
    """
    if not base_url:
        return []

    url = base_url.rstrip("/") + "/models"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw: list[dict] = data.get("data") or []
            models = sorted({
                entry["id"]
                for entry in raw
                if isinstance(entry, dict) and entry.get("id")
            })
            logger.debug("Discovered %d models from %s", len(models), url)
            return models
    except urllib.error.HTTPError as exc:
        logger.debug("Model discovery HTTP %d for %s: %.120s", exc.code, url,
                      exc.read().decode("utf-8", errors="replace") if exc.fp else "")
        return []
    except urllib.error.URLError as exc:
        logger.debug("Model discovery connection error for %s: %s", url, exc.reason)
        return []
    except TimeoutError:
        logger.debug("Model discovery timed out for %s", url)
        return []
    except Exception as exc:
        logger.debug("Model discovery failed for %s: %s", url, exc)
        return []
