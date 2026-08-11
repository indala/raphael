"""
Raphael Browser Control — Playwright multi-browser automation.

Supported browsers (auto-detected on Windows):
  Chrome, Edge, Firefox, Opera, Brave, Vivaldi, Chromium
"""

import contextlib
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright

_OS = platform.system()

logger = logging.getLogger(__name__)

# ── Profile directory (persistent browser contexts) ─────────────────

def _profiles_dir() -> Path:
    """Get or create the profiles directory for persistent browser contexts."""
    if _OS == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".raphael"))
    elif _OS == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "raphael"
    else:
        base = Path.home() / ".config" / "raphael"
    profiles = base / "browser_profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    return profiles


def _real_profile_dir(browser_key: str) -> str:
    """Return a persistent profile directory for the given browser key."""
    p = _profiles_dir() / browser_key
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def _firefox_profile_dir() -> str:
    """Create and return a Firefox-specific persistent profile dir."""
    p = _profiles_dir() / "firefox"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


# ── Browser binary detection (Windows) ──────────────────────────────

def _find_exe_windows(name: str) -> str | None:
    """Search common paths for a browser executable."""
    # Search PATH first
    exe = shutil.which(name)
    if exe:
        return exe

    # Common install locations
    pf = os.environ.get("PROGRAMFILES", "C:\\Program Files")
    pf_x86 = os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")

    paths = [
        os.path.join(pf, name),
        os.path.join(pf_x86, name),
        os.path.join(pf, f"{name}\\{name}.exe"),
        os.path.join(pf_x86, f"{name}\\{name}.exe"),
        os.path.join(local, name, f"{name}.exe"),
        os.path.join(local, "Programs", name, f"{name}.exe"),
    ]

    name_lower = name.lower()
    for p in paths:
        if os.path.isfile(p):
            return p

    # Brute force search in Program Files
    for root in [pf, pf_x86]:
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                if fn.lower() == f"{name_lower}.exe":
                    return os.path.join(dirpath, fn)
            # Limit search depth
            if dirpath.count(os.sep) > 6:
                break
    return None


def _find_opera_windows() -> str | None:
    """Find Opera browser executable."""
    local = os.environ.get("LOCALAPPDATA", "")
    paths = [
        os.path.join(local, "Programs", "Opera", "opera.exe"),
        os.path.join(local, "Programs", "Opera GX", "opera.exe"),
    ]
    for p in paths:
        if os.path.isfile(p):
            return p
    return _find_exe_windows("opera")


# ── Browser specifications ──────────────────────────────────────────

_BROWSER_SPECS: dict = {
    "chrome": {
        "engine": "chromium",
        "paths": {
            "Windows": [
                os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"),
                             "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""),
                             "Google", "Chrome", "Application", "chrome.exe"),
            ],
            "Darwin":  ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
            "Linux":   ["google-chrome", "google-chrome-stable", "chromium-browser"],
        },
        "channel": None,
    },
    "msedge": {
        "engine": "chromium",
        "paths": {
            "Windows": [
                os.path.join(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
                             "Microsoft", "Edge", "Application", "msedge.exe"),
            ],
            "Darwin":  ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
            "Linux":   ["microsoft-edge", "microsoft-edge-stable"],
        },
        "channel": None,
    },
    "firefox": {
        "engine": "firefox",
        "paths": {
            "Windows": [
                os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"),
                             "Mozilla Firefox", "firefox.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
                             "Mozilla Firefox", "firefox.exe"),
            ],
            "Darwin":  ["/Applications/Firefox.app/Contents/MacOS/firefox"],
            "Linux":   ["firefox"],
        },
        "channel": None,
    },
    "opera": {
        "engine": "chromium",
        "paths": {
            "Windows": [],
            "Darwin":  ["/Applications/Opera.app/Contents/MacOS/Opera"],
            "Linux":   ["opera"],
        },
        "channel": "chrome",
    },
    "brave": {
        "engine": "chromium",
        "paths": {
            "Windows": [
                os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"),
                             "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""),
                             "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            ],
            "Darwin":  ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"],
            "Linux":   ["brave-browser", "brave"],
        },
        "channel": None,
    },
    "vivaldi": {
        "engine": "chromium",
        "paths": {
            "Windows": [
                os.path.join(os.environ.get("LOCALAPPDATA", ""),
                             "Vivaldi", "Application", "vivaldi.exe"),
            ],
            "Darwin":  ["/Applications/Vivaldi.app/Contents/MacOS/Vivaldi"],
            "Linux":   ["vivaldi"],
        },
        "channel": None,
    },
    "chromium": {
        "engine": "chromium",
        "paths": {
            "Windows": [],
            "Darwin":  ["/Applications/Chromium.app/Contents/MacOS/Chromium"],
            "Linux":   ["chromium", "chromium-browser"],
        },
        "channel": None,
    },
}


