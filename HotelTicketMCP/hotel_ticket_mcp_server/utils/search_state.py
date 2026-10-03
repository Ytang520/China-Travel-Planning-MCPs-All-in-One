"""Evidence of applied city, location and sorting, independent of input echoes."""
import re
import time
from urllib.parse import parse_qs, urlsplit
from .location_cache import normalize_name
from .location_resolver import parse_location_url
from .url_builder import ACCOMMODATION_TYPE_FILTERS, ROOM_TYPE_FILTERS

STATE_JS = r"""
const visible = el => !!(el && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
const text = selector => [...document.querySelectorAll(selector)].filter(visible).map(el => (el.innerText || '').trim()).filter(Boolean);
return {
  url: location.href,
  city: [...document.querySelectorAll('input[placeholder="目的地"]')].find(visible)?.value || '',
  chips: text('.choosen-item .choosen-name'),
  selected_filters: [...document.querySelectorAll('[role="checkbox"][aria-checked="true"], [role="radio"][aria-checked="true"]')]
    .filter(visible).map(el => el.getAttribute('aria-label') || el.innerText.trim()),
  distances: text('.hotel-list > * .position-desc'),
  sort_label: text('.dropdown-selector-title')[0] || '',
  has_list: !!document.querySelector('.hotel-list'),
  empty: /暂无符合|未找到符合|没有找到符合/.test(document.body.innerText || '')
};
"""
SORT_LABELS = {"smart": "智能排序", "distance": "直线距离", "price_asc": "低价优先", "score_desc": "好评优先"}


def read_state(page):
    state = page.run_js(STATE_JS, timeout=5)
    return state if isinstance(state, dict) else {}


def distance_anchor(text):
    match = re.search(r"距\s*(.+?)\s*(?:步行|驾车|直线)", text or "")
    return match.group(1).strip() if match else None


def request_applied(state, expected_url):
    """Reject city/date/occupancy/filter changes made by the candidate UI or sorting."""
    parsed = urlsplit(state.get("url", ""))
    if parsed.scheme != "https" or parsed.hostname != "hotels.ctrip.com" or parsed.path.rstrip("/") != "/hotels/list":
        return False
    actual = parse_qs(parsed.query)
    expected = parse_qs(urlsplit(expected_url).query)
    for key in ("cityId", "cityName", "destName", "checkin", "checkout", "crn", "adult", "child"):
        # Ctrip omits default occupancy values when it rewrites the URL.
        default = {"adult": ["2"], "child": ["0"], "crn": ["1"]}.get(key)
        if actual.get(key, default) != expected.get(key, default):
            return False
    if normalize_name(state.get("city", "")).removesuffix("市") != normalize_name(expected["cityName"][0]).removesuffix("市"):
        return False
    filters = lambda query: set(filter(None, query.get("listFilters", [""])[0].split(",")))
    wanted, found = filters(expected), filters(actual)
    if not wanted.issubset(found):
        return False
    # 17 = sorting, 29 = occupancy metadata, 30 = keyword, 80 = distance mode.
    if any(value.split("~", 1)[0] not in {"17", "29", "30", "80"} for value in found - wanted):
        return False
    labels = state.get("chips", []) + state.get("selected_filters", [])
    for choices in (ROOM_TYPE_FILTERS, ACCOMMODATION_TYPE_FILTERS):
        for label, code in choices.items():
            if code in wanted and label not in labels:
                return False
    for value in wanted:
        if value.startswith("16~"):
            star = value.split("*")[-1]
            if not any(label.startswith(star + "钻/星") or label == star + " out of 5 diamonds" for label in labels):
                return False
        if value.startswith("15~Range*15*"):
            lo, hi = value.split("*")[-1].split("~")
            prices = [label for label in labels if "¥" in label or "￥" in label]
            bounds = [bound for bound in (lo, hi) if bound not in ("0", "9999")]
            if bounds and not any(all(bound in re.findall(r"\d+", label.replace(",", "")) for bound in bounds) for label in prices):
                return False
    return True


