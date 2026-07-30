"""
Process-Isolated STT Runner — runs speech recognition in a subprocess.

The STT process communicates transcribed speech back via a multiprocessing
Queue. If the subprocess crashes (e.g. SpeechRuntime.exe segfault), it is
automatically restarted without affecting the main application.

Architecture inspired by Zero's dictation server pattern:
  - Health pings detect dead subprocesses within ~2s
  - Graceful degradation: primary → fallback backends
  - Typed error results instead of raw exceptions
"""

import logging
import multiprocessing
import queue
import threading
import time
from dataclasses import dataclass
from collections.abc import Callable

from .registry import STTRegistry
import contextlib

logger = logging.getLogger(__name__)

# ── Max crashes before giving up ─────────────────────────────────────────
_MAX_RESTART_ATTEMPTS = 5
_HEALTH_PING_INTERVAL = 1.0  # seconds
_HEALTH_PING_TIMEOUT = 3.0   # seconds without ping → assumed dead


@dataclass
class IsolatedSTTConfig:
    """Configuration for the isolated STT runner."""
    preferred_backends: tuple[str, ...] = ("winrt", "groq")
    restart_attempts: int = _MAX_RESTART_ATTEMPTS
    health_interval: float = _HEALTH_PING_INTERVAL


# ── Subprocess Entry Point ──────────────────────────────────────────────

