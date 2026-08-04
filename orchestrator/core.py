"""
Core orchestrator — the brain of Raphael.
Manages the LLM conversation loop, tool execution, and module coordination.
"""

import json
import logging
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any, ClassVar

import httpx
from openai import OpenAI

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import contextlib

import config
from controller.state import state
from orchestrator.background import BackgroundTask, init_runner
from orchestrator.event_adapter import stream_with_events
from orchestrator.event_bus import (
    TASK_COMPLETED,
    TASK_FINISHED,
    TOOL_EXECUTED,
    TOOL_FAILED,
    EventBus,
)
from orchestrator.event_payloads import TaskFinishedPayload
from orchestrator.events import (
    InterruptedEvent,
    ProgressEvent,
    StreamEvent,
    TaskCompleteEvent,
    TaskErrorEvent,
    ThinkingEvent,
    TokenEvent,
    ToolErrorEvent,
    ToolResultEvent,
    ToolStartEvent,
)
from orchestrator.log_utils import (
    clear_request_id,
    finalize_timeline,
    log_event,
    set_request_id,
    start_timeline,
)
from orchestrator.plugin import get_hooks
from orchestrator.policy import evaluate_tool_call, permission_message
from orchestrator.tools import get_tool_map, get_tool_schemas

logger = logging.getLogger(__name__)


class _LLMResponse:
    """Simple wrapper to make error responses work like OpenAI response objects."""
    def __init__(self, content: str):
        self.content = content
        self.tool_calls = None


