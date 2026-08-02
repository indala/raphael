"""
Build helper script for packaging Raphael into a standalone Windows .exe application.

Usage:
    python build_app.py
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def run_hybrid_build():
    """Build C# hybrid binaries if build_hybrid.py exists."""
    hybrid_script = ROOT_DIR / "build_hybrid.py"
    if hybrid_script.exists():
        print("[Build App] Building C# hybrid bridge...")
        try:
            res = subprocess.run([sys.executable, str(hybrid_script)], capture_output=True, text=True)
            print(res.stdout)
            if res.returncode != 0:
                print(f"[Build App] WARNING: C# build warning: {res.stderr}")
        except Exception as e:
            print(f"[Build App] WARNING: Skipping C# build: {e}")


def check_pyinstaller():
    """Verify PyInstaller is installed in the current Python environment."""
    try:
        import PyInstaller
        print(f"[Build App] PyInstaller version: {PyInstaller.__version__}")
        return True
    except ImportError:
        print("[Build App] ERROR: PyInstaller is not installed.")
        print("[Build App] Please run: pip install pyinstaller")
        return False


def run_pyinstaller_build(clean: bool = False):
    """Execute PyInstaller build with raphael.spec."""
    spec_path = ROOT_DIR / "raphael.spec"
    if not spec_path.exists():
        print("[Build App] ERROR: raphael.spec not found.")
        return False

    print(f"[Build App] Running PyInstaller build using {spec_path.name}...")
    cmd = [sys.executable, "-m", "PyInstaller", str(spec_path), "--noconfirm"]
    if clean:
        cmd.append("--clean")

    try:
        res = subprocess.run(cmd, text=True)
        if res.returncode == 0:
            exe_path = ROOT_DIR / "dist" / "Raphael" / "Raphael.exe"
            print("\n" + "=" * 60)
            print(" BUILD SUCCESSFUL!")
            print(f" Executable: {exe_path}")
            print(" Run 'iscc raphael.iss' to create the installer")
            print("=" * 60 + "\n")
            return True
        else:
            print(f"[Build App] PyInstaller exited with code {res.returncode}")
            return False
    except Exception as e:
        print(f"[Build App] ERROR during PyInstaller build: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Build helper script for Raphael standalone Windows app.")
    parser.add_argument("--clean", action="store_true", help="Force clean PyInstaller build (wipes cache)")
    parser.add_argument("--skip-hybrid", action="store_true", help="Skip compiling the C# hybrid binaries")
    args = parser.parse_args()

    print("=" * 60)
    print(" Starting Raphael Standalone Executable Build")
    print("=" * 60)

    if not check_pyinstaller():
        sys.exit(1)

    if not args.skip_hybrid:
        run_hybrid_build()
    else:
        print("[Build App] Skipping C# hybrid build as requested.")

    if run_pyinstaller_build(clean=args.clean):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
