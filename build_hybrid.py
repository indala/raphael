"""
Build script for RaphaelHybrid C# project and RaphaelBridge EXE.

Usage:
    python build_hybrid.py           # Build Release
    python build_hybrid.py --debug   # Build Debug
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def find_dotnet() -> str | None:
    """Locate dotnet.exe in common installation paths."""
    try:
        result = subprocess.run(
            ["dotnet", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return "dotnet"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    for base in [
        Path(os.environ.get("ProgramW6432", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    ]:
        dotnet_path = base / "dotnet" / "dotnet.exe"
        if dotnet_path.exists():
            return str(dotnet_path)

    return None


def build(configuration: str = "Release") -> bool:
    """Build the RaphaelHybrid C# project and the RaphaelBridge EXE."""
    hybrid_dir = Path(__file__).resolve().parent / "hybrid"
    csproj_lib = hybrid_dir / "RaphaelHybrid.csproj"
    csproj_bridge = hybrid_dir / "RaphaelBridge" / "RaphaelBridge.csproj"

    dotnet = find_dotnet()
    if dotnet is None:
        print("[Build] ERROR: .NET SDK not found.")
        return False

    try:
        ver = subprocess.run([dotnet, "--version"], capture_output=True, text=True, timeout=10)
        print(f"[Build] .NET SDK version: {ver.stdout.strip()}")
    except Exception:
        pass

    output_dir = hybrid_dir / "bin"
    success = True

    # Build class library
    print("[Build] Building class library...")
    cmd = [dotnet, "build", str(csproj_lib), "-c", configuration, "-o", str(output_dir)]
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        print(f"[Build] Class library FAILED (exit code {result.returncode})")
        success = False
    else:
        lib_dll = output_dir / "RaphaelHybrid.dll"
        print(f"[Build] Class library OK -> {lib_dll}")

    # Build bridge EXE
    if not csproj_bridge.exists():
        print("[Build] Skipping bridge EXE (not found)")
    else:
        bridge_output = output_dir / "Bridge"
        print("[Build] Building bridge EXE...")
        cmd = [dotnet, "build", str(csproj_bridge), "-c", configuration, "-o", str(bridge_output)]
        print(f"  $ {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
            print(f"[Build] Bridge EXE FAILED (exit code {result.returncode})")
            success = False
        else:
            exe_path = bridge_output / "RaphaelBridge.exe"
            print(f"[Build] Bridge EXE OK -> {exe_path}")

    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Raphael C# projects")
    parser.add_argument("--debug", action="store_true", help="Build Debug configuration")
    args = parser.parse_args()

    config = "Debug" if args.debug else "Release"
    success = build(config)
    sys.exit(0 if success else 1)
