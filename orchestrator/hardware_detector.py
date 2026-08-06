"""
Hardware Detector — auto-detect GPU/CPU/RAM and recommend the best local
inference engine and model for first-run setup.

Pattern from OpenJarvis (core/config.py recommend_engine / recommend_model).

Supports:
  - NVIDIA (CUDA) — vllm if server-grade, ollama otherwise
  - AMD (ROCm) — ollama
  - Apple Silicon (MPS) — mlx preferred, ollama fallback
  - CPU-only — ollama with quantized models

Tier table maps available RAM → recommended model size so the user
never downloads a model too large to run.

Usage::
    from orchestrator.hardware_detector import detect, recommend

    hw = detect()
    print(hw)          # HardwareInfo(gpu_vendor='nvidia', vram_gb=8, ram_gb=32)

    engine, model = recommend(hw)
    print(engine, model)   # 'ollama', 'qwen2.5:7b'
"""

from __future__ import annotations

import logging
import platform
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class HardwareInfo:
    """Detected hardware profile."""

    # GPU
    gpu_vendor: str = "unknown"          # 'nvidia', 'amd', 'apple', 'none'
    gpu_name: str = ""
    vram_gb: float = 0.0

    # CPU / system
    cpu_name: str = ""
    ram_gb: float = 0.0
    cpu_cores: int = 0
    os: str = ""                          # 'windows', 'linux', 'macos'
    arch: str = ""                        # 'x86_64', 'arm64'

    # Capabilities
    has_cuda: bool = False
    has_rocm: bool = False
    has_mps: bool = False                 # Apple Silicon

    # Derived tier (set by recommend())
    tier: str = ""                        # 'high', 'mid', 'low', 'cpu'

    def summary(self) -> str:
        parts = []
        if self.gpu_vendor != "none" and self.gpu_vendor != "unknown":
            parts.append(f"{self.gpu_vendor.upper()} {self.gpu_name} {self.vram_gb:.0f}GB VRAM")
        parts.append(f"{self.ram_gb:.0f}GB RAM")
        parts.append(f"{self.cpu_cores} cores")
        parts.append(self.os)
        return " | ".join(parts)


# ── Engine recommendation tier table ─────────────────────────────────────────
# (min_vram_gb, gpu_vendor_match, recommended_engine)
# Evaluated top-to-bottom; first match wins.
_ENGINE_RULES: list[tuple] = [
    # Apple Silicon → mlx is fastest for local inference
    (0,   "apple",  "mlx"),
    # NVIDIA high-end (≥ 24 GB) → vllm for throughput
    (24,  "nvidia", "vllm"),
    # NVIDIA mid-range → ollama
    (4,   "nvidia", "ollama"),
    # AMD with ROCm → ollama
    (4,   "amd",    "ollama"),
    # Anything else → ollama (CPU or small GPU)
    (0,   "*",      "ollama"),
]

# Model tier table: (min_vram_gb OR min_ram_gb for cpu, recommended_model)
# Used when engine == 'ollama' or 'mlx' or 'vllm'.
_MODEL_TIERS: list[tuple[float, str]] = [
    (80,  "qwen2.5:72b"),
    (48,  "qwen2.5:32b"),
    (24,  "qwen2.5:14b"),
    (12,  "qwen2.5:7b"),
    (6,   "qwen2.5:3b"),
    (4,   "qwen2.5:1.5b"),
    (0,   "qwen2.5:0.5b"),
]

_MLX_MODEL_TIERS: list[tuple[float, str]] = [
    (64,  "mlx-community/Qwen2.5-72B-Instruct-4bit"),
    (32,  "mlx-community/Qwen2.5-32B-Instruct-4bit"),
    (16,  "mlx-community/Qwen2.5-14B-Instruct-4bit"),
    (8,   "mlx-community/Qwen2.5-7B-Instruct-4bit"),
    (4,   "mlx-community/Qwen2.5-3B-Instruct-4bit"),
    (0,   "mlx-community/Qwen2.5-1.5B-Instruct-4bit"),
]


# ── Detection helpers ─────────────────────────────────────────────────────────