def _get_browser(name: str) -> dict:
    """Get browser info (engine, exe path, channel) by name."""
    name = name.lower()
    # Normalize common aliases
    aliases = {"edge": "msedge", "ie": "msedge", "google": "chrome", "g chrome": "chrome"}
    name = aliases.get(name, name)
    spec = _BROWSER_SPECS.get(name)
    if not spec:
        return {}

    engine = spec["engine"]
    channel = spec.get("channel")
    exe = None

    # Search paths for the current OS
    paths = spec["paths"].get(_OS, [])
    for p in paths:
        if os.path.isfile(p):
            exe = p
            break

    # PATH search for Linux/Mac
    if not exe:
        for p in paths:
            found = shutil.which(p)
            if found:
                exe = found
                break

    # Windows brute force
    if not exe and _OS == "Windows":
        exe = _find_opera_windows() if name == "opera" else _find_exe_windows(name)

    if not exe and _OS == "Windows" and not channel:
        exe = _find_exe_windows(name)

    return {"engine": engine, "exe": exe, "channel": channel}


def _detect_default_browser() -> str:
    """Detect the default web browser on the system."""
    try:
        if _OS == "Windows":
            # Use C# bridge for registry access when available
            prog_id = None
            try:
                from hybrid.bridge import CRegistryHelper as CsReg
                from hybrid.bridge import is_available
                if is_available():
                    prog_id = CsReg.GetDefaultBrowserProgId()
            except ImportError:
                pass

            if not prog_id:
                # Fallback: direct winreg
                import winreg
                k = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\Shell\Associations"
                    r"\UrlAssociations\http\UserChoice",
                )
                prog_id = winreg.QueryValueEx(k, "ProgId")[0].lower()
                winreg.CloseKey(k)

            prog_id = prog_id.lower()
            for kw in ("edge", "firefox", "opera", "brave", "vivaldi", "chrome"):
                if kw in prog_id:
                    return kw
        elif _OS == "Darwin":
            out = subprocess.run(
                ["defaults", "read",
                 "com.apple.LaunchServices/com.apple.launchservices.secure",
                 "LSHandlers"],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "safari", "chrome", "edge"):
                if kw in out:
                    return kw
        elif _OS == "Linux":
            out = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True, text=True, timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "chrome", "edge"):
                if kw in out:
                    return kw
    except Exception:
        pass
    return "chrome"


# ── Browser session ─────────────────────────────────────────────────

