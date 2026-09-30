"""Conservative login detection: missing evidence is unknown, never success."""
from urllib.parse import urlsplit

STATE_JS = """
const visible = e => !!e && !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
const text = (document.body?.innerText || '').slice(0, 1200);
return {
  ready: document.readyState !== 'loading' && !!document.body && !!text.trim(),
  text,
  login_form: [...document.querySelectorAll('input[type="password"]')].some(visible)
    || [...document.querySelectorAll('a,button,div,span')].some(e => visible(e) && /^(扫码登录|账号密码登录|短信验证码登录)$/.test((e.innerText || '').trim())),
  has_hotel_list: [...document.querySelectorAll('.hotel-list > *')]
    .some(e => visible(e) && (e.innerText || '').includes('查看详情'))
};
"""


def detect_login_state(url, header_text, *, ready=True, has_hotel_list=False, login_form=False):
    try:
        parsed = urlsplit(url or "")
        host = parsed.hostname or ""
    except ValueError:
        return "unknown"
    if host == "passport.ctrip.com":
        return "guest"
    if parsed.scheme != "https" or host != "hotels.ctrip.com":
        return "unknown"
    text = header_text or ""
    if not ready or not text.strip():
        return "unknown"
    if any(marker in text for marker in ("访问验证", "安全验证", "访问过于频繁", "验证您是真人", "网络异常")):
        return "unknown"
    if login_form or ("登录" in text and "注册" in text):
        return "guest"
    if has_hotel_list or any(marker in text for marker in ("退出登录", "退出账号", "我的账户:", "我的账户：")):
        return "logged_in"
    return "unknown"


def observe(page):
    """Inspect only page state; callers never need to log account text."""
    data = page.run_js(STATE_JS)
    if not isinstance(data, dict):
        data = {}
    url = page.url or ""
    return {
        "url": url,
        "ready": bool(data.get("ready")),
        "login_form": bool(data.get("login_form")),
        "state": detect_login_state(url, data.get("text", ""), ready=bool(data.get("ready")),
                                    has_hotel_list=bool(data.get("has_hotel_list")),
                                    login_form=bool(data.get("login_form"))),
    }