def verify_location(state, requested, city_id, *, source="keyword", resolved=None):
    anchors = [distance_anchor(text) for text in state.get("distances", [])]
    anchors = [anchor for anchor in anchors if anchor]
    name = resolved.name if resolved else requested
    chips = state.get("chips", [])
    same = lambda value: normalize_name(value) == normalize_name(name)
    selected = any(same(chip) for chip in chips)
    anchored = bool(anchors) and all(same(anchor) for anchor in anchors)
    url_location = parse_location_url(state.get("url", ""), city_id)
    if requested is None:
        applied = True
    elif resolved:
        applied = bool(url_location and url_location.option_id == resolved.option_id
                       and url_location.entity_type == resolved.entity_type
                       and url_location.search_type == resolved.search_type
                       and same(url_location.name)
                       and selected and (not anchors or anchored))
    else:
        applied = bool((selected or anchored) and (not anchors or anchored))
    if parse_qs(urlsplit(state.get("url", "")).query).get("cityId") != [str(city_id)]:
        applied = False
    return {"status": "applied" if applied else "unverified", "requested": requested,
            "resolved_name": name if applied else None, "source": source if requested else "city",
            "landmark_id": resolved.option_id if resolved else None, "applied": applied,
            "evidence": {"city_id": str(city_id), "city_name": state.get("city", ""),
                         "selected_locations": chips, "distance_anchors": sorted(set(anchors)),
                         "url_location_id": url_location.option_id if url_location else None}}


def verify_sort(state, requested, resolution):
    actual = next((key for key, label in SORT_LABELS.items() if label in state.get("sort_label", "")), None)
    applied = actual == requested
    if requested == "distance":
        # A selected label and a confirmed location are both necessary.
        applied = applied and resolution["applied"] and bool(resolution["requested"])
        distances = state.get("distances", [])
        values = []
        for text in distances:
            match = re.search(r"直线\s*([\d.]+)\s*(公里|千米|米|km|m)", text, re.I)
            if not match:
                applied = False
                break
            values.append(float(match.group(1)) * (1000 if match.group(2).lower() in ("公里", "千米", "km") else 1))
        applied = bool(applied and (values or state.get("empty")) and values == sorted(values))
        if values and not resolution["evidence"]["distance_anchors"]:
            applied = False
    return {"requested": requested, "actual": actual, "applied": bool(applied),
            "label": state.get("sort_label", ""),
            "anchor": resolution["resolved_name"] if requested == "distance" else None}


def apply_sort(page, requested, *, timeout=15):
    state = read_state(page)
    if SORT_LABELS[requested] in state.get("sort_label", ""):
        return state
    deadline = time.monotonic() + timeout
    page.ele("css:.dropdown-selector-title", timeout=3).click(timeout=3)
    label = SORT_LABELS[requested]
    page.ele('xpath://span[@role="option" and contains(text(),"' + label + '")]', timeout=3).click(timeout=3)
    # Wait for the result cards to settle as well as the immediately updated label.
    previous = None
    stable = 0
    while time.monotonic() < deadline:
        time.sleep(0.5)
        state = read_state(page)
        signature = (state.get("sort_label"), state.get("distances"), state.get("url"))
        stable = stable + 1 if signature == previous else 0
        if label in state.get("sort_label", "") and stable >= 3:
            return state
        previous = signature
    return state


def wait_for_state(page, expected_url, requested, city_id, *, source, resolved=None, timeout=12):
    deadline = time.monotonic() + timeout
    state, resolution = {}, None
    while time.monotonic() < deadline:
        state = read_state(page)
        resolution = verify_location(state, requested, city_id, source=source, resolved=resolved)
        if request_applied(state, expected_url) and resolution["applied"] and (state.get("has_list") or state.get("empty")):
            return state, resolution
        time.sleep(0.5)
    return state, resolution or verify_location(state, requested, city_id, source=source, resolved=resolved)
