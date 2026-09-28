"""酒店搜索工具：consent gate、限速、浏览器、三层登录态、人性化滚动采集、解析。

登录态三层流程（用户定义）：
1. 先不注入：浏览器单例的持久 profile 中短期登录过则直接命中；
2. 未登录则注入 cookie 文件（ctrip-hotel-cookies.json，gitignored）再检测；
3. 仍失败返回 LOGIN_REQUIRED，由 Agent 通知用户调用 hotel_ctrip_login。
"""

import logging
import os
import random
import time
from datetime import datetime

from ..utils import cities_dict, cookie_store, login_state, url_builder
from ..utils import consent
from ..utils.browser_factory import SEARCH_LOCK, get_default_singleton
from ..utils.rate_limiter import SearchRateLimiter

logger = logging.getLogger(__name__)

_RATE_LIMITER = SearchRateLimiter()

LOGIN_ERROR = {
    "status": "error",
    "message": (
        "携程登录态缺失且 cookie 注入失败。请停止当前会话并通知用户："
        "调用 hotel_ctrip_login 工具完成携程登录（会打开浏览器窗口等待手动登录），"
        "登录完成后即可继续搜索。"
    ),
    "error_code": "LOGIN_REQUIRED",
    "data_source": "ctrip_web_scraping",
}

# 与验证版一致的卡片快照 JS（div.hotel-list 直接子元素）。
# 注意：DrissionPage run_js 会把代码包进函数执行，必须用顶层 return 语句风格，
# 不能写成箭头函数表达式（箭头函数只会被求值而不会被执行）。
SNAPSHOT_JS = """
const list = document.querySelector('.hotel-list');
if (!list) return [];
return [...list.children]
  .filter(el => (el.innerText || '').includes('查看详情'))
  .map(el => {
    const text = el.innerText;
    const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
    const prices = (text.match(/¥[\\d,]+/g) || []).map(p => parseInt(p.replace(/[¥,]/g, ''), 10));
    const ariaStar = [...el.querySelectorAll('[aria-label]')]
      .map(n => n.getAttribute('aria-label'))
      .find(a => /out of 5/.test(a || '')) || '';
    const distance = (lines.find(l => l.startsWith('距')) || '').replace('查看地图', '').trim();
    const reviews = (lines.find(l => l.includes('条点评')) || '').replace(/^(超棒|很好|不错|一般|差)/, '');
    let room = lines.find(l => /房|床/.test(l) && !l.startsWith('距') && !l.startsWith('热卖') && l.length < 60) || '';
    if (!/房|床/.test(room)) room = '';
    return {
      name: lines[0] || '',
      stars: (ariaStar || '').split(' ')[0] || '',
      score: lines.find(l => /^\\d\\.\\d$/.test(l)) || '',
      reviews: reviews,
      distance: distance,
      room: room,
      price: prices.length ? prices[prices.length - 1] : null,
    };
  });
"""

METRICS_JS = """
const doc = document.documentElement || {};
const body = document.body || {};
return {
  scroll_top: window.pageYOffset || doc.scrollTop || body.scrollTop || 0,
  viewport_height: window.innerHeight || doc.clientHeight || 0,
  scroll_height: Math.max(body.scrollHeight || 0, doc.scrollHeight || 0),
  card_count: document.querySelectorAll('.hotel-list > *').length,
};
"""


def _error(code, message):
    return {
        "status": "error",
        "message": message,
        "error_code": code,
        "data_source": "ctrip_web_scraping",
    }


def _validate_params(city, checkin, checkout, limit, adults, rooms):
    if not city or not checkin or not checkout:
        return _error("INVALID_PARAMS", "city、checkin、checkout 都不能为空")
    for label, value in (("checkin", checkin), ("checkout", checkout)):
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return _error("INVALID_PARAMS", f"{label} 日期格式不正确，请使用 YYYY-MM-DD")
    if checkout <= checkin:
        return _error("INVALID_PARAMS", "checkout 必须晚于 checkin")
    if checkin < datetime.now().strftime("%Y-%m-%d"):
        return _error("INVALID_PARAMS", "不能查询过去的日期")
    if not (1 <= int(limit) <= 50):
        return _error("INVALID_PARAMS", "limit 必须在 1~50 之间")
    if int(adults) < 1 or int(rooms) < 1:
        return _error("INVALID_PARAMS", "adults 和 rooms 至少为 1")
    return None


