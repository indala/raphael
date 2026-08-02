# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

block_cipher = None
project_root = Path.cwd()

# Data files to bundle into .exe directory
datas = []

# Include models.json database
models_json = project_root / "models.json"
if models_json.exists():
    datas.append((str(models_json), "."))

# Include hybrid C# binaries if built
hybrid_bin = project_root / "hybrid" / "bin"
if hybrid_bin.exists():
    datas.append((str(hybrid_bin), "hybrid/bin"))

# Include tools_meta registry
tools_meta = project_root / "tools_meta"
if tools_meta.exists():
    datas.append((str(tools_meta), "tools_meta"))

# Include plugins and knowledge directories
plugins_dir = project_root / "plugins"
if plugins_dir.exists():
    datas.append((str(plugins_dir), "plugins"))

knowledge_dir = project_root / "knowledge"
if knowledge_dir.exists():
    datas.append((str(knowledge_dir), "knowledge"))

# Include providers catalog for endpoint autocomplete
providers_dir = project_root / "providers"
if providers_dir.exists():
    datas.append((str(providers_dir), "providers"))

# ============================================================
# HIDDEN IMPORTS — only what you actually use
# ============================================================
hiddenimports = [
    # ── PyQt6 — CORE ONLY (no QtWebEngine, Qt3D, QtMultimedia, etc.) ──
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",

    # ── Win32 APIs ──
    "win32gui",
    "win32con",
    "win32api",
    "win32process",
    "pywintypes",

    # ── Network & LLM ──
    "httpx",
    "h2",
    "openai",

    # ── Audio & Voice ──
    "edge_tts",
    "sounddevice",
    "miniaudio",

    # ── Data & Charts (matplotlib backend = Qt6Agg only) ──
    "matplotlib",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.figure",
    "numpy",
    "plotly",
    "plotly.graph_objects",

    # ── System & Utilities ──
    "mistune",
    "psutil",
    "pycaw",
    "mss",
    "PIL",
    "pystray",
    "pystray._win32",
    "keyboard",

    # ── Core orchestrator modules ──
    "orchestrator.tools",  # Tool registry (loads native + generated tools)
    "orchestrator.tool_orchestrator",  # Intelligent tool routing
    "orchestrator.tools.native",  # Native tools package
    "orchestrator.tools.generated",  # Generated tools package
    "orchestrator.tools.generated.production",  # Production tools

    # ── Controller, agents, modules ──
    "controller.raphael_controller",
    "controller.state",
    "audio.mic_monitor",
    "modules.tts",
    "modules.tts_engines",
    "modules.tts_registry",
    "modules.tts_backends.sapi5_backend",
    "modules.tts_backends.edge_tts_backend",
    "modules.stt",
    "modules.stt_backends.cloud",
    "modules.stt_backends.whisper_local",
    "modules.stt_backends.isolated",
    "modules.clipboard",
    "modules.hotkeys",
    "modules.notifications",
    "modules.screen",
    "modules.weather",
    "modules.ui_control",
    "modules.chart_gen",
    "modules.music_metadata",

    # ── Agents ──
    "agents.manager_agent",
    "agents.base_agent",
    "agents.tool_manager_agent",
    "agents.executor_agent",
    "agents.analytics_agent",
    "agents.browser_agent",
    "agents.coding_agent",
    "agents.desktop_agent",
    "agents.librarian_agent",
    "agents.researcher_agent",

    # ── Orchestrator subsystems ──
    "orchestrator.orchestrator",
    "orchestrator.startup",
    "orchestrator.task_manager",
    "orchestrator.background",
    "orchestrator.health_check",
    "orchestrator.health_monitor",
    "orchestrator.log_utils",
    "orchestrator.plugin",
    "orchestrator.skill_registry",
    "orchestrator.routines",
    "orchestrator.proactive",
    "orchestrator.event_bus",
    "orchestrator.events",
    "orchestrator.agent_metrics",
    "orchestrator.agent_models",
    "orchestrator.endpoint_registry",
    "orchestrator.dep_check",
    "orchestrator.provider_catalog",
    "orchestrator.memory_agent",
    "orchestrator.mcp.client",
    "orchestrator.mcp.connectors",
    "orchestrator.mcp.mcp_tools",

    # ── Actions & UI ──
    "actions.browser_control",
    "actions.web_fetch",
    "actions.web_search",
    "actions.email_action",
    "actions.file_processor",
    "actions._web_cache",

    # ── Hybrid bridge ──
    "hybrid.bridge",

    # ── Settings system ──
    "ui.settings_dialog",
    "ui.tray_icon",
    "_user_settings.paths",
    "_user_settings.settings_manager",

    # ── STT Backends ──
    "modules.stt_backends.registry",
    "modules.stt_backends.base",

    # ── Optional heavy imports (lazy-loaded) ──
    "faster_whisper",
    "pyttsx3",

    # ── WinRT speech (only if used) ──
    "winrt.windows.media.speechsynthesis",
    "winrt.windows.media.capture",
    "winrt.windows.storage.streams",

    # ── UI system tray / hotkeys ──
    "pystray",
    "pystray._win32",
    "keyboard",
    "pynput",
    "pynput.keyboard",
    "pynput.mouse",

    # ── Utilities ──
    "pyperclip",
    "aiohttp",
    "httpx_sse",
    "pydantic",
    "pytz",
    "dateutil",
    "yaml",
    "toml",
    "tomli",
    "tomli_w",
    "packaging",
    "typing_extensions",
    "dotenv",
    "dotenv.main",
    "psutil._pswindows",

    # ── TTS Registry ──
    "modules.tts_registry",

    # ── Optional heavy features (can be lazy-loaded) ──
    "playwright",
    "playwright.async_api",
    "browser_control",
    "browser_control.smart_browser",
    "browser_control.profile_manager",
    "browser_control.download_manager",
    "browser_control.automation_engine",
    "browser_control.dom_interactor",
    "browser_control.form_filler",
    "browser_control.tab_manager",
    "browser_control.page_analyzer",

    # ── CTranslate2 for faster_whisper ──
    "ctranslate2",
]

