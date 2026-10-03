"""参数 → 携程酒店列表页 URL 构造。

URL 字段与筛选编码来自 2026-10-03/04 携程页面控件验证。
16 为星级、4 为房型、75 为酒店标签；17 是排序而非星级。
"""

from urllib.parse import urlencode, quote

BASE = "https://hotels.ctrip.com/hotels/list/"

SORT_PARAMS = {
    "smart": None,       # 携程智能排序（默认，不传参数）
    "price_asc": "S",    # 低价优先
    "distance": None,    # 必须使用页面排序控件；sort=D 不生效
    "score_desc": "R",   # 好评优先
}

ROOM_TYPE_FILTERS = {
    "大床房": "4~1*4*1",
    "双床房": "4~2*4*2",
    "单人床房": "4~4*4*4",
    "三床房": "4~6*4*6",
    "特大床房": "4~3*4*3",
}

ACCOMMODATION_TYPE_FILTERS = {
    "酒店": "75~TAG_495*75*495",
    "民宿": "75~TAG_510*75*510",
    "青年旅馆": "75~TAG_519*75*519",
    "酒店公寓": "75~TAG_505*75*505",
    "公寓": "75~TAG_513*75*513",
}

VALID_SORTS = tuple(SORT_PARAMS.keys())
VALID_ROOM_TYPES = tuple(ROOM_TYPE_FILTERS.keys())
VALID_ACCOMMODATION_TYPES = tuple(ACCOMMODATION_TYPE_FILTERS.keys())


def build_list_url(
    city,
    city_ids,
    checkin,
    checkout,
    landmark=None,
    rooms=1,
    adults=2,
    children=0,
    price_min=None,
    price_max=None,
    star_min=None,
    star_max=None,
    room_type=None,
    accommodation_type=None,
    sort=None,
    resolved_location=None,
):
    """构造列表页 URL。

    Args:
        city: 城市名（中文，如"武汉"）
        city_ids: (cityId, provinceId, countryId) 三元组
        landmark: 地标名（可选，如"武汉站-东出口"）
        resolved_location: 城市内已解析的完整携程地点编码；关键字查询不需要 ID
        sort: smart/price_asc/distance/score_desc

    Returns:
        dict: {"url": str, "warnings": [str]}
    """
    city_id, province_id, country_id = city_ids
    warnings = []

    filters = []
    if price_min is not None or price_max is not None:
        lo = int(price_min if price_min is not None else 0)
        hi = int(price_max if price_max is not None else 9999)
        filters.append(f"15~Range*15*{lo}~{hi}")
    if star_min is not None or star_max is not None:
        stars = sorted(
            set(
                range(
                    int(star_min if star_min is not None else 1),
                    int(star_max if star_max is not None else 5) + 1,
                )
            )
        )
        filters.extend(f"16~{s}*16*{s}" for s in sorted({max(2, s) for s in stars}))
        if star_min == 2 or star_max == 1:
            warnings.append("携程将 1、2 星合并为‘2钻/星及以下’筛选，无法单独区分")
    if room_type:
        encoded = ROOM_TYPE_FILTERS.get(room_type)
        if encoded:
            filters.append(encoded)
        else:
            warnings.append(f"不支持的房型 {room_type!r}，已忽略")
    if accommodation_type:
        encoded = ACCOMMODATION_TYPE_FILTERS.get(accommodation_type)
        if encoded:
            filters.append(encoded)
        else:
            warnings.append(
                f"不支持的住宿类型 {accommodation_type!r}，已忽略"
            )

    params = [
        ("flexType", "1"),
        ("fixedDate", "0"),
        ("directSearch", "1"),
        ("cityId", str(city_id)),
        ("provinceId", str(province_id)),
        ("countryId", str(country_id)),
        ("cityName", city),
        ("destName", city),
        ("searchWord", resolved_location.name if resolved_location else landmark or city),
    ]
    if resolved_location:
        if str(resolved_location.city_id) != str(city_id):
            raise ValueError("地标与查询城市不一致")
        params.extend([("searchType", resolved_location.search_type),
                       ("searchValue", resolved_location.search_value),
                       ("optionId", resolved_location.option_id)])
    params.extend(
        [
            ("checkin", checkin),
            ("checkout", checkout),
            ("crn", str(rooms)),
            ("adult", str(adults)),
            ("child", str(children)),
        ]
    )
    if filters:
        params.append(("listFilters", ",".join(filters)))
    params.extend([("curr", "CNY"), ("locale", "zh-CN"), ("old", "1")])
    if sort and sort != "smart":
        sort_param = SORT_PARAMS.get(sort)
        if sort_param:
            params.append(("sort", sort_param))
        elif sort not in SORT_PARAMS:
            warnings.append(f"未知排序 {sort!r}，使用默认智能排序")

    url = BASE + "?" + urlencode(params, quote_via=quote)
    return {"url": url, "warnings": warnings}
