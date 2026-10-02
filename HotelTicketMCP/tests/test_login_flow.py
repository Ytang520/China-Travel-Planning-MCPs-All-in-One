import asyncio
from contextlib import contextmanager
from datetime import date, timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qs
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import anyio
import pytest
from DrissionPage.errors import ContextLostError, PageDisconnectedError, JavaScriptError

from hotel_ticket_mcp_server.tools import hotel_login_tools as login, hotel_search_tools as search
from hotel_ticket_mcp_server.utils import browser_factory, cookie_store

TARGET = "https://hotels.ctrip.com/hotels/list/?city=477"
GUEST = {"url": login.LOGIN_URL, "ready": True, "login_form": True, "state": "guest"}
MEMBER = {"url": TARGET, "ready": True, "login_form": False, "state": "logged_in"}


@pytest.fixture
def session(monkeypatch, tmp_path):
    monkeypatch.setenv("HOTEL_MCP_CONSENT", "yes")
    monkeypatch.setenv("HOTEL_MCP_COOKIE_FILE", str(tmp_path / "cookies.json"))
    monkeypatch.setattr(login, "SEARCH_LOCK", threading.Lock())
    monkeypatch.setattr(login, "POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(login, "LOGIN_TIMEOUT_SECONDS", 120)
    now = iter(range(10000))
    monkeypatch.setattr(login.time, "monotonic", lambda: next(now))
    calls, closed, observed = [], [], [GUEST.copy()]
    page = SimpleNamespace(url=login.LOGIN_URL, tab_id="login-tab",
                           set=SimpleNamespace(window=SimpleNamespace(max=lambda: None)))
    page.get = lambda url, **kwargs: (calls.append(url), setattr(page, "url", url))
    page.ele = lambda *args, **kwargs: None
    page.run_cdp = lambda *args: {"cookies": [
        {"name": "cticket", "value": "test-secret", "domain": ".ctrip.com", "httpOnly": True},
        {"name": "unrelated", "value": "discard", "domain": "notctrip.com"},
    ]}

    browser = SimpleNamespace(get=lambda: page, quit=lambda: closed.append("cancel"),
                              connection_status=Mock(return_value="alive"))

    @contextmanager
    def browser_session(**kwargs):
        assert kwargs == {"visible": True}
        try:
            yield browser
        finally:
            closed.append("closed")

    def observe(_, **kwargs):
        state = observed.pop(0) if len(observed) > 1 else observed[0]
        if isinstance(state, Exception):
            raise state
        page.url = state["url"]
        return state.copy()

    monkeypatch.setattr(login, "browser_session", browser_session)
    monkeypatch.setattr(login.login_state, "observe", observe)
    return SimpleNamespace(page=page, browser=browser, calls=calls, closed=closed,
                           states=observed, path=tmp_path / "cookies.json")


@pytest.mark.parametrize("action,code", [(None, "USER_INTERACTION_REQUIRED"), ("cancel", "LOGIN_CANCELLED")])
def test_no_browser_before_user_choice(session, action, code):
    assert login.ctripHotelLogin(action)["error_code"] == code
    assert session.calls == [] and session.closed == []


def test_opens_passport_directly_then_saves_verified_cookie(session):
    session.states[:] = [GUEST, MEMBER]
    result = login.ctripHotelLogin("open_login", TARGET)
    first = urlsplit(session.calls[0])
    assert first.hostname == "passport.ctrip.com" and first.path == "/user/login"
    assert parse_qs(first.query)["backurl"] == [TARGET]
    assert result["status"] == "success"
    assert [c["name"] for c in cookie_store.load_cookies(session.path)] == ["cticket"]
    assert session.closed == ["closed"] and not login.SEARCH_LOCK.locked()


def test_timeout_preserves_existing_cookie(session, caplog):
    session.path.write_text("original cookie", encoding="utf-8")
    with caplog.at_level("INFO"):
        assert login.ctripHotelLogin("open_login", TARGET)["error_code"] == "LOGIN_TIMEOUT"
    assert session.path.read_text() == "original cookie"
    assert session.closed == ["closed"]
    assert "close_reason=LOGIN_TIMEOUT" in caplog.text


def test_closed_browser_and_blank_page_never_succeed(session):
    session.states[:] = [PageDisconnectedError()]
    session.browser.connection_status.return_value = "browser_closed"
    assert login.ctripHotelLogin("open_login", TARGET)["error_code"] == "LOGIN_BROWSER_CLOSED"
    session.states[:] = [{"url": "about:blank", "ready": False, "login_form": False, "state": "unknown"}]
    assert login.ctripHotelLogin("open_login", TARGET)["error_code"] == "LOGIN_PAGE_UNAVAILABLE"
    assert not session.path.exists()


@pytest.mark.parametrize("error", [ContextLostError(), TimeoutError(), RuntimeError("private-cookie=secret")])
def test_login_redirect_recovers_and_saves_before_closing(session, monkeypatch, error, caplog):
    session.states[:] = [GUEST, error, MEMBER]
    original_save = cookie_store.save_cookies
    def save(*args, **kwargs):
        assert session.closed == []
        return original_save(*args, **kwargs)
    monkeypatch.setattr(cookie_store, "save_cookies", save)
    with caplog.at_level("INFO"):
        result = login.ctripHotelLogin("open_login", TARGET)
    assert result["status"] == "success"
    assert cookie_store.load_cookies(session.path)[0]["name"] == "cticket"
    assert session.closed == ["closed"]
    assert type(error).__name__ in caplog.text
    assert "LOGIN_BROWSER_CLOSED" not in caplog.text
    assert "private-cookie" not in caplog.text and "test-secret" not in caplog.text
    assert "event=cookies_saved" in caplog.text and "close_reason=success" in caplog.text


def test_redirect_during_protected_list_verification_recovers(session):
    session.states[:] = [GUEST, {**MEMBER, "url": "https://hotels.ctrip.com/hotels/"},
                         ContextLostError(), MEMBER]
    assert login.ctripHotelLogin("open_login", TARGET)["status"] == "success"
    assert TARGET in session.calls and session.path.exists()


@pytest.mark.parametrize("health,code", [
    ("alive", "LOGIN_STATE_UNKNOWN"),
    ("unknown", "LOGIN_STATE_UNKNOWN"),
    ("connection_lost", "LOGIN_CONNECTION_LOST"),
    ("page_replaced", "LOGIN_STATE_UNKNOWN"),
    ("page_closed", "LOGIN_BROWSER_CLOSED"),
])
def test_persistent_read_failure_uses_connection_evidence(session, health, code, caplog):
    session.path.write_text("original", encoding="utf-8")
    session.states[:] = [GUEST, PageDisconnectedError("sensitive-url-and-cookie")]
    session.browser.connection_status.return_value = health
    with caplog.at_level("INFO"):
        result = login.ctripHotelLogin("open_login", TARGET)
    assert result["error_code"] == code
    assert session.path.read_text() == "original" and session.closed == ["closed"]
    assert session.browser.connection_status.call_count >= 2
    assert f"close_reason={code}" in caplog.text
    assert "stage=waiting_for_login" in caplog.text
    assert "sensitive-url-and-cookie" not in caplog.text


def test_detection_script_error_is_not_browser_closure(session):
    session.states[:] = [JavaScriptError("private-page-text")]
    assert login.ctripHotelLogin("open_login", TARGET)["error_code"] == "LOGIN_STATE_UNKNOWN"
    assert not session.path.exists()


def test_missing_target_once_does_not_close_recovering_page(session):
    session.states[:] = [GUEST, ContextLostError(), MEMBER]
    session.browser.connection_status.return_value = "page_closed"
    assert login.ctripHotelLogin("open_login", TARGET)["status"] == "success"


def test_cancel_during_connection_probe_preserves_cookie(session):
    session.path.write_text("original", encoding="utf-8")
    session.states[:] = [ContextLostError(), MEMBER]
    control = login.LoginControl()
    def probe(*args, **kwargs):
        control.stop()
        return "browser_closed"
    session.browser.connection_status.side_effect = probe
    result = login.ctripHotelLogin("open_login", TARGET, control=control)
    assert result["error_code"] == "LOGIN_CANCELLED"
    assert session.path.read_text() == "original"


def test_recovery_respects_total_timeout(session, monkeypatch):
    session.states[:] = [ContextLostError()]
    monkeypatch.setattr(login, "TOTAL_TIMEOUT_SECONDS", 12)
    assert login.ctripHotelLogin("open_login", TARGET)["error_code"] == "LOGIN_TIMEOUT"
    assert not session.path.exists()


def test_empty_cookie_cannot_finish_login(session):
    session.states[:] = [MEMBER]
    session.page.run_cdp = lambda *args: {"cookies": []}
    assert login.ctripHotelLogin("open_login", TARGET)["error_code"] == "LOGIN_VERIFICATION_FAILED"
    assert not session.path.exists()


@pytest.mark.parametrize("url", ["https://evil.test/", "https://hotels.ctrip.com.evil.test/hotels/",
                                  "http://hotels.ctrip.com/hotels/", "https://user@hotels.ctrip.com/hotels/"])
def test_invalid_return_url_never_opens_browser(session, url):
    assert login.ctripHotelLogin("open_login", url)["error_code"] == "INVALID_PARAMS"
    assert not session.calls


def test_busy_session_does_not_wait_silently(session):
    login.SEARCH_LOCK.acquire()
    try:
        assert login.ctripHotelLogin("open_login", TARGET)["error_code"] == "HOTEL_BROWSER_BUSY"
        assert not session.calls
    finally:
        login.SEARCH_LOCK.release()


@pytest.mark.parametrize("content", [None, b"\xff\xfe"], ids=["missing", "invalid-encoding"])
def test_missing_or_corrupt_cookie_prompts_before_rate_limit_or_browser(monkeypatch, tmp_path, content):
    monkeypatch.setenv("HOTEL_MCP_CONSENT", "yes")
    path = tmp_path / "missing.json"
    if content is not None:
        path.write_bytes(content)
    monkeypatch.setenv("HOTEL_MCP_COOKIE_FILE", str(path))
    monkeypatch.setattr(search._RATE_LIMITER, "wait_if_needed", lambda: pytest.fail("must not throttle a login prompt"))
    checkin = date.today() + timedelta(days=7)
    result = search.searchHotels("武汉", str(checkin), str(checkin + timedelta(days=2)))
    assert result["error_code"] == "LOGIN_REQUIRED"


def test_visible_login_overrides_headless_on_each_platform(monkeypatch, tmp_path):
    calls = []
    class Owned:
        def __init__(self, *args): pass
        def open(self, *args, **kwargs): calls.append(kwargs); return object()
        def close(self): pass
    monkeypatch.setattr(browser_factory, "DRISSION_PAGE_AVAILABLE", True)
    monkeypatch.setattr(browser_factory, "OwnedBrowser", Owned)
    monkeypatch.setenv("HOTEL_MCP_HEADLESS", "1")
    for platform in ("win32", "darwin", "linux"):
        monkeypatch.setattr("sys.platform", platform)
        browser = browser_factory.BrowserSingleton(tmp_path, visible=True)
        browser.get()
        browser.quit()
    assert calls == [{"headless": False}] * 3


def test_async_login_cancellation_stops_worker(monkeypatch, caplog):
    ended = threading.Event()
    def worker(*args, control, **kwargs):
        control.notify("waiting")
        control.stopped.wait(5)
        ended.set()
        return {"status": "error", "message": "cancelled"}
    monkeypatch.setattr(login, "ctripHotelLogin", worker)
    class Context:
        async def report_progress(self, *args, **kwargs): pass
    async def scenario():
        task = asyncio.create_task(login.login_with_progress("open_login", TARGET, Context()))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    assert ended.is_set()
    assert "reason=client_cancelled" in caplog.text
    assert "exception_type=CancelledError" in caplog.text


def test_progress_transport_failure_is_logged_separately_and_stops_worker(monkeypatch, caplog):
    ended = threading.Event()
    def worker(*args, control, **kwargs):
        control.stopped.wait(5)
        ended.set()
        return {"status": "error", "message": "cancelled"}
    monkeypatch.setattr(login, "ctripHotelLogin", worker)
    class Context:
        async def report_progress(self, *args, **kwargs):
            raise RuntimeError("private transport payload")
    with pytest.raises(RuntimeError):
        asyncio.run(login.login_with_progress("open_login", TARGET, Context()))
    assert ended.is_set()
    assert "reason=async_failure" in caplog.text and "operation=reporting_progress" in caplog.text
    assert "private transport payload" not in caplog.text


def test_cookie_write_failure_logs_stage_without_cookie_contents(session, monkeypatch, caplog):
    session.states[:] = [MEMBER]
    session.path.write_text("original", encoding="utf-8")
    def fail(*args, **kwargs):
        raise OSError("private-cookie=test-secret")
    monkeypatch.setattr(cookie_store, "save_cookies", fail)
    with caplog.at_level("INFO"):
        result = login.ctripHotelLogin("open_login", TARGET)
    assert result["error_code"] == "LOGIN_VERIFICATION_FAILED"
    assert session.path.read_text() == "original"
    assert "stage=saving_cookies" in caplog.text and "exception_type=OSError" in caplog.text
    assert "test-secret" not in caplog.text and "private-cookie" not in caplog.text


def test_cookie_replace_failure_keeps_previous_file(monkeypatch, tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text("original", encoding="utf-8")
    def fail(*args): raise OSError("disk failure")
    monkeypatch.setattr(cookie_store.os, "replace", fail)
    with pytest.raises(OSError):
        cookie_store.save_cookies([], path)
    assert path.read_text() == "original"
    assert list(tmp_path.iterdir()) == [path]


def test_cancel_during_cookie_extraction_preserves_previous_file(session):
    session.path.write_text("original", encoding="utf-8")
    session.states[:] = [MEMBER]
    control = login.LoginControl()
    def extract(*args):
        control.cancel()
        return {"cookies": [{"name": "cticket", "value": "mock", "domain": ".ctrip.com"}]}
    session.page.run_cdp = extract
    result = login.ctripHotelLogin("open_login", TARGET, control=control)
    assert result["error_code"] == "LOGIN_CANCELLED"
    assert session.path.read_text() == "original"


def test_cancel_during_cookie_staging_prevents_atomic_replace(monkeypatch, tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text("original", encoding="utf-8")
    control = login.LoginControl()
    original_dump = cookie_store.json.dump
    def dump(*args, **kwargs):
        original_dump(*args, **kwargs)
        control.stop()
    monkeypatch.setattr(cookie_store.json, "dump", dump)
    assert cookie_store.save_cookies([], path, commit_lock=control.commit_lock, cancelled=control.stopped) is None
    assert path.read_text() == "original"
    assert list(tmp_path.iterdir()) == [path]


def test_cancel_before_browser_creation_cannot_reopen(monkeypatch, tmp_path):
    monkeypatch.setenv("HOTEL_MCP_CONSENT", "yes")
    monkeypatch.setattr(browser_factory, "DRISSION_PAGE_AVAILABLE", True)
    monkeypatch.setattr(browser_factory, "OwnedBrowser", lambda *args: pytest.fail("opened after cancellation"))
    browser = browser_factory.BrowserSingleton(tmp_path, visible=True)
    browser.quit()
    with pytest.raises(browser_factory.BrowserError):
        browser.get()
    control = login.LoginControl()
    monkeypatch.setattr(control, "notify", lambda _: control.cancel())
    assert login.ctripHotelLogin("open_login", TARGET, control=control)["error_code"] == "LOGIN_CANCELLED"


@pytest.mark.parametrize("initial_failure", [True, False])
def test_failed_navigation_never_saves_stale_member_cookie(session, initial_failure):
    session.states[:] = [{**MEMBER, "url": "https://hotels.ctrip.com/hotels/"}]
    navigations = []
    def get(url, **kwargs):
        navigations.append(kwargs)
        return False if initial_failure or url == TARGET else True
    session.page.get = get
    result = login.ctripHotelLogin("open_login", TARGET)
    assert result["error_code"] == "LOGIN_PAGE_UNAVAILABLE"
    assert not session.path.exists()
    assert all(args["retry"] == 0 and args["timeout"] <= 45 for args in navigations)


def test_login_navigation_never_exceeds_remaining_budget(monkeypatch):
    monkeypatch.setattr(login.time, "monotonic", lambda: 100)
    calls = []
    page = SimpleNamespace(get=lambda *args, **kwargs: calls.append(kwargs))
    control = login.LoginControl()
    login._navigate(page, TARGET, control, 107, 45)
    assert calls == [{"retry": 0, "timeout": 7}]
    with pytest.raises(login.LoginFlowError, match="超时"):
        login._navigate(page, TARGET, control, 99)
    assert len(calls) == 1


def test_anyio_cancellation_closes_browser_with_saturated_executor(monkeypatch):
    ended, entered, released = threading.Event(), threading.Event(), threading.Event()
    def worker(*args, control, **kwargs):
        control.browser = SimpleNamespace(quit=released.set)
        entered.set()
        released.wait(3)
        ended.set()
        return {"status": "error", "message": "cancelled"}
    monkeypatch.setattr(login, "ctripHotelLogin", worker)
    class Context:
        async def report_progress(self, *args, **kwargs): pass
    async def scenario():
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1))
        async with anyio.create_task_group() as group:
            group.start_soon(login.login_with_progress, "open_login", TARGET, Context())
            with anyio.fail_after(2):
                while not entered.is_set():
                    await anyio.sleep(0.01)
            group.cancel_scope.cancel()
        assert released.is_set() and ended.is_set()
    asyncio.run(scenario())