def parse_cards(raw_cards, min_score=None):
    """纯函数：清洗快照 dict 列表 → 酒店 dict 列表（可选按评分过滤）。"""
    hotels = []
    for c in raw_cards or []:
        if not c or not c.get("name"):
            continue
        score_text = c.get("score") or ""
        try:
            score_value = float(score_text)
        except (TypeError, ValueError):
            score_value = 0.0
        if min_score is not None and score_value and score_value < float(min_score):
            continue
        hotels.append(
            {
                "name": c["name"],
                "stars": c.get("stars") or "",
                "score": score_text,
                "reviews": c.get("reviews") or "",
                "distance": c.get("distance") or "",
                "room": c.get("room") or "",
                "price": c.get("price"),
            }
        )
    return hotels


def _header_text(page):
    try:
        return page.run_js(
            "return (document.body ? document.body.innerText : '').slice(0, 600)"
        )
    except Exception:  # pragma: no cover - 页面异常时按未登录处理
        return ""


def _ensure_logged_in(page, target_url):
    """三层登录态：已登录→None；未登录→注入 cookie 再导航；仍失败→LOGIN_ERROR。"""
    header = _header_text(page)
    if login_state.detect_login_state(page.url or "", header) == "logged_in":
        return None
    logger.info("未登录标记命中，尝试从 cookie 文件注入")
    cookies = cookie_store.load_cookies()
    if not cookies:
        logger.warning("cookie 文件不存在或为空")
        return LOGIN_ERROR
    try:
        page.set.cookies(cookie_store.to_injectable(cookies))
        logger.info("已注入 %s 条 cookie，重新导航到目标页", len(cookies))
    except Exception as e:  # pragma: no cover - 注入异常按失败处理
        logger.warning("cookie 注入失败: %s", e)
        return LOGIN_ERROR
    # 注入后必须完整导航回目标页：停留在 passport 登录页上刷新不会自动跳转
    try:
        page.get(target_url, timeout=90)
    except Exception as e:  # pragma: no cover
        logger.warning("注入后重新导航失败: %s", e)
        return LOGIN_ERROR
    time.sleep(4)
    header = _header_text(page)
    if login_state.detect_login_state(page.url or "", header) == "logged_in":
        logger.info("cookie 注入后登录态恢复")
        return None
    logger.warning("cookie 注入后仍未恢复登录态")
    return LOGIN_ERROR


def _resolve_city_via_ui(page, city):
    """UI 回退：首页表单搜索城市名，从重定向后的 URL 提取 cityId 并缓存。"""
    try:
        page.get("https://hotels.ctrip.com/hotels/", timeout=90)
        time.sleep(4)
        inputs = page.eles("css:input[type='text'], input:not([type])", timeout=8)
        box = None
        for el in inputs[:5]:
            try:
                if el.rect.size and el.rect.size[0] > 100:
                    box = el
                    break
            except Exception:
                continue
        if box is None:
            return None
        box.input(city)
        time.sleep(1)
        btn = page.ele("text:搜索", timeout=5)
        if not btn:
            return None
        btn.click()
        deadline = time.time() + 15
        while time.time() < deadline:
            time.sleep(2)
            url = page.url or ""
            if "cityId=" in url:
                import re

                match = re.search(r"cityId=(\d+)", url)
                if match:
                    city_id = int(match.group(1))
                    province = re.search(r"provinceId=(\d+)", url)
                    country = re.search(r"countryId=(\d+)", url)
                    ids = (
                        city_id,
                        int(province.group(1)) if province else 0,
                        int(country.group(1)) if country else 1,
                    )
                    cities_dict.CITY_IDS[city] = ids
                    logger.info("UI 回退解析出 %s → %s", city, ids)
                    return ids
        return None
    except Exception as e:  # pragma: no cover - UI 回退为尽力而为
        logger.warning("UI 回退搜索失败: %s", e)
        return None


