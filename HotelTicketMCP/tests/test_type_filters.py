"""User-approved choices and encodings observed on Ctrip's actual controls."""
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

import pytest

from hotel_ticket_mcp_server.tools import hotel_search_tools as search
from hotel_ticket_mcp_server.utils import search_state, url_builder

ROOMS = [
    ("大床房", "4~1*4*1"),
    ("双床房", "4~2*4*2"),
    ("单人床房", "4~4*4*4"),
    ("三床房", "4~6*4*6"),
    ("特大床房", "4~3*4*3"),
]
ACCOMMODATIONS = [
    ("酒店", "75~TAG_495*75*495"),
    ("民宿", "75~TAG_510*75*510"),
    ("青年旅馆", "75~TAG_519*75*519"),
    ("酒店公寓", "75~TAG_505*75*505"),
    ("公寓", "75~TAG_513*75*513"),
]
FILTERS = [(name, label, code) for name, options in (
    ("room_type", ROOMS), ("accommodation_type", ACCOMMODATIONS)
) for label, code in options]
ARGS = ("武汉", (477, 20, 1), "2099-01-01", "2099-01-02")


@pytest.mark.parametrize("room,room_code", ROOMS)
@pytest.mark.parametrize("accommodation,accommodation_code", ACCOMMODATIONS)
def test_type_combinations_preserve_price_stars_and_occupancy(room, room_code, accommodation, accommodation_code):
    built = url_builder.build_list_url(
        *ARGS, room_type=room, accommodation_type=accommodation,
        price_min=200, price_max=500, star_min=3, star_max=4, adults=3, rooms=2,
    )
    query = parse_qs(urlsplit(built["url"]).query)
    assert built["warnings"] == []
    assert set(query["listFilters"][0].split(",")) == {
        room_code, accommodation_code, "15~Range*15*200~500", "16~3*16*3", "16~4*16*4",
    }
    assert query["adult"] == ["3"] and query["crn"] == ["2"]


@pytest.mark.parametrize("argument,label,code", FILTERS)
def test_each_type_requires_matching_page_selection_and_url(argument, label, code):
    built = url_builder.build_list_url(*ARGS, **{argument: label})
    assert parse_qs(urlsplit(built["url"]).query)["listFilters"] == [code]
    state = {"url": built["url"], "city": "武汉", "chips": [label]}
    assert search_state.request_applied(state, built["url"])
    assert search_state.request_applied({**state, "chips": [], "selected_filters": [label]}, built["url"])
    assert not search_state.request_applied({**state, "chips": []}, built["url"])
    assert not search_state.request_applied({**state, "chips": [label + "推荐"]}, built["url"])
    assert not search_state.request_applied(
        {**state, "url": url_builder.build_list_url(*ARGS)["url"]}, built["url"],
    )


def test_room_and_accommodation_both_need_selection_evidence():
    url = url_builder.build_list_url(*ARGS, room_type="大床房", accommodation_type="酒店公寓")["url"]
    state = {"url": url, "city": "武汉", "chips": ["大床房", "酒店公寓"]}
    assert search_state.request_applied(state, url)
    for missing in ("大床房", "酒店公寓"):
        assert not search_state.request_applied({**state, "chips": [missing]}, url)


@pytest.mark.parametrize("argument,value", [
    ("room_type", "4+床房"),
    ("room_type", "家庭房"),
    ("room_type", ""),
    ("room_type", ["大床房", "双床房"]),
    ("accommodation_type", "别墅"),
    ("accommodation_type", "青年旅舍"),
    ("accommodation_type", ""),
    ("accommodation_type", ["酒店", "民宿"]),
])
def test_invalid_types_fail_before_login_throttling_or_browser(monkeypatch, argument, value):
    monkeypatch.setattr(search.consent, "is_consented", lambda: True)
    cookies = Mock(side_effect=AssertionError("Invalid types must fail before reading credentials"))
    throttle = Mock(side_effect=AssertionError("Invalid types must not wait"))
    browser = Mock(side_effect=AssertionError("Invalid types must not open a browser"))
    monkeypatch.setattr(search.cookie_store, "load_cookies", cookies)
    monkeypatch.setattr(search._RATE_LIMITER, "wait_if_needed", throttle)
    monkeypatch.setattr(search, "browser_session", browser)
    result = search.searchHotels(city=ARGS[0], checkin=ARGS[2], checkout=ARGS[3], **{argument: value})
    assert result["error_code"] == "INVALID_PARAMS"
    assert argument in result["message"]
    cookies.assert_not_called()
    throttle.assert_not_called()
    browser.assert_not_called()


def test_null_types_leave_search_unfiltered():
    built = url_builder.build_list_url(*ARGS, room_type=None, accommodation_type=None)
    assert built["warnings"] == []
    assert "listFilters" not in parse_qs(urlsplit(built["url"]).query)
    assert search_state.request_applied({"url": built["url"], "city": "武汉"}, built["url"])
