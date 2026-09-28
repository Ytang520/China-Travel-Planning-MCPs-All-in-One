from hotel_ticket_mcp_server.utils.login_state import detect_login_state

MEMBER_HEADER = "携程旅行网 搜索 我的订单 联系客服 通知"
GUEST_HEADER = "携程旅行网 登录 注册 我的订单 联系客服"
GOLD_VIP_HEADER = "携程旅行网 我的账户: 尊敬的黄金贵宾 我的订单 携程客服"


def test_passport_redirect_is_guest():
    url = "https://passport.ctrip.com/user/login?backurl=https%3A%2F%2Fhotels.ctrip.com"
    assert detect_login_state(url, GUEST_HEADER) == "guest"
    # passport 优先，即使 header 没有登录/注册
    assert detect_login_state(url, MEMBER_HEADER) == "guest"


def test_login_and_register_buttons_is_guest():
    assert detect_login_state("https://hotels.ctrip.com/hotels/list/...", GUEST_HEADER) == "guest"


def test_no_guest_markers_is_logged_in():
    assert detect_login_state("https://hotels.ctrip.com/hotels/list/...", MEMBER_HEADER) == "logged_in"
    # 会员身份任意，不依赖"黄金贵宾"文本
    assert detect_login_state("https://hotels.ctrip.com/hotels/list/...", GOLD_VIP_HEADER) == "logged_in"


def test_empty_inputs_are_logged_in():
    # 无 passport、无登录/注册标记 → 按设计视为已登录
    assert detect_login_state("https://hotels.ctrip.com/hotels/list/...", "") == "logged_in"
