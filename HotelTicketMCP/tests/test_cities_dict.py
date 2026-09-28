from hotel_ticket_mcp_server.utils.cities_dict import get_city_ids, get_landmark


def test_known_city():
    assert get_city_ids("武汉") == (477, 20, 1)
    assert get_city_ids("北京") == (1, 1, 1)
    assert get_city_ids(" 上海 ") == (2, 2, 1)


def test_unknown_city():
    assert get_city_ids("不存在的城市") is None
    assert get_city_ids("") is None
    assert get_city_ids(None) is None


def test_known_landmark():
    assert get_landmark("武汉站-东出口") == ("10", "13306087", "30.6076444|114.4256694")


def test_unknown_landmark():
    assert get_landmark("不存在的出口") is None