class LLMClient:
    """Abstracted LLM client supporting multiple backends with fallback."""

    def __init__(self, backend: str | None = None, model: str | None = None, fallback_model: str | None = None,
                 endpoint: str | None = None):
        # ── Resolve endpoint from registry ──────────────────────────
        self.backend = backend or config.LLM_BACKEND
        self._original_backend = self.backend
        self._endpoint_name = endpoint or self.backend

        # Load from dynamic endpoint registry
        self._ep = self._resolve_endpoint(self._endpoint_name)
        self._build_state(model, fallback_model)

        self._auth_failed_backends: set[str] = set()

    def _resolve_endpoint(self, name: str):
        """Resolve an endpoint by name, falling back to the highest-priority configured endpoint."""
        from orchestrator.endpoint_registry import all as _all_eps
        from orchestrator.endpoint_registry import get as _get_ep
        from orchestrator.endpoint_registry import load as _load_eps
        ep = _get_ep(name)
        if ep:
            return ep

        # Registry may not be loaded yet — force load and retry
        with contextlib.suppress(Exception):
            _load_eps()
        ep = _get_ep(name)
        if ep:
            return ep

        # No matching endpoint — auto-pick the highest-priority one
        all_eps = _all_eps()
        if all_eps:
            picked = all_eps[0]
            logger.warning(
                "No endpoint named '%s' in settings.toml; auto-selected '%s' (priority %d). "
                "Set [[endpoints]] name='%s' or change LLM_BACKEND in settings.toml.",
                name, picked.name, picked.priority, name,
            )
            return picked

        raise ValueError(
            f"No endpoint found for '{name}' and no endpoints configured in settings.toml. "
            "Add [[endpoints]] entries to ~/.raphael/settings.toml."
        )

    def _build_state(self, model: str | None, fallback_model: str | None):
        """Set up all state from the resolved endpoint."""
        self.backend = self._ep.name
        self._original_backend = self.backend
        self.fallback_backends = self._build_fallback_list()
        self.client = OpenAI(
            base_url=self._ep.base_url,
            api_key=self._ep.api_key or "dummy-key",
            http_client=self._build_http_client(),
        )
        self.model = model or self._ep.text_model
        self.vision_model = self._ep.vision_model or self.model

        self._fallback_models = []
        if self._ep.fallback_models:
            self._fallback_models = list(self._ep.fallback_models)
        elif self._ep.fallback_model:
            self._fallback_models = [self._ep.fallback_model]
        if fallback_model:
            self._fallback_models = [fallback_model]
        self._fallback_model = self._fallback_models[0] if self._fallback_models else None

    def _build_http_client(self) -> httpx.Client:
        """Shared persistent HTTP client with HTTP/2 multiplexing & connection pooling."""
        if not hasattr(self, "_shared_http_client") or getattr(self._shared_http_client, "is_closed", True):  # type: ignore[has-type]
            self._shared_http_client = httpx.Client(  # type: ignore[has-type]
                http2=True,
                timeout=httpx.Timeout(
                    connect=config.LLM_CONNECT_TIMEOUT,
                    read=config.LLM_READ_TIMEOUT,
                    write=10.0,
                    pool=5.0,
                ),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            )
        return self._shared_http_client

    def _build_client_from_ep(self) -> OpenAI:
        """Build client from the endpoint registry entry."""
        return OpenAI(
            base_url=self._ep.base_url,
            api_key=self._ep.api_key or "dummy-key",
            http_client=self._build_http_client(),
        )

    def _build_fallback_list(self) -> list[str]:
        """Build fallback list from endpoint registry using text_priority order."""
        from orchestrator.endpoint_registry import all as _all_eps
        from orchestrator.endpoint_registry import get_text_priority
        text_priority = get_text_priority()
        all_names = {ep.name for ep in _all_eps()}
        if text_priority:
            return [n for n in text_priority if n in all_names and n != self.backend]
        # Fallback: all endpoints in registry order
        return [ep.name for ep in _all_eps() if ep.name != self.backend]


    def _switch_backend(self, backend: str) -> bool:
        """Switch to a different LLM backend. Returns True on success."""
        if backend == self.backend:
            return True
        old_backend = self.backend
        self.backend = backend
        try:
            from orchestrator.endpoint_registry import get as _get_ep
            ep = _get_ep(backend)
            if not ep:
                logger.error("No endpoint registry entry for '%s'", backend)
                self.backend = old_backend
                return False
            self._ep = ep
            self.client = self._build_client_from_ep()
            self.model = ep.text_model
            self.vision_model = ep.vision_model or ep.text_model
            self._fallback_model = ep.fallback_model or self._fallback_model
            logger.info("Switched LLM backend: %s → %s (model: %s)", old_backend, backend, self.model)
            return True
        except Exception as e:
            logger.error("Failed to switch to backend '%s': %s", backend, e)
            self.backend = old_backend
            return False

    def warmup_kv_cache(self, system_prompt: str = ""):
        """Warm up the KV cache for local LLMs to reduce first-token latency.

        For Ollama/vLLM backends, sends a minimal request with keep_alive=-1
        so the engine pre-evaluates the system prompt. First-token latency
        drops from ~10-20s to <1s on subsequent real requests.

        Runs in a background thread and fails silently — never blocks.
        """
        warmup_backends = {"ollama-local", "ollama-cloud", "vllm"}
        if self.backend not in warmup_backends:
            return

        def _warmup():
            try:
                warmup_messages = [{"role": "user", "content": "warmup"}]
                if system_prompt:
                    warmup_messages.insert(0, {"role": "system", "content": system_prompt})

                kwargs = {
                    "model": self.model,
                    "messages": warmup_messages,
                    "max_tokens": 1,
                    "temperature": 0.0,
                }
                # Ollama-specific: keep model loaded in memory
                if self.backend in {"ollama-local", "ollama-cloud"}:
                    kwargs["extra_body"] = {"keep_alive": -1}
                # vLLM: warmup via a short generation
                if self.backend == "vllm":
                    kwargs["max_tokens"] = 5

                self.client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
                logger.info("KV cache warmed for %s/%s", self.backend, self.model)
            except Exception as e:
                logger.debug("KV cache warmup skipped (%s/%s): %s", self.backend, self.model, e)

        threading.Thread(target=_warmup, daemon=True).start()

    def chat(self, messages: list[dict], tools: list[dict] | None = None, use_vision_model: bool = False, reason: str = "unknown") -> Any:
        """Send a chat completion request with retry and fallback across backends.

        Args:
            messages: The conversation messages.
            tools: Optional tool schemas to include.
            use_vision_model: Use the vision-capable model.
            reason: A label explaining why this LLM call is being made
                    (e.g. "user_request", "tool_result", "memory_librarian").
        """
        # Inject today's date & time context if not already present
        has_system = messages and messages[0].get("role") == "system"
        if not has_system:
            import datetime
            now = datetime.datetime.now()
            date_str = now.strftime("%A, %B %d, %Y")
            time_str = now.strftime("%I:%M %p")
            date_msg = {"role": "system", "content": f"Today's date is {date_str}. The current time is {time_str}."}
            messages = [date_msg, *list(messages)]
        else:
            sys_msg = messages[0].get("content") or ""
            if isinstance(sys_msg, str) and "Today's date is" not in sys_msg:
                import datetime
                now = datetime.datetime.now()
                date_str = now.strftime("%A, %B %d, %Y")
                time_str = now.strftime("%I:%M %p")
                date_prefix = f"Today's date is {date_str}. The current time is {time_str}.\n\n"
                messages = [{"role": "system", "content": date_prefix + sys_msg}, *messages[1:]]

        try:
            from orchestrator.background import get_runner
            runner = get_runner()
            task_id = runner.get_thread_task_id(threading.get_ident())
            if task_id and runner.is_cancelled(task_id):
                raise RuntimeError("Task cancelled by user")
        except Exception as e:
            if "Task cancelled" in str(e):
                raise e

        # Also check main task cancellation (per-task AbortController)
        from orchestrator.task_manager import TaskManager
        main_id = TaskManager.get_main_task_id()
        if main_id and TaskManager.is_cancelled(main_id):
            raise RuntimeError("Task cancelled by user")

        kwargs = {
            "model": self.vision_model if use_vision_model else self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        backend_label = f"{self.backend}/{kwargs['model']}"
        log_event("LLM Call", f"reason={reason} {backend_label}")

        last_error = ""
        # Try primary backend with retries
        for attempt in range(3):
            try:
                if config.DEBUG:
                    logger.debug("Calling %s (reason=%s, attempt %d)...", backend_label, reason, attempt + 1)
                response = self.client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
                msg = response.choices[0].message
                # Handle reasoning models that return empty content
                if not msg.content and hasattr(msg, "reasoning_content") and msg.reasoning_content and (not hasattr(msg, "tool_calls") or not msg.tool_calls):
                    msg.content = msg.reasoning_content
                # If still empty, provide a fallback
                if not msg.content and (not hasattr(msg, "tool_calls") or not msg.tool_calls):
                    msg.content = "I understand. Let me process that."
                return msg  # type: ignore[return-value]
            except Exception as e:
                last_error = str(e)
                error_str = last_error.lower()
                is_auth_error = "401" in error_str or "unauthorized" in error_str
                if is_auth_error:
                    self._auth_failed_backends.add(self.backend)
                is_retryable = any(
                    phrase in error_str
                    for phrase in ["timeout", "timed out", "503", "502", "504",
                                   "service unavailable", "bad gateway",
                                   "connection error", "connection reset",
                                   "rate limit", "429", "too many requests",
                                   "401", "unauthorized"]
                )
                if not is_retryable or attempt >= 2:
                    break
                sleep_time = config.LLM_RETRY_BACKOFF ** (attempt + 1)  # ~1.5s, ~2.25s by default
                logger.warning("LLM call failed (reason=%s, attempt %d/3): %s. Retrying in %ds...",
                               reason, attempt + 1, last_error, sleep_time)
                time.sleep(sleep_time)

        # Primary exhausted — try fallback models on same backend in order
        if last_error and self._fallback_models and self.backend not in self._auth_failed_backends:
            kwargs["model"]
            for fallback_m in self._fallback_models:
                if not fallback_m:
                    continue
                kwargs["model"] = fallback_m
                logger.warning("%s unavailable — falling back to model %s/%s (reason=%s)",
                               self.backend, self.backend, fallback_m, reason)
                for attempt in range(2):
                    try:
                        response = self.client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
                        msg = response.choices[0].message
                        if not msg.content and hasattr(msg, "reasoning_content") and msg.reasoning_content and (not hasattr(msg, "tool_calls") or not msg.tool_calls):
                            msg.content = msg.reasoning_content
                        if not msg.content and (not hasattr(msg, "tool_calls") or not msg.tool_calls):
                            msg.content = "I understand. Let me process that."
                        logger.info("Fallback model '%s' succeeded (reason=%s)", fallback_m, reason)
                        return msg  # type: ignore[return-value]
                    except Exception as e:
                        last_error = str(e)
                        if "401" in last_error or "unauthorized" in last_error.lower():
                            self._auth_failed_backends.add(self.backend)
                            break
                        if attempt >= 1:
                            break
                        time.sleep(2)

        # Primary + fallback model exhausted — try fallback backends
        if last_error and self.fallback_backends:
            priority_list = config.VISION_PRIORITY if use_vision_model else config.TEXT_PRIORITY
            if priority_list:
                def sort_key(name):
                    try:
                        return priority_list.index(name)
                    except ValueError:
                        return len(priority_list)
                sorted_fallbacks = sorted(self.fallback_backends, key=sort_key)
            else:
                sorted_fallbacks = self.fallback_backends

            available = [fb for fb in sorted_fallbacks if fb not in self._auth_failed_backends]
            if not available:
                available = sorted_fallbacks  # fall through to get a proper error message
            for fb in available:
                if not self._switch_backend(fb):
                    continue
                # Update kwargs model for new backend
                kwargs["model"] = self.vision_model if use_vision_model else self.model
                logger.warning("%s unavailable → falling back to %s/%s (reason=%s)",
                               self.backend, self.backend, kwargs["model"], reason)
                for attempt in range(2):
                    try:
                        response = self.client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
                        msg = response.choices[0].message
                        if not msg.content and hasattr(msg, "reasoning_content") and msg.reasoning_content and (not hasattr(msg, "tool_calls") or not msg.tool_calls):
                            msg.content = msg.reasoning_content
                        if not msg.content and (not hasattr(msg, "tool_calls") or not msg.tool_calls):
                            msg.content = "I understand. Let me process that."
                        logger.info("Fallback backend '%s' succeeded after primary failure (reason=%s)", fb, reason)
                        return msg  # type: ignore[return-value]
                    except Exception as e:
                        last_error = str(e)
                        if "401" in last_error or "unauthorized" in last_error.lower():
                            self._auth_failed_backends.add(fb)
                            break
                        if attempt >= 1:
                            break
                        time.sleep(2)
            # Restore original backend for next request
            self._switch_backend(self._original_backend)

        error_msg = f"[Error calling LLM ({backend_label}): {last_error}]"
        if config.DEBUG:
            logger.debug(error_msg)
        return _LLMResponse(content=error_msg)  # type: ignore[return-value]

    def _accumulate_streaming_tool_calls(self, acc: dict, delta_tool_calls) -> dict:
        """Accumulate streaming tool call deltas into a complete tool_calls dict.

        Returns dict keyed by index: {0: {"id": "call_...", "function": {"name": "...", "arguments": "..."}}}
        """
        for tc in delta_tool_calls:
            idx = tc.index
            if idx not in acc:
                acc[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
            if tc.id:
                acc[idx]["id"] = tc.id
            if tc.function:
                if tc.function.name:
                    acc[idx]["function"]["name"] += tc.function.name
                if tc.function.arguments:
                    acc[idx]["function"]["arguments"] += tc.function.arguments
        return acc

    def chat_stream(
        self,
        messages: list[dict],
        on_token: Callable[[str], None],
        tools: list[dict] | None = None,
        use_vision_model: bool = False,
        reason: str = "unknown",
    ) -> Any:
        """Stream a chat completion, calling on_token(text) for each token.

        Returns the same structure as chat() — a dict-like object with .content and .tool_calls.
        Tool calls are accumulated from stream deltas.
        """
        kwargs = {
            "model": self.vision_model if use_vision_model else self.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": False},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        last_error = ""
        for attempt in range(3):
            try:
                if config.DEBUG:
                    logger.debug("Streaming %s/%s (attempt %d)...", self.backend, self.model, attempt + 1)

                response = self.client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
                full_content = ""
                tool_calls_acc: dict[int, dict] = {}

                for chunk in response:
                    if len(chunk.choices) == 0:  # type: ignore[attr-defined]
                        continue
                    delta = chunk.choices[0].delta  # type: ignore[attr-defined]
                    if delta and delta.content:
                        full_content += delta.content
                        if on_token is not None:
                            on_token(delta.content)  # type: ignore[misc]
                    if delta and delta.tool_calls:
                        self._accumulate_streaming_tool_calls(tool_calls_acc, delta.tool_calls)

                # Reconstruct response object from accumulated data
                msg = _LLMResponse(content=full_content)

                # Convert accumulated tool calls to OpenAI-like objects
                if tool_calls_acc:
                    class _StreamToolCall:
                        def __init__(self, _idx, data):
                            self.id = data["id"]
                            self.type = "function"
                            self.function = type("_Func", (), {
                                "name": data["function"]["name"],
                                "arguments": data["function"]["arguments"],
                            })()
                    msg.tool_calls = [  # type: ignore[assignment]
                        _StreamToolCall(idx, data)
                        for idx, data in sorted(tool_calls_acc.items())
                        if data["id"] and data["function"]["name"]
                    ]

                return msg  # type: ignore[return-value]

            except Exception as e:
                last_error = str(e)
                error_str = last_error.lower()
                if "401" in error_str or "unauthorized" in error_str:
                    self._auth_failed_backends.add(self.backend)
                is_retryable = any(
                    phrase in error_str
                    for phrase in ["timeout", "timed out", "503", "502", "504",
                                   "service unavailable", "bad gateway",
                                   "connection error", "connection reset",
                                   "rate limit", "429", "too many requests",
                                   "401", "unauthorized"]
                )
                if not is_retryable or attempt >= 2:
                    break
                sleep_time = config.LLM_RETRY_BACKOFF ** (attempt + 1)
                logger.warning("LLM stream failed (attempt %d/3): %s. Retrying in %ds...",
                               attempt + 1, last_error, sleep_time)
                time.sleep(sleep_time)

        # Fallback to non-streaming chat
        logger.warning("Stream failed after 3 attempts, falling back to non-streaming (reason=%s): %s", reason, last_error)
        return self.chat(messages, tools, use_vision_model, reason=reason)

    def chat_tool_loop(self, messages: list[dict], schemas: list[dict],
                       executor: ToolExecutor, max_rounds: int = 8,
                       reason: str = "tool_loop") -> str:
        """Run a multi-turn tool-calling loop. Returns final text response."""
        msgs = list(messages)
        for _ in range(max_rounds):
            response = self.chat(msgs, schemas, reason=reason)
            if not response or not hasattr(response, "content"):
                return "I encountered an issue processing your request."
            if response.content and response.content.startswith("[Error calling LLM"):
                return response.content  # type: ignore[no-any-return]

            if hasattr(response, "tool_calls") and response.tool_calls:
                assistant_msg = {"role": "assistant", "content": response.content or None}
                tool_calls_data = []
                for tc in response.tool_calls:
                    tool_calls_data.append({
                        "id": tc.id, "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    })
                if tool_calls_data:
                    assistant_msg["tool_calls"] = tool_calls_data
                msgs.append(assistant_msg)

                import concurrent.futures as _cf

                from orchestrator.tools import PARALLEL_SAFE_TOOLS
                _tool_results: dict[str, str] = {}

                # Run parallel-safe tools concurrently
                _safe_calls = [tc for tc in response.tool_calls if tc.function.name in PARALLEL_SAFE_TOOLS]
                if _safe_calls:
                    with _cf.ThreadPoolExecutor(max_workers=min(len(_safe_calls), 5)) as _pool:
                        _future_map = {
                            _pool.submit(executor.execute, tc.function.name,
                                        json.loads(tc.function.arguments)
                                        if tc.function.arguments else {}): tc
                            for tc in _safe_calls
                        }
                        for _future in _cf.as_completed(_future_map):
                            _tc = _future_map[_future]
                            try:
                                _tool_results[_tc.id] = _future.result()
                            except Exception as e:
                                _tool_results[_tc.id] = f"Error executing {_tc.function.name}: {e}"

                # Run non-safe tools sequentially
                for tool_call in response.tool_calls:
                    if tool_call.id in _tool_results:
                        continue  # already ran via parallel pool
                    func_name = tool_call.function.name
                    try:
                        func_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        func_args = {}
                    _tool_results[tool_call.id] = executor.execute(func_name, func_args)

                # Append in original order
                for tool_call in response.tool_calls:
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": _tool_results.get(tool_call.id, "Error: tool result missing"),
                    })
            else:
                return response.content or ""
        return "(reached max rounds without final response)"

    def chat_with_vision(
        self, messages: list[dict], image_path: str, tools: list[dict] | None = None, reason: str = "vision"
    ) -> Any:
        """Send a chat with an image attachment (vision)."""
        import base64
        from pathlib import Path

        image_path = Path(image_path)  # type: ignore[assignment]
        suffix = image_path.suffix.lower()  # type: ignore[attr-defined]

        if suffix in (".png",):
            media_type = "image/png"
        elif suffix in (".jpg", ".jpeg"):
            media_type = "image/jpeg"
        else:
            media_type = "image/png"

        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        # Add image as a user message
        image_message = {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{b64}",
                        "detail": "high",
                    },
                },
                {"type": "text", "text": "Describe what you see on this screen."},
            ],
        }

        vision_messages = [*messages[:-1], image_message, messages[-1]]
        return self.chat(vision_messages, tools, use_vision_model=True, reason=reason)


