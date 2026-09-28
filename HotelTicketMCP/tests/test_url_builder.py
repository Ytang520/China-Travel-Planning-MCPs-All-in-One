from urllib.parse import parse_qs, unquote, urlparse

from hotel_ticket_mcp_server.utils.url_builder import build_list_url

WUHAN = (477, 20, 1)


def qs(url):
    return parse_qs(urlparse(url).query)


def test_city_only_url():
    result = build_list_url("武汉", WUHAN, "2026-10-01", "2026-10-03")
    assert result["warnings"] == []
    params = qs(result["url"])
    assert params["cityId"] == ["477"]
    assert params["cityName"] == [unquote("%E6%AD%A6%E6%B1%89")]
    # 原始查询串必须保留 URL 编码（防止 quote() 被误删）
    assert "cityName=%E6%AD%A6%E6%B1%89" in result["url"]
    assert params["checkin"] == ["2026-10-01"]
    assert params["checkout"] == ["2026-10-03"]
    assert params["crn"] == ["1"]
    assert "searchType" not in params and "searchValue" not in params
    assert "listFilters" not in params
    assert result["url"].startswith("https://hotels.ctrip.com/hotels/list/?")


def test_landmark_url():
    result = build_list_url(
        "武汉",
        WUHAN,
        "2026-10-01",
        "2026-10-03",
        landmark="武汉站-东出口",
        landmark_code=("10", "13306087", "30.6076444|114.4256694"),
    )
    params = qs(result["url"])
    assert params["searchType"] == ["T"]
    sv = unquote(params["searchValue"][0])
    assert sv.startswith("10|13306087*10*30.6076444|114.4256694|武汉站-东出口|13306087")
    assert unquote(params["searchWord"][0]) == "武汉站-东出口"


def test_filters_price_star_room():
    result = build_list_url(
        "武汉",
        WUHAN,
        "2026-10-01",
        "2026-10-03",
        price_min=250,
        price_max=400,
        star_min=3,
        star_max=3,
        room_type="双床房",
        accommodation_type="酒店",
    )
    filters = qs(result["url"])["listFilters"][0].split(",")
    assert "15~Range*15*250~400" in filters
    assert "17~3*17*3" in filters
    assert "29~1*29*1~2*2" in filters
    assert "4~2*4*2" in filters


def test_unknown_room_type_warns_and_skips():
    result = build_list_url("武汉", WUHAN, "2026-10-01", "2026-10-03", room_type="阁楼房")
    assert any("阁楼房" in w for w in result["warnings"])
    assert "listFilters" not in qs(result["url"])


def test_sort_mapping():
    assert "sort" not in qs(build_list_url("武汉", WUHAN, "2026-10-01", "2026-10-03", sort="smart")["url"])
    assert qs(build_list_url("武汉", WUHAN, "2026-10-01", "2026-10-03", sort="price_asc")["url"])["sort"] == ["S"]
    assert qs(build_list_url("武汉", WUHAN, "2026-10-01", "2026-10-03", sort="distance")["url"])["sort"] == ["D"]
    assert qs(build_list_url("武汉", WUHAN, "2026-10-01", "2026-10-03", sort="score_desc")["url"])["sort"] == ["R"]