def _human_scroll_and_collect(page, limit, rng=None):
    """人性化滚动采集：随机步幅（≥0.45 视口）、随机停顿、偶发回滚与鼠标移动。

    判底条件（防误判）：bottom_gap ≤ 15% 视口 且连续 3 轮
    scrollHeight 与卡片数双指标零增长。
    """
    rng = rng or random.Random()
    cards = []
    seen = set()
    last_height = 0
    last_count = 0
    stable = 0

    viewport = 900
    try:
        viewport = int(page.run_js("return window.innerHeight") or 900)
    except Exception:  # pragma: no cover
        pass

    for round_index in range(80):
        snapshot = _snapshot_cards(page)
        snapshot_count = len(snapshot)
        new_added = 0
        for c in snapshot:
            key = c.get("name")
            if key and key not in seen:
                seen.add(key)
                cards.append(c)
                new_added += 1
        if len(cards) >= limit:
            logger.info("已收集 %s 家（目标 %s），停止滚动", len(cards), limit)
            break

        # 随机步幅：视口 0.55~0.9 倍，±10% 抖动，下限 0.45 视口
        step = viewport * rng.uniform(0.55, 0.9) * rng.uniform(0.9, 1.1)
        step = max(step, viewport * 0.45)
        # 每 3~5 轮 30% 概率回滚 0.2~0.4 视口（模拟回看）
        if round_index > 0 and round_index % rng.randint(3, 5) == 0 and rng.random() < 0.3:
            step = -viewport * rng.uniform(0.2, 0.4)
        try:
            page.run_js(f"window.scrollBy(0, {int(step)});")
        except Exception as e:  # pragma: no cover
            logger.warning("滚动失败: %s", e)
            break
        # 30% 概率随机移动鼠标
        if rng.random() < 0.3:
            try:
                page.actions.move_to(
                    rng.randint(100, 1100), rng.randint(100, 700)
                )
            except Exception:  # pragma: no cover
                pass
        time.sleep(rng.uniform(0.8, 2.2))

        metrics = _metrics(page)
        height_grew = metrics["scroll_height"] > last_height
        count_grew = snapshot_count > last_count
        last_height = metrics["scroll_height"]
        last_count = snapshot_count
        reached_bottom = metrics["bottom_gap"] <= viewport * 0.15

        if height_grew or count_grew or new_added > 0:
            stable = 0
        else:
            stable += 1

        logger.debug(
            "第%s轮: 高度=%s 底部距离=%s 卡片=%s 新增=%s 稳定轮=%s",
            round_index + 1,
            metrics["scroll_height"],
            metrics["bottom_gap"],
            metrics["card_count"],
            new_added,
            stable,
        )
        if reached_bottom and stable >= 3:
            logger.info("到达底部且连续 %s 轮无新增，停止采集", stable)
            break

    return cards


def _snapshot_cards(page):
    try:
        result = page.run_js(SNAPSHOT_JS)
    except Exception as e:  # pragma: no cover
        logger.warning("快照失败: %s", e)
        return []
    return [item for item in (result or []) if isinstance(item, dict)]


def _metrics(page):
    try:
        m = page.run_js(METRICS_JS) or {}
    except Exception:  # pragma: no cover
        m = {}
    scroll_top = int(m.get("scroll_top") or 0)
    viewport = int(m.get("viewport_height") or 0)
    height = int(m.get("scroll_height") or 0)
    bottom_gap = max(0, height - (scroll_top + viewport))
    return {
        "scroll_height": height,
        "viewport_height": viewport,
        "bottom_gap": bottom_gap,
        "card_count": int(m.get("card_count") or 0),
    }


def _format_output(hotels, city, checkin, checkout, location):
    lines = [
        "🏨 酒店查询结果",
        f"📍 {location or city}（{city}）",
        f"📅 {checkin} ~ {checkout}",
        f"🔢 共找到 {len(hotels)} 家酒店",
        "",
    ]
    for i, h in enumerate(hotels, 1):
        stars = f" {h['stars']}星" if h.get("stars") else ""
        score = f" · {h['score']}分" if h.get("score") else ""
        price = f"¥{h['price']}起" if h.get("price") else "价格未知"
        lines.append(f"【{i}】{h['name']}{stars}{score}")
        if h.get("reviews"):
            detail = h["reviews"]
            if h.get("distance"):
                detail += f" · {h['distance']}"
            lines.append(f"    💬 {detail}")
        if h.get("room"):
            lines.append(f"    🛏 {h['room']}")
        lines.append(f"    💰 {price}")
        lines.append("")
    return "\n".join(lines)


