"""Opt-in live checks using project credentials and temporary, owned profiles.

HOTEL_MCP_RUN_LOCATION_LIVE=1; credentials are never printed or overwritten.
"""
import os
import json
import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from hotel_ticket_mcp_server.tools import hotel_search_tools as search, hotel_login_tools as login
from hotel_ticket_mcp_server.utils import cookie_store, search_state, location_resolver, url_builder
from hotel_ticket_mcp_server.utils.browser_runtime import OwnedBrowser

pytestmark = pytest.mark.skipif(os.environ.get("HOTEL_MCP_RUN_LOCATION_LIVE") != "1", reason="Opt-in Ctrip live check")
ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def owned(tmp_path, browser="edge"):
    from DrissionPage import ChromiumPage, ChromiumOptions
    # Keep Windows browser-internal paths below MAX_PATH without changing OS policy.
    profile = ROOT.parent / ".validation" / ("live-" + uuid.uuid4().hex[:10])
    session = OwnedBrowser("HOTEL_MCP", ROOT, profile, temporary=True)
    try:
        page = session.open(ChromiumPage, ChromiumOptions, headless=False)
        assert session.diagnostic["actual_browser"] == browser
        yield page
    finally:
        session.close()


@pytest.fixture
def setup_live(monkeypatch, tmp_path):
    from hotel_ticket_mcp_server import main as bootstrap  # project .env loader
    assert bootstrap and cookie_store.load_cookies(), "Project login cookies are required"
    monkeypatch.setenv("HOTEL_MCP_BROWSER", "edge")
    monkeypatch.delenv("HOTEL_MCP_BROWSER_PATH", raising=False)
    monkeypatch.setenv("HOTEL_MCP_HEADLESS", "0")
    original_check = search_state.request_applied
    def check(state, expected):
        applied = original_check(state, expected)
        if not applied:
            print(json.dumps({"page_state": state, "expected_url": expected}, ensure_ascii=False))
        return applied
    monkeypatch.setattr(search_state, "request_applied", check)
    @contextmanager
    def factory(**kwargs):
        with owned(tmp_path) as page:
            yield SimpleNamespace(get=lambda: page)
    monkeypatch.setattr(search, "browser_session", factory)
    checkin = date.today() + timedelta(days=7)
    return dict(city="武汉", checkin=str(checkin), checkout=str(checkin + timedelta(days=1)), limit=5)


@pytest.mark.parametrize("location,sort,filters", [
    ("梨园地铁站", "smart", {}),
    ("梨园", "smart", {}),
    ("武汉站-东出口", "distance", {"price_min": 250, "price_max": 400, "room_type": "双床房"}),
    ("梨园地铁站", "distance", {"price_min": 200, "price_max": 500, "room_type": "双床房", "star_min": 3, "star_max": 4, "accommodation_type": "酒店"}),
])
def test_live_search(setup_live, location, sort, filters):
    result = search.searchHotels(**setup_live, location=location, sort=sort, **filters)
    if location == "梨园" and result.get("error_code") == "LOCATION_AMBIGUOUS":
        assert result["location_resolution"]["candidates"]
        return
    assert result["status"] in ("success", "empty"), result
    assert result["location_resolution"]["applied"] and result["sorting"]["applied"], result
    assert result["location_resolution"]["requested"] == location


def test_live_resolve_and_replay_in_fresh_profile(setup_live, tmp_path):
    args = setup_live
    url = url_builder.build_list_url("武汉", (477, 20, 1), args["checkin"], args["checkout"])["url"]
    with owned(tmp_path / "resolve") as page:
        assert search._ensure_logged_in(page, url) is None
        result = location_resolver.resolve_location(page, 477, "梨园地铁站")
        assert result["status"] == "resolved", result
        location = result["location"]
    replay = url_builder.build_list_url("武汉", (477, 20, 1), args["checkin"], args["checkout"], resolved_location=location)["url"]
    with owned(tmp_path / "replay") as page:
        assert search._ensure_logged_in(page, replay) is None
        state, resolution = search_state.wait_for_state(page, replay, location.name, 477, source="cache", resolved=location)
        assert resolution["applied"] and search_state.request_applied(state, replay), (state, resolution)


def test_live_edge_login_cookies_in_chrome(setup_live, tmp_path, monkeypatch):
    args = setup_live
    url = url_builder.build_list_url("武汉", (477, 20, 1), args["checkin"], args["checkout"])["url"]
    with owned(tmp_path / "edge") as page:
        assert search._ensure_logged_in(page, url) is None
        cookies = login._extract_cookies(page)
        cookie_store.save_cookies(cookies, tmp_path / "transfer.json")
    monkeypatch.setenv("HOTEL_MCP_COOKIE_FILE", str(tmp_path / "transfer.json"))
    monkeypatch.setenv("HOTEL_MCP_BROWSER", "chrome")
    try:
        with owned(tmp_path / "chrome", "chrome") as page:
            assert search._ensure_logged_in(page, url) is None, "Chrome did not confirm the restored login"
    finally:
        (tmp_path / "transfer.json").unlink(missing_ok=True)