class ToolExecutor:
    """Executes tool calls returned by the LLM.

    Tracks execution stats for generated tools to enable OBSERVE→OPTIMIZE.
    Provides optional result caching for idempotent read-only tools.
    """

    # ── Execution tracking (for OBSERVE→OPTIMIZE) ──
    _exec_counts: ClassVar[dict[str, int]] = defaultdict(int)
    _exec_times: ClassVar[dict[str, list[float]]] = defaultdict(list)
    _lock = threading.Lock()

    # ── Result cache (for idempotent read-only tools) ──
    _result_cache: ClassVar[dict[tuple[str, frozenset], tuple[str, float]]] = {}
    _cache_lock = threading.Lock()

    # Tools whose results are safe to cache (read-only, idempotent)
    # Maps tool_name -> TTL in seconds
    CACHEABLE_TOOLS: ClassVar[dict[str, int]] = {
        "get_weather": 600,           # 10 min
        "desktop_processes": 30,      # 30 sec
        "desktop_environment": 120,   # 2 min
        "desktop_system_info": 300,   # 5 min
        "desktop_network": 60,        # 1 min
        "desktop_tray": 60,           # 1 min
        "desktop_taskbar": 60,        # 1 min
        "desktop_snapshot_v2": 30,    # 30 sec
        "get_market_quote": 120,      # 2 min
        "get_portfolio_summary": 120, # 2 min
        "read_clipboard": 5,          # 5 sec (just debounce)
        "get_music_volume": 10,       # 10 sec
        "get_playback_status": 10,    # 10 sec
        "get_current_song": 10,       # 10 sec
        "get_mouse_position": 2,      # 2 sec (stale position is useless)
        "get_screen_size": 3600,      # 1 hr
        "get_agent_performance": 120, # 2 min
        "get_playback_progress": 10,  # 10 sec
        "ui_get_monitors": 3600,      # 1 hr
        "ui_get_screen_size": 3600,   # 1 hr
        "list_goals": 30,             # 30 sec
        "list_workflows": 300,        # 5 min
        "list_playlists": 60,         # 1 min
        "get_portfolio_holdings": 120,# 2 min
        "get_positions": 120,         # 2 min
    }

    def __init__(self):
        self.tool_map = get_tool_map()

    @classmethod
    def observe_tool(cls, name: str, elapsed_ms: float) -> None:
        """Record a tool execution observation."""
        from orchestrator.tools import is_generated_tool
        if not is_generated_tool(name):
            return
        with cls._lock:
            cls._exec_counts[name] += 1
            cls._exec_times[name].append(elapsed_ms)
            # Keep only last 100 samples
            if len(cls._exec_times[name]) > 100:
                cls._exec_times[name] = cls._exec_times[name][-100:]

    @classmethod
    def tool_stats(cls, name: str) -> dict | None:
        """Return execution stats for a generated tool."""
        with cls._lock:
            times = cls._exec_times.get(name, [])
            if not times:
                return None
            avg_ms = sum(times) / len(times)
            return {
                "name": name,
                "calls": cls._exec_counts.get(name, 0),
                "avg_ms": round(avg_ms, 2),
                "min_ms": round(min(times), 2),
                "max_ms": round(max(times), 2),
                "samples": len(times),
            }

    @classmethod
    def needs_optimization(cls, name: str, threshold_ms: float = 300) -> bool:
        """Check if a generated tool is slow and should be optimized."""
        stats = cls.tool_stats(name)
        if not stats:
            return False
        return stats["avg_ms"] > threshold_ms and stats["calls"] >= 5  # type: ignore[no-any-return]

    @classmethod
    def needs_optimization_report(cls) -> list[dict]:
        """Return list of generated tools that need optimization."""
        with cls._lock:
            candidates = []
            for name in list(cls._exec_counts.keys()):
                stats = cls.tool_stats(name)
                if stats and stats["avg_ms"] > 300 and stats["calls"] >= 5:
                    candidates.append(stats)
            return sorted(candidates, key=lambda s: s["avg_ms"], reverse=True)

    @classmethod
    def invalidate_cache(cls, tool_name: str | None = None) -> int:
        """Invalidate cached results.

        Args:
            tool_name: If provided, only invalidate entries for this tool.
                       If None, invalidate the entire cache.

        Returns:
            Number of cache entries invalidated.
        """
        with cls._cache_lock:
            if tool_name is None:
                count = len(cls._result_cache)
                cls._result_cache.clear()
                return count
            keys = [k for k in cls._result_cache if k[0] == tool_name]
            for k in keys:
                del cls._result_cache[k]
            return len(keys)

    def execute(self, tool_name: str, args: dict) -> str:
        """Execute a tool and return its result as a string.

        For cacheable read-only tools, returns the cached result if still
        within TTL, avoiding redundant re-execution.
        """
        if args is None:  # type: ignore[unreachable]
            args = {}  # type: ignore[unreachable]
        try:
            from orchestrator.background import get_runner
            runner = get_runner()
            task_id = runner.get_thread_task_id(threading.get_ident())
            if task_id and runner.is_cancelled(task_id):
                raise RuntimeError("Task cancelled by user")
        except Exception as e:
            if "Task cancelled" in str(e):
                raise e

        # Also check main task cancellation (per-task AbortController)
        from orchestrator.task_manager import TaskManager
        main_id = TaskManager.get_main_task_id()
        if main_id and TaskManager.is_cancelled(main_id):
            raise RuntimeError("Task cancelled by user")

        # ── Cache check ──
        ttl = self.CACHEABLE_TOOLS.get(tool_name)
        if ttl is not None:
            cache_key = (tool_name, frozenset(args.items()))
            with self._cache_lock:
                cached = self._result_cache.get(cache_key)
                if cached is not None:
                    result, expiry = cached
                    if time.monotonic() < expiry:
                        logger.debug("tool=%s cache HIT", tool_name)
                        return result

        func = self.tool_map.get(tool_name)
        if not func:
            return f"Error: Unknown tool '{tool_name}'"

        decision = evaluate_tool_call(tool_name, args)
        if not decision.allowed:
            return permission_message(tool_name, decision)

        start = time.perf_counter()
        try:
            result = func(**args)
            elapsed = (time.perf_counter() - start) * 1000
            self.observe_tool(tool_name, elapsed)

            logger.info("tool=%s duration=%.2fs", tool_name, elapsed / 1000.0)

            # ── Cache store ──
            if ttl is not None:
                cache_key = (tool_name, frozenset(args.items()))
                with self._cache_lock:
                    self._result_cache[cache_key] = (str(result), time.monotonic() + ttl)

            # Plugin hook: on_tool_execute
            for hook in get_hooks("on_tool_execute"):
                modified = hook(tool_name, args, str(result))
                if modified is not None:
                    result = modified
            return str(result)
        except Exception as e:
            return f"Error executing {tool_name}: {e}"


