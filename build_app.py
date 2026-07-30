"""
Build helper script for packaging Raphael into a standalone Windows .exe application.

Usage:
    python build_app.py
"""

import argparse
import os
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


def generate_app_icon() -> Path:
    """Generate high-resolution dark-teal logo assets (icon.ico and icon.png)."""
    assets_dir = ROOT_DIR / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    ico_path = assets_dir / "icon.ico"
    png_path = assets_dir / "icon.png"

    if not ico_path.exists() or not png_path.exists():
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            # Outer dark-slate background circle
            draw.ellipse([10, 10, 246, 246], fill="#0f172a", outline="#1e293b", width=6)
            # Teal glowing ring
            draw.ellipse([50, 50, 206, 206], fill="#14b8a6", outline="#0d9488", width=4)
            # Bright cyan core
            draw.ellipse([90, 90, 166, 166], fill="#5eead4")

            img.save(png_path, "PNG")
            img.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
            print(f"[Build App] Generated icon assets: {ico_path}")
        except Exception as e:
            print(f"[Build App] WARNING: Could not generate icon assets: {e}")

    return ico_path


def create_start_menu_shortcut(target_exe: Path):
    """Create a Windows Start Menu shortcut (.lnk) for instant Start Search registration."""
    try:
        ico_path = generate_app_icon()
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        start_menu.mkdir(parents=True, exist_ok=True)
        shortcut_path = start_menu / "Raphael.lnk"

        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.TargetPath = str(target_exe)
        shortcut.WorkingDirectory = str(target_exe.parent)
        if ico_path.exists():
            shortcut.IconLocation = f"{ico_path},0"
        shortcut.Description = "Raphael Voice-First AI Desktop Assistant"
        shortcut.save()
        print(f"[Build App] Created Windows Start Menu shortcut: {shortcut_path}")
    except Exception as e:
        print(f"[Build App] WARNING: Could not create Start Menu shortcut: {e}")


def install_playwright_browsers() -> Path | None:
    """Download Playwright Chromium and return the path to the browser directory.

    Returns None if the download fails or the package is not available.
    """
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env

        # Download to a staging directory
        staging_dir = ROOT_DIR / "build" / "ms-playwright"
        staging_dir.mkdir(parents=True, exist_ok=True)

        node_exe, cli_js = compute_driver_executable()
        driver_env = get_driver_env()
        env = {**os.environ, **driver_env, "PLAYWRIGHT_BROWSERS_PATH": str(staging_dir)}

        print("[Build App] Downloading Playwright Chromium browser...")
        res = subprocess.run(
            [node_exe, cli_js, "install", "chromium"],
            env=env, capture_output=True, text=True,
        )
        if res.returncode != 0:
            print(f"[Build App] WARNING: Playwright install failed:\n{res.stderr}")
            return None

        # Find the downloaded chromium directory
        chromium_dirs = list(staging_dir.glob("chromium-*"))
        if chromium_dirs:
            print(f"[Build App] Playwright Chromium downloaded: {chromium_dirs[0]}")
            return staging_dir
        return None
    except Exception as e:
        print(f"[Build App] WARNING: Could not install Playwright browsers: {e}")
        return None


def bundle_playwright_browsers(browsers_staging: Path):
    """Copy Playwright browser binaries into the PyInstaller dist bundle."""
    dist_internal = ROOT_DIR / "dist" / "Raphael" / "_internal" / "ms-playwright"
    dist_internal.mkdir(parents=True, exist_ok=True)

    for item in browsers_staging.iterdir():
        dest = dist_internal / item.name
        if item.is_dir():
            import shutil
            shutil.copytree(item, dest, dirs_exist_ok=True)
            print(f"[Build App] Bundled browser: {item.name} ({_dir_size(dest) / 1024 / 1024:.0f} MB)")
        else:
            import shutil
            shutil.copy2(item, dest)


def _dir_size(path: Path) -> int:
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


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
            create_start_menu_shortcut(exe_path)
            print("\n" + "=" * 60)
            print(" BUILD SUCCESSFUL!")
            print(f" Executable: {exe_path}")
            print(" Registered in Windows Start Menu as 'Raphael'")
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
    parser.add_argument("--with-browsers", action="store_true",
                        help="Pre-download Playwright Chromium and bundle it (~500 MB installer)")
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

    # Optionally pre-download Playwright Chromium browser
    browsers_dir = None
    if args.with_browsers:
        browsers_dir = install_playwright_browsers()
    else:
        print("[Build App] Playwright browsers will be downloaded during installation (--install-playwright).")

    if run_pyinstaller_build(clean=args.clean):
        # Bundle browsers into dist AFTER PyInstaller creates the output
        if args.with_browsers and browsers_dir:
            bundle_playwright_browsers(browsers_dir)
        sys.exit(0)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
