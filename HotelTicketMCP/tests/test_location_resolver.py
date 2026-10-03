from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlencode
from hotel_ticket_mcp_server.utils.location_resolver import parse_location_url, resolve_location, matching_candidates

VALUE = "11|16764*11*30.5747097|114.3706248|梨园地铁站|16764"
URL = "https://hotels.ctrip.com/hotels/list/?" + urlencode(dict(cityId=477, searchWord="梨园地铁站", searchType="MT", searchValue=VALUE, optionId=16764))


def test_official_url_city_and_entity_id_must_agree():
    location = parse_location_url(URL, 477)
    assert location.search_type == "MT" and location.entity_type == "11"
    assert location.option_id == "16764"
    assert parse_location_url(URL, 1) is None
    assert parse_location_url(URL.replace("optionId=16764", "optionId=999"), 477) is None
    assert parse_location_url(URL.replace("hotels.ctrip.com", "other.example"), 477) is None
    assert parse_location_url(URL.split("&searchValue")[0], 477) is None


def test_names_lines_and_exits_disambiguate_without_merging_places():
    candidates = [{"name": "梨园地铁站", "detail": "8号线"}, {"name": "梨园公园"},
                  {"name": "梨园地铁站-B口", "detail": "8号线"}]
    assert len(matching_candidates(candidates, "梨园")) == 3
    assert matching_candidates(candidates, "梨园地铁站") == candidates[:1]
    assert matching_candidates(candidates, "梨园地铁站 8号线 B口") == candidates[2:]
    same_names = [{"name": "人民公园", "detail": "江岸区"}, {"name": "人民公园", "detail": "洪山区"}]
    assert len(matching_candidates(same_names, "人民公园")) == 2
    assert matching_candidates(same_names, "人民公园 洪山区") == same_names[1:]


def test_candidate_selection_requires_search_submission():
    page = SimpleNamespace(url="about:blank", run_js=Mock(return_value=[{"name": "梨园地铁站", "selector": "0"}]))
    clicked = []
    def element(selector, **kwargs):
        def click(**kwargs):
            clicked.append(selector)
            if 'aria-label="搜索"' in selector:
                page.url = URL
        return SimpleNamespace(input=Mock(), click=click)
    page.ele = element
    now = [0]
    result = resolve_location(page, 477, "梨园地铁站", clock=lambda: now[0], sleep=lambda n: now.__setitem__(0, now[0] + n))
    assert result["status"] == "resolved"
    assert len(clicked) == 2 and 'aria-label="搜索"' in clicked[1]


def test_ambiguity_and_missing_suggestions_are_bounded():
    now = [0]
    page = SimpleNamespace(ele=Mock(return_value=SimpleNamespace(input=Mock())), run_js=Mock(return_value=[]))
    result = resolve_location(page, 477, "梨园", budget=1, clock=lambda: now[0], sleep=lambda n: now.__setitem__(0, now[0] + n))
    assert result["status"] == "not_found" and now[0] == 1
    page.run_js.return_value = [{"name": "梨园地铁站"}, {"name": "梨园公园"}]
    assert resolve_location(page, 477, "梨园", clock=lambda: now[0], sleep=lambda n: now.__setitem__(0, now[0] + n))["status"] == "ambiguous"
