"""
Flight Search Tools - 航班路线查询工具

提供根据出发地、目的地和出发日期查询航班路线的功能
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import os
import random
import logging
from pathlib import Path
from ..utils.browser_discovery import BrowserDiscovery
from ..utils.browser_runtime import OwnedBrowser
from ..utils.search_interval import FlightSearchInterval
from . import fliggy_search
import tempfile
import time
import re

# 初始化日志器
logger = logging.getLogger(__name__)

# 导入DrissionPage（可选）
try:
    from DrissionPage import ChromiumPage, ChromiumOptions

    DRISSION_PAGE_AVAILABLE = True
except ImportError:
    logger.warning("DrissionPage未安装，航班路线查询功能将不可用")
    ChromiumPage = None
    ChromiumOptions = None
    DRISSION_PAGE_AVAILABLE = False

# 导入城市字典
try:
    from ..utils.cities_dict import get_airport_code, get_city_name
except ImportError:
    logger.warning("城市字典未找到，航班路线查询功能将不可用")
    get_airport_code = None
    get_city_name = None


# =================== 航班路线查询功能 ===================

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_FLIGHT_LIMIT = 200
CTRIP_SEARCH_URL = "https://flights.ctrip.com/online/list/oneway-{}-{}?_=1&depdate={}&cabin=Y_S_C_F"
SOURCE_NAMES = {"ctrip_web_scraping": "携程", fliggy_search.DATA_SOURCE: "飞猪"}
_SEARCH_INTERVAL = FlightSearchInterval()


def _resolve_browser_path() -> Optional[str]:
    return BrowserDiscovery(PROJECT_ROOT).resolve("FLIGHT_MCP").path


def _validate_limit(limit: Optional[int]) -> None:
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("limit must be a positive integer or None")


class FlightRouteSearcher:
    """航班路线查询器"""

    def __init__(self, headless=True):
        """
        初始化浏览器

        Args:
            headless: 是否使用无头模式
        """
        if not DRISSION_PAGE_AVAILABLE:
            raise ImportError("DrissionPage库未安装，无法使用航班路线查询功能")

        self.base_url = CTRIP_SEARCH_URL

        self._profile_dir = tempfile.mkdtemp(prefix="flightctrip-profile-")
        self._session = OwnedBrowser(
            "FLIGHT_MCP", PROJECT_ROOT, self._profile_dir, temporary=True,
        )
        self.page = self._session.open(ChromiumPage, ChromiumOptions, headless=headless)
        # 兜底：清空浏览器内全部 cookie，双保险确保航班查询永远未登录
        # （即使未来 profile 策略变化，也不会把任何登录态带进航班抓取）。
        try:
            self.page.run_cdp("Network.clearBrowserCookies")
        except Exception as e:
            logger.warning("清理浏览器 cookie 失败（可忽略）: %s", e)

        logger.info("航班路线查询器初始化完成")
        self.last_parse_status = "not_started"
        self.last_parse_error = None
        self.last_collection_stop_reason = "not_started"
        self.last_data_source = "ctrip_web_scraping"
        self.source_attempts = []
        self.fallback_used = False
        self._earliestStartTime = None
        self._latestStartTime = None
        self._earliestArrivalTime = None
        self._latestArrivalTime = None

    def search_flights(
        self, departure_city: str, destination_city: str, departure_date: str,
        earliestStartTime: Optional[int] = None,
        latestStartTime: Optional[int] = None,
        earliestArrivalTime: Optional[int] = None,
        latestArrivalTime: Optional[int] = None,
        limit: Optional[int] = DEFAULT_FLIGHT_LIMIT,
    ) -> List[Dict[str, Any]]:
        """Try Ctrip first, then one logged-out Fliggy search if no usable rows remain."""
        _validate_limit(limit)
        self.source_attempts = []
        self.fallback_used = False
        self.last_data_source = "ctrip_web_scraping"
        self.last_parse_status = "not_started"
        self.last_parse_error = None
        self.last_collection_stop_reason = "not_started"
        if not get_airport_code(departure_city) or not get_airport_code(destination_city):
            self.last_parse_status = "request_failed"
            self.last_parse_error = "城市或机场代码无效"
            return []
        try:
            datetime.strptime(departure_date, "%Y-%m-%d")
        except (TypeError, ValueError):
            self.last_parse_status = "request_failed"
            self.last_parse_error = "日期格式不正确，请使用YYYY-MM-DD格式"
            return []
        self._earliestStartTime = earliestStartTime
        self._latestStartTime = latestStartTime
        self._earliestArrivalTime = earliestArrivalTime
        self._latestArrivalTime = latestArrivalTime
        time_filters = (earliestStartTime, latestStartTime, earliestArrivalTime, latestArrivalTime)
        for source in ("ctrip_web_scraping", fliggy_search.DATA_SOURCE):
            self.last_data_source = source
            self.fallback_used = source == fliggy_search.DATA_SOURCE
            self.last_parse_status = "not_started"
            self.last_parse_error = None
            self.last_collection_stop_reason = "not_started"
            with _SEARCH_INTERVAL.search() as interval:
                try:
                    if self.fallback_used:
                        result = fliggy_search.collect_flights(
                            self.page, departure_city, destination_city, departure_date,
                        )
                        self.last_parse_status = result.status
                        self.last_parse_error = result.error
                        filtered, _ = self._client_side_time_filter(result.flights, *time_filters)
                        flights = []
                        self._append_flights(filtered, flights, set(), limit)
                        self.last_collection_stop_reason = (
                            "limit_reached" if limit is not None and len(flights) >= limit
                            else "list_stable" if result.status in {"success", "no_results"}
                            else result.status
                        )
                    else:
                        flights = self._search_ctrip(
                            departure_city, destination_city, departure_date,
                            *time_filters, limit=limit,
                        )
                        flights, _ = self._client_side_time_filter(flights, *time_filters)
                    if not flights and self.last_parse_status == "success":
                        self.last_parse_status = "no_results"
                except Exception as exc:
                    flights = []
                    self.last_parse_status = "request_failed"
                    self.last_parse_error = str(exc)
                    self.last_collection_stop_reason = "request_failed"
                    logger.warning("%s 航班查询失败: %s", source, exc)
            self.source_attempts.append({
                "data_source": source, "status": self.last_parse_status,
                "flight_count": len(flights), "error": self.last_parse_error, **interval,
            })
            if flights:
                for index, flight in enumerate(flights, 1):
                    flight["序号"] = index
                return flights
            if not self.fallback_used:
                logger.info("携程未返回可用航班，等待搜索间隔后尝试飞猪")
        return []

    def _search_ctrip(
        self,
        departure_city: str,
        destination_city: str,
        departure_date: str,
        earliestStartTime: Optional[int] = None,
        latestStartTime: Optional[int] = None,
        earliestArrivalTime: Optional[int] = None,
        latestArrivalTime: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        搜索航班

        Args:
            departure_city: 出发城市
            destination_city: 目的地城市
            departure_date: 出发日期 (YYYY-MM-DD格式)
            earliestStartTime: 最早出发小时 (0-23), None表示无限制
            latestStartTime: 最晚出发小时 (1-24), None表示无限制
            earliestArrivalTime: 最早到达小时 (0-23), None表示无限制
            latestArrivalTime: 最晚到达小时 (1-24), None表示无限制
            limit: 最多采集的有效航班数，None表示不设置数量上限

        Returns:
            航班信息列表
        """
        _validate_limit(limit)
        # Store time filter params as instance attributes for filter methods
        self._earliestStartTime = earliestStartTime
        self._latestStartTime = latestStartTime
        self._earliestArrivalTime = earliestArrivalTime
        self._latestArrivalTime = latestArrivalTime

        logger.info(
            f"开始搜索航班：{departure_city} -> {destination_city}, 日期：{departure_date}"
        )

        # 获取机场代码
        departure_code = get_airport_code(departure_city)
        destination_code = get_airport_code(destination_city)

        if not departure_code or not destination_code:
            logger.warning(
                f"无法找到机场代码：出发地={departure_city}, 目的地={destination_city}"
            )
            return []

        # 验证日期格式
        try:
            datetime.strptime(departure_date, "%Y-%m-%d")
        except ValueError:
            logger.warning(f"日期格式错误: {departure_date}")
            return []

        # 构建搜索URL
        search_url = self.base_url.format(
            departure_code, destination_code, departure_date
        )

        logger.info(f"搜索URL: {search_url}")
        logger.info(
            f"出发地：{get_city_name(departure_city)} ({departure_code.upper()})"
        )
        logger.info(
            f"目的地：{get_city_name(destination_city)} ({destination_code.upper()})"
        )

        try:
            # 访问页面
            self.page.get(search_url, timeout=180)
            # Fail promptly on a visible block instead of scrolling a challenge page.
            try:
                blocked = self.page.run_js(r"""
                    return /访问受限|访问过于频繁|请完成.{0,8}验证|滑动.{0,8}验证|验证码|Access Denied|HTTP 432/i.test(document.body?.innerText || '');
                """)
            except Exception:
                blocked = False
            if blocked:
                raise RuntimeError("携程页面要求验证或限制访问")
            logger.info("页面加载完成，等待内容渲染...")
            # 智能等待页面加载完成
            self._wait_for_page_ready()

            # 等待关键元素出现
            self._wait_for_flight_content()

            # 在滚动之前先应用时间筛选（通过"起抵时间"按钮），减少需要加载的航班数量
            has_time_filter = (
                earliestStartTime is not None
                or latestStartTime is not None
                or earliestArrivalTime is not None
                or latestArrivalTime is not None
            )
            if has_time_filter:
                self._apply_time_filter(
                    earliestStartTime,
                    latestStartTime,
                    earliestArrivalTime,
                    latestArrivalTime,
                )
                logger.info("时间筛选已应用，继续滚动加载筛选后的航班...")

            # 在滚动过程中分段采集航班，避免回到顶部后只解析到一部分虚拟列表
            flights = self._collect_flights_with_scrolling(limit=limit)

            logger.info(f"搜索完成，找到 {len(flights)} 条航班信息")
            return flights

        except Exception as e:
            self.last_parse_status = "request_failed"
            self.last_parse_error = str(e)
            logger.error(f"搜索航班失败: {str(e)}", exc_info=True)
            return []

    def _intelligent_scroll_for_content(self):
        """智能滚动以加载更多航班内容"""
        logger.debug("智能滚动加载航班内容")

        try:
            max_scroll_rounds = 12
            max_stable_rounds = 3
            stable_rounds = 0

            previous_metrics = self._get_scroll_metrics()
            scroll_distance = max(600, int(previous_metrics["viewport_height"] * 0.8))

            logger.info(
                "开始智能滚动，初始页面高度: %s，视口高度: %s，航班元素数量: %s，单次滚动距离: %s",
                previous_metrics["scroll_height"],
                previous_metrics["viewport_height"],
                previous_metrics["flight_count"],
                scroll_distance,
            )

            for round_index in range(1, max_scroll_rounds + 1):
                self.page.run_js(f"window.scrollBy(0, {scroll_distance});")
                logger.info("第%s次向下滚动 %spx", round_index, scroll_distance)
                time.sleep(2)

                self._wait_for_loading_complete(timeout=5)
                time.sleep(1)

                current_metrics = self._get_scroll_metrics()
                height_grew = (
                    current_metrics["scroll_height"] > previous_metrics["scroll_height"]
                )
                count_grew = (
                    current_metrics["flight_count"] > previous_metrics["flight_count"]
                )
                reached_bottom = current_metrics["bottom_gap"] <= 120

                logger.info(
                    "滚动后页面高度: %s，距底部: %s，航班元素数量: %s",
                    current_metrics["scroll_height"],
                    current_metrics["bottom_gap"],
                    current_metrics["flight_count"],
                )

                if height_grew or count_grew:
                    stable_rounds = 0
                else:
                    stable_rounds += 1

                previous_metrics = current_metrics

                if reached_bottom and stable_rounds >= max_stable_rounds:
                    logger.info(
                        "已到达页面底部，且连续%s轮无新增内容，停止滚动",
                        stable_rounds,
                    )
                    break

        except Exception as e:
            logger.debug("智能滚动过程中出错: %s", e)

    def _get_scroll_metrics(self) -> Dict[str, int]:
        """获取当前滚动和内容加载指标"""
        metrics = {"scroll_top": 0, "scroll_height": 0, "viewport_height": 0}

        try:
            js_metrics = self.page.run_js("""
                const doc = document.documentElement || {};
                const body = document.body || {};
                const scrollTop = window.pageYOffset || doc.scrollTop || body.scrollTop || 0;
                const viewportHeight = window.innerHeight || doc.clientHeight || 0;
                const scrollHeight = Math.max(
                    body.scrollHeight || 0,
                    doc.scrollHeight || 0,
                    body.offsetHeight || 0,
                    doc.offsetHeight || 0,
                    body.clientHeight || 0,
                    doc.clientHeight || 0
                );

                return {
                    scrollTop,
                    viewportHeight,
                    scrollHeight,
                };
            """)
            if isinstance(js_metrics, dict):
                metrics["scroll_top"] = int(js_metrics.get("scrollTop", 0) or 0)
                metrics["viewport_height"] = int(
                    js_metrics.get("viewportHeight", 0) or 0
                )
                metrics["scroll_height"] = int(js_metrics.get("scrollHeight", 0) or 0)
        except Exception as exc:
            logger.debug("获取页面滚动指标失败: %s", exc)

        try:
            flight_count = len(self.page.eles("css:.flight-item", timeout=2))
        except Exception:
            flight_count = 0

        bottom_gap = max(
            0,
            metrics["scroll_height"]
            - (metrics["scroll_top"] + metrics["viewport_height"]),
        )

        return {
            **metrics,
            "flight_count": flight_count,
            "bottom_gap": bottom_gap,
        }

    def _wait_for_flight_content(self, timeout=60):
        """等待航班内容加载"""
        logger.debug("等待航班内容加载")

        # 方法1：等待航班容器出现
        flight_container = self.page.ele("css:.body-wrapper", timeout=timeout)
        if flight_container:
            logger.debug("找到航班容器")

            # 方法2：等待航班列表出现
            flight_items = self.page.ele("css:.flight-item", timeout=10)
            if flight_items:
                logger.debug("航班列表加载完成")
            else:
                logger.debug("等待航班列表超时，尝试其他解析方法")

                # 等待可能的加载指示器消失
                self._wait_for_loading_complete()
        else:
            logger.debug("航班容器未找到")

    def _wait_for_page_ready(self, timeout=60):
        """智能等待页面完全加载"""
        logger.debug("等待页面完全加载")

        # 方法1：等待 document.readyState 为 complete
        start_time = time.time()
        while time.time() - start_time < timeout:
            ready_state = self.page.run_js("return document.readyState")
            if ready_state == "complete":
                logger.debug("页面DOM加载完成")
                break
            time.sleep(0.5)
        else:
            logger.debug("页面加载超时，继续执行")

        # 方法2：等待jQuery加载完成（如果页面使用jQuery）
        if self._wait_for_jquery_ready():
            logger.debug("jQuery加载完成")

        # 方法3：等待Ajax请求完成
        if self._wait_for_ajax_complete():
            logger.debug("Ajax请求完成")

    def _wait_for_ajax_complete(self, timeout=10):
        """等待Ajax请求完成"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # 检查是否有活跃的Ajax请求
                ajax_complete = self.page.run_js("""
                    if (typeof XMLHttpRequest !== 'undefined') {
                        return XMLHttpRequest.active === 0 || XMLHttpRequest.active === undefined;
                    }
                    return true;
                """)
                if ajax_complete:
                    return True
            except:
                pass
            time.sleep(0.2)
        return False

    def _wait_for_jquery_ready(self, timeout=10):
        """等待jQuery加载完成"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                jquery_active = self.page.run_js(
                    "return typeof jQuery !== 'undefined' && jQuery.active === 0"
                )
                if jquery_active:
                    return True
            except:
                pass
            time.sleep(0.2)
        return False

    def _wait_for_loading_complete(self, timeout=15):
        """等待加载指示器消失"""
        logger.debug("等待加载指示器消失")

        # 常见的加载指示器选择器
        loading_selectors = [
            ".loading",
            ".spinner",
            ".loader",
            "#loading",
            "[data-loading]",
            ".fa-spinner",
            ".loading-overlay",
        ]

        for selector in loading_selectors:
            try:
                # 等待加载指示器消失
                start_time = time.time()
                while time.time() - start_time < timeout:
                    loader = self.page.ele(f"css:{selector}", timeout=1)
                    if not loader:
                        break
                    time.sleep(0.5)
                else:
                    continue
                logger.debug("加载指示器 %s 已消失", selector)
                break
            except:
                continue

    def _collect_flights_with_scrolling(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """在滚动过程中采集航班，兼容分段渲染/虚拟列表"""
        _validate_limit(limit)
        collected_flights: List[Dict[str, Any]] = []
        seen_flight_keys = set()
        self.last_collection_stop_reason = "scroll_limit"

        max_scroll_rounds = 100
        max_stable_rounds = 8
        stable_rounds = 0

        try:
            initial_metrics = self._get_scroll_metrics()
            scroll_distance = max(400, int(initial_metrics["viewport_height"] * 0.8))
        except Exception:
            initial_metrics = {
                "scroll_height": 0,
                "viewport_height": 0,
                "bottom_gap": 0,
            }
            scroll_distance = 300

        initial_added = self._collect_visible_flights(
            collected_flights, seen_flight_keys, limit=limit
        )
        logger.info(
            "开始滚动采集航班，初始页面高度: %s，视口高度: %s，初始新增航班: %s",
            initial_metrics["scroll_height"],
            initial_metrics["viewport_height"],
            initial_added,
        )

        last_scroll_height = initial_metrics["scroll_height"]
        for round_index in range(1, max_scroll_rounds + 1):
            if limit is not None and len(collected_flights) >= limit:
                self.last_collection_stop_reason = "limit_reached"
                break
            try:
                self.page.run_js(f"window.scrollBy(0, {scroll_distance});")
                logger.info("第%s次向下滚动 %spx", round_index, scroll_distance)
                time.sleep(1)
                self._wait_for_loading_complete(timeout=5)
                time.sleep(1)

                current_metrics = self._get_scroll_metrics()
                new_flights = self._collect_visible_flights(
                    collected_flights, seen_flight_keys, limit=limit
                )
                if limit is not None and len(collected_flights) >= limit:
                    self.last_collection_stop_reason = "limit_reached"
                    break
                height_grew = current_metrics["scroll_height"] > last_scroll_height
                reached_bottom = current_metrics["bottom_gap"] <= 120

                logger.info(
                    "滚动后页面高度: %s，距底部: %s，当前DOM航班元素: %s，本轮新增唯一航班: %s，累计航班: %s",
                    current_metrics["scroll_height"],
                    current_metrics["bottom_gap"],
                    current_metrics["flight_count"],
                    new_flights,
                    len(collected_flights),
                )

                if height_grew or new_flights > 0:
                    stable_rounds = 0
                else:
                    stable_rounds += 1

                last_scroll_height = current_metrics["scroll_height"]

                if reached_bottom and stable_rounds >= max_stable_rounds:
                    self.last_collection_stop_reason = "list_stable"
                    logger.info(
                        "已到达页面底部，且连续%s轮无新增内容，停止采集",
                        stable_rounds,
                    )
                    break
            except Exception as e:
                self.last_collection_stop_reason = "scroll_error"
                logger.warning("第%s次滚动采集失败: %s", round_index, e)
                break

        if collected_flights:
            self.last_parse_status = "success"
            self.last_parse_error = None
            logger.info("滚动采集完成: requested_limit=%s, returned_count=%s, stop_reason=%s",
                        limit, len(collected_flights), self.last_collection_stop_reason)
            return collected_flights

        logger.info("滚动采集未获得有效航班，回退到当前视口直接解析")
        flights = self._parse_flights(limit=limit)
        self.last_collection_stop_reason = (
            "limit_reached" if limit is not None and len(flights) >= limit else "fallback_parse"
        )
        logger.info("兜底采集完成: requested_limit=%s, returned_count=%s, stop_reason=%s",
                    limit, len(flights), self.last_collection_stop_reason)
        return flights

    def _collect_visible_flights(
        self, collected_flights: List[Dict[str, Any]], seen_flight_keys: set,
        limit: Optional[int] = None,
    ) -> int:
        """采集当前视口内可见航班并去重"""
        return self._append_flights(
            self._snapshot_visible_flights(), collected_flights, seen_flight_keys, limit
        )

    def _append_flights(
        self, visible_flights: List[Dict[str, Any]], collected_flights: List[Dict[str, Any]],
        seen_flight_keys: set, limit: Optional[int] = None,
    ) -> int:
        # Filter before counting a bounded sample so rejected rows do not consume the limit.
        if limit is not None:
            visible_flights, _ = self._client_side_time_filter(
                visible_flights, self._earliestStartTime, self._latestStartTime,
                self._earliestArrivalTime, self._latestArrivalTime,
            )
        new_flight_count = 0
        for flight_info in visible_flights:
            if limit is not None and len(collected_flights) >= limit:
                break
            try:
                if (
                    not flight_info
                    or not flight_info.get("航班号")
                    or flight_info.get("航班号") == "未知"
                ):
                    continue

                if limit is not None:
                    time_pattern = r"(?:[01]\d|2[0-3]):[0-5]\d(?:\s*\+\d+天)?"
                    if not (
                        re.fullmatch(r"[A-Z0-9]{2}\s*\d{2,5}", str(flight_info["航班号"]), re.I)
                        and re.fullmatch(time_pattern, str(flight_info.get("出发时间", "")))
                        and re.fullmatch(time_pattern, str(flight_info.get("到达时间", "")))
                    ):
                        continue

                flight_key = self._build_flight_key(flight_info)
                if flight_key in seen_flight_keys:
                    continue

                flight_info["序号"] = len(collected_flights) + 1
                collected_flights.append(flight_info)
                seen_flight_keys.add(flight_key)
                new_flight_count += 1
            except Exception as e:
                logger.debug("采集当前视口航班时出错: %s", e)

        return new_flight_count

    def _snapshot_visible_flights(self) -> List[Dict[str, Any]]:
        """在浏览器上下文中一次性抓取当前视口的航班快照，避免元素句柄失效"""
        try:
            flight_data = self.page.run_js("""
                const extractText = (item, selector) => {
                    const el = item.querySelector(selector);
                    return el ? (el.innerText || el.textContent || '').trim() : '';
                };

                const extractFlightNo = (item) => {
                    const directText = extractText(item, '.plane-No');
                    const directMatch = directText.match(/([A-Z0-9]{2}\\d{3,5})/);
                    if (directMatch) {
                        return directMatch[1];
                    }

                    const airlineId = item.querySelector('.airline-name span')?.id || '';
                    const airlineIdMatch = airlineId.match(/airlineName([A-Z0-9]{2}\\d{3,5})_/);
                    if (airlineIdMatch) {
                        return airlineIdMatch[1];
                    }

                    const html = item.innerHTML || '';
                    const htmlMatch = html.match(/(?:airlineName|comfort-|flightInfo-)([A-Z0-9]{2}\\d{3,5})_/);
                    return htmlMatch ? htmlMatch[1] : '';
                };

                const extractAirport = (item, boxSelector) => ({
                    name: extractText(item, `${boxSelector} .airport .name`),
                    terminal: extractText(item, `${boxSelector} .airport .terminal`),
                });

                return Array.from(document.querySelectorAll('.body-wrapper .flight-item')).map((item, index) => {
                    const lines = (item.innerText || '')
                        .split('\\n')
                        .map(line => line.trim())
                        .filter(Boolean);

                    const departAirport = extractAirport(item, '.depart-box');
                    const arriveAirport = extractAirport(item, '.arrive-box');
                    const priceText = extractText(item, '.price');
                    const airlineText = extractText(item, '.airline-name span');
                    const fallbackAirline = lines.find(
                        line => line.includes('航空') && !/\\d{2}:\\d{2}/.test(line)
                    ) || '';
                    const arrivalTime = extractText(item, '.arrive-box .time').replace(/\\s+/g, ' ').trim();

                    return {
                        '序号': index + 1,
                        '航空公司': airlineText || fallbackAirline,
                        '航班号': extractFlightNo(item),
                        '出发时间': extractText(item, '.depart-box .time'),
                        '出发机场': departAirport.name,
                        '出发航站楼': departAirport.terminal,
                        '到达时间': arrivalTime,
                        '到达机场': arriveAirport.name,
                        '到达航站楼': arriveAirport.terminal,
                        '价格': priceText,
                        '原始文本': lines.join(' | '),
                    };
                });
            """)
        except Exception as e:
            logger.debug("获取当前视口航班快照失败: %s", e)
            return []

        if not isinstance(flight_data, list):
            return []

        return [item for item in flight_data if isinstance(item, dict)]

    def _build_flight_key(self, flight_info: Dict[str, Any]) -> str:
        """构建航班去重键，避免滚动过程中重复采集同一条航班"""
        return "|".join(
            [
                str(flight_info.get("航班号", "")),
                str(flight_info.get("出发时间", "")),
                str(flight_info.get("到达时间", "")),
                str(flight_info.get("出发机场", "")),
                str(flight_info.get("到达机场", "")),
            ]
        )

    def _parse_flights(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """解析航班信息"""
        _validate_limit(limit)
        flights = []

        try:
            flight_containers = self._snapshot_visible_flights()
            if not flight_containers:
                self.last_parse_status = "parse_failed"
                self.last_parse_error = "未找到航班列表容器，页面结构可能已变化"
                logger.warning("未找到航班容器")
                return []

            logger.info(f"找到 {len(flight_containers)} 个航班容器")
            self._append_flights(flight_containers, flights, set(), limit)

            logger.info(f"成功找到 {len(flights)} 个有航班号的航班")
            self.last_parse_status = "success" if flights else "no_results"
            self.last_parse_error = None
            return flights

        except Exception as e:
            self.last_parse_status = "parse_failed"
            self.last_parse_error = str(e)
            logger.error(f"解析航班信息失败: {str(e)}", exc_info=True)
            return []

    def _parse_flight_container(
        self, container, index: int
    ) -> Optional[Dict[str, Any]]:
        """
        解析单个航班容器

        Args:
            container: 航班容器元素
            index: 航班序号

        Returns:
            航班信息字典
        """
        flight_info = {"序号": index}

        try:
            try:
                raw_container_text = container.text
            except Exception:
                raw_container_text = ""

            container_lines = self._split_flight_text_lines(raw_container_text)
            container_text = " | ".join(container_lines)

            # 优先使用文本快照解析，减少滚动过程中的元素句柄失效问题
            airline_name = next(
                (
                    line
                    for line in container_lines
                    if "航空" in line and not re.search(r"\d{2}:\d{2}", line)
                ),
                None,
            )
            if airline_name:
                flight_info["航空公司"] = airline_name

            flight_match = re.search(r"([A-Z0-9]{2}\d{3,5})", container_text)
            if flight_match:
                flight_info["航班号"] = flight_match.group(1)

            time_matches = re.findall(r"\b\d{2}:\d{2}\b", container_text)
            if len(time_matches) >= 1:
                flight_info["出发时间"] = time_matches[0]
            if len(time_matches) >= 2:
                arrival_time = time_matches[1]
                if "+1天" in container_text and "+1天" not in arrival_time:
                    arrival_time = f"{arrival_time} +1天"
                flight_info["到达时间"] = arrival_time

            airport_lines = [line for line in container_lines if "机场" in line]
            if len(airport_lines) >= 1:
                departure_airport, departure_terminal = (
                    self._extract_airport_and_terminal(airport_lines[0])
                )
                flight_info["出发机场"] = departure_airport
                if departure_terminal:
                    flight_info["出发航站楼"] = departure_terminal
            if len(airport_lines) >= 2:
                arrival_airport, arrival_terminal = self._extract_airport_and_terminal(
                    airport_lines[1]
                )
                flight_info["到达机场"] = arrival_airport
                if arrival_terminal:
                    flight_info["到达航站楼"] = arrival_terminal

            price_match = re.search(r"(¥\d+\s*起?)", container_text)
            if price_match:
                flight_info["价格"] = price_match.group(1).replace(" ", "")
            else:
                numeric_price_match = re.search(r"¥?(\d{3,5})", container_text)
                if numeric_price_match:
                    flight_info["价格"] = f"¥{numeric_price_match.group(1)}"

            # 检查是否有足够的信息
            if any(key in flight_info for key in ["航班号", "出发时间", "价格"]):
                return flight_info
            else:
                logger.debug(f"航班 {index} 缺少必要信息")
                return None

        except Exception as e:
            logger.error(f"解析航班容器 {index} 详细信息失败: {str(e)}")
            return None

    def _split_flight_text_lines(self, raw_text: str) -> List[str]:
        """将航班卡片文本拆分成稳定的文本片段"""
        if not raw_text:
            return []

        normalized_text = raw_text.replace("\r", "\n").replace("|", "\n")
        return [line.strip() for line in normalized_text.split("\n") if line.strip()]

    def _extract_airport_and_terminal(self, airport_text: str) -> tuple[str, str]:
        """从机场文本中拆分机场名称和航站楼"""
        normalized_text = airport_text.strip()
        match = re.match(r"(.+?机场)(T\d+)?$", normalized_text)
        if not match:
            return normalized_text, ""

        return match.group(1), match.group(2) or ""

    def _apply_time_filter(
        self,
        earliestStartTime=None,
        latestStartTime=None,
        earliestArrivalTime=None,
        latestArrivalTime=None,
    ):
        """Apply time filter via Ctrip's "起抵时间" filter panel UI.

        Clicks the "起抵时间" button to reveal a panel with departure/arrival
        time tabs. Maps integer hour ranges to Ctrip's 3 discrete time period
        buttons:
        - [6,12) → "上午 6~12点"
        - [12,18) → "下午 12~18点"
        - [18,24) → "晚上 18~24点"

        Handles multi-button ranges (clicks all overlapping period buttons).
        For arrival time, switches to "抵达时段" tab before clicking.
        Gracefully degrades if the filter button is not found.

        Args:
            earliestStartTime: Earliest departure hour (0-23), None for no lower bound
            latestStartTime: Latest departure hour (1-24), None for no upper bound
            earliestArrivalTime: Earliest arrival hour (0-23), None for no lower bound
            latestArrivalTime: Latest arrival hour (1-24), None for no upper bound
        """
        departure_periods = self._get_time_periods(earliestStartTime, latestStartTime)
        arrival_periods = self._get_time_periods(earliestArrivalTime, latestArrivalTime)

        if not departure_periods and not arrival_periods:
            logger.debug("No time filter periods to apply")
            return

        # Open the "起抵时间" filter panel
        try:
            filter_btn = self.page.ele("text:起抵时间", timeout=5)
            if not filter_btn:
                logger.warning(
                    "'起抵时间' filter button not found, skipping time filter"
                )
                return
            filter_btn.click()
            logger.info("Clicked '起抵时间' filter button")
            time.sleep(1)
        except Exception as e:
            logger.warning(
                "Failed to click '起抵时间' button: %s, skipping time filter", e
            )
            return

        # Apply departure time filter (default "起飞时段" tab is active)
        if departure_periods:
            self._click_time_periods(departure_periods, "departure")

        # Apply arrival time filter (switch to "抵达时段" tab first)
        if arrival_periods:
            try:
                arrival_tab = self.page.ele("text:抵达时段", timeout=3)
                if arrival_tab:
                    arrival_tab.click()
                    logger.info("Switched to '抵达时段' tab")
                    time.sleep(0.5)
                    self._click_time_periods(arrival_periods, "arrival")
                else:
                    logger.warning(
                        "'抵达时段' tab not found, skipping arrival time filter"
                    )
            except Exception as e:
                logger.warning("Failed to switch to arrival tab: %s", e)

        # Wait for filter to be applied and page to refresh
        time.sleep(2)
        self._wait_for_loading_complete(timeout=10)
        logger.info(
            "Time filter applied: departure=%s, arrival=%s",
            departure_periods,
            arrival_periods,
        )

    def _click_time_periods(self, periods, label):
        """Click a list of time period buttons on the filter panel.

        Args:
            periods: List of Chinese period labels (e.g. ['上午 6~12点'])
            label: Debug label for logging ('departure' or 'arrival')
        """
        for period in periods:
            try:
                btn = self.page.ele(f"text:{period}", timeout=3)
                if btn:
                    btn.click()
                    logger.info("Clicked %s period: %s", label, period)
                    time.sleep(0.5)
                else:
                    logger.warning("%s period button not found: %s", label, period)
            except Exception as e:
                logger.warning("Failed to click %s period '%s': %s", label, period, e)

    @staticmethod
    def _get_time_periods(earliest, latest):
        """Determine which Ctrip time period buttons overlap with [earliest, latest).

        Maps the integer hour range to Ctrip's 3 discrete buttons:
        - [6, 12) → 上午 6~12点
        - [12, 18) → 下午 12~18点
        - [18, 24) → 晚上 18~24点

        Args:
            earliest: Earliest hour (inclusive), None for 0
            latest: Latest hour (exclusive), None for 24

        Returns:
            List of Chinese period label strings to click.
        """
        if earliest is None and latest is None:
            return []

        effective_earliest = earliest if earliest is not None else 0
        effective_latest = latest if latest is not None else 24

        periods = []
        # [6, 12) → 上午 — overlap when effective_earliest < 12 and effective_latest > 6
        if effective_earliest < 12 and effective_latest > 6:
            periods.append("上午 6~12点")
        # [12, 18) → 下午
        if effective_earliest < 18 and effective_latest > 12:
            periods.append("下午 12~18点")
        # [18, 24) → 晚上
        if effective_earliest < 24 and effective_latest > 18:
            periods.append("晚上 18~24点")

        return periods

    def _client_side_time_filter(
        self,
        flights: List[Dict[str, Any]],
        earliestStartTime: Optional[int] = None,
        latestStartTime: Optional[int] = None,
        earliestArrivalTime: Optional[int] = None,
        latestArrivalTime: Optional[int] = None,
    ):
        """Fallback client-side time filter when UI interaction fails.

        Filters already-scraped flights by departure/arrival hour as a
        post-processing step. Used when the Ctrip "起抵时间" filter panel
        cannot be interacted with (e.g., button not found or click failed).

        Flight dict format (from _snapshot_visible_flights):
            {"出发时间": "14:30", "到达时间": "16:45 +1天", ...}

        Args:
            flights: List of flight dicts to filter
            earliestStartTime: Earliest departure hour (0-23), None for no lower bound
            latestStartTime: Latest departure hour (1-24), None for no upper bound
            earliestArrivalTime: Earliest arrival hour (0-23), None for no lower bound
            latestArrivalTime: Latest arrival hour (1-24), None for no upper bound

        Returns:
            Tuple of (filtered_flights, warnings_list)
            Warnings list contains messages when range spans multiple time periods.
        """
        warnings = []

        has_departure_filter = (
            earliestStartTime is not None or latestStartTime is not None
        )
        has_arrival_filter = (
            earliestArrivalTime is not None or latestArrivalTime is not None
        )

        if not has_departure_filter and not has_arrival_filter:
            return flights, warnings

        logger.warning(
            "Client-side time filtering activated (UI interaction failed or skipped). "
            "Filtering %d flights by departure/arrival hour.",
            len(flights),
        )

        # Warn if range spans multiple time periods (reuses _get_time_periods logic)
        if has_departure_filter:
            dep_periods = self._get_time_periods(earliestStartTime, latestStartTime)
            if len(dep_periods) > 1:
                msg = (
                    f"Departure time range [{earliestStartTime}, {latestStartTime}) "
                    f"spans multiple periods: {dep_periods}"
                )
                logger.warning(msg)
                warnings.append(msg)

        if has_arrival_filter:
            arr_periods = self._get_time_periods(earliestArrivalTime, latestArrivalTime)
            if len(arr_periods) > 1:
                msg = (
                    f"Arrival time range [{earliestArrivalTime}, {latestArrivalTime}) "
                    f"spans multiple periods: {arr_periods}"
                )
                logger.warning(msg)
                warnings.append(msg)

        def _parse_hour(time_str: Optional[str]) -> Optional[int]:
            """Parse the hour from a time string like '14:30' or '16:45 +1天'."""
            if not time_str:
                return None
            clean = str(time_str).replace(" +1天", "").replace("+1天", "").strip()
            match = re.match(r"(\d{1,2}):", clean)
            if match:
                return int(match.group(1))
            return None

        filtered = []
        for flight in flights:
            # Filter by departure hour
            if has_departure_filter:
                dep_hour = _parse_hour(flight.get("出发时间"))
                if dep_hour is not None:
                    if earliestStartTime is not None and dep_hour < earliestStartTime:
                        continue
                    if latestStartTime is not None and dep_hour >= latestStartTime:
                        continue

            # Filter by arrival hour
            if has_arrival_filter:
                arr_hour = _parse_hour(flight.get("到达时间"))
                if arr_hour is not None:
                    if (
                        earliestArrivalTime is not None
                        and arr_hour < earliestArrivalTime
                    ):
                        continue
                    if latestArrivalTime is not None and arr_hour >= latestArrivalTime:
                        continue

            filtered.append(flight)

        logger.info(
            "Client-side time filter: %d → %d flights after filtering",
            len(flights),
            len(filtered),
        )

        return filtered, warnings

    def close(self):
        self._session.close()


def _failure_source_details(searcher=None) -> Dict[str, Any]:
    """Keep attempted providers diagnostic-only when no result can be returned."""
    attempts = getattr(searcher, "source_attempts", [])
    last_source = attempts[-1]["data_source"] if attempts else None
    return {
        "data_source": last_source or "system",
        "data_source_name": None,
        "source_url": None,
        "source_attribution": None,
        "last_attempted_data_source": last_source,
        "last_attempted_data_source_name": SOURCE_NAMES.get(last_source),
        "fallback_used": any(a["data_source"] == fliggy_search.DATA_SOURCE for a in attempts),
        "source_attempts": attempts,
    }


def searchFlightRoutes(
    departure_city: str,
    destination_city: str,
    departure_date: str,
    data_source_preference: str = "auto",
    earliestStartTime: Optional[int] = None,
    latestStartTime: Optional[int] = None,
    earliestArrivalTime: Optional[int] = None,
    latestArrivalTime: Optional[int] = None,
    limit: Optional[int] = DEFAULT_FLIGHT_LIMIT,
) -> Dict[str, Any]:
    """
    根据出发地、目的地和出发日期查询航班路线

    Args:
        departure_city: 出发城市名称或机场代码
        destination_city: 目的地城市名称或机场代码
        departure_date: 出发日期 (YYYY-MM-DD格式)
        data_source_preference: 数据源偏好 ("auto", "default")
        earliestStartTime: 最早出发小时 (0-23), None表示无限制
        latestStartTime: 最晚出发小时 (1-24), None表示无限制
        earliestArrivalTime: 最早到达小时 (0-23), None表示无限制
        latestArrivalTime: 最晚到达小时 (1-24), None表示无限制
        limit: 单次查询最多返回的有效航班数，默认200，可按需指定任意正整数；None表示不限，各次调用独立计数

    Returns:
        包含航班查询结果的字典
    """
    _validate_limit(limit)
    if earliestStartTime is not None and not (0 <= earliestStartTime <= 23):
        raise ValueError("earliestStartTime must be between 0 and 23")
    if latestStartTime is not None and not (1 <= latestStartTime <= 24):
        raise ValueError("latestStartTime must be between 1 and 24")
    if earliestArrivalTime is not None and not (0 <= earliestArrivalTime <= 23):
        raise ValueError("earliestArrivalTime must be between 0 and 23")
    if latestArrivalTime is not None and not (1 <= latestArrivalTime <= 24):
        raise ValueError("latestArrivalTime must be between 1 and 24")

    logger.info(
        f"开始查询航班路线: {departure_city} -> {destination_city}, 日期: {departure_date}, 数据源偏好: {data_source_preference}"
    )

    normalized_preference = (data_source_preference or "auto").strip().lower()
    if normalized_preference == "variflight":
        return {
            "status": "error",
            "message": "VariFlight 数据源已下线，请使用 auto/default（携程网页，飞猪备用）",
            "error_code": "DATA_SOURCE_REMOVED",
            **_failure_source_details(),
        }
    if normalized_preference not in {"auto", "default"}:
        return {
            "status": "error",
            "message": "data_source_preference 仅支持 auto、default",
            "error_code": "INVALID_DATA_SOURCE_PREFERENCE",
            **_failure_source_details(),
        }

    searcher = None
    try:
        # 验证输入参数
        if not departure_city or not destination_city or not departure_date:
            logger.warning("参数不完整")
            return {
                "status": "error",
                "message": "出发地、目的地和出发日期都不能为空",
                "error_code": "INVALID_PARAMS",
                **_failure_source_details(),
            }

        # 检查依赖是否可用
        if not DRISSION_PAGE_AVAILABLE:
            logger.error("DrissionPage库未安装")
            return {
                "status": "error",
                "message": "DrissionPage库未安装，无法进行航班搜索",
                "error_code": "DRISSION_PAGE_NOT_AVAILABLE",
                **_failure_source_details(),
            }

        if not get_airport_code or not get_city_name:
            logger.error("城市字典未找到")
            return {
                "status": "error",
                "message": "城市字典未找到，无法进行航班搜索",
                "error_code": "CITIES_DICT_NOT_AVAILABLE",
                **_failure_source_details(),
            }

        # 验证日期格式
        try:
            flight_date = datetime.strptime(departure_date, "%Y-%m-%d")
            logger.debug(f"日期解析成功: {flight_date}")
        except ValueError:
            logger.warning(f"日期格式错误: {departure_date}")
            return {
                "status": "error",
                "message": "日期格式不正确，请使用YYYY-MM-DD格式",
                "error_code": "INVALID_DATE_FORMAT",
                **_failure_source_details(),
            }

        # 检查日期是否为过去的日期
        if flight_date.date() < datetime.now().date():
            logger.warning(f"查询过去的日期: {departure_date}")
            return {
                "status": "error",
                "message": "不能查询过去的日期",
                "error_code": "PAST_DATE",
                **_failure_source_details(),
            }

        # 验证城市/机场代码
        if not get_airport_code(departure_city):
            logger.warning(f"无效的出发地: {departure_city}")
            return {
                "status": "error",
                "message": f"无效的出发地: {departure_city}",
                "error_code": "INVALID_DEPARTURE_CITY",
                **_failure_source_details(),
            }

        if not get_airport_code(destination_city):
            logger.warning(f"无效的目的地: {destination_city}")
            return {
                "status": "error",
                "message": f"无效的目的地: {destination_city}",
                "error_code": "INVALID_DESTINATION_CITY",
                **_failure_source_details(),
            }

        # 创建搜索器并搜索
        # 携程 WAF（whaleguard）会拦截无头浏览器，因此默认使用可见浏览器；
        # 设置 FLIGHT_MCP_HEADLESS=1 可切回无头模式。
        searcher = FlightRouteSearcher(
            headless=os.environ.get("FLIGHT_MCP_HEADLESS", "0") == "1"
        )

        try:
            flights = searcher.search_flights(
                departure_city,
                destination_city,
                departure_date,
                earliestStartTime=earliestStartTime,
                latestStartTime=latestStartTime,
                earliestArrivalTime=earliestArrivalTime,
                latestArrivalTime=latestArrivalTime,
                limit=limit,
            )

            # Apply time filters if any time params are provided
            time_filter_warnings = []
            has_time_filter = any(
                x is not None
                for x in [
                    earliestStartTime,
                    latestStartTime,
                    earliestArrivalTime,
                    latestArrivalTime,
                ]
            )
            if has_time_filter:
                # Client-side time filter for precision / fallback
                # (UI filter already applied inside search_flights() before scrolling)
                flights, time_filter_warnings = searcher._client_side_time_filter(
                    flights,
                    earliestStartTime,
                    latestStartTime,
                    earliestArrivalTime,
                    latestArrivalTime,
                )

            # merged_flights = _merge_codeshare_flights(flights)
            merged_flights = flights

            if searcher.last_parse_status in {"request_failed", "parse_failed"}:
                return {
                    "status": "error",
                    "message": searcher.last_parse_error or "航班页面抓取失败",
                    "error_code": "SCRAPING_FAILED",
                    "departure_city": departure_city,
                    "destination_city": destination_city,
                    "departure_date": departure_date,
                    "query_time": datetime.now().astimezone().isoformat(),
                    "requested_data_source": normalized_preference,
                    **_failure_source_details(searcher),
                }

            # 格式化结果
            source_name = SOURCE_NAMES[searcher.last_data_source]
            is_fliggy = searcher.last_data_source == fliggy_search.DATA_SOURCE
            source_url = (
                fliggy_search.build_search_url(departure_city, destination_city, departure_date)
                if is_fliggy else CTRIP_SEARCH_URL.format(
                    get_airport_code(departure_city).lower(),
                    get_airport_code(destination_city).lower(), departure_date,
                )
            )
            source_attribution = f"{'数据' if merged_flights else '查询'}来源：{source_name}"
            if is_fliggy and merged_flights:
                source_attribution += f"（票价{fliggy_search.PRICE_BASIS}）"
            result = {
                "status": "success",
                "departure_city": departure_city,
                "destination_city": destination_city,
                "departure_date": departure_date,
                "departure_airport": get_city_name(departure_city),
                "destination_airport": get_city_name(destination_city),
                "flight_count": len(merged_flights),
                "requested_limit": limit,
                "collection_stop_reason": searcher.last_collection_stop_reason,
                "statistics_scope": "returned_flights",
                "raw_flight_count": len(flights),
                "flights": merged_flights,
                "formatted_output": _format_route_result(
                    merged_flights, departure_city, destination_city, departure_date
                ),
                "query_time": datetime.now().astimezone().isoformat(),
                "fallback_used": searcher.fallback_used,
                "requested_data_source": normalized_preference,
                "data_source": searcher.last_data_source,
                "data_source_name": source_name,
                "source_url": source_url,
                "source_attribution": source_attribution,
                "source_attempts": searcher.source_attempts,
                "time_filter_warnings": time_filter_warnings,
            }

            # 添加统计信息
            if merged_flights:
                prices = []
                airlines = {}

                for flight in merged_flights:
                    # 提取价格
                    if "价格" in flight and flight["价格"] != "未知":
                        parsed_price = _extract_price_value(flight["价格"])
                        if parsed_price is not None:
                            prices.append(parsed_price)

                    # 统计航空公司
                    airline = flight.get("航空公司", "未知")
                    airlines[airline] = airlines.get(airline, 0) + 1

                if prices:
                    result["price_statistics"] = {
                        "min_price": min(prices),
                        "max_price": max(prices),
                        "avg_price": round(sum(prices) / len(prices), 2),
                    }

                if airlines:
                    result["airline_statistics"] = airlines

            result["formatted_output"] = (
                f"{source_attribution}\n查询时间：{result['query_time']}\n"
                f"查询链接：{source_url}\n\n{result['formatted_output']}"
            )
            if is_fliggy:
                result["price_basis"] = fliggy_search.PRICE_BASIS

            logger.info(
                "航班路线查询成功: 原始航班 %s 条，合并后独立航班 %s 条",
                len(flights),
                len(merged_flights),
            )
            return result

        finally:
            searcher.close()

    except Exception as e:
        logger.error(f"查询航班路线失败: {str(e)}", exc_info=True)
        primary_error = {
            "status": "error",
            "message": f"查询航班路线失败: {str(e)}",
            "error_code": getattr(e, "code", "SEARCH_FAILED"),
            "requested_data_source": normalized_preference,
            **_failure_source_details(searcher),
        }
        return primary_error


def _format_route_result(
    flights: List[Dict[str, Any]],
    departure_city: str,
    destination_city: str,
    departure_date: str,
) -> str:
    """
    格式化航班路线查询结果

    Args:
        flights: 航班列表
        departure_city: 出发城市
        destination_city: 目的地城市
        departure_date: 出发日期

    Returns:
        格式化后的字符串
    """
    if not flights:
        return f"😔 未找到 {departure_city} -> {destination_city} 在 {departure_date} 的航班"

    output = []
    output.append(f"✈️ 航班查询结果")
    output.append(
        f"📍 {get_city_name(departure_city)} -> {get_city_name(destination_city)}"
    )
    output.append(f"📅 {departure_date}")
    output.append(f"🔢 共找到 {len(flights)} 条航班")
    output.append("")

    # 显示航班列表
    for i, flight in enumerate(flights, 1):
        output.append(
            f"【{i}】{flight.get('航空公司', '未知')} {flight.get('航班号', '未知')}"
        )
        if flight.get("是否共享航班"):
            output.append(
                f"    🔗 共享航班 {flight.get('共享航班数', 1)} 个：{flight.get('关联航班号', '')}"
            )
        output.append(
            f"    🛫 {flight.get('出发时间', '未知')} {flight.get('出发机场', '未知')} {flight.get('出发航站楼', '')}"
        )
        output.append(
            f"    🛬 {flight.get('到达时间', '未知')} {flight.get('到达机场', '未知')} {flight.get('到达航站楼', '')}"
        )
        output.append(f"    💰 {flight.get('价格', '未知')}")
        output.append("")

    return "\n".join(output)


def _merge_codeshare_flights(flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并共享航班，输出更接近独立执飞航班数"""
    if not flights:
        return []

    grouped_flights: Dict[str, List[Dict[str, Any]]] = {}
    for flight in flights:
        flight_group_key = _build_independent_flight_key(flight)
        grouped_flights.setdefault(flight_group_key, []).append(flight)

    merged_flights: List[Dict[str, Any]] = []
    for group in grouped_flights.values():
        merged_flights.append(_merge_flight_group(group, len(merged_flights) + 1))

    return merged_flights


def _build_independent_flight_key(flight: Dict[str, Any]) -> str:
    """构建更接近实际独立航班的分组键"""
    raw_text = str(flight.get("原始文本", ""))
    route_type = "transfer" if "中转" in raw_text else "direct"
    route_signature = _extract_route_signature(raw_text)

    return "|".join(
        [
            route_type,
            route_signature,
            str(flight.get("出发时间", "")),
            str(flight.get("到达时间", "")),
            str(flight.get("出发机场", "")),
            str(flight.get("出发航站楼", "")),
            str(flight.get("到达机场", "")),
            str(flight.get("到达航站楼", "")),
        ]
    )


def _merge_flight_group(
    group: List[Dict[str, Any]], merged_index: int
) -> Dict[str, Any]:
    """合并同一独立航班下的多个共享航班"""
    primary_flight = dict(group[0])
    primary_flight["序号"] = merged_index

    unique_airlines = []
    unique_flight_numbers = []
    price_values = []

    for flight in group:
        airline = str(flight.get("航空公司", "")).strip()
        flight_no = str(flight.get("航班号", "")).strip()

        if airline and airline not in unique_airlines:
            unique_airlines.append(airline)
        if flight_no and flight_no not in unique_flight_numbers:
            unique_flight_numbers.append(flight_no)

        parsed_price = _extract_price_value(flight.get("价格"))
        if parsed_price is not None:
            price_values.append(parsed_price)

    primary_flight["是否共享航班"] = len(unique_flight_numbers) > 1
    primary_flight["共享航班数"] = len(unique_flight_numbers)
    primary_flight["共享航空公司"] = unique_airlines
    primary_flight["共享航班号"] = unique_flight_numbers
    primary_flight["关联航空公司"] = "、".join(unique_airlines)
    primary_flight["关联航班号"] = "、".join(unique_flight_numbers)

    if len(unique_airlines) > 1 and not primary_flight.get("航空公司"):
        primary_flight["航空公司"] = unique_airlines[0]

    if price_values:
        min_price = min(price_values)
        max_price = max(price_values)
        primary_flight["最低价格"] = min_price
        primary_flight["最高价格"] = max_price
        if min_price == max_price:
            primary_flight["价格"] = f"¥{min_price}起"
        else:
            primary_flight["价格"] = f"¥{min_price}-{max_price}起"

    return primary_flight


def _extract_price_value(price: Any) -> Optional[int | float]:
    """从价格文本中提取数值"""
    if price is None:
        return None

    match = re.search(r"\d+(?:,\d{3})*(?:\.\d{1,2})?", str(price))
    if not match:
        return None

    number = match.group(0).replace(",", "")
    return float(number) if "." in number else int(number)


def _extract_route_signature(raw_text: str) -> str:
    """提取中转/经停摘要，避免不同中转方案被误合并"""
    if not raw_text:
        return ""

    route_parts = []
    for part in str(raw_text).split("|"):
        normalized_part = part.strip()
        if not normalized_part:
            continue
        if any(keyword in normalized_part for keyword in ["中转", "经停", "转"]):
            route_parts.append(normalized_part)

    return " | ".join(route_parts)
