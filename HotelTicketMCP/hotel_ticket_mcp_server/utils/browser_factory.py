"""Per-call hotel sessions with persistent login data and owned crash recovery."""
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from .browser_discovery import BrowserDiscovery, BrowserError
from .browser_runtime import OwnedBrowser

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    DRISSION_PAGE_AVAILABLE = True
except ImportError:
    ChromiumPage = ChromiumOptions = None
    DRISSION_PAGE_AVAILABLE = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PROFILE_DIR = PROJECT_ROOT / ".browser-profile"
SEARCH_LOCK = threading.Lock()


def resolve_browser_path():
    return BrowserDiscovery(PROJECT_ROOT).resolve("HOTEL_MCP").path


class BrowserSingleton:
    def __init__(self, profile_dir=None, visible=False):
        selected = profile_dir or os.environ.get("HOTEL_MCP_PROFILE_DIR")
        self.profile_dir = Path(selected) if selected else DEFAULT_PROFILE_DIR
        self.visible = visible
        self._session = None
        self._page = None
        self._state_lock = threading.Lock()
        self._closed = False

    def get(self):
        if not DRISSION_PAGE_AVAILABLE:
            raise BrowserError("DRISSION_PAGE_NOT_AVAILABLE", "DrissionPage is not installed")
        with self._state_lock:
            if self._closed:
                raise BrowserError("BROWSER_SHUTTING_DOWN", "浏览器会话已关闭")
            if self._page is not None:
                return self._page
            self._session = OwnedBrowser("HOTEL_MCP", PROJECT_ROOT, self.profile_dir)
            session = self._session
        # OwnedBrowser coordinates cancellation while its constructor is running.
        page = session.open(
            ChromiumPage, ChromiumOptions,
            headless=not self.visible and os.environ.get("HOTEL_MCP_HEADLESS", "0") == "1",
        )
        with self._state_lock:
            if self._closed:
                raise BrowserError("BROWSER_SHUTTING_DOWN", "浏览器会话已关闭")
            self._page = page
            return page

    def quit(self):
        with self._state_lock:
            self._closed = True
            session = self._session
        if session is not None:
            session.close()
        with self._state_lock:
            if self._session is session:
                self._session = self._page = None

    reset = quit


@contextmanager
def browser_session(*, visible=False):
    singleton = BrowserSingleton(visible=visible)
    try:
        yield singleton
    finally:
        singleton.quit()
