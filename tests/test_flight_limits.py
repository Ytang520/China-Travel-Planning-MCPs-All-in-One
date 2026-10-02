"""Bounded flight acceptance exercises the real collector without a browser/network."""
from datetime import date, timedelta
import importlib
from types import SimpleNamespace

import pytest

from flight_ticket_mcp_server.tools import flight_search_tools as tools


def flight(number, departure="08:30", arrival="10:45"):
    return {"航班号": f"MU{5100 + number}", "出发时间": departure, "到达时间": arrival,
            "出发机场": "虹桥机场", "到达机场": "首都机场", "价格": "¥500"}


@pytest.fixture
def make_searcher(monkeypatch):
    monkeypatch.setattr(tools.time, "sleep", lambda _: None)

    def make(pages):
        searcher = object.__new__(tools.FlightRouteSearcher)
        state = SimpleNamespace(scrolls=0, closed=False)

        def scroll(script):
            assert "scrollBy" in script
            state.scrolls += 1

        searcher.page = SimpleNamespace(run_js=scroll, get=lambda *a, **k: None)
        searcher.base_url = "https://example.invalid/{}/{}/{}"
        searcher.last_parse_status = "not_started"
        searcher.last_parse_error = None
        searcher.last_collection_stop_reason = "not_started"
        searcher._earliestStartTime = searcher._latestStartTime = None
        searcher._earliestArrivalTime = searcher._latestArrivalTime = None
        searcher._get_scroll_metrics = lambda: {
            "scroll_height": 900, "viewport_height": 900, "bottom_gap": 0, "flight_count": 10,
        }
        searcher._snapshot_visible_flights = lambda: [dict(row) for row in pages[min(state.scrolls, len(pages) - 1)]]
        searcher._wait_for_loading_complete = lambda **k: None
        searcher._wait_for_page_ready = lambda: None
        searcher._wait_for_flight_content = lambda: None
        searcher._apply_time_filter = lambda *a: None
        searcher.close = lambda: setattr(state, "closed", True)
        return searcher, state

    return make


def test_limit_stops_before_any_scroll_when_first_page_has_enough(make_searcher):
    searcher, state = make_searcher([[flight(i) for i in range(1, 11)]])
    records = searcher._collect_flights_with_scrolling(limit=5)
    assert [row["航班号"] for row in records] == [f"MU{5100 + i}" for i in range(1, 6)]
    assert state.scrolls == 0
    assert searcher.last_collection_stop_reason == "limit_reached"


def test_duplicates_invalid_rows_and_time_filters_do_not_consume_limit(make_searcher):
    searcher, state = make_searcher([
        [flight(1, "06:00"), flight(2), flight(2), flight(3, "unknown"), flight(4, arrival="26:00")],
        [flight(2), flight(5), flight(6), flight(7), flight(8, arrival="00:30 +1天"), flight(9)],
    ])
    records = searcher.search_flights("上海", "北京", "2099-01-01", earliestStartTime=8, limit=5)
    assert [row["航班号"] for row in records] == ["MU5102", "MU5105", "MU5106", "MU5107", "MU5108"]
    assert [row["序号"] for row in records] == [1, 2, 3, 4, 5]
    assert state.scrolls == 1


def test_fewer_than_limit_is_returned_at_stable_end(make_searcher):
    searcher, state = make_searcher([[flight(1), flight(2)]])
    assert len(searcher._collect_flights_with_scrolling(limit=5)) == 2
    assert state.scrolls == 8
    assert searcher.last_collection_stop_reason == "list_stable"


def test_omitted_limit_keeps_collecting_beyond_five(make_searcher):
    searcher, state = make_searcher([[flight(i) for i in range(1, 7)], [flight(i) for i in range(5, 10)]])
    assert len(searcher._collect_flights_with_scrolling()) == 9
    assert state.scrolls > 0


def test_fallback_parser_applies_same_limit_and_deduplication(make_searcher):
    searcher, _ = make_searcher([[flight(1), flight(1), {"航班号": "未知"}, *[flight(i) for i in range(2, 10)]]])
    searcher._collect_visible_flights = lambda *a, **k: 0
    assert len(searcher._collect_flights_with_scrolling(limit=5)) == 5
    assert searcher.last_collection_stop_reason == "limit_reached"


def test_empty_page_does_not_become_a_successful_sample(make_searcher):
    searcher, _ = make_searcher([[]])
    assert searcher._collect_flights_with_scrolling(limit=5) == []
    assert searcher.last_parse_status == "parse_failed"


@pytest.mark.parametrize("invalid", [0, -1, 1.5, True, "5"])
def test_invalid_limit_rejected_before_browser_creation(monkeypatch, invalid):
    monkeypatch.setattr(tools, "FlightRouteSearcher", lambda **k: pytest.fail("Browser must not start"))
    with pytest.raises(ValueError, match="positive integer"):
        tools.searchFlightRoutes("上海", "北京", "2099-01-01", limit=invalid)


@pytest.mark.asyncio
async def test_mcp_limit_schema_forwarding_results_and_cleanup(make_searcher, monkeypatch):
    from fastmcp import Client, FastMCP
    from fastmcp.exceptions import ToolError
    main = importlib.import_module("flight_ticket_mcp_server.main")

    searcher, state = make_searcher([[flight(i) for i in range(1, 11)]])
    monkeypatch.setattr(tools, "FlightRouteSearcher", lambda **k: searcher)
    monkeypatch.setattr(main, "mcp", FastMCP("limit-contract"))
    main.register_tools()
    args = {"departure_city": "上海", "destination_city": "北京",
            "departure_date": (date.today() + timedelta(days=7)).isoformat(), "limit": 5}
    async with Client(main.mcp) as client:
        tool = next(tool for tool in await client.list_tools() if tool.name == "searchFlightRoutes")
        schema = tool.model_dump(by_alias=True)["inputSchema"]
        assert "limit" in schema["properties"]
        assert "limit" not in schema.get("required", [])
        for invalid in [0, -1, 1.5, True, "5"]:
            with pytest.raises(ToolError):
                await client.call_tool("searchFlightRoutes", {**args, "limit": invalid})
        result = await client.call_tool("searchFlightRoutes", args)
    data = result.data
    assert data["flight_count"] == len(data["flights"]) == 5
    assert data["requested_limit"] == 5
    assert data["collection_stop_reason"] == "limit_reached"
    assert data["statistics_scope"] == "returned_flights"
    assert state.scrolls == 0
    assert state.closed