class RaphaelOrchestrator:
    """Main orchestrator — the core conversation loop."""

    _last_memory_update: float

    def __init__(self):
        # Load dynamic endpoint registry (seeds defaults on first run)
        try:
            from orchestrator.endpoint_registry import load as _load_eps
            _load_eps()
        except Exception:
            pass

        self.llm = LLMClient()
        self.executor = ToolExecutor()
        self.tool_schemas = get_tool_schemas()
        self._extra_tool_schemas: list[dict] = []  # injected at runtime
        from orchestrator.tool_orchestrator import ToolOrchestrator
        self.tool_orchestrator = ToolOrchestrator()
        # Boot-time integrity check: verifies every prompt/map-referenced tool
        # is registered and flags weak descriptions. Logs warnings only.
        from orchestrator.tool_audit import run_boot_audit
        run_boot_audit()
        self.history: list[dict] = []
        # UI callback — set by RaphaelController after construction
        self._ui_log: Callable | None = None
        self._activity_callback: Callable | None = None

        # Background task runner — thread pool for long-running tools
        self.bg_runner = init_runner(
            on_done=self._on_background_done,
            max_workers=getattr(config, "BACKGROUND_MAX_WORKERS", 4),
        )
        self.bg_runner.set_executor(self.executor)

        # Start metrics collector (subscribes to event bus — singleton, safe to call once)
        from orchestrator.agent_metrics import MetricsCollector
        MetricsCollector().subscribe()

    def _on_background_done(self, task: BackgroundTask) -> None:
        """Called from a background thread when a task finishes. Notifies via event bus."""
        label = task.label or task.tool_name

        if task.status.value == "done":
            self._synthesize_and_present_result(task)
            return
        elif task.status.value == "failed":
            error_msg = task.error or "Unknown error"
            logger.info("Background task %s failed: %s", task.task_id, error_msg)
            EventBus().publish_typed(
                TASK_FINISHED,
                TaskFinishedPayload(
                    task_id=task.task_id,
                    label=label,
                    status="failed",
                    summary="",
                    error=error_msg,
                ),
            )

    def _synthesize_and_present_result(self, task: BackgroundTask) -> None:
        """Trigger an LLM pass to summarize the background task result conversationally."""
        label = task.label or task.tool_name
        logger.info("Synthesizing background task %s result...", task.task_id)

        try:
            system_prompt = (
                "You are Raphael, an advanced AI personal assistant on Windows.\n"
                "A background task that the user initiated has just finished execution.\n"
                "Your job is to review the completed task details and raw result, "
                "then present a friendly, concise, and conversational summary to the user.\n\n"
                f"Task Name: {label}\n"
                f"Raw Result:\n{task.result}\n\n"
                "Instructions:\n"
                "- Speak directly to the user.\n"
                "- State clearly that the background task is complete.\n"
                "- Keep the response concise and focused on the key takeaways.\n"
                "- Avoid sounding robotic. Be conversational."
            )
            messages = [{"role": "system", "content": system_prompt}]
            response = self.llm.chat(messages, None, reason="synthesize_background")
            if response and hasattr(response, "content") and response.content:
                summary = response.content.strip()
            else:
                summary = f"Background task '{label}' completed, but I was unable to summarize the results."
        except Exception as e:
            logger.error("Failed to run synthesis LLM call: %s", e)
            summary = f"Background task '{label}' completed: {(task.result or '')[:300]}"

        logger.info("Background task %s completed successfully", task.task_id)
        EventBus().publish_typed(
            TASK_FINISHED,
            TaskFinishedPayload(
                task_id=task.task_id,
                label=label,
                status="done",
                summary=summary,
                error="",
            ),
        )

    def set_ui_log(self, fn: Callable) -> None:
        """Attach the HUD log callback so background notifications appear in the UI."""
        self._ui_log = fn

    def set_activity_callback(self, fn: Callable) -> None:
        """Attach activity callback to notify controller that progress is being made."""
        self._activity_callback = fn

    def _get_system_prompt(self, user_query: str = "", task_context: str = "") -> dict:
        """Dynamically generate the system prompt using SystemPromptBuilder."""
        memory_context = ""
        try:
            from orchestrator.memory_agent import get_relevant_context
            memory_context = get_relevant_context(user_query)
        except Exception as e:
            logger.error("Failed to load memory context: %s", e)

        # Load Raphael's own evolution memory (learned rules from corrections)
        raphael_context = ""
        try:
            from memory.agent_memory import get_context
            raphael_context = get_context("raphael", user_query)
        except Exception as e:
            logger.debug("Failed to load Raphael evolution context: %s", e)

        import datetime
        now = datetime.datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M %p")

        # Hardware & Audio State
        spk_ok = state.audio_output_available
        tts_ok = state.tts_enabled
        mic_ok = state.audio_input_available

        from orchestrator.prompt_builder import SystemPromptBuilder
        content = SystemPromptBuilder.build(
            date_str=date_str,
            time_str=time_str,
            spk_ok=spk_ok,
            tts_ok=tts_ok,
            mic_ok=mic_ok,
            memory_context=memory_context,
            raphael_context=raphael_context,
            screenshot_dir=getattr(config, 'SCREENSHOT_DIR', 'outputs'),
            task_context=task_context,
        )

        return {"role": "system", "content": content}

    @property
    def _all_tool_schemas(self) -> list[dict]:
        """Merged tool schemas: native + MCP + dynamically injected.

        ``update_tools()`` appends to ``_extra_tool_schemas``, which is
        then included in every LLM tool-use request.
        """
        base = list(self.tool_schemas)
        base.extend(self._extra_tool_schemas)
        return base

    def _get_domain_schemas(self, user_input: str) -> list[dict]:
        """Return tool schemas dynamically filtered by ToolOrchestrator."""
        return self.tool_orchestrator.get_filtered_schemas(
            user_input, extra_schemas=self._extra_tool_schemas
        )

    def update_tools(self, new_schemas: list[dict], validate: bool = True) -> list[str]:
        """Inject or replace tool schemas at runtime.

        Two-phase transactional validation:
          1. Validate ALL new schemas have the required structure.
          2. If ALL valid, commit them to ``_extra_tool_schemas``.

        Args:
            new_schemas: List of OpenAI/Anthropic-style tool definition dicts.
            validate: When True (default), validates every schema before committing.

        Returns:
            List of error messages (empty = all passed).

        Raises:
            ValueError: If validation fails and at least one schema is malformed.
        """
        if validate:
            errors: list[str] = []
            for i, schema in enumerate(new_schemas):
                func = schema.get("function", {}) if "function" in schema else schema
                if "name" not in func:
                    errors.append(f"Schema #{i} is missing 'function.name'")
                if "parameters" not in func:
                    errors.append(f"Schema #{i} is missing 'function.parameters'")
            if errors:
                raise ValueError(
                    f"Tool schema validation failed ({len(errors)} errors):\n"
                    + "\n".join(errors[:10])
                )

        # Phase 2: commit
        self._extra_tool_schemas.extend(new_schemas)
        return []

    def inject_agents(self, agent_map: dict[str, Callable]) -> None:
        """Register new agent callable types at runtime.

        Args:
            agent_map: Mapping of agent type name → callable(goal, context) -> str.
        """
        from orchestrator.tools.native.agent import (
            register_agent_type,  # type: ignore[attr-defined]
        )
        for name, handler in agent_map.items():
            register_agent_type(name, handler)

    def request_interrupt(self):
        """Signal the orchestrator to stop processing at the next opportunity.

        Cancels the current main task (and all its sub-tasks) via
        per-task abort signal. Each cancellation is independent —
        sub-agents spawned by this task will also be cancelled.
        """
        from orchestrator.task_manager import TaskManager
        TaskManager.cancel_task(TaskManager.get_main_task_id())  # type: ignore[arg-type]

    def clear_interrupt(self):
        """Reset interrupt state for a new request.

        No-op with per-task cancellation — each new request creates
        a fresh task with a clean abort signal.
        """
        pass

    def _run_proactive_check(self, instruction: str) -> str:
        """
        Run a read-only proactive check: no tools, no agent routing.

        Appends the [PROACTIVE_CHECK] instruction to the system prompt and
        makes a single LLM call. The LLM should respond with 1-2 sentences
        or ``__noop__`` to stay silent.
        """
        try:
            # Build system prompt with the proactive instruction appended
            base_system = self._get_system_prompt("")
            proactive_content = base_system["content"] + instruction

            messages = [
                {"role": "system", "content": proactive_content},
            ]

            # Include recent conversation so the check knows what was just
            # discussed and doesn't repeat it.
            recent_context: list[dict[str, str]] = []
            budget = 1500
            for m in self.history[-6:]:
                content = m.get("content")
                if not isinstance(content, str) or m["role"] not in ("user", "assistant"):
                    continue
                if len(content) > 300:
                    content = content[:300] + "..."
                remaining = budget - sum(len(x["content"]) for x in recent_context)
                if remaining <= 0:
                    break
                recent_context.append({"role": m["role"], "content": content})
            if recent_context:
                messages.extend(recent_context)

            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The user has been idle. Based on the recent conversation above, "
                        "only speak up if you have something genuinely new, useful, and "
                        "not already said or offered. Do NOT repeat offers or information "
                        "the assistant already provided. Otherwise respond with exactly "
                        "'__noop__' to stay silent."
                    ),
                },
            )

            # Single LLM call with NO tools
            response = self.llm.chat(messages, [], reason="proactive_check")
            if response and hasattr(response, "content") and response.content:
                result = response.content.strip()
                if result.lower() == "__noop__":
                    return "__noop__"
                return result  # type: ignore[no-any-return]
            return "__noop__"
        except Exception as e:
            logger.debug("Proactive check LLM call failed: %s", e)
            return "__noop__"

    @staticmethod
    def _build_task_context(goal: str, completed_steps: list[str]) -> str:
        """Build a TASK PROGRESS section for the system prompt.

        Delegates to TaskManager.build_progress_prompt when a task_id is available.
        This stub is kept for backward compatibility during migration.
        """
        if not completed_steps:
            return ""
        steps_text = "\n".join(f"  \u2713 {s}" for s in completed_steps[-10:])
        return (
            "=== TASK PROGRESS ===\n"
            f"Goal: {goal[:150]}\n"
            "Completed steps:\n"
            f"{steps_text}\n\n"
            "IMPORTANT RULES:\n"
            "\u2022 Do NOT repeat any completed step \u2014 they are already done.\n"
            "\u2022 If all planned steps are done, respond with your final answer text "
            "\u2014 do NOT call more tools.\n"
            "\u2022 Only call a tool if you need to do something new that is NOT already completed."
        )

    def _init_task(self, user_input: str) -> str:
        """Create a new task via TaskManager. Returns the task ID."""
        from orchestrator.task_manager import TaskManager
        task_id = TaskManager.create_task(user_input, "main")
        TaskManager.start_task(task_id)
        return task_id

    def _record_tool_step(self, task_id: str, tool_name: str, arguments: dict) -> None:
        """Record a tool call step via TaskManager."""
        from orchestrator.task_manager import TaskManager
        TaskManager.add_step_from_tool_call(task_id, tool_name, arguments)

    def _finalize_task(self, task_id: str, result: str = "", error: str = "") -> None:
        """Mark the task as completed or failed and write persistent output."""
        from orchestrator.task_manager import TaskManager
        if error:
            TaskManager.fail_task(task_id, error)
            TaskManager.write_output(task_id, (
                f"=== TASK {task_id} ===\n"
                f"Status: FAILED\n"
                f"Error: {error}\n"
                f"Completed: {time.strftime('%H:%M:%S')}\n"
                "==================\n"
            ))
        else:
            TaskManager.complete_task(task_id, result)
            TaskManager.write_output(task_id, (
                f"=== TASK {task_id} ===\n"
                f"Status: COMPLETED\n"
                f"Result: {result[:500]}\n"
                f"Completed: {time.strftime('%H:%M:%S')}\n"
                "==================\n"
            ))

    def _get_task_progress(self, task_id: str) -> str:
        """Get the current task progress prompt for system prompt injection."""
        from orchestrator.task_manager import TaskManager
        return TaskManager.build_progress_prompt(task_id)

    def _check_sub_agent_results(self, messages: list, task_id: str) -> None:
        """Check for completed sub-agents and inject their results as user messages.

        Called each tool round so the LLM sees sub-agent results naturally
        in the conversation flow.
        """
        from orchestrator.task_manager import TaskManager, TaskState
        task = TaskManager.get_task(task_id)
        if not task:
            return

        notified: set[str] = getattr(self, "_notified_sub_tasks", set())
        for sub_id in list(task.sub_task_ids):
            sub = TaskManager.get_task(sub_id)
            if not sub or sub.status not in (TaskState.COMPLETED, TaskState.FAILED):
                continue
            if sub_id in notified:
                continue

            notified.add(sub_id)
            if sub.status == TaskState.COMPLETED:
                preview = (sub.result or "")[:500]
                msg = (
                    f"**\u2139 Sub-agent [{sub.id}] completed**\n"
                    f"Goal: {sub.goal[:150]}\n"
                    f"Steps: {len(sub.steps)}\n\n"
                    f"Result:\n{preview}"
                )
            else:
                msg = (
                    f"**\u26a0 Sub-agent [{sub.id}] failed**\n"
                    f"Goal: {sub.goal[:150]}\n"
                    f"Error: {sub.error}"
                )
            messages.append({"role": "user", "content": msg})
            logger.info("Injected sub-agent result: %s", sub_id)

        self._notified_sub_tasks = notified

    def _check_tool_loop(
        self, tool_name: str, tool_args: dict, result: str,
    ) -> str | None:
        """Tool Failure Loop Guard — detect and break repetitive tool call loops.

        OpenClaude pattern (toolFailureLoopGuard.ts): if the LLM calls the same
        tool with the same type of arguments and fails repeatedly, inject a
        warning message suggesting a different approach.

        Returns a warning message to inject, or None if no loop detected.
        """
        cache = getattr(self, "_tool_loop_cache", None)
        if cache is None:
            self._tool_loop_cache = {
                "last_name": "",
                "sig": "",
                "fail_count": 0,
            }
            cache = self._tool_loop_cache

        if tool_args is None:  # type: ignore[unreachable]
            tool_args = {}  # type: ignore[unreachable]

        # Build a signature from key args only (ignore file content / command length)
        sig_parts = []
        for key in ("file_path", "url", "app_name"):
            if key in tool_args:
                val = str(tool_args[key])
                sig_parts.append(f"{key}={val.split('/')[-1].split('\\')[-1][:30]}")
        if not sig_parts:
            sig_parts.append(tool_name)
        sig = "; ".join(sig_parts)

        is_failure = result.startswith("Error:")

        if tool_name == cache["last_name"] and sig == cache["sig"] and is_failure:
            cache["fail_count"] += 1  # type: ignore[operator]
            if cache["fail_count"] >= 3:  # type: ignore[operator]
                count = cache["fail_count"]
                cache["fail_count"] = 0  # reset to avoid repeated warnings
                return (
                    f"\u26a0 You've tried `{tool_name}` {count} times "
                    f"consecutively and it keeps failing. Try a completely different "
                    f"approach instead of repeating the same tool with similar arguments."
                )
        else:
            # Reset — different tool/args or success
            cache["last_name"] = tool_name
            cache["sig"] = sig
            cache["fail_count"] = 1 if is_failure else 0

        return None

    def process_message(self, user_input: str, file_path: str | None = None) -> str:
        """
        Process a user message through the LLM loop.
        Returns the assistant's text response.
        """
        # ── Request tracking ───────────────────────────────────────
        set_request_id()
        start_timeline()

        # Reset read-before-edit registry for this request
        from orchestrator.tools.native.files import clear_read_file_registry
        clear_read_file_registry()

        # ── Proactive check mode ──────────────────────────────────────────────
        # When [PROACTIVE_CHECK] is in the input, run a read-only, no-tools
        # LLM call for idle check-ins. Response is 1-2 sentences or "__noop__".
        is_proactive = "[PROACTIVE_CHECK]" in user_input

        if is_proactive:
            # Skip file handling, agent routing — just append to system prompt
            log_event("Proactive Check")
            result = self._run_proactive_check(user_input)
            clear_request_id()
            return result

        # Handle file drops
        image_path = None
        if file_path:
            from pathlib import Path
            path = Path(file_path)
            if path.is_file():
                ext = path.suffix.lower().lstrip(".")
                image_exts = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "svg", "ico"}
                text_exts = {"py", "js", "ts", "jsx", "tsx", "html", "css", "java", "c", "cpp",
                             "cs", "go", "rs", "rb", "php", "swift", "kt", "sh", "sql", "lua",
                             "txt", "md", "rst", "log", "json", "csv", "tsv", "xml"}

                if ext in image_exts:
                    image_path = str(path)
                    log_event("File Drop", f"image={path.name}")
                elif ext in text_exts:
                    try:
                        with open(path, encoding="utf-8", errors="ignore") as f:
                            file_content = f.read()
                        user_input += f"\n\n[Attached File: {path.name}]\n```\n{file_content}\n```"
                        log_event("File Drop", f"text={path.name} ({len(file_content)} chars)")
                    except Exception as e:
                        user_input += f"\n\n[Error reading attached file {path.name}: {e}]"
                else:
                    user_input += f"\n\n[Attached File Path: {path.resolve()}]\nNote: This is a binary/non-text file. Use process_file or other system tools to read/analyze it if necessary."
                    log_event("File Drop", f"binary={path.name}")

        self.history.append({"role": "user", "content": user_input})

        # Compact history (intelligent summarization instead of truncation)
        self._compact_history()

        log_event("System Prompt Build")
        messages = [self._get_system_prompt(user_input), *self.history]

        # Reset interrupt flag for this new request
        self.clear_interrupt()

        # Main loop — handle multiple tool calls
        max_tool_rounds = 25
        completed_rounds = 0
        _task_id = self._init_task(user_input)
        for round_idx in range(max_tool_rounds):
            completed_rounds += 1
            if self._activity_callback:
                with contextlib.suppress(Exception):
                    self._activity_callback()  # type: ignore[misc]

            # Check for interrupt between rounds
            from orchestrator.task_manager import TaskManager
            if TaskManager.is_cancelled(_task_id):
                self.history.append({
                    "role": "assistant",
                    "content": "(interrupted)"
                })
                TaskManager.fail_task(_task_id, "interrupted")
                TaskManager.write_output(_task_id, f"=== TASK {_task_id} ===\nStatus: INTERRUPTED\n==================\n")
                log_event("Interrupted")
                clear_request_id()
                return "(interrupted)"

            if image_path and round_idx == 0:
                log_event("Vision Call")
                # Don't pass tools on vision round — many vision models don't support function calling
                response = self.llm.chat_with_vision(messages, image_path, reason="vision")
            else:
                reason = "user_request" if round_idx == 0 else "tool_result"
                response = self.llm.chat(messages, self._get_domain_schemas(user_input), reason=reason)
            if not response or not hasattr(response, "content"):
                error_msg = "I encountered an issue processing your request."
                self.history.append({
                    "role": "assistant",
                    "content": error_msg
                })
                finalize_timeline()
                clear_request_id()
                return error_msg

            # Check if LLM returned an error
            if response.content and response.content.startswith("[Error calling LLM"):
                self.history.append({
                    "role": "assistant",
                    "content": response.content,
                })
                log_event("LLM Error", response.content[:80])
                finalize_timeline()
                clear_request_id()
                return response.content  # type: ignore[no-any-return]

            # Check for tool calls
            if hasattr(response, "tool_calls") and response.tool_calls:
                # Convert OpenAI Message object to plain dict for compatibility
                assistant_msg = {
                    "role": "assistant",
                    "content": response.content or None
                }
                if hasattr(response, "reasoning_content") and response.reasoning_content:
                    assistant_msg["reasoning_content"] = response.reasoning_content
                # Include tool_calls if present
                tool_calls_data = []
                for tc in response.tool_calls:
                    tool_calls_data.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })
                if tool_calls_data:
                    assistant_msg["tool_calls"] = tool_calls_data
                messages.append(assistant_msg)

                log_event("Tool Round", f"{len(response.tool_calls)} tool(s)")
                results: dict[str, str] = {}
                import concurrent.futures as _cf

                from orchestrator.tools import PARALLEL_SAFE_TOOLS

                # Run parallel-safe tools concurrently
                safe_calls = [
                    tc for tc in response.tool_calls
                    if tc.function.name in PARALLEL_SAFE_TOOLS
                ]
                if safe_calls:
                    with _cf.ThreadPoolExecutor(max_workers=min(len(safe_calls), 5)) as pool:
                        _future_map = {
                            pool.submit(self.executor.execute, tc.function.name,
                                        json.loads(tc.function.arguments)
                                        if tc.function.arguments else {}): tc
                            for tc in safe_calls
                        }
                        for future in _cf.as_completed(_future_map):
                            tc = _future_map[future]
                            try:
                                result = future.result()
                            except Exception as e:
                                result = f"Error executing {tc.function.name}: {e}"
                            results[tc.id] = result

                # Run non-safe tools sequentially
                unsafe_calls = [
                    tc for tc in response.tool_calls
                    if tc.function.name not in PARALLEL_SAFE_TOOLS
                ]
                for tool_call in unsafe_calls:
                    func_name = tool_call.function.name
                    try:
                        func_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        func_args = {}

                    logger.info("%s(%s)", func_name, func_args)
                    result = self.executor.execute(func_name, func_args)
                    results[tool_call.id] = result

                    # Check for interrupt between sequential tools
                    from orchestrator.task_manager import TaskManager
                    if TaskManager.is_cancelled(_task_id):
                        self.history.append({
                            "role": "assistant",
                            "content": "(interrupted)"
                        })
                        TaskManager.fail_task(_task_id, "interrupted")
                        TaskManager.write_output(_task_id, f"=== TASK {_task_id} ===\nStatus: INTERRUPTED\n==================\n")
                        log_event("Interrupted")
                        clear_request_id()
                        return "(interrupted)"

                # Append results in original order (preserving LLM's intent)
                for tool_call in response.tool_calls:
                    result = results.get(tool_call.id, "Error: tool result missing")
                    # Truncate oversized results
                    if len(result) > config.MAX_TOOL_RESULT_CHARS:
                        result = result[:config.MAX_TOOL_RESULT_CHARS] + "\n...(truncated)"
                    if self._activity_callback:
                        with contextlib.suppress(Exception):
                            self._activity_callback()  # type: ignore[misc]

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })

                    # Publish tool execution event
                    EventBus().publish(
                        TOOL_FAILED if result.startswith("Error:")
                            else TOOL_EXECUTED,
                        agent="raphael",
                        tool=tool_call.function.name,
                        args=json.loads(tool_call.function.arguments)
                            if tool_call.function.arguments else {},
                        result=result[:200],
                        round=round_idx,
                    )

                    # ── Tool Failure Loop Guard ──
                    _loop_warning = self._check_tool_loop(
                        tool_call.function.name,
                        json.loads(tool_call.function.arguments)
                            if tool_call.function.arguments else {},
                        result,
                    )
                    if _loop_warning:
                        messages.append({"role": "user", "content": _loop_warning})

                # ── Update task progress for next LLM round ──
                for tc in response.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except json.JSONDecodeError:
                        args = {}
                    self._record_tool_step(_task_id, tc.function.name, args)
                task_context_str = self._get_task_progress(_task_id)
                if task_context_str:
                    messages[0] = self._get_system_prompt(user_input, task_context_str)

                # ── Check for completed sub-agents ──
                self._check_sub_agent_results(messages, _task_id)

                continue  # Let LLM respond to tool results

            # Text response — final answer
            if response.content:
                assistant_msg = {
                    "role": "assistant",
                    "content": response.content,
                }
                if hasattr(response, "reasoning_content") and response.reasoning_content:
                    assistant_msg["reasoning_content"] = response.reasoning_content
                EventBus().publish(TASK_COMPLETED, user_input=user_input, response=response.content[:200])
                self.history.append(assistant_msg)
                log_event("Text Response", f"{len(response.content)} chars")
                self._finalize_task(_task_id, result=response.content)
                self._trigger_background_memory_update(user_input, response.content)
                finalize_timeline()
                clear_request_id()
                return response.content  # type: ignore[no-any-return]

            break

        if completed_rounds >= max_tool_rounds:
            error_msg = "I have reached the limit of tool executions (25 rounds) for this request. Please let me know what you want to focus on next."
        else:
            error_msg = "I encountered an issue processing your request."
        self._finalize_task(_task_id, error=error_msg)

        EventBus().publish(TASK_COMPLETED, user_input=user_input, response=error_msg[:200])
        self.history.append({
            "role": "assistant",
            "content": error_msg
        })
        finalize_timeline()
        clear_request_id()
        return error_msg

    def process_message_stream(
        self,
        user_input: str,
        on_token: Callable[[str], None] | None = None,
        file_path: str | None = None,
    ) -> str:
        """
        Process a user message through the LLM loop with token streaming.

        Legacy blocking wrapper around the event-based generator.
        Calls ``on_token`` for each token event and returns the final text.
        New code should prefer ``process_message_events()``.

        Returns the final assistant response as a string (same as process_message).
        """
        final_result: str = ""
        for event in self.process_message_events(user_input, file_path=file_path):
            if isinstance(event, TokenEvent) and on_token:
                on_token(event.token)  # type: ignore[misc]
            elif isinstance(event, TaskCompleteEvent):
                final_result = event.result
            elif isinstance(event, TaskErrorEvent):
                final_result = event.error
            elif isinstance(event, InterruptedEvent):
                final_result = "(interrupted)"
        return final_result

    def process_message_events(
        self,
        user_input: str,
        file_path: str | None = None,
    ) -> Generator[StreamEvent]:
        """
        Process a user message through the LLM loop, yielding typed events.

        Wraps :meth:`_process_message_events_raw` so the stream is the single
        emitter: each yielded event is also published as a typed ``EventBus``
        payload by :func:`orchestrator.event_adapter.stream_with_events`.

        Yields StreamEvent sub-types so that callers (UI, controller, API)
        can stream every stage of processing in real time:
        token chunks, tool starts/results, progress updates, and the final outcome.

        Yields:
            StreamEvent — sub-types include TokenEvent, ThinkingEvent,
            ToolStartEvent, ToolResultEvent, ToolErrorEvent, ProgressEvent,
            TaskCompleteEvent, TaskErrorEvent, InterruptedEvent.
        """
        return stream_with_events(self._process_message_events_raw(user_input, file_path=file_path))

    def _process_message_events_raw(
        self,
        user_input: str,
        file_path: str | None = None,
    ) -> Generator[StreamEvent]:
        """
        Process a user message through the LLM loop, yielding typed events.

        Raw event generator. Public callers should use
        :meth:`process_message_events`, which wraps this stream with the
        single-emitter adapter.
        """
        # ── Request tracking ───────────────────────────────────────
        set_request_id()
        start_timeline()

        # ── Proactive check mode ──
        is_proactive = "[PROACTIVE_CHECK]" in user_input
        if is_proactive:
            log_event("Proactive Check")
            result = self._run_proactive_check(user_input)
            clear_request_id()
            yield TaskCompleteEvent(result=result, proactive=True)
            return

        # Handle file drops
        image_path = None
        if file_path:
            from pathlib import Path
            path = Path(file_path)
            if path.is_file():
                ext = path.suffix.lower().lstrip(".")
                image_exts = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "svg", "ico"}
                text_exts = {"py", "js", "ts", "jsx", "tsx", "html", "css", "java", "c", "cpp",
                             "cs", "go", "rs", "rb", "php", "swift", "kt", "sh", "sql", "lua",
                             "txt", "md", "rst", "log", "json", "csv", "tsv", "xml"}

                if ext in image_exts:
                    image_path = str(path)
                    log_event("File Drop", f"image={path.name}")
                elif ext in text_exts:
                    try:
                        with open(path, encoding="utf-8", errors="ignore") as f:
                            file_content = f.read()
                        user_input += f"\n\n[Attached File: {path.name}]\n```\n{file_content}\n```"
                        log_event("File Drop", f"text={path.name} ({len(file_content)} chars)")
                    except Exception as e:
                        user_input += f"\n\n[Error reading attached file {path.name}: {e}]"
                else:
                    user_input += f"\n\n[Attached File Path: {path.resolve()}]\nNote: This is a binary/non-text file. Use process_file or other system tools to read/analyze it if necessary."
                    log_event("File Drop", f"binary={path.name}")

        self.history.append({"role": "user", "content": user_input})

        # Limit history
        if len(self.history) > config.MAX_HISTORY * 2:
            self.history = self.history[-config.MAX_HISTORY * 2:]

        log_event("System Prompt Build")
        messages = [self._get_system_prompt(user_input), *self.history]

        max_tool_rounds = 25
        completed_rounds = 0
        _task_id = self._init_task(user_input)
        for round_idx in range(max_tool_rounds):
            completed_rounds += 1
            if self._activity_callback:
                with contextlib.suppress(Exception):
                    self._activity_callback()  # type: ignore[misc]

            yield ProgressEvent(round=round_idx, total_rounds=max_tool_rounds)

            from orchestrator.task_manager import TaskManager
            if TaskManager.is_cancelled(_task_id):
                self.history.append({"role": "assistant", "content": "(interrupted)"})
                TaskManager.fail_task(_task_id, "interrupted")
                TaskManager.write_output(_task_id, f"=== TASK {_task_id} ===\nStatus: INTERRUPTED\n==================\n")
                log_event("Interrupted")
                clear_request_id()
                yield InterruptedEvent(task_id=_task_id)
                return

            if image_path and round_idx == 0:
                log_event("Vision Call")
                response = self.llm.chat_with_vision(messages, image_path, reason="vision")
            else:
                yield ThinkingEvent(round=round_idx)
                reason = "user_request" if round_idx == 0 else "tool_result"
                if round_idx == 0:
                    # Collect streaming tokens and yield them as TokenEvents
                    _event_tokens: list[str] = []
                    def _on_token(t: str, _event_tokens=_event_tokens) -> None:
                        _event_tokens.append(t)
                    response = self.llm.chat_stream(messages, _on_token, self._get_domain_schemas(user_input), reason=reason)
                    # Yield collected tokens
                    for t in _event_tokens:
                        yield TokenEvent(token=t)
                else:
                    response = self.llm.chat(messages, self._get_domain_schemas(user_input), reason=reason)
            if not response or not hasattr(response, "content"):
                error_msg = "I encountered an issue processing your request."
                self.history.append({"role": "assistant", "content": error_msg})
                finalize_timeline()
                clear_request_id()
                yield TaskErrorEvent(task_id=_task_id, error=error_msg)
                return

            if response.content and response.content.startswith("[Error calling LLM"):
                self.history.append({"role": "assistant", "content": response.content})
                log_event("LLM Error", response.content[:80])
                finalize_timeline()
                clear_request_id()
                yield TaskErrorEvent(task_id=_task_id, error=response.content)
                return

            # ── Budget tracking ───────────────────────────────────
            _est_tokens = len(str(response.content or "") + str(
                getattr(response, "reasoning_content", "") or ""
            )) // 4  # rough estimate: ~4 chars per token
            TaskManager.record_usage(_task_id, tokens=_est_tokens)
            budget_msg = TaskManager.budget_exceeded(_task_id)
            if budget_msg:
                logger.warning("Budget exceeded for task %s: %s", _task_id, budget_msg)
                self.history.append({"role": "assistant", "content": budget_msg})
                TaskManager.fail_task(_task_id, budget_msg)
                TaskManager.write_output(_task_id, f"=== TASK {_task_id} ===\nStatus: BUDGET_EXCEEDED\n{budget_msg}\n==================\n")
                finalize_timeline()
                clear_request_id()
                yield TaskErrorEvent(task_id=_task_id, error=budget_msg)
                return

            if hasattr(response, "tool_calls") and response.tool_calls:
                assistant_msg = {
                    "role": "assistant",
                    "content": response.content or None,
                }
                if hasattr(response, "reasoning_content") and response.reasoning_content:
                    assistant_msg["reasoning_content"] = response.reasoning_content
                tool_calls_data = []
                for tc in response.tool_calls:
                    tool_calls_data.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })
                if tool_calls_data:
                    assistant_msg["tool_calls"] = tool_calls_data
                messages.append(assistant_msg)

                log_event("Tool Round", f"{len(response.tool_calls)} tool(s)")
                import concurrent.futures as _cf

                from orchestrator.tools import PARALLEL_SAFE_TOOLS

                _tool_results: dict[str, str] = {}

                # Emit tool start events
                for tc in response.tool_calls:
                    try:
                        func_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except json.JSONDecodeError:
                        func_args = {}
                    yield ToolStartEvent(tool=tc.function.name, args=func_args, round=round_idx)

                # Run parallel-safe tools concurrently
                _safe_calls = [
                    tc for tc in response.tool_calls
                    if tc.function.name in PARALLEL_SAFE_TOOLS
                ]
                if _safe_calls:
                    with _cf.ThreadPoolExecutor(max_workers=min(len(_safe_calls), 5)) as _pool:
                        _future_map = {
                            _pool.submit(self.executor.execute, tc.function.name,
                                        json.loads(tc.function.arguments)
                                        if tc.function.arguments else {}): tc
                            for tc in _safe_calls
                        }
                        for _future in _cf.as_completed(_future_map):
                            _tc = _future_map[_future]
                            try:
                                _result = _future.result()
                            except Exception as e:
                                _result = f"Error executing {_tc.function.name}: {e}"
                            _tool_results[_tc.id] = _result

                # Run non-safe tools sequentially (state-changing ops)
                _unsafe_calls = [
                    tc for tc in response.tool_calls
                    if tc.function.name not in PARALLEL_SAFE_TOOLS
                ]
                for tool_call in _unsafe_calls:
                    func_name = tool_call.function.name
                    try:
                        func_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        func_args = {}
                    logger.info("%s(%s)", func_name, func_args)
                    _tool_results[tool_call.id] = self.executor.execute(func_name, func_args)

                    from orchestrator.task_manager import TaskManager
                    if TaskManager.is_cancelled(_task_id):
                        self.history.append({"role": "assistant", "content": "(interrupted)"})
                        TaskManager.fail_task(_task_id, "interrupted")
                        TaskManager.write_output(_task_id, f"=== TASK {_task_id} ===\nStatus: INTERRUPTED\n==================\n")
                        log_event("Interrupted")
                        clear_request_id()
                        yield InterruptedEvent(task_id=_task_id)
                        return

                # Append results in original order and emit result events
                for tool_call in response.tool_calls:
                    result = _tool_results.get(tool_call.id, "Error: tool result missing")
                    truncated = False
                    if len(result) > config.MAX_TOOL_RESULT_CHARS:
                        result = result[:config.MAX_TOOL_RESULT_CHARS] + "\n...(truncated)"
                        truncated = True

                    if self._activity_callback:
                        with contextlib.suppress(Exception):
                            self._activity_callback()  # type: ignore[misc]

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })

                    if result.startswith("Error:"):
                        yield ToolErrorEvent(
                            tool=tool_call.function.name, error=result, round=round_idx,
                            agent="raphael",
                            args=json.loads(tool_call.function.arguments)
                                if tool_call.function.arguments else {},
                        )
                    else:
                        yield ToolResultEvent(
                            tool=tool_call.function.name, result=result[:500], round=round_idx,
                            truncated=truncated, agent="raphael",
                            args=json.loads(tool_call.function.arguments)
                                if tool_call.function.arguments else {},
                        )

                # ── Update task progress for next LLM round ──
                for tc in response.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except json.JSONDecodeError:
                        args = {}
                    self._record_tool_step(_task_id, tc.function.name, args)
                task_context_str = self._get_task_progress(_task_id)
                if task_context_str:
                    messages[0] = self._get_system_prompt(user_input, task_context_str)

                continue

            # Text response — final answer
            if response.content:
                assistant_msg = {
                    "role": "assistant",
                    "content": response.content,
                }
                if hasattr(response, "reasoning_content") and response.reasoning_content:
                    assistant_msg["reasoning_content"] = response.reasoning_content
                self.history.append(assistant_msg)
                log_event("Text Response", f"{len(response.content)} chars")
                self._finalize_task(_task_id, result=response.content)
                self._trigger_background_memory_update(user_input, response.content)
                finalize_timeline()
                clear_request_id()
                yield TaskCompleteEvent(task_id=_task_id, result=response.content)
                return

            break

        if completed_rounds >= max_tool_rounds:
            error_msg = "I have reached the limit of tool executions (25 rounds) for this request. Please let me know what you want to focus on next."
        else:
            error_msg = "I encountered an issue processing your request."
        self._finalize_task(_task_id, error=error_msg)

        self.history.append({"role": "assistant", "content": error_msg})
        finalize_timeline()
        clear_request_id()
        yield TaskErrorEvent(task_id=_task_id, error=error_msg)

    def _compact_history(self) -> None:
        """Compress old history turns rather than blindly truncating.

        When the conversation history exceeds ``MAX_HISTORY``, the oldest
        turns are summarized into a compact ``[Compressed history]`` message.
        This preserves high-level context (goals, decisions, files changed)
        while drastically reducing token count — analogous to OpenClaude's
        snip-boundary compaction.
        """
        if len(self.history) <= config.MAX_HISTORY:
            return

        # Compact the oldest half of the overage
        target = config.MAX_HISTORY // 2
        to_compact = self.history[:target]
        rest = self.history[target:]

        # Build a compact summary prompt from the oldest turns
        compact_text = ""
        for msg in to_compact:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            tc = msg.get("tool_calls", [])
            line = f"[{role}] {content[:300]}"
            compact_text += line + "\n"
            if tc:
                for t in tc:
                    fn = t.get("function", {}).get("name", "?")
                    compact_text += f"  -> tool_call: {fn}\n"
            compact_text += "\n"

        try:
            summary = self.llm.chat([
                {"role": "system", "content": (
                    "You are a conversation summarizer. Summarize the following "
                    "conversation history concisely. Focus on: user goals, decisions "
                    "made, files modified, tools used, key facts established. "
                    "Keep the summary under 200 words."
                )},
                {"role": "user", "content": f"Summarize this conversation:\n\n{compact_text}"},
            ], tools=None, reason="history_compaction")
            summary_text = summary.content if summary else ""
            if not summary_text:
                raise ValueError("empty summary")
        except Exception:
            # Fallback: just truncate as before
            self.history = rest  # type: ignore[attr-defined]
            return

        # Replace compacted turns with a single compressed message
        compressed = {
            "role": "system",
            "content": f"[Compressed history]: {summary_text[:500]}",
        }
        self.history = [compressed, *rest]

    def _trigger_background_memory_update(self, user_text: str, assistant_text: str):
        """Spawns a background thread to organize and persist memory updates."""

        # ── Smarter skip: tool commands and non-conversational requests ──
        _skip_memory = {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay",
                         "done", "yes", "no", "sure", "bye", "goodbye", "stop",
                         "cancel", "never mind", "abort"}
        text_lower = user_text.lower().strip()
        if not user_text or not assistant_text or len(user_text) < 10 or \
           text_lower in _skip_memory or text_lower.rstrip(".!?").strip() in _skip_memory:
            return

        # ── Debounce: skip if a memory update ran in the last 30s ──
        now = time.monotonic()
        if hasattr(self, "_last_memory_update") and self._last_memory_update and (now - self._last_memory_update) < 30.0:
            logger.debug("Skipping memory organizer — debounced (last run %.1fs ago)", now - self._last_memory_update)
            return
        if not hasattr(self, "_last_memory_update"):
            self._last_memory_update = 0.0

        # ── Check for user corrections to automatically learn behavioral rules ──
        if len(self.history) >= 3 and self.history[-3]["role"] == "assistant":
            prev_assistant_text = self.history[-3]["content"]

            # Heuristics: user criticizes/asks why or the assistant apologizes/corrects
            user_lower = user_text.lower()
            assistant_lower = assistant_text.lower()

            apology_keywords = ["apologize", "apologies", "sorry", "my mistake", "my bad", "slip on my part", "you're absolutely right"]
            user_keywords = ["wrong", "incorrect", "error", "mistake", "why did you", "why you said", "not ", "don't", "should be", "actually", "why did", "why you"]

            has_apology = any(kw in assistant_lower for kw in apology_keywords)
            has_user_correction = any(kw in user_lower for kw in user_keywords) or (user_lower.endswith("?") and any(kw in user_lower for kw in ["morning", "afternoon", "evening", "said", "did"]))

            if has_apology or has_user_correction:
                def _run_correction():
                    try:
                        from memory.agent_memory import process_correction
                        logger.info("Automatic correction detected. Processing evolution rules for 'raphael'...")
                        process_correction("raphael", prev_assistant_text, user_text)
                    except Exception as e:
                        logger.debug("Automatic correction extraction failed: %s", e)
                import threading
                threading.Thread(target=_run_correction, daemon=True, name="auto_correction").start()

        try:
            import threading

            from orchestrator.memory_agent import run_memory_agent
            self._memory_thread = threading.Thread(
                target=run_memory_agent,
                args=(user_text, assistant_text),
                daemon=True
            )
            self._memory_thread.start()
            self._last_memory_update = now

            # Record Raphael's interaction for evolution memory
            threading.Thread(
                target=self._record_raphael_interaction,
                args=(user_text,),
                daemon=True,
            ).start()

            # Also trigger agent memory consolidation — moved from "every response"
            # to a lazy check inside the spawned thread to avoid spawning extra threads
            threading.Thread(
                target=self._trigger_agent_consolidation,
                daemon=True,
            ).start()
        except Exception as e:
            logger.error("Failed to spawn background memory thread: %s", e)

    def _record_raphael_interaction(self, user_text: str):
        """Record Raphael's interaction in evolution memory for learning patterns."""
        try:
            from memory.agent_memory import record_interaction
            record_interaction("raphael", user_text, [], "completed")
        except Exception:
            pass

    def _trigger_agent_consolidation(self):
        """Periodic agent memory consolidation — runs in background thread."""
        try:
            from memory.agent_memory import _load, consolidate
            memory = _load()
            if not memory:
                return
            total_interactions = sum(
                len(a.get("interactions", []))
                for a in memory.values()
            )
            # Consolidate every 50 total interactions across all agents
            if total_interactions > 0 and total_interactions % 50 == 0:
                logger.info("Triggering agent memory consolidation (%d interactions)", total_interactions)
                consolidate()
        except Exception as e:
            logger.debug("Agent consolidation skipped: %s", e)

    def wait_for_memory(self):
        """Wait for the active background memory thread to complete."""
        thread = getattr(self, "_memory_thread", None)
        if thread and thread.is_alive():
            logger.info("Waiting for background memory organizer thread to complete...")
            thread.join()

    def reset_conversation(self):
        """Clear conversation history."""
        self.history = []
        logger.info("Conversation reset.")



