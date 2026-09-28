from hotel_ticket_mcp_server.tools.hotel_search_tools import parse_cards

# 2026-09-28 真实抓取样本（Edge + cookie 注入后，武汉站-东出口双床房列表，
# 已经过 JS 快照层的字段清洗，与 edge_hotels.json 同构）
REAL_SAMPLE = [
    {
        "name": "爱豪国际酒店(武汉高铁站东广场店)",
        "stars": "3",
        "score": "4.4",
        "reviews": "1,537条点评",
        "distance": "距武汉站-东出口直线280米 · 近武汉站",
        "room": "行政双床房",
        "price": 295,
    },
    {
        "name": "乐捷酒店(武汉站东广场店)",
        "stars": "2",
        "score": "4.2",
        "reviews": "111条点评",
        "distance": "距武汉站-东出口直线280米 · 近武汉站",
        "room": "甄享丨豪华双床房",
        "price": 334,
    },
    {
        "name": "维也纳酒店(武汉高铁站东广场店)",
        "stars": "3",
        "score": "4.7",
        "reviews": "2,013条点评",
        "distance": "距武汉站-东出口直线310米 · 近武汉站",
        "room": "标准双床房",
        "price": 364,
    },
    {
        "name": "鑫盛电竞影院酒店(武汉高铁站店)",
        "stars": "2",
        "score": "4.0",
        "reviews": "64条点评",
        "distance": "距武汉站-东出口直线1.6公里 · 近武汉站",
        "room": "",
        "price": 275,
    },
    {},
    {"name": ""},
    None,
]


def test_parse_real_sample():
    hotels = parse_cards(REAL_SAMPLE)
    assert [h["name"] for h in hotels] == [
        "爱豪国际酒店(武汉高铁站东广场店)",
        "乐捷酒店(武汉站东广场店)",
        "维也纳酒店(武汉高铁站东广场店)",
        "鑫盛电竞影院酒店(武汉高铁站店)",
    ]
    assert hotels[0]["price"] == 295
    assert hotels[0]["stars"] == "3"
    assert hotels[2]["score"] == "4.7"
    assert hotels[3]["room"] == ""
    # 空 name / 空 dict / None 一律跳过
    assert len(hotels) == 4


def test_min_score_filter():
    # 4.5 以上：维也纳(4.7) 保留；爱豪(4.4)/乐捷(4.2)/鑫盛(4.0) 过滤
    hotels = parse_cards(REAL_SAMPLE, min_score=4.5)
    assert [h["name"] for h in hotels] == ["维也纳酒店(武汉高铁站东广场店)"]


def test_no_score_card_kept_under_min_score():
    # 无评分记录的卡片无法判定，保留（避免误伤）
    hotels = parse_cards([{"name": "无评分酒店", "score": "", "price": 100}], min_score=4.0)
    assert len(hotels) == 1


def test_empty_input():
    assert parse_cards([]) == []
    assert parse_cards(None) == []
