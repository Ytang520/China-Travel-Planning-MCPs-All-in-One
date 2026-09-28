from datetime import datetime, timedelta

from hotel_ticket_mcp_server.tools.hotel_search_tools import _validate_params

# 用远未来日期，避免"过去日期"校验随时间推移而抢先触发、掩盖被测分支
FUTURE_CHECKIN = "2099-01-01"
FUTURE_CHECKOUT = "2099-01-03"
PAST_CHECKIN = "2020-01-01"
PAST_CHECKOUT = "2020-01-03"


def test_valid_params():
    assert _validate_params("武汉", FUTURE_CHECKIN, FUTURE_CHECKOUT, 20, 2, 1) is None
    assert _validate_params("武汉", FUTURE_CHECKIN, FUTURE_CHECKOUT, 1, 1, 1) is None
    assert _validate_params("武汉", FUTURE_CHECKIN, FUTURE_CHECKOUT, 50, 2, 1) is None


def test_missing_required():
    err = _validate_params("", FUTURE_CHECKIN, FUTURE_CHECKOUT, 20, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"


def test_bad_date_format():
    err = _validate_params("武汉", "2099/01/01", FUTURE_CHECKOUT, 20, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"


def test_checkout_must_be_after_checkin():
    err = _validate_params("武汉", FUTURE_CHECKOUT, FUTURE_CHECKIN, 20, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"
    err = _validate_params("武汉", FUTURE_CHECKIN, FUTURE_CHECKIN, 20, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"


def test_past_date_rejected():
    err = _validate_params("武汉", PAST_CHECKIN, PAST_CHECKOUT, 20, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"


def test_limit_bounds():
    err = _validate_params("武汉", FUTURE_CHECKIN, FUTURE_CHECKOUT, 0, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"
    err = _validate_params("武汉", FUTURE_CHECKIN, FUTURE_CHECKOUT, 51, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"


def test_guests_rooms_minimum():
    err = _validate_params("武汉", FUTURE_CHECKIN, FUTURE_CHECKOUT, 20, 0, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"
    err = _validate_params("武汉", FUTURE_CHECKIN, FUTURE_CHECKOUT, 20, 2, 0)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"


def test_dates_are_far_future():
    # 防回归：若有人改回近日期，该测试立即失败（3 天引爆器检查）
    assert datetime.now() < datetime.strptime(FUTURE_CHECKIN, "%Y-%m-%d") - timedelta(days=365 * 10)
