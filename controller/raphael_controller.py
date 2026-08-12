"""
RaphaelController — bridges VAD voice thread, LLM orchestrator, and PyQt6 HUD.

Extracted from main.py for testability and clean separation of concerns.
"""

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPoint, QTimer, QObject, pyqtSignal

import config
from controller.processing_lanes import ProcessingLanes
from controller.state import state
from orchestrator.proactive_engine import ProactiveEngine
from orchestrator.startup import StartupManager
import contextlib

logger = logging.getLogger(__name__)

_controller_instance: RaphaelController | None = None


def get_controller_instance() -> RaphaelController | None:
    """Return the active RaphaelController singleton instance."""
    return _controller_instance

# ── Physical speaker detection ──────────────────────────────────

def detect_physical_speaker() -> bool:
    """Check if any physical speaker/headphone is actually connected.

    Returns True if a physical audio output device appears connected,
    False if all physical jacks are unplugged.

    Uses pycaw (Windows Core Audio) to check device states.
    Manual override via config HAS_SPEAKER (settings.toml) if set.
    """
    # Manual override
    manual = getattr(config, "HAS_SPEAKER", "")
    if str(manual).lower() in ("1", "true", "yes"):
        return True
    if str(manual).lower() in ("0", "false", "no"):
        return False

    # Automatic detection via pycaw
    try:
        from pycaw.pycaw import AudioUtilities
        from pycaw.constants import EDataFlow, DEVICE_STATE

        # Only enumerate active render (output) devices — same approach as OBS's
        # EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE)
        devices = AudioUtilities.GetAllDevices(
            data_flow=EDataFlow.eRender.value,
            device_state=DEVICE_STATE.ACTIVE.value,
        )

        count = len(devices)
        if count == 0:
            logger.info("Speaker detection: no active render devices → no speaker")
            return False

        logger.info("Speaker detection: %d active render device(s) → speaker found", count)
        return True
    except Exception:
        logger.debug("pycaw speaker detection failed — assuming speaker available")
        return True


class RaphaelSignals(QObject):
    response_received = pyqtSignal(str)
    response_token = pyqtSignal(str)  # streaming token
    error_occurred = pyqtSignal(str)
    processing_done = pyqtSignal()
    processing_state_changed = pyqtSignal(bool)
    reset_watchdog = pyqtSignal()
    task_status_changed = pyqtSignal(dict)
    task_finished = pyqtSignal(dict)
    orchestrator_ready = pyqtSignal(object)
    confirmation_requested = pyqtSignal(object)  # ConfirmationRequest


