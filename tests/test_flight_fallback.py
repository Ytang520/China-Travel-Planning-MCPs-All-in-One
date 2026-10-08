"""Fliggy parsing, fallback contracts and process-wide pacing without network access."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from flight_ticket_mcp_server.tools import flight_search_tools as tools
from flight_ticket_mcp_server.tools import fliggy_search as fliggy
from flight_ticket_mcp_server.utils.search_interval import FlightSearchInterval


class Clock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def row(**overrides):
    # Fields observed in the logged-out SHA -> BJS DOM (2026-10-12).
    return dict({"airline": "国航CA8342", "flight_count": 1, "departure": "19:00",
                 "arrival": "20:55", "departure_airport": "浦东国际机场T2",
                 "arrival_airport": "大兴国际机场", "price": "422", "aircraft": "320",
                 "transfer": False, "raw_text": "国航CA8342\n19:00\n20:55\n¥422 2.0折"}, **overrides)


def snapshot(**overrides):
    return dict({"url": "https://sjipiao.fliggy.com/homeow/trip_flight_search.htm",
                 "query": {"depCity": "SHA", "arrCity": "BJS", "depDate": "2099-01-01", "tripType": "0"},
                 "rows": [row()], "list_present": True, "message": "", "blocked": False}, **overrides)


def collect(monkeypatch, snapshots, timeout=10):
    clock = Clock()
    monkeypatch.setattr(fliggy, "time", clock)
    reads = []
    urls = []

    def run_js(script):
        assert "scroll" not in script
        state = snapshots[min(len(reads), len(snapshots) - 1)]
        reads.append(state)
        return state

    page = SimpleNamespace(get=lambda url, **kw: urls.append(url), run_js=run_js)
    result = fliggy.collect_flights(page, "上海", "北京", "2099-01-01", timeout=timeout)
    assert len(urls) == 1
    return result, reads, clock


def test_url_is_a_new_single_trip_with_encoded_semantic_fields():
    url = fliggy.build_search_url("sha", "北京(BJS)", "2099-01-01")
    query = parse_qs(urlparse(url).query)
    assert query == {"depCity": ["SHA"], "arrCity": ["BJS"], "depCityName": ["上海"],
                     "arrCityName": ["北京"], "depDate": ["2099-01-01"],
                     "tripType": ["0"], "mTripType": ["1"], "pcOtaMode": ["1"]}


def test_parse_scoped_fare_airports_overnight_and_codeshare():
    flights, invalid = fliggy.parse_rows([
        row(), row(airline="厦航MF2642", departure="23:00", arrival="01:00 +1天",
                   price="1,234", raw_text="厦航MF2642\n共享\n¥1234 4.0折"),
        row(transfer=True, flight_count=2, price="100"),
    ])
    assert not invalid and len(flights) == 2
    first, second = flights
    assert (first["航班号"], first["航空公司"], first["价格"]) == ("CA8342", "国航", "¥422")
    assert (first["出发机场"], first["出发航站楼"], first["到达航站楼"]) == ("浦东国际机场", "T2", "")
    assert second["到达时间"] == "01:00 +1天"
    assert second["价格"] == "¥1234" and second["价格说明"] == "不含税费"


@pytest.mark.parametrize("text,expected", [("00:30 第2天", "00:30 +1天"), ("01:00 第3天", "01:00 +2天"),
                                          ("00:30 次日", "00:30 +1天"), ("08:00 第1天", "08:00")])
def test_fliggy_day_ordinals_are_normalized_to_existing_day_offsets(text, expected):
    # MU5185 / MF3627 in the live SHA -> BJS DOM show "00:30 第2天".
    flights, invalid = fliggy.parse_rows([row(airline="东航MU5185", departure="22:00", arrival=text)])
    assert not invalid and flights[0]["到达时间"] == expected


@pytest.mark.parametrize("changes", [
    {"price": ""}, {"price": "售罄"}, {"price": "0"}, {"departure": "24:90"},
    {"arrival": "待定"}, {"airline": "国航"}, {"arrival_airport": ""},
    {"flight_count": 2, "transfer": False},
])
def test_missing_or_invalid_card_fields_are_not_valid_flights(changes):
    flights, invalid = fliggy.parse_rows([row(**changes)])
    assert flights == [] and invalid == 1


def test_waits_for_stable_full_list_without_scrolling(monkeypatch):
    result, reads, clock = collect(monkeypatch, [
        snapshot(rows=[]), snapshot(), snapshot(),
        snapshot(rows=[row(), row(airline="东航MU5232")]),
    ])
    assert result.status == "success" and len(result.flights) == 2
    assert len(reads) >= 6 and clock.now >= 5


def test_waits_for_unrendered_prices_instead_of_returning_partial_list(monkeypatch):
    partial = snapshot(rows=[row(), row(airline="东航MU5232", price="")])
    complete = snapshot(rows=[row(), row(airline="东航MU5232", price="506")])
    result, _, clock = collect(monkeypatch, [partial] * 6 + [complete])
    assert result.status == "success" and len(result.flights) == 2 and clock.now >= 8


def test_partial_invalid_list_times_out_as_error(monkeypatch):
    result, _, _ = collect(monkeypatch, [snapshot(rows=[row(), row(price="")])])
    assert result.status == "parse_failed" and not result.flights


def test_visible_loading_indicator_prevents_early_success(monkeypatch):
    result, _, clock = collect(monkeypatch, [snapshot(loading=True)] * 6 + [snapshot()])
    assert result.status == "success" and clock.now >= 8


@pytest.mark.parametrize("price,expected", [("¥99", 99), ("¥9", 9), ("¥1,234", 1234), ("¥99.50", 99.5)])
def test_fare_statistics_accept_low_and_formatted_fares(price, expected):
    assert tools._extract_price_value(price) == expected


@pytest.mark.parametrize("state, status", [
    (snapshot(blocked=True), "request_failed"),
    (snapshot(query={"depCity": "CAN"}), "parse_failed"),
    (snapshot(url="https://login.taobao.com/"), "parse_failed"),
    (snapshot(rows=[], list_present=False), "parse_failed"),
    (snapshot(rows=[row(price="售罄")]), "parse_failed"),
    (snapshot(rows=[], message="未找到符合条件的航班"), "no_results"),
    (snapshot(rows=[row(transfer=True, flight_count=2)]), "no_results"),
])
def test_blocked_mismatched_and_unknown_pages_are_not_empty_success(monkeypatch, state, status):
    result, _, _ = collect(monkeypatch, [state])
    assert result.status == status
    assert not result.flights


@pytest.fixture
def searcher(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(tools, "_SEARCH_INTERVAL", FlightSearchInterval(
        clock=clock.monotonic, sleep=clock.sleep, uniform=lambda a, b: a,
    ))
    monkeypatch.setenv("FLIGHT_MCP_MIN_DELAY", "15")
    monkeypatch.setenv("FLIGHT_MCP_MAX_DELAY", "45")
    instance = object.__new__(tools.FlightRouteSearcher)
    instance.page = object()
    instance.close = lambda: None
    return instance, clock


def test_primary_success_does_not_search_fliggy(searcher, monkeypatch):
    instance, clock = searcher

    def primary(*args, **kw):
        instance.last_parse_status = "success"
        instance.last_collection_stop_reason = "limit_reached"
        return fliggy.parse_rows([row()])[0]

    instance._search_ctrip = primary
    monkeypatch.setattr(fliggy, "collect_flights", lambda *a: pytest.fail("Must keep Ctrip results"))
    assert len(instance.search_flights("上海", "北京", "2099-01-01", limit=1)) == 1
    assert instance.last_data_source == "ctrip_web_scraping" and not instance.fallback_used
    assert len(instance.source_attempts) == 1 and not clock.waits


@pytest.mark.parametrize("failure", ["exception", "parse_failed", "no_results"])
@pytest.mark.parametrize("preference", ["auto", "default"])
def test_public_fallback_preserves_filters_limits_provenance_and_cleanup(searcher, monkeypatch, failure, preference):
    instance, clock = searcher
    closed = []
    instance.close = lambda: closed.append(True)

    def primary(*args, **kw):
        if failure == "exception":
            raise RuntimeError("primary timed out")
        instance.last_parse_status = failure
        instance.last_parse_error = "primary failed" if failure == "parse_failed" else None
        return []

    instance._search_ctrip = primary
    flights = fliggy.parse_rows([
        row(departure="07:00"), row(airline="东航MU5232", departure="08:30"),
        row(airline="东航MU5232", departure="08:30"),
        row(airline="南航CZ8900", departure="11:25"), row(airline="国航CA8342", departure="19:00"),
    ])[0]
    monkeypatch.setattr(fliggy, "collect_flights", lambda *a: fliggy.FliggyResult("success", flights))
    monkeypatch.setattr(tools, "FlightRouteSearcher", lambda **kw: instance)
    result = tools.searchFlightRoutes("上海", "北京", (date.today() + timedelta(days=7)).isoformat(),
                                     data_source_preference=preference, earliestStartTime=8, latestStartTime=12, limit=2)
    assert result["status"] == "success" and result["fallback_used"]
    assert result["data_source"] == "fliggy_web_scraping" and result["flight_count"] == 2
    assert [f["航班号"] for f in result["flights"]] == ["MU5232", "CZ8900"]
    assert [f["序号"] for f in result["flights"]] == [1, 2]
    assert result["collection_stop_reason"] == "limit_reached"
    assert result["statistics_scope"] == "returned_flights"
    assert result["price_basis"] == "不含税费"
    assert result["data_source_name"] == "飞猪"
    assert result["source_attribution"] == "数据来源：飞猪（票价不含税费）"
    assert result["formatted_output"].startswith(result["source_attribution"])
    query = parse_qs(urlparse(result["source_url"]).query)
    assert urlparse(result["source_url"]).hostname == "sjipiao.fliggy.com"
    assert (query["depCity"], query["arrCity"], query["depDate"]) == (
        ["SHA"], ["BJS"], [result["departure_date"]],
    )
    assert result["source_url"] in result["formatted_output"]
    assert result["query_time"] in result["formatted_output"]
    assert datetime.fromisoformat(result["query_time"]).utcoffset() is not None
    assert len(result["source_attempts"]) == 2 and clock.waits == [15]
    assert closed == [True]


def test_both_sources_fail_returns_error_and_closes(searcher, monkeypatch):
    instance, _ = searcher
    closed = []
    instance.close = lambda: closed.append(True)
    instance._search_ctrip = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("ctrip unavailable"))
    monkeypatch.setattr(fliggy, "collect_flights", lambda *a: fliggy.FliggyResult("request_failed", error="飞猪限制访问"))
    monkeypatch.setattr(tools, "FlightRouteSearcher", lambda **kw: instance)
    result = tools.searchFlightRoutes("上海", "北京", (date.today() + timedelta(days=7)).isoformat())
    assert result["status"] == "error" and result["error_code"] == "SCRAPING_FAILED"
    assert result["data_source"] == "fliggy_web_scraping" and result["fallback_used"]
    assert result["last_attempted_data_source"] == "fliggy_web_scraping"
    assert result["last_attempted_data_source_name"] == "飞猪"
    assert all(result[key] is None for key in ("data_source_name", "source_url", "source_attribution"))
    assert [a["status"] for a in result["source_attempts"]] == ["request_failed", "request_failed"]
    assert closed == [True]


@pytest.mark.parametrize("args,dependency,error", [
    ({"departure_city": ""}, None, "INVALID_PARAMS"),
    ({"departure_date": "bad-date"}, None, "INVALID_DATE_FORMAT"),
    ({"departure_date": "2000-01-01"}, None, "PAST_DATE"),
    ({"departure_city": "not-a-city"}, None, "INVALID_DEPARTURE_CITY"),
    ({"destination_city": "not-a-city"}, None, "INVALID_DESTINATION_CITY"),
    ({"data_source_preference": "variflight"}, None, "DATA_SOURCE_REMOVED"),
    ({"data_source_preference": "invalid"}, None, "INVALID_DATA_SOURCE_PREFERENCE"),
    ({}, "DRISSION_PAGE_AVAILABLE", "DRISSION_PAGE_NOT_AVAILABLE"),
    ({}, "get_airport_code", "CITIES_DICT_NOT_AVAILABLE"),
    ({}, None, "SEARCH_FAILED"),
])
def test_pre_search_errors_do_not_claim_a_provider(monkeypatch, args, dependency, error):
    def fail_to_open(**kwargs):
        if error != "SEARCH_FAILED":
            pytest.fail("Validation failure must not open a browser")
        raise RuntimeError("browser initialization failed")

    monkeypatch.setattr(tools, "FlightRouteSearcher", fail_to_open)
    if dependency:
        monkeypatch.setattr(tools, dependency, None)
    result = tools.searchFlightRoutes(**{
        "departure_city": "上海", "destination_city": "北京", "departure_date": "2099-01-01", **args,
    })
    assert result["status"] == "error" and result["error_code"] == error
    assert result["data_source"] == "system"
    assert not result["fallback_used"] and result["source_attempts"] == []
    assert all(result[key] is None for key in (
        "data_source_name", "source_url", "source_attribution",
        "last_attempted_data_source", "last_attempted_data_source_name",
    ))


def test_verified_empty_result_attributes_query_without_claiming_fares(searcher, monkeypatch):
    instance, _ = searcher
    instance._search_ctrip = lambda *a, **kw: []
    monkeypatch.setattr(fliggy, "collect_flights", lambda *a: fliggy.FliggyResult("no_results"))
    monkeypatch.setattr(tools, "FlightRouteSearcher", lambda **kw: instance)
    result = tools.searchFlightRoutes("上海", "北京", "2099-01-01")
    assert result["status"] == "success" and result["flight_count"] == 0
    assert result["data_source_name"] == "飞猪" and result["source_attribution"] == "查询来源：飞猪"
    assert result["formatted_output"].startswith(result["source_attribution"])


def test_cleanup_failure_keeps_attempted_fliggy_diagnostic_only(searcher, monkeypatch):
    instance, _ = searcher
    instance._search_ctrip = lambda *a, **kw: []
    monkeypatch.setattr(fliggy, "collect_flights", lambda *a: fliggy.FliggyResult("success", fliggy.parse_rows([row()])[0]))
    monkeypatch.setattr(tools, "FlightRouteSearcher", lambda **kw: instance)
    instance.close = lambda: (_ for _ in ()).throw(RuntimeError("cleanup failed"))
    result = tools.searchFlightRoutes("上海", "北京", "2099-01-01")
    assert result["status"] == "error" and result["error_code"] == "SEARCH_FAILED"
    assert result["data_source"] == result["last_attempted_data_source"] == "fliggy_web_scraping"
    assert result["last_attempted_data_source_name"] == "飞猪" and result["fallback_used"]
    assert all(result[key] is None for key in ("data_source_name", "source_url", "source_attribution"))


def test_low_decimal_fares_are_included_in_returned_sample_statistics(searcher, monkeypatch):
    instance, _ = searcher
    instance._search_ctrip = lambda *a, **kw: []
    flights, _ = fliggy.parse_rows([row(price="9.99"), row(airline="东航MU5232", price="89.99")])
    monkeypatch.setattr(fliggy, "collect_flights", lambda *a: fliggy.FliggyResult("success", flights))
    monkeypatch.setattr(tools, "FlightRouteSearcher", lambda **kw: instance)
    result = tools.searchFlightRoutes("上海", "北京", (date.today() + timedelta(days=7)).isoformat())
    assert result["price_statistics"] == {"min_price": 9.99, "max_price": 89.99, "avg_price": 49.99}


@pytest.mark.parametrize("options,expected", [({}, 200), ({"limit": 80}, 80), ({"limit": 250}, 250), ({"limit": None}, 290)])
def test_fliggy_obeys_default_and_overridden_limits(searcher, monkeypatch, options, expected):
    instance, _ = searcher
    instance._search_ctrip = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("primary unavailable"))
    flights, _ = fliggy.parse_rows([row(airline=f"国航CA{8000 + i}") for i in range(290)])
    monkeypatch.setattr(fliggy, "collect_flights", lambda *a: fliggy.FliggyResult("success", flights))
    monkeypatch.setattr(tools, "FlightRouteSearcher", lambda **kw: instance)
    result = tools.searchFlightRoutes("上海", "北京", (date.today() + timedelta(days=7)).isoformat(), **options)
    assert result["flight_count"] == len(result["flights"]) == expected
    assert result["requested_limit"] == options.get("limit", 200)
    assert result["data_source"] == "fliggy_web_scraping"


def test_interval_counts_from_completion_and_handles_failures(monkeypatch):
    monkeypatch.setenv("FLIGHT_MCP_MIN_DELAY", "15")
    monkeypatch.setenv("FLIGHT_MCP_MAX_DELAY", "45")
    clock = Clock()
    limiter = FlightSearchInterval(clock=clock.monotonic, sleep=clock.sleep, uniform=lambda a, b: a)
    with limiter.search() as first:
        clock.now += 100
    assert first["waited_seconds"] == 0
    with pytest.raises(RuntimeError), limiter.search() as second:
        assert second["waited_seconds"] == 15
        raise RuntimeError("failed request")
    clock.now += 5
    with limiter.search() as third:
        assert third["waited_seconds"] == 10
    clock.now += 60
    with limiter.search() as fourth:
        assert fourth["waited_seconds"] == 0
    assert clock.waits == [15, 10]


@pytest.mark.parametrize("minimum,maximum", [("nan", "inf"), ("bad", "-1"), ("45", "15")])
def test_interval_invalid_settings_stay_finite_and_nonnegative(monkeypatch, minimum, maximum):
    monkeypatch.setenv("FLIGHT_MCP_MIN_DELAY", minimum)
    monkeypatch.setenv("FLIGHT_MCP_MAX_DELAY", maximum)
    clock = Clock()
    limiter = FlightSearchInterval(clock=clock.monotonic, sleep=clock.sleep, uniform=lambda a, b: a)
    with limiter.search():
        pass
    with limiter.search():
        pass
    assert clock.waits == [45 if minimum == "45" else 15]
