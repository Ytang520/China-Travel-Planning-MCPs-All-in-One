from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest

from hotel_ticket_mcp_server.utils.browser_factory import BrowserSingleton


@pytest.fixture
def browser(tmp_path):
    owner = BrowserSingleton(tmp_path)
    owner._session = SimpleNamespace(
        record={"browser_pid": 101, "browser_created": 1000},
        processes=SimpleNamespace(identity=Mock(return_value=(object(), 1000))),
    )
    owner._page = SimpleNamespace(
        browser=SimpleNamespace(states=SimpleNamespace(is_alive=True),
                                _run_cdp=Mock(return_value={"targetInfos": [{"targetId": "login", "type": "page"}]})),
        driver=SimpleNamespace(is_running=True),
    )
    return owner


def test_live_browser_uses_bounded_probe_without_page_js(browser):
    assert browser.connection_status("login", timeout=0.7) == "alive"
    browser._page.browser._run_cdp.assert_called_once_with("Target.getTargets", _timeout=0.7)


@pytest.mark.parametrize("identity", [(None, None), (object(), 2000)])
def test_exit_and_pid_reuse_confirm_original_browser_gone(browser, identity):
    browser._session.processes.identity.return_value = identity
    assert browser.connection_status("login", timeout=1) == "browser_closed"
    browser._page.browser._run_cdp.assert_not_called()


def test_lost_control_connection_is_not_process_exit(browser):
    browser._page.browser.states.is_alive = False
    assert browser.connection_status("login", timeout=1) == "connection_lost"


def test_only_tab_connection_lost_is_not_window_closure(browser):
    browser._page.driver.is_running = False
    assert browser.connection_status("login", timeout=1) == "connection_lost"


def test_explicitly_disconnected_tab_is_not_closed(browser):
    browser._page._driver = None
    assert browser.connection_status("login", timeout=1) == "connection_lost"


def test_missing_target_is_distinct_from_disconnected_browser(browser):
    browser._page.browser._run_cdp.return_value = {"targetInfos": []}
    assert browser.connection_status("login", timeout=1) == "page_closed"


def test_related_successor_tab_is_not_reported_as_closed(browser):
    browser._page.browser._run_cdp.return_value = {"targetInfos": [
        {"targetId": "successor", "type": "page", "openerId": "login"},
    ]}
    assert browser.connection_status("login", timeout=1) == "page_replaced"


@pytest.mark.parametrize("result", [{}, {"targetInfos": None}, {"targetInfos": [None]}])
def test_invalid_probe_response_cannot_prove_target_closed(browser, result):
    browser._page.browser._run_cdp.return_value = result
    assert browser.connection_status("login", timeout=1) == "unknown"


def test_probe_timeout_and_denied_process_access_remain_unknown(browser, caplog):
    browser._session.processes.identity.side_effect = psutil.AccessDenied(101)
    browser._page.browser._run_cdp.side_effect = TimeoutError("private-response")
    assert browser.connection_status("login", timeout=1) == "unknown"
    assert "private-response" not in caplog.text