def _stt_process_main(
    result_queue: multiprocessing.Queue,
    ping_queue: multiprocessing.Queue,
    preferred_backends: tuple[str, ...],
):
    """
    Runs in a child process. On crash, the process exits and the parent auto-restarts.
    """
    # Import inside the subprocess to avoid inheriting parent's COM state
    import sys
    from pathlib import Path

    # Ensure project root is on sys.path
    root = Path(__file__).resolve().parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    logging.basicConfig(
        level=logging.INFO,
        format="[stt-process] %(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )

    logger = logging.getLogger("stt-process")

    # ── Check mic availability in subprocess ──
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        has_input = any(
            d.get("max_input_channels", 0) > 0 for d in devices if isinstance(d, dict)
        )
        if not has_input:
            logger.warning("No microphone input devices found — STT process exiting")
            with contextlib.suppress(Exception):
                result_queue.put_nowait(("error", "No microphone input devices found", True, time.time()))
            while True:
                time.sleep(1)
    except Exception as e:
        logger.debug("Subprocess mic check failed (%s) — proceeding anyway", e)

    # ── Callback: push results to parent ──
    def on_result(text: str, is_final: bool):
        try:
            result_queue.put_nowait(("transcript", text, is_final, time.time()))
        except Exception:
            pass  # Queue full → drop

    # ── Get backends in order ──
    backends = []
    for name in preferred_backends:
        instance = STTRegistry.get(name)
        if instance is not None:
            try:
                if instance.health():
                    backends.append(instance)
                    logger.info("Backend '%s' available", name)
                else:
                    logger.warning("Backend '%s' unhealthy on startup", name)
            except Exception as e:
                logger.warning("Backend '%s' health check failed: %s", name, e)
        else:
            logger.warning("Backend '%s' not registered", name)

    if not backends:
        logger.error("No STT backends available — subprocess will idle")
        with contextlib.suppress(Exception):
            result_queue.put_nowait(("error", "No STT backends available", True, time.time()))
        # Keep process alive for parent to manage shutdown
        while True:
            time.sleep(1)

    # ── Try each backend in order ──
    for backend in backends:
        logger.info("Starting STT backend: %s", backend.name)
        try:
            if backend.supports_streaming:
                backend.start_streaming(on_result)
            else:
                # Batch-mode backends not suitable for always-listening
                logger.warning("Backend '%s' does not support streaming, skipping", backend.name)
                continue
        except Exception as e:
            logger.error("Backend '%s' failed to start: %s", backend.name, e)
            with contextlib.suppress(Exception):
                result_queue.put_nowait(("error", f"Backend '{backend.name}' failed: {e}", True, time.time()))
            continue

        # Backend started — signal parent
        with contextlib.suppress(Exception):
            result_queue.put_nowait(("backend_active", backend.name, True, time.time()))
        break
    else:
        logger.error("All backends failed to start — subprocess idle")
        with contextlib.suppress(Exception):
            result_queue.put_nowait(("error", "All STT backends failed", True, time.time()))

    # ── Health ping loop ──
    # Reply to pings from parent to prove we're alive
    while True:
        try:
            # Blocking wait for ping with timeout so we stay responsive
            _ = ping_queue.get(timeout=1.0)
            # Echo back the ping timestamp — parent knows we're alive
            ping_queue.put(time.time())
        except queue.Empty:
            continue
        except (EOFError, OSError, BrokenPipeError):
            # Parent process died — exit cleanly
            break
        except KeyboardInterrupt:
            # Graceful shutdown requested — exit without traceback
            break
        except Exception:
            continue


# ── Parent-side Manager ─────────────────────────────────────────────────

class IsolatedSTTRunner:
    """
    Manages the STT subprocess with crash detection and auto-restart.

    Usage:
        runner = IsolatedSTTRunner()
        runner.start(on_transcript=lambda text, is_final: ...)
        ...
        runner.stop()
    """

    def __init__(self, config: IsolatedSTTConfig | None = None):
        self.config = config or IsolatedSTTConfig()
        self._process: multiprocessing.Process | None = None
        self._result_queue: multiprocessing.Queue | None = None
        self._ping_queue: multiprocessing.Queue | None = None
        self._restart_count = 0
        self._running = False
        self._health_thread: threading.Thread | None = None
        self._callback: Callable[[str, bool], None] | None = None

    # ── Public API ─────────────────────────────────────────────────────

    @property
    def is_alive(self) -> bool:
        """Check if the subprocess is running."""
        return self._process is not None and self._process.is_alive()

    def start(self, on_transcript: Callable[[str, bool], None]):
        """Start the isolated STT subprocess with a transcript callback."""
        self._callback = on_transcript
        self._running = True
        self._restart_count = 0
        self._start_process()

    def stop(self):
        """Stop the subprocess and health monitor."""
        self._running = False
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=3.0)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=2.0)
        self._process = None

    def pause(self):
        """Pause processing (subprocess stays alive)."""
        # Implementation detail: we don't pause the subprocess,
        # but the parent can stop draining the queue
        pass

    # ── Internal ───────────────────────────────────────────────────────

    def _start_process(self):
        """Create and start a new STT subprocess."""
        if not self._running:
            return

        # Close old queues if any
        self._close_queues()

        self._result_queue = multiprocessing.Queue(maxsize=64)
        self._ping_queue = multiprocessing.Queue(maxsize=8)

        self._process = multiprocessing.Process(
            target=_stt_process_main,
            args=(
                self._result_queue,
                self._ping_queue,
                self.config.preferred_backends,
            ),
            daemon=True,
            name="stt-isolated",
        )
        self._process.start()
        logger.info("STT subprocess started (PID: %s)", self._process.pid)

        # Start health + result drain threads
        self._health_thread = threading.Thread(
            target=self._health_monitor, daemon=True, name="stt-health",
        )
        self._health_thread.start()

        # Start result drain thread
        drain_thread = threading.Thread(
            target=self._drain_results, daemon=True, name="stt-drain",
        )
        drain_thread.start()

    def _close_queues(self):
        """Safely close and release old queues."""
        for q in [self._result_queue, self._ping_queue]:
            if q is not None:
                with contextlib.suppress(Exception):
                    q.close()

    def _drain_results(self):
        """Drain transcription results from the subprocess queue."""
        while self._running:
            try:
                if self._result_queue is None:
                    time.sleep(0.1)
                    continue
                msg = self._result_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            except (EOFError, OSError, ValueError):
                # Queue closed or process died
                break
            except Exception:
                continue

            if not self._running:
                break  # type: ignore[unreachable]

            try:
                msg_type = msg[0]
                if msg_type == "transcript":
                    _, text, is_final, _ts = msg
                    if self._callback:  # type: ignore[unreachable]
                        self._callback(text, is_final)
                elif msg_type == "error":
                    _, error_text, _is_final, _ts = msg
                    logger.error("STT subprocess error: %s", error_text)
                elif msg_type == "backend_active":
                    _, backend_name, _is_final, _ts = msg
                    logger.info("STT subprocess: backend '%s' active", backend_name)
            except Exception as e:
                logger.debug("STT drain error: %s", e)

    def _health_monitor(self):
        """Monitor subprocess health with ping/pong."""
        missed_pings = 0
        max_missed = int(_HEALTH_PING_TIMEOUT / _HEALTH_PING_INTERVAL) + 1

        while self._running and self.is_alive:
            time.sleep(_HEALTH_PING_INTERVAL)

            if not self._running or not self.is_alive:
                break  # type: ignore[unreachable]

            # Send ping
            try:
                if self._ping_queue is None:
                    missed_pings += 1
                    continue
                self._ping_queue.put(time.time(), timeout=0.5)
                # Wait for pong
                try:
                    _ = self._ping_queue.get(timeout=1.0)
                    missed_pings = 0  # Healthy
                except queue.Empty:
                    missed_pings += 1
                    logger.debug("STT health ping timeout (%d/%d)",
                                 missed_pings, max_missed)
            except (EOFError, OSError, BrokenPipeError):
                # Process died
                missed_pings = max_missed
            except Exception:
                missed_pings += 1

            # Check if process is dead
            if not self.is_alive:  # type: ignore[unreachable]
                missed_pings = max_missed  # type: ignore[unreachable]

            # Auto-restart if unhealthy
            if missed_pings >= max_missed:
                logger.warning("STT subprocess unhealthy — restarting")
                self._restart_count += 1
                if self._restart_count > self.config.restart_attempts:
                    logger.error("STT subprocess exceeded max restart attempts (%d) — giving up",
                                 self.config.restart_attempts)
                    self._running = False
                    break
                # Kill old process
                if self._process and self._process.is_alive():
                    self._process.terminate()
                    self._process.join(timeout=2.0)
                self._process = None
                self._close_queues()
                # Start new process
                self._start_process()
                missed_pings = 0


