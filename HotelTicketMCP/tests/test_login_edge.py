"""Opt-in Edge integration checks with local CDP responses and synthetic cookies.

Set HOTEL_MCP_RUN_EDGE_TESTS=1 to run. No real Ctrip login is performed.
"""
import base64
import os
from contextlib import contextmanager
from urllib.parse import urlsplit

import pytest

from hotel_ticket_mcp_server.tools import hotel_login_tools as login
from hotel_ticket_mcp_server.utils import browser_factory, cookie_store, login_state

pytestmark = pytest.mark.skipif(os.environ.get("HOTEL_MCP_RUN_EDGE_TESTS") != "1",
                                reason="Opt-in test requires installed Edge")
TARGET = "https://hotels.ctrip.com/hotels/list/?city=477"


@pytest.fixture
def edge(monkeypatch, tmp_path):
    monkeypatch.setenv("HOTEL_MCP_BROWSER", "edge")
    monkeypatch.delenv("HOTEL_MCP_BROWSER_PATH", raising=False)
    monkeypatch.setenv("HOTEL_MCP_HEADLESS", "1")
    monkeypatch.setenv("HOTEL_MCP_CONSENT", "yes")
    monkeypatch.setenv("HOTEL_MCP_COOKIE_FILE", str(tmp_path / "cookies.json"))
    owner = browser_factory.BrowserSingleton(tmp_path / "profile")
    try:
        page = owner.get()
        assert owner._session.diagnostic["actual_browser"] == "edge"
        yield owner, page
    finally:
        owner.quit()


def test_edge_login_recovers_context_loss_and_persists_before_close(edge, monkeypatch, caplog):
    owner, page = edge
    intercepted, persisted_at_close = [], []

    def response(**event):
        request_id = event["requestId"]
        url = event["request"]["url"]
        host = urlsplit(url).hostname
        headers = [{"name": "Content-Type", "value": "text/html; charset=utf-8"}]
        if host == "passport.ctrip.com":
            html = '<html><body><input type="password"><div>账号密码登录</div></body></html>'
        elif url == TARGET:
            html = '<html><body>我的账户：测试<div class="hotel-list"><div>测试酒店 查看详情</div></div></body></html>'
            headers.append({"name": "Set-Cookie", "value":
                            "cticket=synthetic-edge-test; Domain=.ctrip.com; Path=/; HttpOnly; Secure"})
        else:
            page.run_cdp("Fetch.failRequest", requestId=request_id, errorReason="BlockedByClient", _timeout=2)
            return
        intercepted.append(host)
        page.run_cdp("Fetch.fulfillRequest", requestId=request_id, responseCode=200,
                     responseHeaders=headers, body=base64.b64encode(html.encode()).decode(), _timeout=2)

    page.driver.set_callback("Fetch.requestPaused", response)
    page.run_cdp("Fetch.enable", patterns=[{"urlPattern": "*"}], _timeout=2)
    observe = login_state.observe
    reads = 0

    def navigate_during_observation(tab, **kwargs):
        nonlocal reads
        reads += 1
        if reads == 2:
            assert tab.get(TARGET, retry=0, timeout=5)
            # The real CDP/DrissionPage exception for a destroyed context. Using
            # an absent context makes the navigation race deterministic.
            tab.run_cdp("Runtime.evaluate", expression="1", contextId=2147483647, _timeout=2)
            pytest.fail("Expected ContextLostError from the expired context")
        return observe(tab, **kwargs)

    @contextmanager
    def session(**kwargs):
        assert kwargs == {"visible": True}
        try:
            yield owner
        finally:
            persisted_at_close.append(any(cookie["name"] == "cticket" for cookie in cookie_store.load_cookies()))
            owner.quit()

    monkeypatch.setattr(login_state, "observe", navigate_during_observation)
    monkeypatch.setattr(login, "browser_session", session)
    with caplog.at_level("INFO"):
        result = login.ctripHotelLogin("open_login", TARGET)
    assert result["status"] == "success"
    assert persisted_at_close == [True]
    cookies = cookie_store.load_cookies()
    assert any(cookie["name"] == "cticket" and cookie["httpOnly"] for cookie in cookies)
    assert {"passport.ctrip.com", "hotels.ctrip.com"} <= set(intercepted)
    assert "ContextLostError" in caplog.text and "event=observation_recovered" in caplog.text
    assert "synthetic-edge-test" not in caplog.text


def test_edge_closed_tab_keeps_browser_alive(edge):
    owner, page = edge
    target_id = page.tab_id
    assert owner.connection_status(target_id, timeout=1) == "alive"
    page.new_tab("about:blank")
    page.close()
    assert page.browser.states.is_alive
    assert owner.connection_status(target_id, timeout=1) == "page_closed"


def test_edge_tab_disconnect_is_not_window_closure(edge):
    owner, page = edge
    target_id = page.tab_id
    page.disconnect()
    assert page.browser.states.is_alive
    assert owner.connection_status(target_id, timeout=1) == "connection_lost"
