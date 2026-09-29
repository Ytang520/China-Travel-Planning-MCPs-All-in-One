"""携程酒店登录助手：打开可见窗口等用户手动登录，成功后保存 cookie。

供搜索返回 LOGIN_REQUIRED 后调用；cookie 保存在 gitignored 的文件中
（utils/cookie_store.py，默认 HotelTicketMCP/ctrip-hotel-cookies.json）。
"""

import logging
import time

from ..utils import consent, cookie_store, login_state
from ..utils.browser_factory import SEARCH_LOCK, browser_session

logger = logging.getLogger(__name__)

LOGIN_TIMEOUT_SECONDS = 300
POLL_INTERVAL_SECONDS = 3


def _error(code, message):
    return {
        "status": "error",
        "message": message,
        "error_code": code,
        "data_source": "ctrip_web_scraping",
    }


def _header_text(page):
    try:
        return page.run_js(
            "return (document.body ? document.body.innerText : '').slice(0, 600)"
        )
    except Exception:  # pragma: no cover
        return ""


def _extract_cookies(page):
    """CDP Network.getAllCookies 提取（保留 httpOnly 标志），只保留 ctrip 域。"""
    try:
        result = page.run_cdp("Network.getAllCookies")
    except Exception as e:  # pragma: no cover
        logger.warning("提取 cookie 失败: %s", e)
        result = {}
    raw = result.get("cookies", []) if isinstance(result, dict) else []
    out = []
    for c in raw:
        domain = c.get("domain", "")
        if "ctrip.com" not in domain or not c.get("name"):
            continue
        out.append(
            {
                "name": c["name"],
                "value": c.get("value", ""),
                "domain": domain,
                "path": c.get("path", "/"),
                "httpOnly": bool(c.get("httpOnly")),
                "secure": bool(c.get("secure")),
            }
        )
    return out


def ctripHotelLogin():
    if not consent.is_consented():
        return consent.CONSENT_ERROR

    with SEARCH_LOCK, browser_session() as singleton:
        try:
            page = singleton.get()
        except Exception as e:
            logger.error("浏览器启动失败: %s", e)
            singleton.reset()
            try:
                page = singleton.get()
            except Exception as e2:  # pragma: no cover
                return _error("SCRAPING_FAILED", f"浏览器启动失败: {e2}")

        try:
            page.set.window.max()
            page.get("https://hotels.ctrip.com/hotels/", timeout=90)
        except Exception as e:  # pragma: no cover
            return _error("SCRAPING_FAILED", f"打开登录页失败: {e}")
        time.sleep(3)

        state = login_state.detect_login_state(page.url or "", _header_text(page))
        deadline = time.time() + LOGIN_TIMEOUT_SECONDS
        while state != "logged_in" and time.time() < deadline:
            logger.info("等待用户手动登录…（剩余 %.0fs）", deadline - time.time())
            time.sleep(POLL_INTERVAL_SECONDS)
            state = login_state.detect_login_state(
                page.url or "", _header_text(page)
            )

        if state != "logged_in":
            return _error(
                "LOGIN_TIMEOUT",
                f"登录超时（{LOGIN_TIMEOUT_SECONDS // 60} 分钟）或用户未完成登录，请重试。",
            )

        cookies = _extract_cookies(page)
        if not cookies:
            return _error(
                "LOGIN_TIMEOUT", "登录态检测通过但未提取到 cookie，请重试。"
            )
        path = cookie_store.save_cookies(cookies)

        logger.info("登录成功，已保存 %s 条 cookie 到 %s", len(cookies), path)
        return {
            "status": "success",
            "message": f"登录成功，已保存 {len(cookies)} 条 cookie 到 {path}（后续搜索自动复用）。",
            "cookie_count": len(cookies),
            "cookie_file": str(path),
            "data_source": "ctrip_web_scraping",
        }
