"""
Raphael — AI Desktop Assistant for Windows
Voice-first with PyQt6 animated HUD interface.
"""

import os
# Suppress Qt's DPI awareness warning which occurs because the C# bridge handles native window contexts first
os.environ["QT_LOGGING_RULES"] = "qt.qpa.window=false"

import atexit
import io
import logging
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from _user_settings.settings_manager import apply_to_config as _apply_settings
_apply_settings(config)
from controller.state import state

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.ROAMING_DIR / "logs" / "raphael.log", mode="a", encoding="utf-8"),
    ],
)

# Inject request-ID filter into root logger for all loggers
from orchestrator.log_utils import RequestIDFilter
import contextlib
for handler in logging.getLogger().handlers:
    handler.addFilter(RequestIDFilter())

if sys.stdout is not None and getattr(sys.stdout, "encoding", None) is not None:
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logger = logging.getLogger(__name__)


def validate_config():
    """Check config values at startup — exit with clear errors on failure."""
    import os
    errors = []

    # Validate that the LLM backend exists in the endpoint registry
    from orchestrator.endpoint_registry import get as _get_ep
    if not _get_ep(config.LLM_BACKEND):
        # Attempt to load endpoints if registry hasn't been seeded
        from orchestrator.endpoint_registry import load as _load_eps
        with contextlib.suppress(Exception):
            _load_eps()
        if not _get_ep(config.LLM_BACKEND):
            errors.append(
                f"LLM_BACKEND='{config.LLM_BACKEND}' has no matching [endpoints] entry "
                f"in settings.toml. Add an [[endpoints]] section with name='{config.LLM_BACKEND}'."
            )

    tts_supported = ["edge-tts"]
    if config.TTS_BACKEND not in tts_supported:
        errors.append(f"TTS_BACKEND='{config.TTS_BACKEND}' not in {tts_supported}")

    for attr, label in [("SCREENSHOT_DIR", "Screenshot dir"), ("CHART_DIR", "Chart dir")]:
        path = getattr(config, attr, None)
        if path and not os.path.isdir(path):
            errors.append(f"{label} '{path}' does not exist")

    if errors:
        for e in errors:
            logger.error("Config validation: %s", e)
        sys.exit(1)


def main():
    """Entry point — launches PyQt6 HUD or MCP server mode."""
    if "--mcp" in sys.argv:
        from raphael_mcp_server import mcp
        mcp.run()
        return

    # Check if settings.toml exists and has at least one endpoint configured
    from _user_settings.settings_manager import settings_path
    from orchestrator.endpoint_registry import all as _all_eps
    from orchestrator.endpoint_registry import load as _load_eps
    
    path = settings_path()
    has_endpoints = False
    if path.exists():
        try:
            _load_eps()
            if _all_eps():
                has_endpoints = True
        except Exception:
            pass

    if not has_endpoints:
        if "--mcp" in sys.argv:
            logger.error(
                "No LLM endpoints are configured in settings.toml.\n"
                "Please run the desktop application to configure your endpoints or add "
                "[[endpoints]] sections to ~/.raphael/settings.toml."
            )
            sys.exit(1)
        else:
            try:
                from PyQt6.QtWidgets import QApplication, QMessageBox
                from ui.settings_dialog import SettingsDialog
                
                # Start temporary QApplication to show dialogs
                app = QApplication.instance() or QApplication(sys.argv)
                if hasattr(app, "setStyle"):
                    app.setStyle("Fusion")
                
                QMessageBox.information(
                    None,
                    "Raphael — Configuration Required",
                    "No LLM endpoints are configured in your settings.\n\n"
                    "The Settings panel will now open so you can add and configure your LLM backends."
                )
                
                dlg = SettingsDialog(None)
                res = dlg.exec()
                if res != 1:  # Not saved (Cancelled/Closed)
                    logger.info("Configuration cancelled by user. Exiting.")
                    sys.exit(0)
                
                # Verify that they actually saved at least one endpoint
                _load_eps()
                if not _all_eps():
                    QMessageBox.warning(
                        None,
                        "Raphael — Configuration Incomplete",
                        "You must configure at least one LLM endpoint to use Raphael. Exiting."
                    )
                    sys.exit(0)
                
                # Apply newly saved settings to config module
                from _user_settings.settings_manager import apply_to_config as _apply_settings
                _apply_settings(config)
            except Exception as exc:
                logger.error("Failed to show initial settings dialog: %s", exc)
                sys.exit(1)

    # Import UI and start it first to show the splash screen immediately
    from ui.raphael_ui import RaphaelUI
    from PyQt6.QtCore import QTimer

    ui = RaphaelUI()
    ui.update_splash(10, "Validating configuration...")

    validate_config()

    ui.update_splash(20, "Loading plugins and extensions...")
    from orchestrator.plugin import discover_and_register, startup as plugin_startup
    discover_and_register()
    plugin_startup()

    # Dependency checks in background — run only when --dev flag is provided
    if "--dev" in sys.argv:
        ui.update_splash(30, "Checking dependencies...")
        threading.Thread(
            target=lambda: __import__("orchestrator.dep_check", fromlist=["check_dependencies"]).check_dependencies(),
            daemon=True,
            name="dep-check",
        ).start()

    logger.info("Raphael — Voice-first AI Desktop Assistant")
    logger.info("Backend: %s  |  TTS: %s", config.LLM_BACKEND, 'ON' if state.tts_enabled else 'OFF')

    controller = None

    def deferred_init():
        nonlocal controller
        logger.info("[Startup] Running deferred heavy initialization...")
        ui.update_splash(40, "Loading cognitive neural modules...")

        # Defer importing controller to avoid blocking startup with heavy dependencies (sounddevice, winrt, openai)
        from controller.raphael_controller import RaphaelController

        ui.update_splash(60, "Initializing system controller...")
        controller = RaphaelController(ui)

        def _cleanup():
            if controller and controller.vad_detector:
                controller.vad_detector.stop()

        atexit.register(_cleanup)
        logger.info("[Startup] Deferred initialization complete.")

    # Schedule deferred initialization 50ms after the event loop starts
    QTimer.singleShot(50, deferred_init)

    signal.signal(signal.SIGINT, lambda s, f: ui.exit_app())
    ui.mainloop()


if __name__ == "__main__":
    main()