def _safe_run(cmd: list[str]) -> str:
    """Run a subprocess, return stdout or empty string on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5, check=False
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _detect_nvidia() -> tuple[str, float]:
    """Return (gpu_name, vram_gb) for the first NVIDIA GPU, or ('', 0)."""
    out = _safe_run([
        "nvidia-smi",
        "--query-gpu=name,memory.total",
        "--format=csv,noheader,nounits",
    ])
    if not out:
        return "", 0.0
    line = out.splitlines()[0]
    parts = [p.strip() for p in line.split(",")]
    if len(parts) >= 2:
        try:
            vram_mb = float(parts[1])
            return parts[0], vram_mb / 1024.0
        except ValueError:
            return parts[0], 0.0
    return "", 0.0


def _detect_amd() -> tuple[str, float]:
    """Return (gpu_name, vram_gb) for AMD GPU via rocm-smi, or ('', 0)."""
    out = _safe_run(["rocm-smi", "--showmeminfo", "vram", "--csv"])
    if not out:
        return "", 0.0
    # rocm-smi output varies — try a simple heuristic
    for line in out.splitlines():
        if "GPU" in line.upper() and "MiB" in line:
            try:
                nums = [float(p) for p in line.split() if p.replace(".", "").isdigit()]
                if nums:
                    return "AMD GPU", nums[0] / 1024.0
            except ValueError:
                pass
    return "AMD GPU", 0.0


def _detect_apple_silicon() -> bool:
    """Return True if running on Apple Silicon (M-series)."""
    if platform.system() != "Darwin":
        return False
    arch = platform.machine()
    return arch == "arm64"


def _get_total_ram_gb() -> float:
    """Return total system RAM in GB."""
    try:
        import psutil  # type: ignore[import]
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        pass

    # Fallback: platform-specific
    if platform.system() == "Windows":
        out = _safe_run(["wmic", "computersystem", "get", "TotalPhysicalMemory"])
        for line in out.splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line) / (1024 ** 3)
    elif platform.system() == "Linux":
        out = _safe_run(["grep", "MemTotal", "/proc/meminfo"])
        if out:
            try:
                kb = int(out.split()[1])
                return kb / (1024 ** 2)
            except (IndexError, ValueError):
                pass
    elif platform.system() == "Darwin":
        out = _safe_run(["sysctl", "-n", "hw.memsize"])
        if out:
            try:
                return int(out) / (1024 ** 3)
            except ValueError:
                pass
    return 8.0  # conservative fallback


def _get_cpu_info() -> tuple[str, int]:
    """Return (cpu_name, core_count)."""
    cores = 0
    name = ""
    try:
        import psutil  # type: ignore[import]
        cores = psutil.cpu_count(logical=False) or 0
    except Exception:
        import os
        cores = os.cpu_count() or 0

    if platform.system() == "Windows":
        name = _safe_run(["wmic", "cpu", "get", "Name"]).splitlines()[-1].strip() if _safe_run(["wmic", "cpu", "get", "Name"]) else ""
    elif platform.system() in ("Linux", "Darwin"):
        out = _safe_run(["grep", "-m1", "model name", "/proc/cpuinfo"])
        if out:
            name = out.split(":")[-1].strip()

    return name, cores


# ── Public API ────────────────────────────────────────────────────────────────

def detect() -> HardwareInfo:
    """Detect hardware and return a HardwareInfo dataclass.

    Probes GPU (NVIDIA → nvidia-smi, AMD → rocm-smi, Apple → arch check),
    total RAM, CPU name and core count. All probes are isolated — one
    failure never prevents the rest from running.
    """
    hw = HardwareInfo()
    hw.os = platform.system().lower()
    hw.arch = platform.machine().lower()

    # ── GPU detection ────────────────────────────────────────────
    # NVIDIA
    gpu_name, vram = _detect_nvidia()
    if gpu_name:
        hw.gpu_vendor = "nvidia"
        hw.gpu_name = gpu_name
        hw.vram_gb = vram
        hw.has_cuda = True
    # AMD (only if no NVIDIA found)
    elif not hw.gpu_name:
        amd_name, amd_vram = _detect_amd()
        if amd_name:
            hw.gpu_vendor = "amd"
            hw.gpu_name = amd_name
            hw.vram_gb = amd_vram
            hw.has_rocm = True
    # Apple Silicon
    if _detect_apple_silicon():
        hw.gpu_vendor = "apple"
        hw.gpu_name = "Apple Silicon"
        hw.has_mps = True
        # Unified memory: RAM = effective VRAM
        # vram_gb will be set from RAM below

    # ── System RAM ───────────────────────────────────────────────
    hw.ram_gb = _get_total_ram_gb()

    # Apple: unified memory = VRAM
    if hw.gpu_vendor == "apple":
        hw.vram_gb = hw.ram_gb

    # ── CPU ──────────────────────────────────────────────────────
    hw.cpu_name, hw.cpu_cores = _get_cpu_info()

    # ── No GPU fallback ──────────────────────────────────────────
    if hw.gpu_vendor == "unknown":
        hw.gpu_vendor = "none"

    logger.info("Hardware detected: %s", hw.summary())
    return hw


def recommend(hw: HardwareInfo) -> tuple[str, str]:
    """Recommend (engine, model) based on detected hardware.

    Returns:
        (engine_name, model_name) — e.g. ('ollama', 'qwen2.5:7b')
        Both strings are ready to insert into settings.toml.
    """
    # ── Engine selection ─────────────────────────────────────────
    engine = "ollama"  # safe default
    for min_vram, vendor_match, recommended in _ENGINE_RULES:
        if vendor_match != "*" and hw.gpu_vendor != vendor_match:
            continue
        if hw.vram_gb >= min_vram:
            engine = recommended
            break

    # ── Model selection ──────────────────────────────────────────
    # Use VRAM as the budget (GPU inference).
    # CPU-only: use RAM / 6 as rough model size budget (4-bit quant rule of thumb).
    if hw.gpu_vendor == "none":
        budget_gb = hw.ram_gb / 6.0
        tier_table = _MODEL_TIERS
    elif engine == "mlx":
        budget_gb = hw.vram_gb
        tier_table = _MLX_MODEL_TIERS
    else:
        budget_gb = hw.vram_gb
        tier_table = _MODEL_TIERS

    model = tier_table[-1][1]  # smallest fallback
    for min_gb, mdl in tier_table:
        if budget_gb >= min_gb:
            model = mdl
            break

    # ── Tier label ───────────────────────────────────────────────
    if hw.vram_gb >= 24 or hw.ram_gb >= 64:
        hw.tier = "high"
    elif hw.vram_gb >= 8 or hw.ram_gb >= 16:
        hw.tier = "mid"
    elif hw.vram_gb >= 4 or hw.ram_gb >= 8:
        hw.tier = "low"
    else:
        hw.tier = "cpu"

    logger.info(
        "Hardware recommendation: engine=%s model=%s (tier=%s, budget=%.1f GB)",
        engine, model, hw.tier, budget_gb,
    )
    return engine, model


def recommend_first_run() -> dict:
    """Full first-run recommendation: detect hardware and suggest endpoint config.

    Returns a dict ready to display in the setup wizard or log at startup::

        {
          "engine":  "ollama",
          "model":   "qwen2.5:7b",
          "base_url": "http://localhost:11434/v1",
          "tier":    "mid",
          "summary": "NVIDIA RTX 3070 8GB VRAM | 32GB RAM | ...",
          "message": "Recommended: ollama with qwen2.5:7b ..."
        }
    """
    hw = detect()
    engine, model = recommend(hw)

    base_url_map = {
        "ollama": "http://localhost:11434/v1",
        "vllm":   "http://localhost:8000/v1",
        "mlx":    "http://localhost:8080/v1",
    }
    base_url = base_url_map.get(engine, "http://localhost:11434/v1")

    message = (
        f"Detected: {hw.summary()}\n"
        f"Recommended engine: {engine}\n"
        f"Recommended model:  {model}\n"
        f"Endpoint URL:       {base_url}\n\n"
        f"To use this, add to ~/.raphael/settings.toml:\n\n"
        f"[[endpoints]]\n"
        f'name       = "{engine}-local"\n'
        f'base_url   = "{base_url}"\n'
        f'text_model = "{model}"\n'
    )

    return {
        "engine": engine,
        "model": model,
        "base_url": base_url,
        "tier": hw.tier,
        "summary": hw.summary(),
        "message": message,
        "hardware": hw,
    }
