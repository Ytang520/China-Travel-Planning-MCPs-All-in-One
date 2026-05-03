"""
Variflight backup tools for flight search and transfer queries.

Provides a direct API integration used as a fallback when the primary
web-scraping providers fail.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

try:
    from ..utils.cities_dict import get_airport_code, get_city_name
except ImportError:
    get_airport_code = None
    get_city_name = None


logger = logging.getLogger(__name__)

VARIFLIGHT_BASE_URL = os.getenv(
    "VARIFLIGHT_API_URL", "https://mcp.variflight.com/api/v1/mcp/data"
)
VARIFLIGHT_DATA_SOURCE = "variflight_api"


class VariflightClient:
    """Simple Variflight API client used for backup queries."""

    def __init__(self):
        self.api_key = os.getenv("VARIFLIGHT_API_KEY")
        self.base_url = os.getenv("VARIFLIGHT_API_URL", VARIFLIGHT_BASE_URL)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "User-Agent": "FlightTicketMCP/1.0",
            }
        )

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "status": "error",
                "message": "VARIFLIGHT_API_KEY 未配置，无法使用 Variflight 备选方案",
                "error_code": "VARIFLIGHT_API_KEY_MISSING",
                "data_source": VARIFLIGHT_DATA_SOURCE,
            }

        try:
            response = self.session.post(
                self.base_url,
                headers={"X-VARIFLIGHT-KEY": self.api_key},
                json={"endpoint": endpoint, "params": params},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "message": "Variflight 请求超时",
                "error_code": "VARIFLIGHT_TIMEOUT",
                "data_source": VARIFLIGHT_DATA_SOURCE,
            }
        except requests.exceptions.RequestException as exc:
            logger.error("Variflight request failed: %s", exc, exc_info=True)
            return {
                "status": "error",
                "message": f"Variflight 请求失败: {exc}",
                "error_code": "VARIFLIGHT_REQUEST_FAILED",
                "data_source": VARIFLIGHT_DATA_SOURCE,
            }
        except ValueError as exc:
            logger.error("Variflight response decode failed: %s", exc, exc_info=True)
            return {
                "status": "error",
                "message": f"Variflight 响应解析失败: {exc}",
                "error_code": "VARIFLIGHT_RESPONSE_INVALID",
                "data_source": VARIFLIGHT_DATA_SOURCE,
            }

        if payload.get("code") != 200:
            return {
                "status": "error",
                "message": payload.get("message") or "Variflight 返回失败",
                "error_code": "VARIFLIGHT_API_ERROR",
                "raw_response": payload,
                "data_source": VARIFLIGHT_DATA_SOURCE,
            }

        return {
            "status": "success",
            "message": payload.get("message", "Success"),
            "data": payload.get("data"),
            "request_id": payload.get("request_id"),
            "timestamp": payload.get("timestamp"),
            "data_source": VARIFLIGHT_DATA_SOURCE,
        }


def _lookup_code(place: str) -> Optional[str]:
    if not place:
        return None

    if len(place) == 3 and place.isascii():
        return place.upper()

    if not get_airport_code:
        return None

    code = get_airport_code(place)
    return code.upper() if code else None


def _lookup_name(place: str, fallback_code: Optional[str] = None) -> str:
    if get_city_name:
        resolved = get_city_name(place)
        if resolved:
            return resolved
    return place or fallback_code or "未知"


def _format_time_display(raw_time: str) -> str:
    if not raw_time:
        return "未知"

    try:
        dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S")
        time_part = dt.strftime("%H:%M")
        if dt.date() > datetime.strptime(raw_time[:10], "%Y-%m-%d").date():
            return f"{time_part} +1天"
        return time_part
    except ValueError:
        return raw_time


def _extract_time_part(raw_time: str) -> str:
    if not raw_time:
        return "未知"
    try:
        return datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
    except ValueError:
        return raw_time


def _format_arrival_display(raw_time: str, departure_date: str) -> str:
    if not raw_time:
        return "未知"

    try:
        arrival_dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S")
        departure_dt = datetime.strptime(departure_date, "%Y-%m-%d")
        display = arrival_dt.strftime("%H:%M")
        if arrival_dt.date() > departure_dt.date():
            return f"{display} +{(arrival_dt.date() - departure_dt.date()).days}天"
        return display
    except ValueError:
        return raw_time


def _normalize_route_flight(
    flight: Dict[str, Any], index: int, departure_date: str
) -> Dict[str, Any]:
    dep_code = flight.get("FlightDepcode") or "未知"
    arr_code = flight.get("FlightArrcode") or "未知"
    dep_name = flight.get("FlightDep") or flight.get("FlightDepAirport") or dep_code
    arr_name = flight.get("FlightArr") or flight.get("FlightArrAirport") or arr_code

    return {
        "序号": index,
        "航空公司": flight.get("FlightCompany") or "未知",
        "航班号": flight.get("FlightNo") or "未知",
        "机型": flight.get("ftype") or flight.get("generic") or "未知",
        "出发时间": _extract_time_part(flight.get("FlightDeptimePlanDate", "")),
        "出发机场": f"{dep_name} ({dep_code})",
        "出发航站楼": flight.get("FlightHTerminal") or "",
        "到达时间": _format_arrival_display(
            flight.get("FlightArrtimePlanDate", ""), departure_date
        ),
        "到达机场": f"{arr_name} ({arr_code})",
        "到达航站楼": flight.get("FlightTerminal") or "",
        "价格": "未知",
        "准点率": flight.get("OntimeRate") or "未知",
        "raw_data": flight,
    }


def _format_route_result(
    flights: List[Dict[str, Any]],
    departure_city: str,
    destination_city: str,
    departure_date: str,
) -> str:
    if not flights:
        return (
            f"😔 未找到 {departure_city} -> {destination_city} 在 {departure_date} 的航班\n"
            f"数据源: {VARIFLIGHT_DATA_SOURCE}"
        )

    output = [
        "✈️ 航班查询结果",
        f"📍 {departure_city} -> {destination_city}",
        f"📅 {departure_date}",
        f"🔢 共找到 {len(flights)} 条航班",
        f"🧾 数据源: {VARIFLIGHT_DATA_SOURCE}",
        "",
    ]

    for i, flight in enumerate(flights, 1):
        output.append(
            f"【{i}】{flight.get('航空公司', '未知')} {flight.get('航班号', '未知')}"
        )
        output.append(
            f"    🛫 {flight.get('出发时间', '未知')} {flight.get('出发机场', '未知')} {flight.get('出发航站楼', '')}"
        )
        output.append(
            f"    🛬 {flight.get('到达时间', '未知')} {flight.get('到达机场', '未知')} {flight.get('到达航站楼', '')}"
        )
        output.append(f"    💰 {flight.get('价格', '未知')}")
        output.append(f"    ⏱️ 准点率 {flight.get('准点率', '未知')}")
        output.append("")

    return "\n".join(output)


def searchFlightRoutes(
    departure_city: str, destination_city: str, departure_date: str
) -> Dict[str, Any]:
    client = VariflightClient()

    departure_code = _lookup_code(departure_city)
    destination_code = _lookup_code(destination_city)
    if not departure_code or not destination_code:
        return {
            "status": "error",
            "message": "Variflight 备选方案无法解析出发地或目的地代码",
            "error_code": "VARIFLIGHT_LOCATION_LOOKUP_FAILED",
            "data_source": VARIFLIGHT_DATA_SOURCE,
        }

    response = client.request(
        "flights",
        {
            "depcity": departure_code,
            "arrcity": destination_code,
            "date": departure_date,
        },
    )
    if response.get("status") != "success":
        return response

    raw_flights = response.get("data") or []
    if not isinstance(raw_flights, list):
        return {
            "status": "error",
            "message": "Variflight 航班查询返回了无法识别的数据格式",
            "error_code": "VARIFLIGHT_ROUTE_FORMAT_INVALID",
            "raw_response": response.get("data"),
            "data_source": VARIFLIGHT_DATA_SOURCE,
        }

    normalized_flights = [
        _normalize_route_flight(flight, index, departure_date)
        for index, flight in enumerate(raw_flights[:10], 1)
        if isinstance(flight, dict)
    ]

    departure_name = _lookup_name(departure_city, departure_code)
    destination_name = _lookup_name(destination_city, destination_code)

    return {
        "status": "success",
        "message": response.get("message") or "Variflight 航班查询成功",
        "departure_city": departure_city,
        "destination_city": destination_city,
        "departure_date": departure_date,
        "departure_airport": departure_name,
        "destination_airport": destination_name,
        "flight_count": len(normalized_flights),
        "flights": normalized_flights,
        "formatted_output": _format_route_result(
            normalized_flights,
            departure_name,
            destination_name,
            departure_date,
        ),
        "query_time": datetime.now().isoformat(),
        "request_id": response.get("request_id"),
        "fallback_used": True,
        "requested_data_source": "variflight",
        "data_source": VARIFLIGHT_DATA_SOURCE,
    }


def _calculate_transfer_hours(first_arrival: str, second_departure: str) -> float:
    try:
        arrival_dt = datetime.strptime(first_arrival, "%Y-%m-%d %H:%M:%S")
        departure_dt = datetime.strptime(second_departure, "%Y-%m-%d %H:%M:%S")
        return round((departure_dt - arrival_dt).total_seconds() / 3600, 3)
    except ValueError:
        return 0.0


def _normalize_transfer_segment(segment: Dict[str, Any], index: int) -> Dict[str, Any]:
    dep_time = segment.get("DepTime", "")
    arr_time = segment.get("ArrTime", "")

    return {
        "flight_id": str(index),
        "flight_number": segment.get("FlightNo") or "未知",
        "airline": segment.get("FlightNo", "")[:2] or "未知",
        "aircraft": "未知",
        "origin": segment.get("DepAirportCode") or segment.get("DepCityCode") or "未知",
        "destination": segment.get("ArrAirportCode")
        or segment.get("ArrCityCode")
        or "未知",
        "schedule": {
            "departure_time": _extract_time_part(dep_time),
            "arrival_time": _extract_time_part(arr_time),
            "duration": "未知",
            "timezone": "UTC+8",
        },
        "price": {
            "economy": 0.0,
            "business": 0.0,
            "first": 0.0,
            "currency": "CNY",
        },
        "seat_config": {"economy": {}, "business": {}, "first": {}},
        "services": {},
        "status": "scheduled",
        "raw_data": segment,
    }


def getTransferFlightsByThreePlace(
    from_place: str,
    transfer_place: str,
    to_place: str,
    departure_date: str,
    min_transfer_time: float,
    max_transfer_time: float,
) -> Dict[str, Any]:
    client = VariflightClient()

    from_code = _lookup_code(from_place)
    to_code = _lookup_code(to_place)
    if not from_code or not to_code:
        return {
            "status": "error",
            "message": "Variflight 备选方案无法解析始发地或目的地代码",
            "error_code": "VARIFLIGHT_LOCATION_LOOKUP_FAILED",
            "data_source": VARIFLIGHT_DATA_SOURCE,
        }

    response = client.request(
        "transfer",
        {
            "depcity": from_code,
            "arrcity": to_code,
            "depdate": departure_date,
        },
    )
    if response.get("status") != "success":
        return response

    raw_transfers = response.get("data") or []
    if not isinstance(raw_transfers, list):
        return {
            "status": "error",
            "message": "Variflight 中转查询返回了无法识别的数据格式",
            "error_code": "VARIFLIGHT_TRANSFER_FORMAT_INVALID",
            "raw_response": response.get("data"),
            "data_source": VARIFLIGHT_DATA_SOURCE,
        }

    transfers: List[Dict[str, Any]] = []
    for index, option in enumerate(raw_transfers, 1):
        if not isinstance(option, list) or len(option) < 2:
            continue

        first_segment = option[0]
        second_segment = option[1]
        if not isinstance(first_segment, dict) or not isinstance(second_segment, dict):
            continue

        transfer_city_code = second_segment.get("DepCityCode") or second_segment.get(
            "DepAirportCode"
        )
        if transfer_place:
            requested_transfer_code = _lookup_code(transfer_place)
            if (
                requested_transfer_code
                and transfer_city_code != requested_transfer_code
            ):
                continue

        transfer_hours = _calculate_transfer_hours(
            first_segment.get("ArrTime", ""), second_segment.get("DepTime", "")
        )
        if transfer_hours < min_transfer_time or transfer_hours > max_transfer_time:
            continue

        transfers.append(
            {
                "transfer_id": str(index),
                "first_flight": _normalize_transfer_segment(
                    first_segment, index * 2 - 1
                ),
                "second_flight": _normalize_transfer_segment(second_segment, index * 2),
                "departure_date": departure_date,
                "transfer_time": transfer_hours,
            }
        )

    return {
        "status": "success",
        "message": "查询成功" if transfers else "未找到符合条件的中转航班",
        "from_place": from_place,
        "transfer_place": transfer_place,
        "to_place": to_place,
        "departure_date": departure_date,
        "transfer_count": len(transfers),
        "transfers": transfers,
        "query_time": datetime.now().isoformat(),
        "request_id": response.get("request_id"),
        "fallback_used": True,
        "requested_data_source": "variflight",
        "data_source": VARIFLIGHT_DATA_SOURCE,
    }