# ============================================================
# EXCLUDES — remove packages you don't use
# ============================================================
excludes = [
    # ── PyQt6 modules you DON'T use ──
    "PyQt6.QtMultimedia",
    "PyQt6.QtMultimediaWidgets",
    "PyQt6.QtWebEngine",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtOpenGL",
    "PyQt6.QtOpenGLWidgets",
    "PyQt6.QtSvg",
    "PyQt6.QtSvgWidgets",
    "PyQt6.Qt3DCore",
    "PyQt6.Qt3DRender",
    "PyQt6.Qt3DInput",
    "PyQt6.Qt3DLogic",
    "PyQt6.Qt3DExtras",
    "PyQt6.Qt3DAnimation",
    "PyQt6.QtNfc",
    "PyQt6.QtBluetooth",
    "PyQt6.QtPositioning",
    "PyQt6.QtLocation",
    "PyQt6.QtRemoteObjects",
    "PyQt6.QtSensors",
    "PyQt6.QtSerialPort",
    "PyQt6.QtTest",
    "PyQt6.QtHelp",
    "PyQt6.QtShaderTools",
    "PyQt6.QtQuick",
    "PyQt6.QtQuickWidgets",
    "PyQt6.QtQml",
    "PyQt6.QtQuick3D",
    "PyQt6.QtHttpServer",
    "PyQt6.QtPdf",
    "PyQt6.QtPdfWidgets",
    "PyQt6.QtSpatialAudio",
    "PyQt6.QtTextToSpeech",
    "PyQt6.QtUiTools",

    # ── Other unused packages ──
    "tkinter",
    "tkinter.dialog",
    "tkinter.filedialog",
    "tkinter.font",
    "tkinter.ttk",
    "scipy",
    "IPython",
    "notebook",
    "jupyter",
    "nbformat",
    "nbconvert",
    "pytest",
    "unittest",
    "doctest",
    "xmlrpc",
    "pydoc",
    "lib2to3",
    "pdb",
    "profile",
    "pstats",
    "cProfile",
    "pyautogui",  # NOT USED in codebase

    # ── Matplotlib backends you don't need ──
    "matplotlib.backends.backend_tkagg",
    "matplotlib.backends.backend_gtk3agg",
    "matplotlib.backends.backend_gtk4agg",
    "matplotlib.backends.backend_wxagg",
    "matplotlib.backends.backend_macosx",
    "matplotlib.backends.backend_cairo",

    # ── Plotly submodules you don't use ──
    "plotly.io",
    "plotly.express",
    "plotly.subplots",
    "plotly.figure_factory",
    "plotly.offline",
    "plotly.dashboard_objs",
    "plotly.colors",
    "plotly.data",
    "plotly.express._imshow",
    "plotly.express._core",
    "plotly.express._chart_types",

    # ── Unused scientific packages ──
    "pandas",
    "sklearn",
    "seaborn",
    "sympy",
    "statsmodels",

    # ── Unused network packages ──
    "grpc",
    "grpc._cython",
    "protobuf",
    "google.protobuf",

    # ── Unused web frameworks ──
    "flask",
    "django",
    "fastapi",
    "uvicorn",

    # ── Unused build/test tools ──
    "setuptools",
    "pip",
    "wheel",
    "distutils",
    "pkg_resources",
    "Cython",
    "nose",
    "tox",
    "black",
    "flake8",
    "mypy",
    "ruff",

    # ── Unused GUI toolkits ──
    "wx",
    "gtk",
    "gi",
    "pyglet",
    "pygame",
    "sdl2",
]

# ============================================================
# Analysis configuration
# ============================================================
a = Analysis(
    ['main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filter out unused PyQt6 DLLs from the bin list
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Raphael',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Raphael',
)
