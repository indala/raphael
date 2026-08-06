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
import logging.handlers
import signal
import subprocess
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
        logging.handlers.RotatingFileHandler(
            config.ROAMING_DIR / "logs" / "raphael.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
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


def _install_playwright_browsers() -> int:
    """Download Playwright Chromium browser to the user data directory.

    Uses the bundled Node.js driver that ships with the ``playwright``
    Python package — no system Node.js required.

    Returns the subprocess exit code (0 = success).
    """
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env
    except ImportError:
        print("ERROR: Playwright Python package is not installed.", file=sys.stderr)
        return 1

    browsers_dir = config.ROAMING_DIR / "ms-playwright"
    browsers_dir.mkdir(parents=True, exist_ok=True)

    # Skip download if Chromium is already installed
    existing = list(browsers_dir.glob("chromium-*"))
    if existing:
        print(f"Playwright Chromium already installed at {existing[0]}")
        return 0

    node_exe, cli_js = compute_driver_executable()
    driver_env = get_driver_env()

    env = {**os.environ, **driver_env, "PLAYWRIGHT_BROWSERS_PATH": str(browsers_dir)}

    print(f"Installing Playwright Chromium to {browsers_dir} ...")
    if sys.stdout:
        sys.stdout.flush()

    result = subprocess.run(
        [node_exe, cli_js, "install", "chromium"],
        env=env,
        capture_output=False,
    )
    if result.returncode == 0:
        print("Playwright Chromium installed successfully.")
    else:
        print(f"Playwright install failed (exit code {result.returncode}).", file=sys.stderr)
    return result.returncode


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


def _check_single_instance():
    """Ensure only one instance of Raphael runs at a time.

    Uses Qt's QLocalServer / QLocalSocket IPC. If another instance is already
    running, sends it a "show" signal and returns False so the caller exits.

    A QApplication must already exist before calling this function.
    """
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket

    app = QApplication.instance()
    assert app is not None, "_check_single_instance() requires a running QApplication"

    server_name = "raphael_single_instance"

    # Try to connect to an existing instance
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if socket.waitForConnected(2000):
        # Another instance is running — tell it to show
        socket.write(b"show")
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        return False

    # No existing instance — become the server
    server = QLocalServer()
    server.removeServer(server_name)  # Clean up stale server
    if not server.listen(server_name):
        logger.warning("QLocalServer failed to listen on '%s'; "
                       "single-instance guard disabled.", server_name)
        return True

    def _on_connection():
        while sock := server.nextPendingConnection():
            sock.waitForReadyRead(1000)
            if sock.readAll().data() == b"show":
                _signal_show_window()
            sock.disconnectFromServer()

    server.newConnection.connect(_on_connection)
    # Keep server alive for the app's lifetime
    app._instance_server = server
    return True


def _signal_show_window():
    """Post a custom event to the main window to bring it to front."""
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    # Send a deferred call to find and activate the main window
    for widget in app.topLevelWidgets():
        if hasattr(widget, "show_and_activate"):
            widget.show_and_activate()
            break


def main():
    """Entry point — launches PyQt6 HUD or MCP server mode."""
    if "--install-playwright" in sys.argv:
        sys.exit(_install_playwright_browsers())

    if "--mcp" in sys.argv:
        from raphael_mcp_server import mcp
        mcp.run()
        return

    # Create the application early so _check_single_instance() and
    # RaphaelUI share the same QApplication instance.
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    # Single-instance guard — exit if Raphael is already running
    if not _check_single_instance():
        sys.exit(0)

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
        try:
            logger.info("[Startup] Running deferred heavy initialization...")
            ui.update_splash(40, "Loading cognitive neural modules...")

            # Defer importing controller to avoid blocking startup with heavy dependencies (sounddevice, winrt, openai)
            from controller.raphael_controller import RaphaelController

            ui.update_splash(60, "Initializing system controller...")
            controller = RaphaelController(ui)

            # ── Start Cron Scheduler ──
            if config.CRON_ENABLED:
                try:
                    from cron.scheduler import start_ticker_thread
                    start_ticker_thread(
                        interval=config.CRON_TICK_INTERVAL,
                        verbose=config.CRON_VERBOSE_LOGGING,
                    )
                    logger.info("Cron scheduler started (interval: %ds)", config.CRON_TICK_INTERVAL)
                except Exception as e:
                    logger.error("Failed to start cron scheduler: %s", e)

            def _cleanup():
                if controller and controller.vad_detector:
                    controller.vad_detector.stop()
                
                # ── Stop Cron Scheduler ──
                if config.CRON_ENABLED:
                    try:
                        from cron.scheduler import stop_ticker_thread
                        stop_ticker_thread(timeout=3.0)
                        logger.info("Cron scheduler stopped")
                    except Exception as e:
                        logger.debug("Error stopping cron scheduler: %s", e)

            atexit.register(_cleanup)
            logger.info("[Startup] Deferred initialization complete.")
        except Exception as exc:
            logger.exception("[Startup] Deferred initialization FAILED: %s", exc)
            ui.update_splash(0, f"Startup failed: {exc}")

        # Check for updates in background (only in GUI mode)
        def _on_update_found(release):
            try:
                from PyQt6.QtWidgets import QMessageBox  # noqa: F811
                msg = QMessageBox(ui)
                msg.setWindowTitle("Update Available")
                msg.setText(
                    f"Raphael {release.tag_name} is available!\n"
                    f"(Current version: v{config.VERSION})\n\n"
                    f"{release.body.strip()[:300]}"
                )
                msg.setInformativeText("Download and install the update?")
                msg.setStandardButtons(
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                )
                msg.setDefaultButton(QMessageBox.StandardButton.Yes)
                if msg.exec() == QMessageBox.StandardButton.Yes:
                    ui.update_splash(80, "Downloading update...")
                    from orchestrator.updater import download_installer, apply_update
                    installer = download_installer(release)
                    if installer:
                        apply_update(installer)
            except Exception as exc:
                logger.warning("Update dialog failed: %s", exc)

        from orchestrator.updater import _check_in_background
        _check_in_background(_on_update_found)

    # Schedule deferred initialization 50ms after the event loop starts
    QTimer.singleShot(50, deferred_init)

    signal.signal(signal.SIGINT, lambda s, f: ui.exit_app())
    ui.mainloop()


if __name__ == "__main__":
    main()
