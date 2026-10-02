from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from hotel_ticket_mcp_server.utils.login_state import detect_login_state, observe, LoginObservationError

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
    assert detect_login_state("https://hotels.ctrip.com/hotels/list/...", MEMBER_HEADER, has_hotel_list=True) == "logged_in"
    # 会员身份任意，不依赖"黄金贵宾"文本
    assert detect_login_state("https://hotels.ctrip.com/hotels/list/...", GOLD_VIP_HEADER) == "logged_in"


def test_empty_inputs_are_unknown():
    assert detect_login_state("https://hotels.ctrip.com/hotels/list/...", "") == "unknown"


def test_only_positive_evidence_on_the_official_hotel_origin_passes():
    for url in ("about:blank", "https://hotels.ctrip.com.evil.test/hotels/", "https://other.test/"):
        assert detect_login_state(url, GOLD_VIP_HEADER, has_hotel_list=True) == "unknown"
    assert detect_login_state("https://hotels.ctrip.com/hotels/", MEMBER_HEADER) == "unknown"
    assert detect_login_state("https://hotels.ctrip.com/hotels/", MEMBER_HEADER, ready=False, has_hotel_list=True) == "unknown"
    assert detect_login_state("https://hotels.ctrip.com/hotels/", "安全验证", has_hotel_list=True) == "unknown"


def test_observation_gets_url_and_dom_in_one_bounded_snapshot():
    snapshot = {"url": "https://hotels.ctrip.com/hotels/list/", "text": GOLD_VIP_HEADER,
                "ready": True, "has_hotel_list": True, "login_form": False}
    # There is no page.url property: an extra lookup could block or see another document.
    page = SimpleNamespace(run_cdp=Mock(return_value={"result": {"value": snapshot}}))
    assert observe(page, timeout=0.7) == {"url": snapshot["url"], "ready": True,
                                         "login_form": False, "state": "logged_in"}
    args, kwargs = page.run_cdp.call_args
    assert args == ("Runtime.evaluate",)
    assert kwargs["returnByValue"] is True and kwargs["_timeout"] == 0.7
    assert "window.location.href" in kwargs["expression"]


@pytest.mark.parametrize("response", [None, {}, {"result": None}, {"result": {"value": None}},
                                       {"exceptionDetails": {"text": "private-page-content"}}])
def test_invalid_snapshot_is_a_detection_error_without_account_text(response):
    page = SimpleNamespace(run_cdp=Mock(return_value=response))
    with pytest.raises(LoginObservationError) as error:
        observe(page)
    assert "private-page-content" not in str(error.value)
