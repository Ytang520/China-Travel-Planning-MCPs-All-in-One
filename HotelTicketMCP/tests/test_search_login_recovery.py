from contextlib import nullcontext
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pytest

from hotel_ticket_mcp_server.tools import hotel_search_tools as search


TARGET = "https://hotels.ctrip.com/hotels/list/?city=477"


@pytest.fixture
def page(monkeypatch):
    monkeypatch.setattr(search.cookie_store, "load_cookies", lambda: [
        {"name": "cticket", "value": "fake-ticket", "domain": ".ctrip.com"},
    ])
    monkeypatch.setattr(search.time, "sleep", lambda _: None)
    return SimpleNamespace(get=Mock(return_value=True), set=SimpleNamespace(cookies=Mock()))


@pytest.mark.parametrize("failure", ["navigation_false", "navigation_exception", "injection_exception"])
def test_browser_failures_do_not_trigger_login_or_trust_stale_dom(monkeypatch, page, failure, caplog):
    observe = Mock(return_value={"state": "logged_in"})
    monkeypatch.setattr(search.login_state, "observe", observe)
    if failure == "navigation_false":
        page.get.return_value = False
    elif failure == "navigation_exception":
        page.get.side_effect = TimeoutError("mock network timeout")
    else:
        page.set.cookies.side_effect = RuntimeError("mock disconnect: fake-ticket")
    result = search._ensure_logged_in(page, TARGET)
    assert result["error_code"] == "LOGIN_STATE_UNKNOWN"
    observe.assert_not_called()
    assert "fake-ticket" not in caplog.text
    if failure != "injection_exception":
        page.get.assert_called_once_with(TARGET, retry=0, timeout=90)


@pytest.mark.parametrize("cookies", [[], [{"name": "missing_value"}]])
def test_missing_or_invalid_credentials_still_request_login(monkeypatch, page, cookies):
    monkeypatch.setattr(search.cookie_store, "load_cookies", lambda: cookies)
    assert search._ensure_logged_in(page, TARGET)["error_code"] == "LOGIN_REQUIRED"
    page.set.cookies.assert_not_called()
    page.get.assert_not_called()


@pytest.mark.parametrize("state", ["guest", "logged_in"])
def test_loaded_page_can_confirm_login_state(monkeypatch, page, state):
    monkeypatch.setattr(search.login_state, "observe", lambda _: {"state": state})
    result = search._ensure_logged_in(page, TARGET)
    if state == "guest":
        assert result["error_code"] == "LOGIN_REQUIRED"
        assert result["return_url"] == TARGET
    else:
        assert result is None


def test_search_stops_before_login_recovery_when_initial_navigation_fails(monkeypatch, page):
    monkeypatch.setenv("HOTEL_MCP_CONSENT", "yes")
    monkeypatch.setattr(search, "SEARCH_LOCK", threading.Lock())
    monkeypatch.setattr(search, "browser_session", lambda: nullcontext(SimpleNamespace(get=lambda: page)))
    monkeypatch.setattr(search._RATE_LIMITER, "wait_if_needed", lambda: {"waited_seconds": 0})
    recovery = Mock(side_effect=AssertionError("Do not request login after failed navigation"))
    monkeypatch.setattr(search, "_ensure_logged_in", recovery)
    page.get.return_value = False
    checkin = date.today() + timedelta(days=7)
    result = search.searchHotels("武汉", str(checkin), str(checkin + timedelta(days=2)), limit=5)
    assert result["error_code"] == "SCRAPING_FAILED"
    recovery.assert_not_called()
    assert page.get.call_args.kwargs == {"retry": 0, "timeout": 90}