class RaphaelController(QObject):
    """
    Bridges the VAD voice thread, the LLM orchestrator, and the PyQt6 HUD.
    Runs the VAD polling on the Qt main thread via QTimer.

    Uses a staggered ``__init__`` → ``_init_phaseN`` pattern so the UI
    appears and stays responsive while components load incrementally
    (Next.js dynamic-rendering style).
    """

    def __init__(self, ui):
        super().__init__()
        global _controller_instance
        _controller_instance = self
        self.ui = ui
        self.raphael = None  # built in background thread — see _build_orchestrator
        self.vad_detector = None
        # Processing-state contract (three lanes): the controller's
        # "processing" flag means USER LLM work only — proactive and
        # background work run in their own lanes (ProcessingLanes) and
        # never flip it, so the mic and chat stay responsive.
        self._lanes = ProcessingLanes()
        self._bg_response_queue: queue.Queue = queue.Queue()
        self._current_file = ""
        self._last_tts_end_time = time.time()
        self._processing_timer = QTimer(self)
        self._processing_timer.setSingleShot(True)
        self._processing_timer.timeout.connect(self._processing_timeout)

        # ── Floating Minion State & UI State ──
        self._minion_response_pending = False  # True when minion submitted a message
        self._ui_state: str = "window"  # "window" or "floating_icon"

        # ── Active Listening & Sleep State ──
        self.wake_word_required_by_default = state.wake_word_required
        self._active_listening_timer = QTimer(self)
        self._active_listening_timer.setSingleShot(True)
        self._active_listening_timer.timeout.connect(self._active_listening_timeout)

        # ── Idle-time Memory Consolidation ──
        self._last_interaction_time = time.time()
        self._consolidation_triggered = False

        # ── Tool confirmation handshake ──
        # Worker thread sets the event + result; GUI thread resolves it by
        # showing the ConfirmationDialog. Timeout ⇒ deny (safe default).
        self._confirm_event = threading.Event()
        self._confirm_result = False

        # ── Proactive Engine (idle check-ins + topic monitoring) ──
        self.proactive_engine = ProactiveEngine(
            submit_cb=self._submit_proactive,
            get_idle_time_cb=lambda: time.time() - self._last_interaction_time,
            storage_dir=config.PROACTIVE_STORAGE_DIR,
            cooldown=config.PROACTIVE_COOLDOWN,
            min_interval=config.PROACTIVE_MIN_INTERVAL,
            topics_enabled=config.PROACTIVE_TOPICS_ENABLED,
            ddg_check_interval_hours=config.PROACTIVE_DDG_CHECK_INTERVAL_HOURS,
        )
        self.proactive_engine.set_enabled(config.PROACTIVE_ENABLED)

        # ── Setup signals for thread-safe GUI updates ──
        self.signals = RaphaelSignals()
        self.signals.response_received.connect(self._show_response)
        self.signals.response_token.connect(self._on_stream_token)
        self.signals.error_occurred.connect(self._show_error)
        self.signals.processing_done.connect(self._done)
        self.signals.processing_state_changed.connect(lambda val: self.ui.set_processing(val))
        self.signals.reset_watchdog.connect(self._reset_watchdog_timer)
        self.signals.task_status_changed.connect(self._handle_task_status_changed_gui)
        self.signals.task_finished.connect(self._handle_task_finished_gui)
        self.signals.orchestrator_ready.connect(self._on_orchestrator_ready)
        self.signals.confirmation_requested.connect(self._on_confirmation_requested_gui)

        # ── Model State Tracking ──
        from orchestrator.model_state_manager import get_model_state_manager
        self._model_state_manager = get_model_state_manager()

        # ── Reactive state subscriptions (replaces manual ui.set_* calls) ──
        # on_change callbacks fire on the *setting* thread.  For properties
        # that may be set from background threads (e.g. tts_speaking), we
        # defer the UI update to the main event loop.
        def _on_state(prop: str, val: Any) -> None:
            if prop == "muted":
                self.ui.set_muted(val)
            elif prop == "tts_enabled":
                self.ui.set_tts_enabled(val)

        def _on_state_deferred(prop: str, val: Any) -> None:
            """UI-safe wrapper — always delivers on the main thread."""
            QTimer.singleShot(0, lambda p=prop, v=val: _on_state(p, v))

        state.on_change("muted", _on_state_deferred)
        state.on_change("tts_enabled", _on_state_deferred)

        # TTS Queue Worker (serializes all TTS to prevent thread explosion)
        import collections
        self._recent_spoken_texts: collections.deque[str] = collections.deque(maxlen=10)
        self._tts_queue: queue.Queue = queue.Queue()
        self._tts_interrupt = threading.Event()
        self._tts_worker = threading.Thread(target=self._tts_worker_loop, daemon=True)
        self._tts_worker.start()

        # ── Build orchestrator in background so UI never blocks ──
        threading.Thread(target=self._build_orchestrator, daemon=True).start()

        # ── Staggered initialisation — UI appears immediately ──
        self.ui.update_splash(70, "Connecting audio subsystems...")
        QTimer.singleShot(0, self._init_phase1)

    # ── Background orchestrator creation ─────────────────────────

    def _build_orchestrator(self):
        """Create RaphaelOrchestrator in a background thread (avoids 3 s import/init)."""
        try:
            from orchestrator.core import RaphaelOrchestrator
            orch = RaphaelOrchestrator()

            # Pre-warm local Moonshine backend if preferred (eliminates first-call latency)
            preferred = list(getattr(config, "STT_PREFERRED_BACKENDS", [])) + list(getattr(config, "STT_BATCH_PREFERRED_BACKENDS", []))
            if getattr(config, "STT_BACKEND", "") == "moonshine" or "moonshine" in preferred:
                try:
                    from modules.stt_backends import STTRegistry
                    moonshine_backend = STTRegistry.get("moonshine")
                    if moonshine_backend and hasattr(moonshine_backend, "prewarm"):
                        moonshine_backend.prewarm()
                except Exception as e:
                    logger.debug("Moonshine prewarm skip: %s", e)

            self.signals.orchestrator_ready.emit(orch)
        except Exception as exc:
            logger.error("Failed to create orchestrator: %s", exc)
            self.signals.error_occurred.emit(f"Brain failed to load: {exc}")

    def _init_phase1(self):
        """UI callbacks, signal wiring, VAD start, poll timer."""
        # Register HUD callbacks
        self.ui.register_callbacks(
            on_state_change=lambda s: None,
            on_log=lambda t, x: None,
            on_chat_submit=self._on_chat_submit,
        )

        # Connect drag & drop signal
        self.ui.window.drop_zone.file_selected.connect(self._on_file_selected)

        # Stop VAD before Qt event loop shuts down
        self.ui.window.closing.connect(self._shutdown)

        # Connect UI interaction signals
        self.ui.window.toggle_sleep_triggered.connect(self._toggle_sleep)
        self.ui.window.toggle_mute_triggered.connect(self._toggle_mute)
        self.ui.window.toggle_tts_triggered.connect(self._toggle_tts)
        self.ui.window.settings_triggered.connect(self._open_settings)
        self.ui.window.reload_triggered.connect(self._on_reload)
        self.ui.window.interrupt_triggered.connect(self._interrupt)
        self.ui.window.hud.mouse_clicked.connect(self._on_hud_clicked)

        # Wire music panel open request (from HUD music button)
        if hasattr(self.ui, "music_panel") and self.ui.music_panel:
            self.ui.music_panel.open_music_requested.connect(self._open_music_popup)

        # ── Start voice detection ──
        if config.STT_ENABLED:
            self._start_vad()

        # ── Poll VAD queue on main thread ──
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_vad)
        self._poll_timer.start(50)

        # Next phase: audio system discovery
        self.ui.update_splash(80, "Detecting speakers...")
        QTimer.singleShot(200, self._init_phase2)

    def _on_orchestrator_ready(self, orch):
        """Called on main thread when the orchestrator is done building."""
        self.raphael = orch
        self.raphael.set_activity_callback(lambda: self.signals.reset_watchdog.emit())
        self.raphael.set_ui_log(self.ui.write_log)
        # Route confirm_required policy decisions through the HUD dialog.
        self.raphael.executor.confirmation_provider = self._request_confirmation

    def _init_phase2(self):
        """Audio system state — COM bridge calls that may block briefly.
        
        Task 17: Phase 1 of two-phase eager tool loading starts here (frequent tools).
        """
        # ── Detect physical speaker before querying audio state ──
        has_physical_spk = detect_physical_speaker()
        if not has_physical_spk:
            state.audio_output_available = False
            self.ui.set_audio_output_available(False)
            logger.warning("No physical speaker detected — audio_output_available=False")

        # ── Query actual system audio device state ──
        try:
            from hybrid.bridge import CAudioDeviceState
            audio_info = CAudioDeviceState.GetAudioState()
            if audio_info:
                mic_vol = 100
                spk_vol = 100
                spk_muted = False
                if audio_info.get("playback") and has_physical_spk:
                    state.audio_output_available = True
                    state.speaker_muted = audio_info["playback"].get("muted", False)
                    state.speaker_volume = audio_info["playback"].get("volume_percent", 100)
                    spk_muted = audio_info["playback"].get("muted", False)
                    spk_vol = audio_info["playback"].get("volume_percent", 100)
                else:
                    state.audio_output_available = False
                    self.ui.set_audio_output_available(False)
                if audio_info.get("recording"):
                    state.muted = audio_info["recording"].get("muted", False)
                    state.mic_volume = audio_info["recording"].get("volume_percent", 100)
                    mic_vol = audio_info["recording"].get("volume_percent", 100)
                self.ui.set_audio_state(mic_vol, spk_vol, spk_muted)
        except Exception:
            pass

        # Next phase: tray, hotkeys, event bus, startup greeting
        self.ui.update_splash(90, "Configuring system tray & hotkeys...")
        QTimer.singleShot(300, self._init_phase3)

    def _init_phase3(self):
        """Tray icon, hotkeys, EventBus subscriptions, startup briefing."""
        # ── System Tray Icon Integration ──
        try:
            from ui.tray_icon import RaphaelTrayIcon
            self.tray_icon = RaphaelTrayIcon(parent=self.ui.window)
            self.tray_icon.toggle_hud_requested.connect(self.ui.window.toggle_visibility)
            self.tray_icon.toggle_mute_requested.connect(self._toggle_mute)
            self.tray_icon.toggle_tts_requested.connect(self._toggle_tts)
            self.tray_icon.open_settings_requested.connect(self._open_settings)
            self.tray_icon.open_music_requested.connect(self._open_music_popup)
            self.tray_icon.open_playground_requested.connect(self._open_playground_popup)
            self.tray_icon.exit_requested.connect(self.ui.exit_app)
            if not state.audio_input_available:
                self.tray_icon.set_audio_input_available(False)
            self.tray_icon.show()
        except Exception as e:
            logger.warning("Failed to initialize system tray icon: %s", e)

        # ── Floating Minion Icon + Popup Windows ──
        try:
            from ui.floating_icon import FloatingIcon, CompactChatInput
            from ui.window_manager import PopupWindowManager

            self._window_manager = PopupWindowManager()
            self._floating_icon = FloatingIcon()
            self._compact_chat = CompactChatInput()

            # Wire floating icon signals
            self._floating_icon.double_clicked.connect(self._on_floating_double_click)
            self._floating_icon.single_clicked.connect(self._on_floating_single_click)
            self._floating_icon.right_clicked.connect(self._on_floating_right_click)
            self._floating_icon.dragged.connect(self._on_icon_dragged)

            # Wire compact chat signals
            self._compact_chat.message_submitted.connect(self._on_minion_submit)
            self._compact_chat.stop_requested.connect(self._interrupt)
            self._compact_chat.expand_requested.connect(self.show_main_window)
            self._compact_chat.closed.connect(self._on_compact_chat_closed)

            # Show floating icon when main window hides, hide when it shows
            self.ui.window.visibility_changed.connect(self._on_main_window_visibility)

            # Subscribe to tool.executed for auto-opening popup windows
            from orchestrator.event_bus import EventBus
            bus = EventBus()
            bus.subscribe("tool.executed", self._on_tool_executed_event)

            # Show floating icon initially (main window starts visible)
            self._floating_icon.hide()
        except Exception as e:
            logger.warning("Failed to initialize floating minion: %s", e)

        # ── Global Hotkey Listener (Win+Shift+R) ──
        try:
            from modules.hotkeys import GlobalHotkeyListener
            self._hotkey_listener = GlobalHotkeyListener(
                callback=lambda: QTimer.singleShot(0, self.ui.window.show_and_activate)
            )
            self._hotkey_listener.start()
        except Exception as e:
            logger.warning("Failed to start global hotkey listener: %s", e)

        # ── Subscribe to task events on EventBus ──
        from orchestrator.event_bus import EventBus
        bus = EventBus()
        bus.subscribe("task.status_changed", self._on_task_status_changed_event)
        bus.subscribe("task.finished", self._on_task_finished_event)

        # ── Trigger startup greeting ──
        self.startup_manager = StartupManager(
            write_log_cb=self.ui.write_log,
            set_state_cb=self.ui.set_state,
            speak_cb=self._speak_briefing,
        )
        QTimer.singleShot(500, self.startup_manager.start)

        # Done loading - transition to main window!
        self.ui.update_splash(100, "Done")
        QTimer.singleShot(200, self.ui.close_splash_and_show_main)

        # Task 17: Phase 2 of two-phase eager tool loading (background load of remaining tools)
        threading.Thread(target=self._eager_load_tools_phase2, daemon=True).start()

    def _eager_load_tools_phase2(self):
        """Task 17: Background phase of two-phase tool loading.
        
        Phase 1 (sync): Frequent tools (web_search, read_file, capture_screen)
        are loaded eagerly during _build_orchestrator() to reduce first query latency.
        
        Phase 2 (async): Remaining tools are loaded in background after UI is visible,
        avoiding startup delay while maintaining cache warmth for future queries.
        """
        try:
            import logging as log_module
            logger_phase2 = log_module.getLogger(__name__)

            # Trigger tool registry to ensure all tools are imported and cached
            from orchestrator.tools import get_tool_schemas, get_tool_map
            from orchestrator.log_utils import log_prefixed, LOG_PREFIX_PARALLEL

            log_prefixed(LOG_PREFIX_PARALLEL, log_module.DEBUG, "Phase 2: Starting background tool preload")

            # Load all tool schemas and the full tool map (this triggers lazy imports)
            schemas = get_tool_schemas()
            tool_map = get_tool_map()

            log_prefixed(
                LOG_PREFIX_PARALLEL, log_module.INFO,
                "Phase 2: Preloaded %d tool schemas + %d tool implementations",
                len(schemas), len(tool_map)
            )

            # Warm up cached schemas for next query
            from orchestrator.cache_manager import get_cache_manager
            cache = get_cache_manager()
            cache_stats = cache.stats()
            log_prefixed(
                LOG_PREFIX_PARALLEL, log_module.DEBUG,
                "Cache state: %d entries, hit_rate=%.1f%%",
                cache_stats.get("cache_size", 0),
                cache_stats.get("hit_rate_percent", 0)
            )
        except Exception as e:
            logger.warning("Phase 2 eager tool loading failed: %s", e)

    # ── Processing state ─────────────────────────────────────────

    def _is_processing(self) -> bool:
        """True only while USER work is running (proactive/bg never count)."""
        return self._lanes.is_user_processing()

    def _set_processing(self, value: bool) -> None:
        """Enter/leave the USER lane (thread-safe — defers GUI work to main thread)."""
        if value:
            self._lanes.begin_user()
        else:
            self._lanes.end_user()
        # Timer start/stop MUST happen on the GUI thread.  When called from a
        # background thread (e.g. EventBus handler), Qt would emit
        # QBasicTimer warnings and the processing state could get stuck.
        # Use singleShot(0, …) to always run on the main event loop.
        QTimer.singleShot(0, lambda v=value: self._apply_processing_state(v))
        self.signals.processing_state_changed.emit(value)

    def _apply_processing_state(self, value: bool) -> None:
        """Apply processing timer start/stop on the main thread."""
        if value:
            self._processing_timer.start(180000)
        else:
            self._processing_timer.stop()

    def _on_task_status_changed_event(self, event: str, data: dict):
        self.signals.task_status_changed.emit(data)

    def _on_task_finished_event(self, event: str, data: dict):
        self.signals.task_finished.emit(data)

    def _handle_task_status_changed_gui(self, data: dict):
        try:
            self.ui.update_task_badge(
                data.get("task_id", ""),
                data.get("label", ""),
                data.get("status", ""),
                data.get("tool_name", ""),
                data.get("current_action", "")
            )
        except Exception as e:
            logger.debug("Failed to update task badge in GUI: %s", e)

    def _handle_task_finished_gui(self, data: dict):
        # Only USER-lane work queues background results — proactive/background
        # lanes deliver immediately (Task 2 contract).
        if self._is_processing():
            self._bg_response_queue.put(data)
            logger.info("Raphael is busy, queued background response for task %s", data.get("task_id"))
        else:
            self._deliver_bg_response(data)

    def _deliver_bg_response(self, data: dict):
        task_id = data.get("task_id", "")
        label = data.get("label", "")
        status = data.get("status", "")
        summary = data.get("summary", "")
        error = data.get("error", "")

        if status == "done":
            text = summary or f"Background task '{label}' completed."
            self.ui.write_log("sys", f"[BG:{task_id}] {label} — COMPLETE")
            self.ui.write_log("ai", text)
        else:
            text = f"Background task '{label}' failed: {error}"
            self.ui.write_log("sys", f"[BG:{task_id}] {label} — FAILED")
            self.ui.write_log("err", error or "Unknown error")

        # Background results should never flip the processing flag (Task 5).
        # TTS queue is already serialized by the worker thread; no need to
        # set processing. User always wins if they submit while BG is speaking.
        if state.tts_enabled:
            self.ui.set_state("SPEAKING")
            self._tts_queue.put((text, lambda: self.signals.processing_done.emit()))
        else:
            self._done()

    # ── Tool confirmation (policy confirm_required → HUD dialog) ──

    def _request_confirmation(self, request) -> bool:
        """Provider for ToolExecutor — runs on the worker thread.

        Session grants short-circuit.  Otherwise the GUI thread shows the
        ConfirmationDialog; we block on an Event until it answers.
        Timeout (2 min) ⇒ deny, so a stuck dialog can never wedge the
        executor.
        """
        if state.session_allows(request.tool_name):
            return True
        self._confirm_result = False
        self._confirm_event.clear()
        self.signals.confirmation_requested.emit(request)
        if not self._confirm_event.wait(timeout=120):
            logger.warning("Confirmation for %s timed out — denied", request.tool_name)
        return self._confirm_result

    def _on_confirmation_requested_gui(self, request):
        """Main-thread slot: show the modal dialog and record the verdict."""
        try:
            from ui.confirmation_dialog import ConfirmationDialog

            dialog = ConfirmationDialog(request, parent=self.ui.window)
            result = dialog.exec()
            if result == ConfirmationDialog.RESULT_ALLOW_SESSION:
                state.allow_session_tool(request.tool_name)
                self._confirm_result = True
            elif result == ConfirmationDialog.RESULT_ALLOW_ONCE:
                self._confirm_result = True
            else:
                self._confirm_result = False
        except Exception as exc:
            logger.error("Confirmation dialog failed: %s — denying", exc)
            self._confirm_result = False
        finally:
            self._confirm_event.set()

    # ── Floating Minion Handlers & UI State ───────────────────────

    def get_ui_state(self) -> str:
        """Return current UI presentation state ('window' or 'floating_icon')."""
        return getattr(self, "_ui_state", "window")

    def is_floating_icon_state(self) -> bool:
        """Return True if Raphael is currently in floating icon mode."""
        return self.get_ui_state() == "floating_icon"

    def is_window_state(self) -> bool:
        """Return True if Raphael is currently in main HUD window mode."""
        return self.get_ui_state() == "window"

    def show_main_window(self):
        """Show and activate Raphael's main HUD window."""
        if hasattr(self.ui, "window") and self.ui.window is not None:
            if self.ui.window.isMinimized():
                self.ui.window.showNormal()
            self.ui.window.show()
            self.ui.window.raise_()
            self.ui.window.activateWindow()
            self._ui_state = "window"
            if hasattr(self, "_floating_icon"):
                self._floating_icon.hide()

    def hide_main_window(self):
        """Hide Raphael's main HUD window to floating minion icon mode."""
        if hasattr(self.ui, "window") and self.ui.window is not None:
            if self.ui.window.isMinimized():
                self.ui.window.showNormal()
            self.ui.window.hide()
            self._ui_state = "floating_icon"

    def _on_main_window_visibility(self, visible: bool):
        """Show floating icon when main window is closed/hidden, but NOT when minimized."""
        window = getattr(self.ui, "window", None)
        if window is not None and window.isMinimized():
            # Main window was minimized to Windows Taskbar - do NOT show floating icon
            if hasattr(self, "_floating_icon"):
                self._floating_icon.hide()
            if hasattr(self, "_compact_chat") and self._compact_chat.isVisible():
                self._compact_chat.close()
            logger.info("Raphael UI state updated: MINIMIZED mode (floating icon hidden)")
            return

        if visible:
            self._ui_state = "window"
            if hasattr(self, "_floating_icon"):
                self._floating_icon.hide()
            # Close compact chat if open
            if hasattr(self, "_compact_chat") and self._compact_chat.isVisible():
                self._compact_chat.close()
            logger.info("Raphael UI state updated: WINDOW mode")
        else:
            self._ui_state = "floating_icon"
            if hasattr(self, "_floating_icon"):
                self._floating_icon.show()
                self._floating_icon.raise_()
            logger.info("Raphael UI state updated: FLOATING_ICON mode")

    def _on_floating_single_click(self):
        """Single click: wake the icon (visual feedback)."""
        self._floating_icon.start_glow()
        QTimer.singleShot(600, self._floating_icon.stop_glow)

    def _on_floating_double_click(self):
        """Double click: open compact chat input near the icon."""
        if self._compact_chat.isVisible():
            self._compact_chat.close()
            return
        self._compact_chat.popup_near(self._floating_icon.pos())

    def _on_floating_right_click(self, pos: QPoint):
        """Right click: show context menu near the floating icon."""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #1a1a2e; color: #ccc; border: 1px solid #333; padding: 4px; border-radius: 6px; }"
            "QMenu::item { padding: 6px 16px; border-radius: 4px; }"
            "QMenu::item:selected { background: #14b8a6; color: white; }"
        )

        hud_action = QAction("🗔  Open Main Window", menu)
        hud_action.triggered.connect(self.show_main_window)
        menu.addAction(hud_action)

        music_action = QAction("🎵  Music Player", menu)
        music_action.triggered.connect(self._open_music_popup)
        menu.addAction(music_action)

        playground_action = QAction("🎨  Raphael Playground", menu)
        playground_action.triggered.connect(self._open_playground_popup)
        menu.addAction(playground_action)

        menu.addSeparator()

        if not state.audio_input_available:
            mic_action = QAction("🎙️  Mic Unavailable (Chat Mode)", menu)
            mic_action.setToolTip("No microphone detected — chat-only mode active")
            mic_action.setEnabled(False)
            menu.addAction(mic_action)
        else:
            mic_label = "🎙️  Unmute Microphone" if state.muted else "🎙️  Mute Microphone"
            mic_action = QAction(mic_label, menu)
            mic_action.triggered.connect(self._toggle_mute)
            menu.addAction(mic_action)

        tts_label = "🔊  Disable Voice TTS" if state.tts_enabled else "🔊  Enable Voice TTS"
        tts_action = QAction(tts_label, menu)
        tts_action.triggered.connect(self._toggle_tts)
        menu.addAction(tts_action)

        settings_action = QAction("⚙️  Settings", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        exit_action = QAction("❌  Exit", menu)
        exit_action.triggered.connect(self.ui.exit_app)
        menu.addAction(exit_action)

        menu.exec(pos)

    def _on_icon_dragged(self, center: QPoint):
        """Make the compact chat follow the icon when dragged."""
        if hasattr(self, "_compact_chat") and self._compact_chat.isVisible():
            self._compact_chat.follow_icon(center)

    def _on_compact_chat_closed(self):
        """Compact chat was closed."""
        pass

    def _on_minion_submit(self, text: str):
        """Handle message submitted from the compact chat input."""
        if self._is_processing():
            self._compact_chat.set_processing(True)
            self.ui.write_log("sys", "Busy processing previous request...")
            return
        self._minion_response_pending = True
        self._compact_chat.set_processing(True)
        self._floating_icon.set_processing(True)
        self._submit_message(text)

    def _on_tool_executed_event(self, event: str, data: dict):
        """Auto-open popup windows for tool results when in floating minion mode or minion response is pending."""
        if not (self.is_floating_icon_state() or getattr(self, "_minion_response_pending", False)):
            return
        tool = data.get("tool", "")
        result = data.get("result", "")
        if not tool or not result:
            return
        # Route tool results to appropriate popup windows
        if tool in ("music_play", "music_search"):
            QTimer.singleShot(0, self._open_music_popup)
        elif tool in ("web_search", "web_browse", "news_search"):
            title = f"{tool.replace('_', ' ').title()} Result"
            QTimer.singleShot(0, lambda t=title, r=result: self._open_content_popup("news", t, r))
        elif tool in ("read_file", "write_file", "edit_file"):
            title = f"{tool.replace('_', ' ').title()} Result"
            QTimer.singleShot(0, lambda t=title, r=result: self._open_content_popup("file", t, r))
        else:
            # Generic tool result
            title = f"{tool.replace('_', ' ').title()} Result"
            QTimer.singleShot(0, lambda t=title, r=result: self._open_content_popup(tool, t, r))

    def _open_content_popup(self, key: str, title: str, text: str):
        """Open a content popup window via the window manager."""
        if not hasattr(self, "_window_manager"):
            return
        self._window_manager.show_content(key, title, text)

    def _open_music_popup(self):
        """Toggle the standalone music player window (show/hide)."""
        if not hasattr(self, "_window_manager"):
            return
        from ui.spotify_music_window import SpotifyMusicWindow
        key = "__music__"
        if key in self._window_manager._windows:
            w = self._window_manager._windows[key]
            if isinstance(w, SpotifyMusicWindow) and w.isVisible():
                w.hide()
                return
        self._window_manager.show_music()

    def _open_playground_popup(self):
        """Toggle the standalone Raphael Playground Studio window (show/hide)."""
        if not hasattr(self, "_window_manager"):
            return
        from ui.playground_window import PlaygroundWindow
        key = "__playground__"
        if key in self._window_manager._windows:
            w = self._window_manager._windows[key]
            if isinstance(w, PlaygroundWindow) and w.isVisible():
                w.hide()
                return
        self._window_manager.show_playground()

    # ── File attachment ─────────────────────────────────────────────

    def _on_file_selected(self, path: str):
        self._current_file = path
        if path:
            self.ui.write_log("sys", f"File attached: {Path(path).name}")
        else:
            self.ui.write_log("sys", "File attachment cleared")

    # ─── Startup briefing ──────────────────────────────────────────

    def _speak_briefing(self, text: str):
        if state.tts_enabled:
            self.ui.set_state("SPEAKING")
            def on_briefing_done():
                if not self._is_processing():
                    if state.muted:
                        self.ui.set_state("MUTED")
                    elif state.wake_word_required:
                        self.ui.set_state("SLEEPING")
                    else:
                        self.ui.set_state("LISTENING")
            self._tts_queue.put((text, on_briefing_done))

    # ── Toggles ─────────────────────────────────────────────────────

    def _toggle_sleep(self):
        if not state.audio_input_available:
            self.ui.write_log("sys", "Sleep toggle unavailable — no microphone detected")
            return
        if state.muted:
            self._unmute()
            return

        is_sleeping = state.wake_word_required
        if is_sleeping:
            state.wake_word_required = False
            self.ui.set_state("LISTENING")
            self.ui.write_log("sys", "Waking up... (Always listening)")
            if state.tts_enabled:
                self._tts_queue.put(("Listening.", None))
        else:
            state.wake_word_required = True
            self.ui.set_state("SLEEPING")
            self.ui.write_log("sys", "Going to sleep... (Wake word required)")
            if state.tts_enabled:
                self._tts_queue.put(("Sleeping.", None))

    def _open_settings(self):
        """Open settings dialog (triggered from tray menu)."""
        from ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.ui.window)
        dlg.exec()

    def _toggle_mute(self):
        if not state.audio_input_available:
            self.ui.write_log("sys", "Mute toggle unavailable — no microphone detected")
            return
        if state.muted:
            self._unmute()
        else:
            self._mute()

    def _mute(self):
        state.muted = True
        self.ui.set_state("MUTED")
        self.ui.write_log("sys", "Microphone off.")
        if state.tts_enabled:
            self._tts_queue.put(("Microphone off.", None))

    def _unmute(self):
        state.muted = False
        if state.wake_word_required:
            self.ui.set_state("SLEEPING")
            self.ui.write_log("sys", "Microphone on (Sleeping).")
            if state.tts_enabled:
                self._tts_queue.put(("Microphone on, sleeping.", None))
        else:
            self.ui.set_state("LISTENING")
            self.ui.write_log("sys", "Microphone on (Listening).")
            if state.tts_enabled:
                self._tts_queue.put(("Microphone on, listening.", None))

    def _toggle_tts(self):
        from modules.tts import stop as tts_stop
        new_val = not state.tts_enabled
        state.tts_enabled = new_val
        if new_val:
            self.ui.write_log("sys", "Text-to-speech turned on.")
            self._tts_queue.put(("Text to speech enabled.", None))
        else:
            self.ui.write_log("sys", "Text-to-speech turned off.")
            tts_stop()
            while not self._tts_queue.empty():
                try:
                    self._tts_queue.get_nowait()
                except Exception:
                    break

    def _on_hud_clicked(self, button: str):
        if button == "left":
            if state.muted:
                self._unmute()
            else:
                self._toggle_sleep()
        elif button == "right":
            self._toggle_mute()

    # ── VAD ─────────────────────────────────────────────────────────

    def _start_vad(self):
        try:
            from modules.stt import create_detector
            self.vad_detector = create_detector()

            # The VAD-gated pipeline owns wake/listening transitions itself;
            # the streaming detectors rely on the controller's text matching.
            gated_mode = False
            try:
                from modules.voice_pipeline import GatedDetector
                gated_mode = isinstance(self.vad_detector, GatedDetector)
            except Exception:
                gated_mode = False
            self._gated_vad = gated_mode

            def handle_state_change(new_state):
                if gated_mode:
                    self.ui.set_state(new_state)
                elif state.wake_word_required and new_state in ("LISTENING", "IDLE"):
                    self.ui.set_state("SLEEPING")
                else:
                    self.ui.set_state(new_state)

            self.vad_detector.set_state_callback(handle_state_change)
            started = self.vad_detector.start()

            if not started:
                state.audio_input_available = False
                self.ui.set_audio_input_available(False)
                logger.info("No microphone detected — entering chat-only mode")
                self._enter_chat_mode()
                return

            if gated_mode:
                # GatedDetector emitted its initial state during start()
                logger.info("Voice detection active (VAD-gated pipeline)")
            elif self.wake_word_required_by_default:
                self.ui.set_state("SLEEPING")
                logger.info("Voice detection active (Wake word required)")
            else:
                self.ui.set_state("LISTENING")
                logger.info("Voice detection active (Always listening)")
        except Exception as e:
            state.audio_input_available = False
            self.ui.set_audio_input_available(False)
            logger.error("Voice input unavailable: %s", e)
            self._enter_chat_mode()

    def _enter_chat_mode(self):
        self.vad_detector = None
        state.audio_input_available = False
        self.ui.set_audio_input_available(False)
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.set_audio_input_available(False)
        self.ui.set_state("CHAT")
        logger.info("Chat-only mode active (No microphone detected)")

    # ── VAD Poll ─────────────────────────────────────────────────────

    def _poll_drain_stt(self):
        """Drain the STT transcript queue to discard TTS echo audio."""
        if not self.vad_detector:
            return
        drained = 0
        while not self.vad_detector.transcript_queue.empty():
            try:
                self.vad_detector.transcript_queue.get_nowait()
                drained += 1
            except queue.Empty:
                break
        if drained:
            logger.debug("Echo guard: drained %d STT transcript(s) while TTS active", drained)

    def _poll_vad(self):
        """Called every 50ms on the main thread — check VAD for transcriptions."""
        # Don't touch the queue while processing — speech accumulates until _done()
        if self._is_processing():
            return

        # ── Echo guard: skip/drain STT while TTS is playing ─────────
        # Prevents the assistant from hearing its own voice through the mic.
        # Also applies a short cooldown after TTS stops to catch residual
        # audio that's still in the mic/STT pipeline.
        if state.tts_speaking:
            self._poll_drain_stt()
            return
        if time.time() - self._last_tts_end_time < 0.5:
            self._poll_drain_stt()
            return

        # Check queued background responses when idle
        if not self._bg_response_queue.empty():
            try:
                data = self._bg_response_queue.get_nowait()
                self._deliver_bg_response(data)
            except queue.Empty:
                pass

        # Idle memory consolidation (max once per 5 minutes)
        if not self._consolidation_triggered and (time.time() - self._last_interaction_time > 30):
            if state.memory_needs_consolidation:
                self._consolidation_triggered = True
                state.memory_needs_consolidation = False
                self.ui.write_log("sys", "[Memory Agent] Memory optimization in progress...")
                threading.Thread(target=self._run_idle_consolidation, daemon=True).start()

        # Proactive check during idle time (includes topic monitors + reminders)
        if not state.muted and not state.wake_word_required:
            self.proactive_engine.check()
            self.proactive_engine.on_check_complete()

        if not self.vad_detector or not state.audio_input_available:
            return

        try:
            transcription = self.vad_detector.transcript_queue.get_nowait()
        except queue.Empty:
            return

        if not transcription:
            return

        # ── Semantic Echo Filter ──
        # Discard the transcription if it matches or overlaps with recently spoken TTS text
        import re
        clean_trans = re.sub(r'[^\w\s]', '', transcription.lower()).strip()
        is_echo = False
        if clean_trans:
            for spoken in list(self._recent_spoken_texts):
                clean_spoken = re.sub(r'[^\w\s]', '', spoken.lower()).strip()
                if clean_spoken and (clean_trans in clean_spoken or clean_spoken in clean_trans):
                    is_echo = True
                    break
        if is_echo:
            logger.info("Echo guard: discarded transcription matching spoken text: \"%s\"", transcription)
            return

        text_lower = transcription.lower().strip()

        # Wake word detection — use substring matching for flexibility
        extended_wake_words = list(getattr(config, "STT_WAKE_WORDS", []))
        for w in ["voice access wake up", "unmute", "wake up"]:
            if w not in extended_wake_words:
                extended_wake_words.append(w)

        # Strip punctuation for more flexible matching
        text_clean = text_lower.rstrip(".!?,;:")

        wake_detected = False
        matched_wake_word = None
        for wake_word in extended_wake_words:
            if wake_word in text_clean:
                wake_detected = True
                matched_wake_word = wake_word
                break
            elif text_clean in wake_word:
                wake_detected = True
                matched_wake_word = text_clean
                break

        if state.wake_word_required and not wake_detected:
            if self._gated_vad or getattr(self.vad_detector, "wake_handled", False) or getattr(self.vad_detector, "_armed", False):
                logger.debug("Gated pipeline already handled wake word; accepting command")
            else:
                if getattr(config, "STT_LOG_IGNORED", False):
                    logger.debug("Wake word required: ignored transcription '%s'", transcription)
                return

        if wake_detected:
            state.wake_word_required = False
            # Strip the wake word from the transcription
            remaining_text = transcription
            if matched_wake_word:
                import re as re_mod
                remaining_text = re_mod.sub(re_mod.escape(matched_wake_word), "", transcription, flags=re_mod.IGNORECASE).strip()

            # Clean up punctuation/spaces from remaining text
            import re as re_mod
            remaining_clean = re_mod.sub(r'[^\w\s]', '', remaining_text).strip()

            if remaining_clean:
                logger.info("Wake word + command detected. Processing: '%s'", remaining_text)
                self._submit_message(remaining_text)
                return
            else:
                self.ui.write_log("ai", "Raphael is here.")
                # Defer _done() until the greeting finishes speaking. Calling
                # _done() right here would start the active-listening window
                # while TTS is still playing; the echo guard drains STT during
                # and just after TTS, so the user's reply gets swallowed and the
                # 8s window expires → the assistant "falls asleep after greeting".
                if state.tts_enabled:
                    self.ui.set_state("SPEAKING")
                    self._tts_queue.put(("Raphael is here.", lambda: self.signals.processing_done.emit()))
                else:
                    self._done()
                return

        self._submit_message(transcription)

    # ── Memory consolidation ────────────────────────────────────────

    def _save_mechanical_session_summary(self, history: list[dict]):
        """Write a 1-2 sentence 'where we left off' note at session end.

        Mechanical (no LLM call): last user message + last assistant reply,
        truncated. The Morning Briefing routine pops it once via
        ``pop_last_session`` so it surfaces exactly once.
        """
        try:
            from memory.memory_manager import save_session_summary
            last_user = last_assistant = ""
            for turn in reversed(history):
                content = (turn.get("content") or "").strip()
                role = turn.get("role", "")
                if not content or content == "(interrupted)":
                    continue
                if role == "assistant" and not last_assistant:
                    last_assistant = content
                elif role == "user" and not last_user:
                    last_user = content
                if last_user and last_assistant:
                    break
            parts = []
            if last_user:
                parts.append(f"Last you said: {last_user[:180]}")
            if last_assistant:
                parts.append(f"Raphael replied: {last_assistant[:180]}")
            summary = " | ".join(parts)
            if len(summary) > 380:
                summary = summary[:380].rsplit(" ", 1)[0] + "..."
            save_session_summary(summary)
        except Exception as e:
            logger.error("Failed to save mechanical session summary: %s", e)

    def _run_idle_consolidation(self):
        if not self.raphael:
            return
        try:
            from orchestrator.memory_agent import consolidate_memory
            history_copy = list(self.raphael.history)
            consolidate_memory(history_copy)
            self._save_mechanical_session_summary(history_copy)
        except Exception as e:
            logger.error("Background memory consolidation failed: %s", e)
            self.ui.write_log("err", f"[Memory Agent] Optimization failed: {e}")

    # ── Message submission ─────────────────────────────────────────

    def _on_chat_submit(self, text: str):
        if self._is_processing():
            self.ui.write_log("sys", "Busy processing previous request...")
            return
        self._submit_message(text)

    def _submit_message(self, text: str):
        self._last_interaction_time = time.time()
        self._consolidation_triggered = False
        self.proactive_engine.reset_timer()

        self._active_listening_timer.stop()

        self._set_processing(True)
        self._processing_timer.start(180000)
        self.ui.write_log("you", text)
        self.ui.hud.set_transcription(text)

        text_lower = text.lower().strip()

        was_sleeping = state.wake_word_required
        if was_sleeping and not state.muted:
            state.wake_word_required = False

        # Wake word detection
        extended_wake_words = list(getattr(config, "STT_WAKE_WORDS", []))
        for w in ["voice access wake up", "unmute", "wake up"]:
            if w not in extended_wake_words:
                extended_wake_words.append(w)

        if was_sleeping and not state.muted and text_lower in extended_wake_words:
            self.ui.write_log("ai", "Raphael is here.")
            if state.tts_enabled:
                self.ui.set_state("SPEAKING")
                self._tts_queue.put(("Raphael is here.", lambda: self.signals.processing_done.emit()))
            else:
                self._done()
            return

        # Voice Access Sleep / Mute
        if text_lower in ("voice access sleep", "mute", "go to sleep", "sleep"):
            state.wake_word_required = True
            self.ui.set_state("SLEEPING")
            logger.info("Going to sleep... (Wake word required)")
            if state.tts_enabled:
                self.ui.set_state("SPEAKING")
                self._tts_queue.put(("Going to sleep.", lambda: self.signals.processing_done.emit()))
            else:
                self._done()
            return

        if text_lower in ("turn off microphone", "mute microphone", "microphone off"):
            state.muted = True
            self.ui.set_state("MUTED")
            logger.info("Microphone off.")
            if state.tts_enabled:
                self.ui.set_state("SPEAKING")
                self._tts_queue.put(("Microphone turned off.", lambda: self.signals.processing_done.emit()))
            else:
                self._done()
            return

        # System commands
        if text_lower in ("exit", "quit", "bye", "goodbye"):
            self.ui.write_log("ai", "Goodbye! Shutting down.")
            self._done()
            if state.tts_enabled:
                self._tts_queue.put(("Goodbye!", None))
            QTimer.singleShot(2000, self._quit)
            return

        if text_lower == "reset":
            if not self.raphael:
                self._done()
                return
            self.raphael.reset_conversation()
            logger.info("Conversation reset")
            self._done()
            return

        # Local intent fast path (skip LLM for deterministic intents)
        try:
            from orchestrator.local_intents import try_match_intent
            matched_intent = try_match_intent(text, controller=self)
            if matched_intent is not None:
                intent_name, result_text = matched_intent
                self.ui.write_log("ai", result_text)
                self.signals.response_received.emit(result_text)
                self._done()
                if state.tts_enabled:
                    self.ui.set_state("SPEAKING")
                    self._tts_queue.put((result_text, lambda: self.signals.processing_done.emit()))
                return
        except Exception as e:
            logger.warning("Local intent fast path check failed: %s", e)

        # Process through LLM
        self.ui.set_state("THINKING")
        logger.info("Thinking...")
        threading.Thread(target=self._process_llm, args=(text, self._current_file), daemon=True).start()

    def _submit_proactive(self, instruction: str):
        """Submit a proactive check-in to the LLM (read-only, no tools).

        Runs in the proactive lane: never flips the user-lane processing
        flag, so the mic and chat stay responsive. The result carries the
        lane generation captured at start; if the user takes over (or a
        newer proactive round begins) before it lands, it is discarded.
        """
        if self._lanes.is_user_processing() or state.muted or not self.raphael:
            self.proactive_engine.on_check_complete()
            return

        def _run():
            try:
                assert self.raphael is not None
                gen = self._lanes.begin_proactive()
                try:
                    response = self.raphael.process_message(instruction)
                    self.proactive_engine.on_check_complete()
                    if self._lanes.is_stale("proactive", gen):
                        logger.debug("Proactive result discarded (superseded generation)")
                        return
                    if response and response.strip().lower() != "__noop__":
                        if state.tts_enabled and not state.muted:
                            from modules.tts import speak
                            self._recent_spoken_texts.append(response)
                            speak(response)
                        self.ui.write_log("ai", f"[Proactive] {response}")
                finally:
                    self._lanes.end_proactive()
            except Exception as e:
                logger.debug("Proactive check failed: %s", e)
                self.proactive_engine.on_check_complete()

        threading.Thread(target=_run, daemon=True, name="proactive").start()

    def _process_llm(self, user_input: str, file_path: str | None = None):
        if not self.raphael:
            self.signals.error_occurred.emit("Raphael is still connecting — please wait a moment.")
            return
        from orchestrator.events import (
            InterruptedEvent, TaskCompleteEvent,
            TaskErrorEvent, ThinkingEvent, TokenEvent,
            ToolErrorEvent, ToolResultEvent, ToolStartEvent,
        )
        import time

        session_id = f"session_{int(time.time() * 1000)}"
        self.ui.log.start_steps_session(session_id)

        try:
            final_text: str | None = None
            for event in self.raphael.process_message_events(
                user_input, file_path=file_path,
            ):
                if isinstance(event, TokenEvent):
                    self.signals.response_token.emit(event.token)

                elif isinstance(event, ThinkingEvent):
                    if event.round == 0:
                        self.ui.status_ticker.show_status("⚙️ Thinking...")

                elif isinstance(event, ToolStartEvent):
                    tool_label = event.tool.replace("_", " ").title()
                    self.ui.status_ticker.show_status(f"⚙️ Running {tool_label}...")

                elif isinstance(event, ToolResultEvent):
                    preview = event.result[:120].replace("\n", " ")
                    self.ui.log.add_step(event.tool, "success", preview)
                    tool_label = event.tool.replace("_", " ").title()
                    self.ui.status_ticker.show_status(f"✅ Completed {tool_label}")

                elif isinstance(event, ToolErrorEvent):
                    preview = event.error[:120].replace("\n", " ")
                    self.ui.log.add_step(event.tool, "error", preview)
                    tool_label = event.tool.replace("_", " ").title()
                    self.ui.status_ticker.show_status(f"❌ Failed {tool_label}")

                elif isinstance(event, TaskCompleteEvent):
                    final_text = event.result

                elif isinstance(event, TaskErrorEvent):
                    self.signals.error_occurred.emit(event.error)
                    return

                elif isinstance(event, InterruptedEvent):
                    self.signals.processing_done.emit()
                    return

            if final_text:
                self.signals.response_received.emit(final_text)
            else:
                self.signals.processing_done.emit()
        except Exception as e:
            err_msg = f"LLM error: {e}"
            logger.error(err_msg)
            self.signals.error_occurred.emit(err_msg)
        finally:
            self.ui.log.commit_steps()
            self.ui.status_ticker.clear_status()

    def _on_stream_token(self, token: str):
        """Slot: append streaming token to UI and queue complete sentences to TTS immediately."""
        self.ui.log.stream_token("ai", token)

        if not state.tts_enabled or state.muted:
            return

        if not hasattr(self, "_stream_tts_buffer"):
            self._stream_tts_buffer = ""

        self._stream_tts_buffer += token

        # Check for sentence boundaries
        for delim in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
            if delim in self._stream_tts_buffer:
                parts = self._stream_tts_buffer.split(delim, 1)
                sentence = (parts[0] + delim[0]).strip()
                self._stream_tts_buffer = parts[1]
                if sentence and len(sentence) > 3:
                    self.ui.set_state("SPEAKING")
                    self._tts_queue.put((sentence, None))
                break

    def _show_response(self, response: str):
        self.ui.write_log("ai", response)

        # If minion submitted or in floating icon mode, route final response to a popup window
        if self._minion_response_pending or self.is_floating_icon_state():
            self._minion_response_pending = False
            if hasattr(self, "_floating_icon"):
                self._floating_icon.set_processing(False)
            if hasattr(self, "_compact_chat"):
                self._compact_chat.set_processing(False)
            if hasattr(self, "_window_manager"):
                self._window_manager.show_content("response", "Raphael", response)
            if state.tts_enabled:
                rem = getattr(self, "_stream_tts_buffer", "").strip()
                self._stream_tts_buffer = ""
                if rem:
                    self._tts_queue.put((rem, lambda: self.signals.processing_done.emit()))
                else:
                    self._tts_queue.put(("", lambda: self.signals.processing_done.emit()))
            else:
                self._done()
            return

        if state.tts_enabled:
            # Flush any remaining sentence fragment in the stream buffer
            rem = getattr(self, "_stream_tts_buffer", "").strip()
            self._stream_tts_buffer = ""
            if rem:
                self.ui.set_state("SPEAKING")
                self._tts_queue.put((rem, lambda: self.signals.processing_done.emit()))
            else:
                # If everything was streamed, trigger done when queue empties
                self._tts_queue.put(("", lambda: self.signals.processing_done.emit()))
        else:
            self._done()

    # ── TTS Worker ──────────────────────────────────────────────────

    def _tts_worker_loop(self):
        from modules.tts import speak, clear_interrupt, _interrupted
        while True:
            if _interrupted.is_set():
                drained = False
                while True:
                    try:
                        item = self._tts_queue.get_nowait()
                        drained = True
                        if item is None:
                            break
                        _, done_callback = item
                        if done_callback:
                            with contextlib.suppress(Exception):
                                done_callback()
                    except queue.Empty:
                        break
                if drained:
                    continue
                clear_interrupt()
                self._tts_interrupt.clear()
                continue

            item = self._tts_queue.get()
            if item is None:
                break
            text, done_callback = item
            try:
                if text:
                    self._recent_spoken_texts.append(text)
                speak(text)
            except Exception as e:
                logger.error("TTS Worker: %s", e)
            finally:
                self._last_tts_end_time = time.time()
                if done_callback:
                    with contextlib.suppress(Exception):
                        done_callback()

    # ── Lifecycle ──────────────────────────────────────────────────

    def _shutdown(self):
        if self.vad_detector:
            self.vad_detector.stop()
        # Force garbage collection of lingering comtypes/pycaw COM wrappers
        # before the COM apartment is torn down. Without this, comtypes
        # __del__ → Release() calls fail with "COM method call without VTable"
        # during Python interpreter shutdown.
        import gc
        gc.collect()

    def _processing_timeout(self):
        if self._is_processing():
            logger.warning("Processing stuck — resetting state")
            self.ui.write_log("err", "Request timed out — resetting")
            self._done()

    def _reset_watchdog_timer(self):
        if self._is_processing():
            self._processing_timer.start(180000)

    def _interrupt(self):
        from modules.tts import stop
        stop()
        self._tts_interrupt.set()
        self._processing_timer.stop()
        if self.raphael:
            self.raphael.request_interrupt()
        self._set_processing(False)

    def _show_error(self, msg: str):
        self.ui.write_log("err", msg)
        self._done()

    def _done(self):
        self._processing_timer.stop()
        self._set_processing(False)
        if state.muted:
            self.ui.set_state("MUTED")
        elif state.wake_word_required:
            self.ui.set_state("SLEEPING")
        else:
            self.ui.set_state("LISTENING")
            if self.wake_word_required_by_default:
                timeout_ms = getattr(config, "STT_ACTIVE_LISTENING_TIMEOUT", 300) * 1000
                self._active_listening_timer.start(timeout_ms)

    def _active_listening_timeout(self):
        if not self._is_processing() and not state.muted:
            state.wake_word_required = True
            self.ui.set_state("SLEEPING")
            logger.info("Going to sleep... (Wake word required)")

    def _on_reload(self):
        """Reload configuration and restart connections (MCP servers, LLM Client) without removing chat."""
        if self._is_processing():
            logger.warning("Cannot reload while processing a request.")
            return

        logger.info("Reloading configuration and connections...")
        try:
            # 1. Reload settings from settings.toml into config
            from _user_settings import settings_manager
            settings_manager.apply_to_config(config)

            # 2. Reset/Close existing MCP tools and processes
            from orchestrator.tools import reset_mcp_tools, get_tool_schemas
            reset_mcp_tools()

            # 3. Re-initialize MCP manager and schemas
            assert self.raphael is not None
            self.raphael.tool_schemas = get_tool_schemas()

            # 4. Re-initialize LLMClient and ToolExecutor
            from orchestrator.core import LLMClient, ToolExecutor
            self.raphael.llm = LLMClient()
            self.raphael.executor = ToolExecutor()

            # 5. Reinitialize proactive check cooldowns/settings
            self.proactive_engine.set_enabled(config.PROACTIVE_ENABLED)
            self.proactive_engine._cooldown = config.PROACTIVE_COOLDOWN  # type: ignore[attr-defined]
            self.proactive_engine._min_interval = config.PROACTIVE_MIN_INTERVAL  # type: ignore[attr-defined]

            # 6. Reinitialize VAD voice detection if setting changed
            if config.STT_ENABLED:
                if not self.vad_detector:
                    self._start_vad()
            else:
                if self.vad_detector:
                    self.vad_detector.stop()
                    self.vad_detector = None

            logger.info("Reload complete. All servers and configurations restarted successfully.")
        except Exception as e:
            logger.error("System reload failed: %s", e, exc_info=True)

    def _quit(self):
        self.ui.exit_app()