class _BrowserSession:
    """Full browser session using Playwright persistent context."""

    def __init__(self, browser_name: str, headless: bool = False, viewport_width: int = 1280, viewport_height: int = 720, user_agent: str | None = None):
        self.browser_name = browser_name
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.user_agent = user_agent
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._pages: list = []
        self.downloads: list[str] = []

    def _setup_page(self, page):
        """Setup event listeners for the page (dialogs, downloads)."""
        # 1. Dialog handling (prevent page lock on JS alerts/confirms)
        page.on("dialog", lambda dialog: dialog.accept())

        # 2. Download handling
        def handle_download(download):
            import tempfile
            download_dir = Path(tempfile.gettempdir()) / "Raphael" / "downloads"
            download_dir.mkdir(exist_ok=True, parents=True)
            dest = download_dir / download.suggested_filename
            download.save_as(dest)
            logger.info("Sandbox downloaded file: %s", dest)
            self.downloads.append(str(dest))

        page.on("download", handle_download)

    def start(self):
        """Launch the browser and create a persistent context."""
        # Check for Playwright browsers bundled inside the PyInstaller package
        if hasattr(sys, "frozen") and hasattr(sys, "_MEIPASS"):
            _bundled_browsers = Path(sys._MEIPASS) / "ms-playwright"
            if _bundled_browsers.is_dir():
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_bundled_browsers)

        # Fall back to user AppData directory (installed via --install-playwright)
        if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
            _default_browsers_dir = (
                Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
                / ".raphael"
                / "ms-playwright"
            )
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_default_browsers_dir)

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright is not installed. Run: pip install playwright && python -m playwright install"
            )

        info = _get_browser(self.browser_name)
        if not info or not info.get("exe"):
            # Fallback: try default browser or Playwright's bundled browser
            info = {
                "engine": "chromium",
                "exe": None,
                "channel": None,
            }

        # Verify Playwright's managed Chromium is installed when no system browser was found
        if not info.get("exe") and not info.get("channel"):
            _check_browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
            if _check_browsers_path:
                _existing = list(Path(_check_browsers_path).glob("chromium-*"))
                if not _existing:
                    # Check default Playwright location as fallback
                    _default_locations = [
                        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ms-playwright",
                        Path.home() / ".cache" / "ms-playwright",
                    ]
                    for _alt in _default_locations:
                        if _alt.is_dir() and list(_alt.glob("chromium-*")):
                            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_alt)
                            logger.info("Found Playwright browsers at default location: %s", _alt)
                            break
                    else:
                        raise RuntimeError(
                            "Playwright Chromium browser is not installed.\n\n"
                            "Run the following command to install it:\n"
                            "    Raphael.exe --install-playwright\n\n"
                            "Or re-run the Raphael installer and make sure the\n"
                            "'Install Playwright browser' step completes."
                        )

        self.playwright = sync_playwright().__enter__()
        engine = info.get("engine", "chromium")
        channel = info.get("channel")
        executable_path = info.get("exe")

        # Launch options
        launch_options = {
            "headless": self.headless,
        }
        if executable_path:
            launch_options["executable_path"] = executable_path

        # Context options
        context_args = {
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
            "accept_downloads": True,
        }
        if self.user_agent:
            context_args["user_agent"] = self.user_agent

        # Try to connect to existing browser, or launch new one
        assert self.playwright is not None
        browser_types = {
            "chromium": self.playwright.chromium,
            "firefox": self.playwright.firefox,
            "webkit": self.playwright.webkit,
        }
        browser_type = browser_types.get(engine, self.playwright.chromium)

        try:
            if engine == "firefox":
                profile_dir = _firefox_profile_dir()
                self.context = browser_type.launch_persistent_context(
                    profile_dir,
                    **{k: v for k, v in launch_options.items() if k != "executable_path"},  # type: ignore[arg-type]
                    **context_args  # type: ignore[arg-type]
                )
            else:
                # Chromium-based with optional channel
                if channel:
                    launch_options["channel"] = channel
                self.browser = browser_type.launch(**launch_options)  # type: ignore[arg-type]
                self.context = self.browser.new_context(**context_args)  # type: ignore[arg-type]
                self.context.set_default_timeout(15000)

            # Get or create a page
            pages = self.context.pages
            if pages:
                self.page = pages[0]
            else:
                self.page = self.context.new_page()

            self._setup_page(self.page)

            logger.info("Started %s session", self.browser_name)
            return True

        except Exception as e:
            logger.error("Failed to start %s: %s", self.browser_name, e)
            self._cleanup()
            raise

    def navigate(self, url: str):
        """Navigate to a URL."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        assert self.page is not None
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)
        return f"Navigated to {url} — title: {self.page.title()}"

    def click(self, selector: str):
        """Click an element by CSS selector."""
        assert self.page is not None
        self.page.click(selector, timeout=10000)
        time.sleep(0.5)
        return f"Clicked: {selector}"

    def fill(self, selector: str, text: str):
        """Fill a form field by CSS selector."""
        assert self.page is not None
        self.page.fill(selector, text)
        return f"Filled {selector} with: {text[:50]}..."

    def screenshot(self, path: str | None = None, full_page: bool = False) -> str:
        """Take a screenshot of the current page."""
        if not path:
            path = os.path.join(tempfile.gettempdir(), f"raphael_screenshot_{int(time.time())}.png")
        else:
            # Ensure destination folder exists
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        assert self.page is not None
        self.page.screenshot(path=path, full_page=full_page)
        return path

    def get_text(self, selector: str = "body") -> str:
        """Get visible text content from page or element."""
        assert self.page is not None
        el = self.page.query_selector(selector)
        if el:
            return el.inner_text()[:3000]  # type: ignore[no-any-return]
        return self.page.inner_text("body")[:3000]  # type: ignore[no-any-return]

    def get_html(self) -> str:
        """Get the page HTML content (truncated)."""
        assert self.page is not None
        return self.page.content()[:5000]  # type: ignore[no-any-return]

    def execute_js(self, script: str) -> str:
        """Execute JavaScript in the page context."""
        assert self.page is not None
        result = self.page.evaluate(script)
        return str(result)[:2000]

    def scroll(self, direction: str = "down", amount: int = 500):
        """Scroll the page."""
        assert self.page is not None
        if direction == "down":
            self.page.evaluate(f"window.scrollBy(0, {amount})")
        else:
            self.page.evaluate(f"window.scrollBy(0, -{amount})")
        time.sleep(0.3)
        return f"Scrolled {direction} by {amount}px"

    def new_tab(self, url: str | None = None):
        """Open a new tab, optionally navigating to a URL."""
        assert self.context is not None
        page = self.context.new_page()
        self._setup_page(page)
        self._pages.append(page)
        self.page = page
        if url:
            assert self.page is not None
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return f"Opened new tab: {url}"
        return "Opened new tab"

    def close_tab(self):
        """Close the current tab."""
        if self.page:
            self.page.close()
        if self._pages:
            self.page = self._pages.pop()
        elif self.context:
            pages = self.context.pages
            self.page = pages[-1] if pages else self.context.new_page()
        else:
            return "No active browser context."
        return "Closed current tab"

    def list_tabs(self) -> str:
        """List all open tabs with index, title, and URL."""
        if not self.context:
            return "No active browser context."
        pages = self.context.pages
        lines = []
        for idx, page in enumerate(pages):
            is_active = "*" if page == self.page else " "
            try:
                title = page.title() or "Untitled"
                url = page.url or "about:blank"
            except Exception:
                title = "Unknown"
                url = "Unknown"
            lines.append(f"{is_active}[{idx}] {title} — {url}")
        return "\n".join(lines) if lines else "No open tabs."

    def switch_tab(self, index: int) -> str:
        """Switch active tab by index."""
        if not self.context:
            return "No active browser context."
        pages = self.context.pages
        if 0 <= index < len(pages):
            self.page = pages[index]
            self.page.bring_to_front()
            return f"Switched to tab [{index}]: {self.page.title()} ({self.page.url})"
        return f"Invalid tab index {index}. Available: 0..{len(pages)-1}"

    def back(self):
        """Navigate back in history."""
        if not self.page:
            return "No active page."
        self.page.go_back()
        return f"Went back to: {self.page.title()}"

    def _cleanup(self):
        """Close browser and clean up resources, saving session state."""
        try:
            if self.context:
                try:
                    state_file = _profiles_dir() / f"{self.browser_name}_state.json"
                    self.context.storage_state(path=str(state_file))
                except Exception:
                    pass
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.__exit__(None, None, None)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None


# ── Session registry ────────────────────────────────────────────────

class _SessionRegistry:
    """Manage multiple browser sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, _BrowserSession] = {}

    def get_or_create(self, browser_name: str | None = None, headless: bool = False, viewport_width: int = 1280, viewport_height: int = 720, user_agent: str | None = None) -> _BrowserSession:
        """Get an existing session or create a new one."""
        if browser_name is None:
            browser_name = _detect_default_browser()

        # Check for matching session
        if self._sessions:
            for name, session in self._sessions.items():
                if name == browser_name and session.page and not session.page.is_closed():
                    return session
            # Return the first alive session
            for _name, session in self._sessions.items():
                if session.page and not session.page.is_closed():
                    return session

        # Create new session
        session = _BrowserSession(
            browser_name,
            headless=headless,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            user_agent=user_agent
        )
        session.start()
        self._sessions[browser_name] = session
        return session

    def close_all(self):
        """Close all browser sessions."""
        for name, session in self._sessions.items():
            with contextlib.suppress(Exception):
                session._cleanup()
            logger.info("Closed %s session", name)
        self._sessions.clear()