def searchHotels(
    city,
    checkin,
    checkout,
    location=None,
    adults=2,
    children=0,
    rooms=1,
    price_min=None,
    price_max=None,
    star_min=None,
    star_max=None,
    min_score=None,
    room_type=None,
    accommodation_type=None,
    breakfast=None,
    sort="smart",
    limit=20,
):
    if not consent.is_consented():
        return consent.CONSENT_ERROR

    err = _validate_params(city, checkin, checkout, limit, adults, rooms)
    if err:
        return err

    rate_info = _RATE_LIMITER.wait_if_needed()
    if rate_info["waited_seconds"] > 0:
        logger.info(
            "限速等待 %.1fs（随机间隔 %.1fs）", rate_info["waited_seconds"], rate_info["delay_seconds"]
        )

    with SEARCH_LOCK:
        singleton = get_default_singleton()
        try:
            page = singleton.get()
        except Exception as e:
            logger.error("浏览器启动失败: %s", e)
            singleton.reset()
            try:
                page = singleton.get()
            except Exception as e2:  # pragma: no cover
                return _error("SCRAPING_FAILED", f"浏览器启动失败: {e2}")

        city_ids = cities_dict.get_city_ids(city)
        landmark_code = cities_dict.get_landmark(location) if location else None
        if city_ids is None:
            logger.info("城市 %s 不在字典中，尝试 UI 回退解析", city)
            city_ids = _resolve_city_via_ui(page, city)
            if city_ids is None:
                return _error(
                    "CITY_NOT_FOUND",
                    f"暂不支持城市 {city!r}（内置字典未覆盖且 UI 回退解析失败）",
                )

        built = url_builder.build_list_url(
            city,
            city_ids,
            checkin,
            checkout,
            landmark=location,
            landmark_code=landmark_code,
            rooms=rooms,
            adults=adults,
            children=children,
            price_min=price_min,
            price_max=price_max,
            star_min=star_min,
            star_max=star_max,
            room_type=room_type,
            accommodation_type=accommodation_type,
            sort=sort,
        )
        warnings = list(built["warnings"])
        if breakfast:
            warnings.append("早餐筛选暂无已验证的筛选编码，已忽略")

        try:
            page.get(built["url"], timeout=90)
        except Exception as e:
            return _error("SCRAPING_FAILED", f"页面打开失败: {e}")
        time.sleep(5)

        login_err = _ensure_logged_in(page, built["url"])
        if login_err:
            return login_err

        # 登录判定通过但列表容器缺失 → 可能被反爬拦截或页面结构变化。
        # 注意：DrissionPage 找不到元素时返回 falsy 的 NoneElement（不是 None），
        # 必须用真值判断而非 `is not None`。
        try:
            has_list = bool(page.ele("css:.hotel-list", timeout=10))
        except Exception:  # pragma: no cover - ele 超时抛错视为未渲染
            has_list = False
        if not has_list:
            return _error(
                "SCRAPING_FAILED", "酒店列表未渲染（可能被拦截或页面结构变化）"
            )

        # 首屏随机停驻，模拟阅读
        time.sleep(random.uniform(1.5, 4.0))

        raw_cards = _human_scroll_and_collect(page, int(limit))
        hotels = parse_cards(raw_cards, min_score=min_score)[: int(limit)]

        if not hotels:
            return {
                "status": "empty",
                "message": "未找到符合条件的酒店",
                "error_code": "EMPTY_RESULTS",
                "count": 0,
                "hotels": [],
                "warnings": warnings,
                "data_source": "ctrip_web_scraping",
                "query_time": datetime.now().isoformat(),
            }

        if len(hotels) < int(limit):
            warnings.append(f"仅返回 {len(hotels)} 家（列表加载到底或筛选后不足）")

        formatted = _format_output(hotels, city, checkin, checkout, location)
        formatted += "\n\n🧾 数据源: ctrip_web_scraping"

        return {
            "status": "success",
            "city": city,
            "location": location,
            "checkin": checkin,
            "checkout": checkout,
            "count": len(hotels),
            "hotels": hotels,
            "warnings": warnings,
            "formatted_output": formatted,
            "query_time": datetime.now().isoformat(),
            "data_source": "ctrip_web_scraping",
            "rate_limiter": rate_info,
        }
