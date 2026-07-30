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

# Explicit hidden imports for dynamic/lazy modules
hiddenimports = [
    # Qt6 Modules
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    # Win32 APIs
    "win32gui",
    "win32con",
    "win32api",
    "win32process",
    "pywintypes",
    # Network & LLM
    "httpx",
    "h2",
    "requests",
    "openai",
    # Audio & Voice
    "edge_tts",
    "sounddevice",
    "miniaudio",
    "faster_whisper",
    # Data & UI
    "matplotlib",
    "plotly",
    "numpy",
    "mistune",
    "psutil",
    "pycaw",
    "pyautogui",
    "mss",
    "PIL",
    # Internal native tool modules
    "orchestrator.tools.native.memory",
    "orchestrator.tools.native.clipboard",
    "orchestrator.tools.native.system",
    "orchestrator.tools.native.tts",
    "orchestrator.tools.native.chart",
    "orchestrator.tools.native.web",
    "orchestrator.tools.native.files",
    "orchestrator.tools.native.browser",
    "orchestrator.tools.native.ui",
    "orchestrator.tools.native.screen",
    "orchestrator.tools.native.weather",
    "orchestrator.tools.native.background_tools",
    "orchestrator.tools.native.knowledge",
    "orchestrator.tools.native.web_fetch",
    "orchestrator.tools.native.delegation",
    "orchestrator.tools.native.upstox",
    "orchestrator.tools.native.goals",
    "orchestrator.tools.native.music",
    "orchestrator.tools.native.email",
    # STT backends
    "modules.stt_backends.whisper_local",
    "modules.stt_backends.winrt_stt",
]

a = Analysis(
    ['main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'scipy', 'IPython', 'notebook'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

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
    console=False,  # Windowed desktop application (no black terminal window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "assets" / "icon.ico") if (project_root / "assets" / "icon.ico").exists() else None,
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
