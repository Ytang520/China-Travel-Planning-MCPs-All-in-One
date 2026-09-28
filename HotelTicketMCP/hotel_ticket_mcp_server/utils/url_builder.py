"""参数 → 携程酒店列表页 URL 构造。

URL 模板与筛选编码均来自对 hotels.ctrip.com 列表页的真实观察
（2026-09-28 验证：武汉站-东出口 双床房 ¥250-400 3星 搜索）。
"""

from urllib.parse import quote

BASE = "https://hotels.ctrip.com/hotels/list/"

SORT_PARAMS = {
    "smart": None,       # 携程智能排序（默认，不传参数）
    "price_asc": "S",    # 低价优先
    "distance": "D",     # 直线距离近→远
    "score_desc": "R",   # 好评优先
}

ROOM_TYPE_FILTERS = {
    "双床房": "29~1*29*1~2*2",
}

ACCOMMODATION_TYPE_FILTERS = {
    "酒店": "4~2*4*2",
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
    landmark_code=None,
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
):
    """构造列表页 URL。

    Args:
        city: 城市名（中文，如"武汉"）
        city_ids: (cityId, provinceId, countryId) 三元组
        landmark: 地标名（可选，如"武汉站-东出口"）
        landmark_code: (searchType, landmarkId, "lat|lng")（与 landmark 配套）
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
        filters.extend(f"17~{s}*17*{s}" for s in stars)
    if room_type:
        encoded = ROOM_TYPE_FILTERS.get(room_type)
        if encoded:
            filters.append(encoded)
        else:
            warnings.append(f"房型 {room_type!r} 暂无已验证的筛选编码，已忽略")
    if accommodation_type:
        encoded = ACCOMMODATION_TYPE_FILTERS.get(accommodation_type)
        if encoded:
            filters.append(encoded)
        else:
            warnings.append(
                f"住宿类型 {accommodation_type!r} 暂无已验证的筛选编码，已忽略"
            )

    dest_name = landmark or city
    params = [
        ("flexType", "1"),
        ("cityId", str(city_id)),
        ("provinceId", str(province_id)),
        ("countryId", str(country_id)),
        ("cityName", quote(city)),
        ("destName", quote(dest_name)),
        ("searchWord", quote(landmark or city)),
    ]
    if landmark and landmark_code:
        search_type, landmark_id, latlng = landmark_code
        search_value = f"{search_type}|{landmark_id}*{search_type}*{latlng}|{landmark}|{landmark_id}"
        params.append(("searchType", "T"))
        params.append(("searchValue", quote(search_value)))
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
        else:
            warnings.append(f"未知排序 {sort!r}，使用默认智能排序")

    url = BASE + "?" + "&".join(f"{k}={v}" for k, v in params)
    return {"url": url, "warnings": warnings}
