"""Logged-out Fliggy DOM adapter. No scrolling or private API calls are needed."""

from dataclasses import dataclass, field
import re
import time
from urllib.parse import urlencode, urlparse

from ..utils.cities_dict import get_airport_code, get_city_name

DATA_SOURCE = "fliggy_web_scraping"
PRICE_BASIS = "不含税费"


def build_search_url(departure_city, destination_city, departure_date):
    """Build a fresh one-way search, without a preselected flight from a deep link."""
    return "https://sjipiao.fliggy.com/flight_search_result.htm?" + urlencode({
        "depCity": get_airport_code(departure_city).upper(),
        "arrCity": get_airport_code(destination_city).upper(),
        "depCityName": get_city_name(departure_city).split("(")[0],
        "arrCityName": get_city_name(destination_city).split("(")[0],
        "depDate": departure_date,
        "tripType": "0",
        "mTripType": "1",
        "pcOtaMode": "1",
    })


# Selectors come from the rendered domestic flight list. Calendar/recommendation
# prices and transfer itineraries must not be interpreted as direct flight fares.
SNAPSHOT_JS = r"""
const text = (root, selector) => {
    const node = root.querySelector(selector);
    return node ? (node.innerText || '').trim() : '';
};
const value = name => document.querySelector(`input[name="${name}"]`)?.value || '';
const list = document.querySelector('#J_FlightListBox');
const bodyText = document.body?.innerText || '';
const visible = node => {
    const style = getComputedStyle(node);
    return !!node.getClientRects().length && style.display !== 'none'
        && style.visibility !== 'hidden' && style.opacity !== '0';
};
return {
    url: location.href,
    query: {
        depCity: value('depCity'), arrCity: value('arrCity'), depDate: value('depDate'),
        tripType: document.querySelector('input[name="tripType"]:checked')?.value || ''
    },
    list_present: !!list,
    loading: Array.from(document.querySelectorAll(
        '[aria-busy="true"], [role="progressbar"], [class*="loading"], [class*="Loading"], [id*="Loading"]'
    )).some(visible),
    message: (document.querySelector('.J_FlightList')?.innerText || '').slice(0, 2000),
    blocked: /访问受限|访问过于频繁|请求过于频繁|请完成.{0,8}验证|滑动.{0,8}验证|拖动.{0,8}滑块|验证码|punish|Access Denied/i.test(bodyText),
    rows: Array.from(list?.querySelectorAll('.J_FlightItem') || []).map(item => ({
        airline: text(item, '.airline-name .J_TestFlight'),
        flight_count: item.querySelectorAll('.J_TestFlight').length,
        departure: text(item, '.flight-time-deptime'),
        arrival: (item.querySelector('.flight-time .s-time')?.parentElement?.innerText || '').trim(),
        departure_airport: text(item, '.port-dep'),
        arrival_airport: text(item, '.port-arr'),
        price: text(item, '.J_FlightListPrice'),
        aircraft: text(item, '.J_FlightType'),
        transfer: item.classList.contains('transferItem') || !!item.querySelector('[data-is-transfer="1"]'),
        raw_text: (item.innerText || '').trim()
    }))
};
"""


@dataclass
class FliggyResult:
    status: str
    flights: list = field(default_factory=list)
    error: str | None = None


def _airport(value):
    value = re.sub(r"\s+", "", value)
    match = re.fullmatch(r"(.+?)(T\d+[A-Z]?)", value, re.I)
    return (match[1], match[2].upper()) if match else (value, "")


def _time(value):
    value = re.sub(r"\s+", " ", value).strip()
    match = re.fullmatch(r"((?:[01]\d|2[0-3]):[0-5]\d)(?:\s*(?:\+\s*(\d+)\s*(?:天|日)?|(次日|翌日)|第\s*([1-9]\d*)\s*[天日]))?", value)
    if not match:
        return None
    offset = int(match[2]) if match[2] else (1 if match[3] else int(match[4]) - 1 if match[4] else 0)
    return match[1] + (f" +{offset}天" if offset else "")


def parse_rows(rows):
    flights = []
    invalid = 0
    for row in rows:
        if row.get("transfer"):
            continue
        if row.get("flight_count") != 1:
            invalid += 1
            continue
        airline = row.get("airline", "")
        number = re.search(r"([A-Z0-9]{2}\s*\d{2,5})$", airline, re.I)
        departure = _time(row.get("departure", ""))
        arrival = _time(row.get("arrival", ""))
        price = row.get("price", "").strip().replace(",", "")
        dep_airport, dep_terminal = _airport(row.get("departure_airport", ""))
        arr_airport, arr_terminal = _airport(row.get("arrival_airport", ""))
        if not (number and departure and arrival and dep_airport and arr_airport
                and re.fullmatch(r"\d+(?:\.\d{1,2})?", price) and float(price) > 0):
            invalid += 1
            continue
        flights.append({
            "航空公司": airline[:number.start()].strip(),
            "航班号": re.sub(r"\s+", "", number[1]).upper(),
            "出发时间": departure, "到达时间": arrival,
            "出发机场": dep_airport, "出发航站楼": dep_terminal,
            "到达机场": arr_airport, "到达航站楼": arr_terminal,
            "价格": f"¥{price}", "价格说明": PRICE_BASIS,
            "机型": row.get("aircraft", ""),
            "原始文本": " | ".join(line.strip() for line in row.get("raw_text", "").splitlines() if line.strip()),
        })
    return flights, invalid


def collect_flights(page, departure_city, destination_city, departure_date, *, timeout=40):
    """Wait for a stable rendered list and verify its actual search form values."""
    expected = {
        "depCity": get_airport_code(departure_city).upper(),
        "arrCity": get_airport_code(destination_city).upper(),
        "depDate": departure_date, "tripType": "0",
    }
    page.get(build_search_url(departure_city, destination_city, departure_date), timeout=60)
    started = time.monotonic()
    stable_since = started
    previous = None
    last_error = "飞猪航班列表未完成渲染或页面结构已变化"
    while time.monotonic() - started < timeout:
        snapshot = page.run_js(SNAPSHOT_JS)
        if not isinstance(snapshot, dict):
            return FliggyResult("parse_failed", error="飞猪页面快照无效")
        if snapshot.get("blocked"):
            return FliggyResult("request_failed", error="飞猪页面要求验证或限制访问")
        matches = (urlparse(snapshot.get("url", "")).hostname == "sjipiao.fliggy.com"
                   and snapshot.get("query") == expected)
        if not matches:
            last_error = "无法确认飞猪页面已应用请求的城市、日期和单程条件"
        rows = snapshot.get("rows", [])
        empty = bool(re.search(r"(?:没有|暂无|未找到|未查询到|无符合).{0,12}(?:航班|机票)", snapshot.get("message", "")))
        loading = snapshot.get("loading", False)
        fingerprint = repr((matches, snapshot.get("list_present"), rows, empty, loading))
        now = time.monotonic()
        if fingerprint != previous:
            stable_since = now
            previous = fingerprint
        if matches and not loading and now - started >= 4 and now - stable_since >= 2:
            if rows and snapshot.get("list_present"):
                flights, invalid = parse_rows(rows)
                if flights and not invalid:
                    return FliggyResult("success", flights)
                if not invalid:
                    return FliggyResult("no_results")  # Only transfer itineraries.
                last_error = "飞猪航班卡片缺少有效航班号、时间、机场或价格"
            elif empty and snapshot.get("list_present"):
                return FliggyResult("no_results")
        time.sleep(1)
    return FliggyResult("parse_failed", error=last_error)
