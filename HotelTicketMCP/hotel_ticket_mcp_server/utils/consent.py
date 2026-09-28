"""风险同意开关：酒店搜索涉及登录态抓取，必须显式同意才能使用。"""

import os

CONSENT_ERROR = {
    "status": "error",
    "message": (
        "酒店搜索未启用：需要先同意风险条款（HOTEL_MCP_CONSENT=yes）。"
        "本功能通过浏览器模拟真人浏览并抓取需要登录的携程酒店数据，"
        "存在账号被封禁的风险；启用即表示用户已了解并自愿承担该风险，作者概不负责。"
    ),
    "error_code": "CONSENT_REQUIRED",
    "data_source": "ctrip_web_scraping",
}


def is_consented():
    return os.environ.get("HOTEL_MCP_CONSENT", "").strip().lower() == "yes"
