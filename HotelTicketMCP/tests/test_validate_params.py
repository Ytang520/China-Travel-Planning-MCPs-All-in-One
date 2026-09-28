from hotel_ticket_mcp_server.tools.hotel_search_tools import _validate_params


def test_valid_params():
    assert _validate_params("武汉", "2026-10-01", "2026-10-03", 20, 2, 1) is None
    assert _validate_params("武汉", "2026-10-01", "2026-10-03", 1, 1, 1) is None
    assert _validate_params("武汉", "2026-10-01", "2026-10-03", 50, 2, 1) is None


def test_missing_required():
    err = _validate_params("", "2026-10-01", "2026-10-03", 20, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"


def test_bad_date_format():
    err = _validate_params("武汉", "2026/10/01", "2026-10-03", 20, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"


def test_checkout_must_be_after_checkin():
    err = _validate_params("武汉", "2026-10-03", "2026-10-01", 20, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"
    err = _validate_params("武汉", "2026-10-01", "2026-10-01", 20, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"


def test_past_date_rejected():
    err = _validate_params("武汉", "2020-01-01", "2020-01-03", 20, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"


def test_limit_bounds():
    err = _validate_params("武汉", "2026-10-01", "2026-10-03", 0, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"
    err = _validate_params("武汉", "2026-10-01", "2026-10-03", 51, 2, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"


def test_guests_rooms_minimum():
    err = _validate_params("武汉", "2026-10-01", "2026-10-03", 20, 0, 1)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"
    err = _validate_params("武汉", "2026-10-01", "2026-10-03", 20, 2, 0)
    assert err is not None and err["error_code"] == "INVALID_PARAMS"
