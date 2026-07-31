"""
RaphaelController — bridges VAD voice thread, LLM orchestrator, and PyQt6 HUD.

Extracted from main.py for testability and clean separation of concerns.
"""

import logging
import os
import queue
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QTimer, QObject, pyqtSignal

import config
from audio.mic_monitor import MicLevelMonitor
from controller.state import state
from orchestrator.proactive import ProactiveEngine
from orchestrator.startup import StartupManager
import contextlib

logger = logging.getLogger(__name__)

# ── Physical speaker detection ──────────────────────────────────

def detect_physical_speaker() -> bool:
    """Check if any physical speaker/headphone is actually connected.

    Returns True if a physical audio output device appears connected,
    False if all physical jacks are unplugged.

    Uses pycaw (Windows Core Audio) to check device states.
    Falls back to manual HAS_SPEAKER env var if set.
    """
    # Manual override
    manual = getattr(config, "HAS_SPEAKER", None)
    if manual is None:
        manual = os.getenv("HAS_SPEAKER", "")
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
        self.ui = ui
        self.raphael = None  # built in background thread — see _build_orchestrator
        self.vad_detector = None
        self._processing = False
        self._processing_lock = threading.Lock()
        self._bg_response_queue: queue.Queue = queue.Queue()
        self._current_file = ""
        self._last_tts_end_time = time.time()
        self._processing_timer = QTimer(self)
        self._processing_timer.setSingleShot(True)
        self._processing_timer.timeout.connect(self._processing_timeout)

        # ── Active Listening & Sleep State ──
        self.wake_word_required_by_default = state.wake_word_required
        self._active_listening_timer = QTimer(self)
        self._active_listening_timer.setSingleShot(True)
        self._active_listening_timer.timeout.connect(self._active_listening_timeout)

        # ── Idle-time Memory Consolidation ──
        self._last_interaction_time = time.time()
        self._consolidation_triggered = False

        # ── Proactive Engine (idle check-ins) ──
        self.proactive_engine = ProactiveEngine(
            submit_cb=self._submit_proactive,
            get_idle_time_cb=lambda: time.time() - self._last_interaction_time,
            cooldown=config.PROACTIVE_COOLDOWN,
            min_interval=config.PROACTIVE_MIN_INTERVAL,
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

        # TTS Queue Worker (serializes all TTS to prevent thread explosion)
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

    def _init_phase2(self):
        """Audio system state — COM bridge calls that may block briefly."""
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

        # ── Start live mic level monitor ──
        def _on_mic_level(level: float) -> None:
            setattr(state, "mic_level", level)
            self.ui.set_mic_level(level)

        self._mic_monitor = MicLevelMonitor(callback=_on_mic_level)
        if not self._mic_monitor.start():
            logger.info("Mic level monitor not available (no mic or permission)")
            state.audio_input_available = False
            self.ui.set_audio_input_available(False)

        # Initialize button states
        self.ui.set_muted(state.muted)
        self.ui.set_tts_enabled(state.tts_enabled)

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
            self.tray_icon.exit_requested.connect(self.ui.exit_app)
            self.tray_icon.show()
        except Exception as e:
            logger.warning("Failed to initialize system tray icon: %s", e)

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

    # ── Processing state ─────────────────────────────────────────

    def _is_processing(self) -> bool:
        """Check if currently processing a request."""
        return self._processing

    def _set_processing(self, value: bool) -> None:
        """Set the processing state."""
        self._processing = value
        self.signals.processing_state_changed.emit(value)

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

        self._set_processing(True)
        if state.tts_enabled:
            self.ui.set_state("SPEAKING")
            self._tts_queue.put((text, lambda: self.signals.processing_done.emit()))
        else:
            self._done()

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
        self.ui.set_muted(True)
        self.ui.set_state("MUTED")
        self.ui.write_log("sys", "Microphone off.")
        if state.tts_enabled:
            self._tts_queue.put(("Microphone off.", None))

    def _unmute(self):
        state.muted = False
        self.ui.set_muted(False)
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
        self.ui.set_tts_enabled(new_val)
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

            def handle_state_change(new_state):
                if state.wake_word_required and new_state in ("LISTENING", "IDLE"):
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

            if self.wake_word_required_by_default:
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
        self.ui.set_state("CHAT")
        logger.info("Chat-only mode active")

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

        # Proactive check during idle time
        if not state.muted and not state.wake_word_required:
            self.proactive_engine.check()

        if not self.vad_detector or not state.audio_input_available:
            return

        try:
            transcription = self.vad_detector.transcript_queue.get_nowait()
        except queue.Empty:
            return

        if not transcription:
            return

        text_lower = transcription.lower().strip()

        # Wake word detection
        extended_wake_words = list(getattr(config, "STT_WAKE_WORDS", []))
        for w in ["voice access wake up", "unmute", "wake up"]:
            if w not in extended_wake_words:
                extended_wake_words.append(w)

        if text_lower in extended_wake_words:
            self.ui.set_state("LISTENING")
            self.ui.write_log("ai", "Raphael is here.")
            if state.tts_enabled:
                self.ui.set_state("SPEAKING")
                self._tts_queue.put(("Raphael is here.", None))
            self._done()
            return

        self._submit_message(transcription)

    # ── Memory consolidation ────────────────────────────────────────

    def _run_idle_consolidation(self):
        if not self.raphael:
            return
        try:
            from orchestrator.memory_agent import consolidate_memory
            history_copy = list(self.raphael.history)
            consolidate_memory(history_copy)
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
            self.ui.set_muted(True)
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

        # Process through LLM
        self.ui.set_state("THINKING")
        logger.info("Thinking...")
        threading.Thread(target=self._process_llm, args=(text, self._current_file), daemon=True).start()

    def _submit_proactive(self, instruction: str):
        """Submit a proactive check-in to the LLM (read-only, no tools)."""
        if self._is_processing() or state.muted or not self.raphael:
            self.proactive_engine.on_check_complete()
            return

        def _run():
            try:
                assert self.raphael is not None
                self._set_processing(True)
                response = self.raphael.process_message(instruction)
                self.proactive_engine.on_check_complete()
                if response and response.strip().lower() != "__noop__":
                    if state.tts_enabled and not state.muted:
                        from modules.tts import speak
                        speak(response)
                    self.ui.write_log("ai", f"[Proactive] {response}")
                self._set_processing(False)
            except Exception as e:
                logger.debug("Proactive check failed: %s", e)
                self.proactive_engine.on_check_complete()
                self._set_processing(False)

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
        if hasattr(self, "_mic_monitor"):
            self._mic_monitor.stop()
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
            self.ui.set_muted(True)
        elif state.wake_word_required:
            self.ui.set_state("SLEEPING")
        else:
            self.ui.set_state("LISTENING")
            if self.wake_word_required_by_default:
                timeout_ms = getattr(config, "STT_ACTIVE_LISTENING_TIMEOUT", 8) * 1000
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