# Global registry
_registry = _SessionRegistry()


# ── Public API ──────────────────────────────────────────────────────

def browser_control(
    action: str,
    url: str | None = None,
    selector: str | None = None,
    text: str | None = None,
    script: str | None = None,
    browser: str | None = None,
    file_path: str | None = None,
    direction: str = "down",
    amount: int = 500,
    headless: bool = False,
    full_page: bool = False,
    viewport_width: int = 1280,
    viewport_height: int = 720,
    user_agent: str | None = None,
) -> str:
    """
    Control a web browser programmatically.

    Args:
        action: One of: navigate, click, fill, screenshot, get_text, get_html,
                execute_js, scroll, new_tab, close_tab, back, close_all
        url: URL for navigate/new_tab actions.
        selector: CSS selector for click/fill/get_text actions.
        text: Text for fill action.
        script: JavaScript code for execute_js action.
        browser: Browser name (chrome, firefox, edge, brave, etc.).
                 Auto-detects default if not specified.
        file_path: Path to save screenshot.
        direction: Scroll direction (up/down).
        amount: Scroll amount in pixels.
        headless: Run browser without visible window.
        full_page: Take screenshot of entire page.
        viewport_width: Width of browser viewport.
        viewport_height: Height of browser viewport.
        user_agent: Custom User-Agent string.

    Returns:
        Result string describing what happened.
    """
    global _registry

    action = action.lower().strip()

    # Close all is special — no session needed
    if action == "close_all":
        _registry.close_all()
        return "All browser sessions closed."

    # Get or create session
    try:
        session = _registry.get_or_create(
            browser,
            headless=headless,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            user_agent=user_agent
        )
    except ImportError as e:
        return str(e)
    except Exception as e:
        return f"Failed to start browser: {e}"

    # Track downloads count before action
    initial_downloads_count = len(session.downloads)

    # Dispatch action
    try:
        if action == "navigate":
            if not url:
                return "URL is required for navigate action."
            res = session.navigate(url)
        elif action == "click":
            if not selector:
                return "CSS selector is required for click action."
            res = session.click(selector)
        elif action == "fill":
            if not selector or text is None:
                return "CSS selector and text are required for fill action."
            res = session.fill(selector, text)
        elif action == "screenshot":
            saved = session.screenshot(file_path, full_page)
            res = f"Screenshot saved to: {saved}"
        elif action == "get_text":
            res = session.get_text(selector or "body")
        elif action == "get_html":
            res = session.get_html()
        elif action == "execute_js":
            if not script:
                return "JavaScript code is required for execute_js action."
            res = session.execute_js(script)
        elif action == "scroll":
            res = session.scroll(direction, amount)
        elif action == "new_tab":
            res = session.new_tab(url)
        elif action == "close_tab":
            res = session.close_tab()
        elif action == "list_tabs":
            res = session.list_tabs()
        elif action == "switch_tab":
            try:
                idx = int(text) if text and text.isdigit() else 0
            except ValueError:
                idx = 0
            res = session.switch_tab(idx)
        elif action == "back":
            res = session.back()
        else:
            return f"Unknown action: {action}. Supported: navigate, click, fill, screenshot, get_text, get_html, execute_js, scroll, new_tab, close_tab, list_tabs, switch_tab, back, close_all"

        # Check for new downloads
        new_downloads = session.downloads[initial_downloads_count:]
        if new_downloads:
            res += f"\nFile(s) downloaded: {', '.join(new_downloads)}"
        return res  # type: ignore[no-any-return]

    except Exception as e:
        return f"Browser action '{action}' failed: {e}"


def close_browser():
    """Convenience function to close all browser sessions."""
    _registry.close_all()

