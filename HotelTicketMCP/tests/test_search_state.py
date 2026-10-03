from urllib.parse import parse_qs, urlencode, urlsplit
from hotel_ticket_mcp_server.utils import search_state, url_builder
from hotel_ticket_mcp_server.utils.location_cache import ResolvedLocation

LOCATION = ResolvedLocation("477", "梨园地铁站", "MT", "11|16764*11*30.5747097|114.3706248|梨园地铁站|16764", "16764", "11")
URL = url_builder.build_list_url("武汉", (477, 20, 1), "2026-11-09", "2026-11-10", landmark=LOCATION.name)["url"]
STATE = {"url": URL, "city": "武汉", "chips": [], "has_list": True,
         "distances": ["距梨园地铁站直线140米", "距梨园地铁站直线1.2公里"], "sort_label": "直线距离 近→远"}


def test_keyword_needs_matching_card_anchors_or_a_selected_chip():
    assert search_state.verify_location(STATE, "梨园地铁站", 477)["applied"]
    assert not search_state.verify_location(STATE, "梨园", 477)["applied"]
    assert not search_state.verify_location({**STATE, "distances": []}, "梨园地铁站", 477)["applied"]
    assert not search_state.verify_location({**STATE, "distances": ["距梨园公园步行300米"]}, "梨园地铁站", 477)["applied"]


def test_resolved_id_alone_does_not_prove_application():
    url = url_builder.build_list_url("武汉", (477, 20, 1), "2026-11-09", "2026-11-10", resolved_location=LOCATION)["url"]
    state = {**STATE, "url": url}
    assert not search_state.verify_location(state, LOCATION.name, 477, resolved=LOCATION)["applied"]
    state["chips"] = [LOCATION.name]
    assert search_state.verify_location(state, LOCATION.name, 477, resolved=LOCATION)["applied"]
    assert not search_state.verify_location({**state, "distances": ["距其他地铁站直线100米"]}, LOCATION.name, 477, resolved=LOCATION)["applied"]


def test_distance_sort_checks_label_anchor_metric_and_order():
    resolution = search_state.verify_location(STATE, LOCATION.name, 477)
    assert search_state.verify_sort(STATE, "distance", resolution)["applied"]
    for changed in [{"sort_label": "智能排序"}, {"distances": ["距梨园地铁站步行140米"]},
                    {"distances": list(reversed(STATE["distances"]))}, {"distances": []}]:
        assert not search_state.verify_sort({**STATE, **changed}, "distance", resolution)["applied"]


def test_dates_occupancy_filters_and_city_cannot_silently_change():
    assert search_state.request_applied(STATE, URL)
    assert not search_state.request_applied({**STATE, "city": "北京"}, URL)
    parsed = urlsplit(URL)
    for field, value in [("cityId", "1"), ("checkin", "2026-12-09"), ("crn", "2"), ("listFilters", "4~2*4*2")]:
        query = parse_qs(parsed.query)
        query[field] = [value]
        changed = parsed._replace(query=urlencode(query, doseq=True)).geturl()
        assert not search_state.request_applied({**STATE, "url": changed}, URL)


def test_filters_require_page_selection_and_sort_code_is_not_a_star():
    url = url_builder.build_list_url("武汉", (477, 20, 1), "2026-11-09", "2026-11-10",
                                     room_type="双床房", star_min=3, star_max=3, accommodation_type="酒店")["url"]
    state = {**STATE, "url": url, "chips": ["双床房", "3钻/星|舒适", "酒店"]}
    assert search_state.request_applied(state, url)
    assert not search_state.request_applied({**state, "chips": []}, url)
    assert search_state.request_applied({**state, "url": url.replace("listFilters=", "listFilters=17~5*17*5,")}, url)


def test_verified_empty_location_differs_from_unverified_empty_keyword():
    state = {**STATE, "empty": True, "distances": [], "chips": [LOCATION.name]}
    resolution = search_state.verify_location(state, LOCATION.name, 477)
    assert resolution["applied"] and search_state.verify_sort(state, "distance", resolution)["applied"]
    assert not search_state.verify_location({**state, "chips": []}, LOCATION.name, 477)["applied"]
