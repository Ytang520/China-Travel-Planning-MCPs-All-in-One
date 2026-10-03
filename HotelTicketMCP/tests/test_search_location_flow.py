from contextlib import nullcontext
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from hotel_ticket_mcp_server.tools import hotel_search_tools as search
from hotel_ticket_mcp_server.utils import search_state, url_builder
from hotel_ticket_mcp_server.utils.location_cache import LocationCache, ResolvedLocation

LOCATION = ResolvedLocation("477", "梨园地铁站", "MT", "11|16764*11*30.5747097|114.3706248|梨园地铁站|16764", "16764", "11")


@pytest.fixture
def flow(monkeypatch):
    monkeypatch.setenv("HOTEL_MCP_CONSENT", "yes")
    monkeypatch.setattr(search, "_LOCATION_CACHE", LocationCache())
    monkeypatch.setattr(search.cookie_store, "load_cookies", lambda: [{"name": "test", "value": "test"}])
    monkeypatch.setattr(search._RATE_LIMITER, "wait_if_needed", lambda: {"waited_seconds": 0})
    monkeypatch.setattr(search, "_ensure_logged_in", lambda *args: None)
    monkeypatch.setattr(search.time, "sleep", lambda *_: None)
    page = SimpleNamespace(url="", urls=[], keyword_anchor=LOCATION.name, reject_id=None)
    def navigate(url, **kwargs):
        page.url = url
        page.urls.append(url)
        return True
    def state():
        query = parse_qs(urlsplit(page.url).query)
        identity = query.get("optionId", [None])[0]
        good = identity != page.reject_id if identity else page.keyword_anchor == LOCATION.name
        anchor = LOCATION.name if good else "另一地点"
        chips = [LOCATION.name] if identity and good else []
        filters = query.get("listFilters", [""])[0]
        for choices in (url_builder.ROOM_TYPE_FILTERS, url_builder.ACCOMMODATION_TYPE_FILTERS):
            chips.extend(label for label, code in choices.items() if code in filters.split(","))
        if "15~Range*15*200~400" in filters:
            chips.append("¥200 - ¥400")
        return {"url": page.url, "city": "武汉", "has_list": True,
                "chips": chips,
                "distances": [f"距{anchor}步行100米"], "sort_label": "智能排序"}
    page.get, page.run_js = navigate, lambda *args, **kwargs: state()
    monkeypatch.setattr(search, "browser_session", lambda: nullcontext(SimpleNamespace(get=lambda: page)))
    def wait(page, expected_url, requested, city_id, *, source, resolved=None):
        current = state()
        return current, search_state.verify_location(current, requested, city_id, source=source, resolved=resolved)
    monkeypatch.setattr(search_state, "wait_for_state", wait)
    monkeypatch.setattr(search, "_human_scroll_and_collect", lambda *_: [{"name": "示例酒店", "distance": f"距{LOCATION.name}步行100米", "price": 300}])
    resolver = Mock(return_value={"status": "resolved", "location": LOCATION})
    monkeypatch.setattr(search.location_resolver, "resolve_location", resolver)
    checkin = date.today() + timedelta(days=7)
    args = dict(city="武汉", checkin=str(checkin), checkout=str(checkin + timedelta(days=1)), location=LOCATION.name, limit=1)
    return page, args, resolver


def test_keyword_success_avoids_resolver_and_does_not_invent_id(flow):
    page, args, resolver = flow
    result = search.searchHotels(**args)
    assert result["status"] == "success"
    assert result["location_resolution"]["source"] == "keyword"
    assert result["location_resolution"]["landmark_id"] is None
    assert search._LOCATION_CACHE.get(477, LOCATION.name) is None
    resolver.assert_not_called()


@pytest.mark.parametrize("types,expected_codes", [
    ({"room_type": "双床房"}, {"4~2*4*2"}),
    ({"room_type": "大床房", "accommodation_type": "民宿"}, {"4~1*4*1", "75~TAG_510*75*510"}),
    ({"room_type": "特大床房", "accommodation_type": "酒店公寓"}, {"4~3*4*3", "75~TAG_505*75*505"}),
])
def test_failed_keyword_resolves_once_rebuilds_original_conditions_then_caches(flow, types, expected_codes):
    page, args, resolver = flow
    page.keyword_anchor = "另一地点"
    result = search.searchHotels(**args, price_min=200, price_max=400, rooms=2, adults=3, **types)
    assert result["status"] == "success", result
    assert result["location_resolution"]["source"] == "candidate"
    resolver.assert_called_once()
    query = parse_qs(urlsplit(page.url).query)
    assert query["crn"] == ["2"] and query["adult"] == ["3"]
    assert query["checkin"] == [args["checkin"]]
    assert set(query["listFilters"][0].split(",")) == {"15~Range*15*200~400"} | expected_codes
    assert search._LOCATION_CACHE.get(477, LOCATION.name) == LOCATION


def test_stale_cache_is_invalidated_before_keyword_fallback(flow):
    page, args, resolver = flow
    search._LOCATION_CACHE.put(LOCATION.name, LOCATION, applied=True)
    page.reject_id = LOCATION.option_id
    result = search.searchHotels(**args)
    assert result["status"] == "success" and result["location_resolution"]["source"] == "keyword"
    assert "optionId=" in page.urls[0] and "optionId=" not in page.urls[1]
    assert search._LOCATION_CACHE.get(477, LOCATION.name) is None
    resolver.assert_not_called()


def test_cache_hit_is_reverified_and_ambiguity_is_explicit(flow):
    page, args, resolver = flow
    search._LOCATION_CACHE.put(LOCATION.name, LOCATION, applied=True)
    result = search.searchHotels(**args)
    assert result["location_resolution"]["source"] == "cache" and result["location_resolution"]["applied"]
    search._LOCATION_CACHE.invalidate(477, LOCATION.name)
    page.keyword_anchor = "另一地点"
    resolver.return_value = {"status": "ambiguous", "candidates": [{"name": "梨园公园"}, {"name": LOCATION.name}]}
    result = search.searchHotels(**args)
    assert result["error_code"] == "LOCATION_AMBIGUOUS"
    assert not result["location_resolution"]["applied"] and len(result["location_resolution"]["candidates"]) == 2
    resolver.assert_called_once()


def test_resolved_but_unapplied_does_not_claim_nearby_success(flow):
    page, args, resolver = flow
    page.keyword_anchor, page.reject_id = "另一地点", LOCATION.option_id
    result = search.searchHotels(**args)
    assert result["error_code"] == "LOCATION_NOT_APPLIED"
    assert not result["location_resolution"]["applied"]
    assert search._LOCATION_CACHE.get(477, LOCATION.name) is None


def test_distance_cannot_succeed_with_smart_order(flow, monkeypatch):
    page, args, _ = flow
    monkeypatch.setattr(search_state, "apply_sort", lambda page, sort: page.run_js("state"))
    result = search.searchHotels(**args, sort="distance")
    assert result["error_code"] == "SORT_NOT_APPLIED"
    assert result["sorting"]["actual"] == "smart" and not result["sorting"]["applied"]


def test_known_expired_credentials_fail_before_throttle(flow, monkeypatch):
    _, args, _ = flow
    monkeypatch.setattr(search.cookie_store, "load_cookies", lambda: [{"name": "expired", "value": "x", "expires": 1}])
    wait = Mock(side_effect=AssertionError("Do not throttle an unauthenticated query"))
    monkeypatch.setattr(search._RATE_LIMITER, "wait_if_needed", wait)
    assert search.searchHotels(**args)["error_code"] == "LOGIN_REQUIRED"
    wait.assert_not_called()
