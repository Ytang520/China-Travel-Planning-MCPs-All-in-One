"""
Flight Search Tools - 航班路线查询工具

提供根据出发地、目的地和出发日期查询航班路线的功能
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
import json
import random
import logging
import time
import re

# 初始化日志器
logger = logging.getLogger(__name__)

try:
    from . import variflight_tools
except ImportError:
    variflight_tools = None

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

        self.base_url = "https://flights.ctrip.com/online/list/oneway-{}-{}?_=1&depdate={}&cabin=Y_S_C_F"

        if headless:
            co = ChromiumOptions()
            co.headless()
            self.page = ChromiumPage(co)
        else:
            self.page = ChromiumPage()

        logger.info("航班路线查询器初始化完成")
        self.last_parse_status = "not_started"
        self.last_parse_error = None

    def search_flights(
        self, departure_city: str, destination_city: str, departure_date: str
    ) -> List[Dict[str, Any]]:
        """
        搜索航班

        Args:
            departure_city: 出发城市
            destination_city: 目的地城市
            departure_date: 出发日期 (YYYY-MM-DD格式)

        Returns:
            航班信息列表
        """
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
            self.page.get(search_url)
            logger.info("页面加载完成，等待内容渲染...")
            # 智能等待页面加载完成
            self._wait_for_page_ready()

            # 等待关键元素出现
            self._wait_for_flight_content()

            # 在滚动过程中分段采集航班，避免回到顶部后只解析到一部分虚拟列表
            flights = self._collect_flights_with_scrolling()

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
            scroll_distance = max(
                600, int(previous_metrics["viewport_height"] * 0.8)
            )

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

    def _wait_for_flight_content(self, timeout=30):
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

    def _wait_for_page_ready(self, timeout=30):
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

    def _collect_flights_with_scrolling(self) -> List[Dict[str, Any]]:
        """在滚动过程中采集航班，兼容分段渲染/虚拟列表"""
        collected_flights: List[Dict[str, Any]] = []
        seen_flight_keys = set()

        max_scroll_rounds = 100
        max_stable_rounds = 5
        stable_rounds = 0

        try:
            initial_metrics = self._get_scroll_metrics()
            scroll_distance = max(300, int(initial_metrics["viewport_height"] * 0.6))
        except Exception:
            initial_metrics = {"scroll_height": 0, "viewport_height": 0, "bottom_gap": 0}
            scroll_distance = 300

        initial_added = self._collect_visible_flights(
            collected_flights, seen_flight_keys
        )
        logger.info(
            "开始滚动采集航班，初始页面高度: %s，视口高度: %s，初始新增航班: %s",
            initial_metrics["scroll_height"],
            initial_metrics["viewport_height"],
            initial_added,
        )

        last_scroll_height = initial_metrics["scroll_height"]
        for round_index in range(1, max_scroll_rounds + 1):
            target_position = round_index * scroll_distance
            try:
                self.page.run_js(f"window.scrollTo(0, {target_position});")
                logger.info("第%s次滚动到 %spx", round_index, target_position)
                time.sleep(2)
                self._wait_for_loading_complete(timeout=5)
                time.sleep(1)

                current_metrics = self._get_scroll_metrics()
                new_flights = self._collect_visible_flights(
                    collected_flights, seen_flight_keys
                )
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
                    logger.info(
                        "已到达页面底部，且连续%s轮无新增内容，停止采集",
                        stable_rounds,
                    )
                    break
            except Exception as e:
                logger.warning("第%s次滚动采集失败: %s", round_index, e)
                break

        if collected_flights:
            self.last_parse_status = "success"
            self.last_parse_error = None
            logger.info("滚动采集完成，共收集 %s 条唯一航班", len(collected_flights))
            return collected_flights

        logger.info("滚动采集未获得有效航班，回退到当前视口直接解析")
        return self._parse_flights()

    def _collect_visible_flights(
        self, collected_flights: List[Dict[str, Any]], seen_flight_keys: set
    ) -> int:
        """采集当前视口内可见航班并去重"""
        visible_flights = self._snapshot_visible_flights()
        new_flight_count = 0
        for flight_info in visible_flights:
            try:
                if (
                    not flight_info
                    or not flight_info.get("航班号")
                    or flight_info.get("航班号") == "未知"
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

    def _parse_flights(self) -> List[Dict[str, Any]]:
        """解析航班信息"""
        flights = []

        try:
            flight_containers = self._snapshot_visible_flights()
            if not flight_containers:
                self.last_parse_status = "parse_failed"
                self.last_parse_error = "未找到航班列表容器，页面结构可能已变化"
                logger.warning("未找到航班容器")
                return []

            logger.info(f"找到 {len(flight_containers)} 个航班容器")
            seen_flight_keys = set()

            for flight_info in flight_containers:
                try:
                    if (
                        flight_info
                        and flight_info.get("航班号")
                        and flight_info.get("航班号") != "未知"
                    ):
                        flight_key = self._build_flight_key(flight_info)
                        if flight_key in seen_flight_keys:
                            continue

                        # 只有当航班号存在且不是'未知'时才添加
                        flight_info["序号"] = len(flights) + 1
                        flights.append(flight_info)
                        seen_flight_keys.add(flight_key)
                        logger.debug(
                            f"成功解析航班 {len(flights)}: {flight_info.get('航班号')}"
                        )
                    else:
                        logger.debug("航班容器无有效航班号，跳过")

                except Exception as e:
                    logger.error(f"解析航班容器出错: {str(e)}")
                    continue

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
                departure_airport, departure_terminal = self._extract_airport_and_terminal(
                    airport_lines[0]
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

    def close(self):
        """关闭浏览器"""
        if hasattr(self, "page"):
            self.page.quit()
            logger.info("浏览器已关闭")


def searchFlightRoutes(
    departure_city: str,
    destination_city: str,
    departure_date: str,
    data_source_preference: str = "auto",
) -> Dict[str, Any]:
    """
    根据出发地、目的地和出发日期查询航班路线

    Args:
        departure_city: 出发城市名称或机场代码
        destination_city: 目的地城市名称或机场代码
        departure_date: 出发日期 (YYYY-MM-DD格式)

    Returns:
        包含航班查询结果的字典
    """
    logger.info(
        f"开始查询航班路线: {departure_city} -> {destination_city}, 日期: {departure_date}, 数据源偏好: {data_source_preference}"
    )

    normalized_preference = (data_source_preference or "auto").strip().lower()
    if normalized_preference not in {"auto", "default", "variflight"}:
        return {
            "status": "error",
            "message": "data_source_preference 仅支持 auto、default、variflight",
            "error_code": "INVALID_DATA_SOURCE_PREFERENCE",
            "data_source": "system",
        }

    def use_variflight_fallback(primary_error: Dict[str, Any]) -> Dict[str, Any]:
        if normalized_preference == "default" or not variflight_tools:
            return primary_error

        fallback_result = variflight_tools.searchFlightRoutes(
            departure_city,
            destination_city,
            departure_date,
        )
        if fallback_result.get("status") == "success":
            fallback_result["primary_error"] = primary_error
            fallback_result["message"] = "主数据源失败，已切换到 Variflight 备选方案"
            return fallback_result

        primary_error["fallback_error"] = fallback_result
        return primary_error

    try:
        if normalized_preference == "variflight":
            if not variflight_tools:
                return {
                    "status": "error",
                    "message": "Variflight 数据源不可用",
                    "error_code": "VARIFLIGHT_NOT_AVAILABLE",
                    "data_source": "system",
                }
            direct_result = variflight_tools.searchFlightRoutes(
                departure_city,
                destination_city,
                departure_date,
            )
            direct_result["requested_data_source"] = "variflight"
            return direct_result

        # 验证输入参数
        if not departure_city or not destination_city or not departure_date:
            logger.warning("参数不完整")
            return {
                "status": "error",
                "message": "出发地、目的地和出发日期都不能为空",
                "error_code": "INVALID_PARAMS",
                "data_source": "ctrip_web_scraping",
            }

        # 检查依赖是否可用
        if not DRISSION_PAGE_AVAILABLE:
            logger.error("DrissionPage库未安装")
            return use_variflight_fallback(
                {
                    "status": "error",
                    "message": "DrissionPage库未安装，无法进行航班搜索",
                    "error_code": "DRISSION_PAGE_NOT_AVAILABLE",
                    "data_source": "ctrip_web_scraping",
                }
            )

        if not get_airport_code or not get_city_name:
            logger.error("城市字典未找到")
            return use_variflight_fallback(
                {
                    "status": "error",
                    "message": "城市字典未找到，无法进行航班搜索",
                    "error_code": "CITIES_DICT_NOT_AVAILABLE",
                    "data_source": "ctrip_web_scraping",
                }
            )

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
                "data_source": "ctrip_web_scraping",
            }

        # 检查日期是否为过去的日期
        if flight_date.date() < datetime.now().date():
            logger.warning(f"查询过去的日期: {departure_date}")
            return {
                "status": "error",
                "message": "不能查询过去的日期",
                "error_code": "PAST_DATE",
                "data_source": "ctrip_web_scraping",
            }

        # 验证城市/机场代码
        if not get_airport_code(departure_city):
            logger.warning(f"无效的出发地: {departure_city}")
            return {
                "status": "error",
                "message": f"无效的出发地: {departure_city}",
                "error_code": "INVALID_DEPARTURE_CITY",
                "data_source": "ctrip_web_scraping",
            }

        if not get_airport_code(destination_city):
            logger.warning(f"无效的目的地: {destination_city}")
            return {
                "status": "error",
                "message": f"无效的目的地: {destination_city}",
                "error_code": "INVALID_DESTINATION_CITY",
                "data_source": "ctrip_web_scraping",
            }

        # 创建搜索器并搜索
        searcher = FlightRouteSearcher(headless=True)

        try:
            flights = searcher.search_flights(
                departure_city, destination_city, departure_date
            )
            # merged_flights = _merge_codeshare_flights(flights)
            merged_flights = flights

            if searcher.last_parse_status in {"request_failed", "parse_failed"}:
                return use_variflight_fallback(
                    {
                        "status": "error",
                        "message": searcher.last_parse_error or "航班页面抓取失败",
                        "error_code": "SCRAPING_FAILED",
                        "departure_city": departure_city,
                        "destination_city": destination_city,
                        "departure_date": departure_date,
                        "query_time": datetime.now().isoformat(),
                        "data_source": "ctrip_web_scraping",
                    }
                )

            # 格式化结果
            result = {
                "status": "success",
                "departure_city": departure_city,
                "destination_city": destination_city,
                "departure_date": departure_date,
                "departure_airport": get_city_name(departure_city),
                "destination_airport": get_city_name(destination_city),
                "flight_count": len(merged_flights),
                "raw_flight_count": len(flights),
                "flights": merged_flights,
                "formatted_output": _format_route_result(
                    merged_flights, departure_city, destination_city, departure_date
                ),
                "query_time": datetime.now().isoformat(),
                "fallback_used": False,
                "requested_data_source": normalized_preference,
                "data_source": "ctrip_web_scraping",
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
                        "avg_price": sum(prices) // len(prices),
                    }

                if airlines:
                    result["airline_statistics"] = airlines

            result["formatted_output"] += "\n\n🧾 数据源: ctrip_web_scraping"

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
            "error_code": "SEARCH_FAILED",
            "requested_data_source": normalized_preference,
            "data_source": "ctrip_web_scraping",
        }
        return use_variflight_fallback(primary_error)


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


def _extract_price_value(price: Any) -> Optional[int]:
    """从价格文本中提取数值"""
    if price is None:
        return None

    match = re.search(r"(\d{3,6})", str(price))
    if not match:
        return None

    return int(match.group(1))


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
