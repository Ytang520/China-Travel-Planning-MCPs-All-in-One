"""Per-call hotel sessions with persistent login data and owned crash recovery."""
import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
import psutil
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
logger = logging.getLogger(__name__)


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

    def connection_status(self, target_id, *, timeout):
        """Probe our browser without page JS; uncertainty never means closure."""
        with self._state_lock:
            session, page = self._session, self._page
            record = dict(session.record or {}) if session is not None else {}
        if record.get("browser_pid") and record.get("browser_created") is not None:
            try:
                process, created = session.processes.identity(record["browser_pid"])
                if process is None or created != record["browser_created"]:
                    return "browser_closed"
            except (OSError, psutil.Error) as exc:
                logger.warning("Hotel browser identity probe failed: exception_type=%s", type(exc).__name__)
        if page is None or timeout <= 0:
            return "unknown"
        try:
            if not page.browser.states.is_alive:
                return "connection_lost"
            # tab_ids may use an HTTP request without a per-call timeout. This
            # small adapter uses DrissionPage's browser CDP driver explicitly.
            result = page.browser._run_cdp("Target.getTargets", _timeout=timeout)
            targets = result.get("targetInfos") if isinstance(result, dict) else None
            if not isinstance(targets, list) or any(
                not isinstance(target, dict) or not target.get("targetId") for target in targets
            ):
                return "unknown"
            if any(target["targetId"] == target_id for target in targets):
                # disconnect() clears the tab driver even when the browser's
                # independent connection and the target are still available.
                if getattr(page, "_driver", True) is None:
                    return "connection_lost"
                return "alive" if page.driver.is_running else "connection_lost"
            if any(target.get("openerId") == target_id for target in targets):
                return "page_replaced"
            return "page_closed"
        except Exception as exc:
            logger.warning("Hotel browser connection probe failed: exception_type=%s", type(exc).__name__)
            return "unknown"

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
