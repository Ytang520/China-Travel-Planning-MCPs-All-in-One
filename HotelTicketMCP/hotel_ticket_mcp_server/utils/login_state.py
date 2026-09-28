"""登录态判定（反转型）。

以「非登录态标记」为准：命中任何未登录标记 → guest；
不命中 → 视为已登录。不依赖"黄金贵宾"等具体会员身份文本
（登录者可能是任意会员等级）。
"""


def detect_login_state(url, header_text):
    """判断携程页面登录态。

    Args:
        url: 当前页面 URL
        header_text: 页面顶部区域文本（body 前若干字即可覆盖顶栏）

    Returns:
        "guest" | "logged_in"
    """
    url = url or ""
    if "passport" in url:
        return "guest"
    text = header_text or ""
    if "登录" in text and "注册" in text:
        return "guest"
    return "logged_in"
