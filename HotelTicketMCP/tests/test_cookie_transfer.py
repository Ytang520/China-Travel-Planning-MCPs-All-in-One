"""Synthetic Edge -> Chrome attribute round trip; opt in to launch browsers."""
import os
import time
from pathlib import Path
import pytest
from hotel_ticket_mcp_server.tools.hotel_login_tools import _extract_cookies
from hotel_ticket_mcp_server.utils import cookie_store
from hotel_ticket_mcp_server.utils.browser_runtime import OwnedBrowser

pytestmark = pytest.mark.skipif(os.environ.get("HOTEL_MCP_RUN_COOKIE_TRANSFER") != "1", reason="Opt-in installed Edge and Chrome check")


def test_edge_to_actual_chrome_cookie_attributes(monkeypatch, tmp_path):
    from DrissionPage import ChromiumPage, ChromiumOptions
    expires = int(time.time()) + 3600
    cookies = [
        {"name": "synthetic_persistent", "value": "test-only", "domain": ".ctrip.com", "path": "/hotels/",
         "httpOnly": True, "secure": True, "sameSite": "Lax", "expires": expires},
        {"name": "synthetic_session", "value": "test-only", "domain": "hotels.ctrip.com", "path": "/",
         "httpOnly": False, "secure": True, "sameSite": "Strict"},
        {"name": "synthetic_partition", "value": "test-only", "domain": ".ctrip.com", "path": "/",
         "secure": True, "sameSite": "None",
         "partitionKey": {"topLevelSite": "https://ctrip.com", "hasCrossSiteAncestor": False}},
    ]
    root = Path(__file__).resolve().parents[1]
    monkeypatch.delenv("HOTEL_MCP_BROWSER_PATH", raising=False)
    for engine in ("edge", "chrome"):
        monkeypatch.setenv("HOTEL_MCP_BROWSER", engine)
        owner = OwnedBrowser("HOTEL_MCP", root, tmp_path / engine, temporary=True)
        try:
            page = owner.open(ChromiumPage, ChromiumOptions, headless=True)
            assert owner.diagnostic["actual_browser"] == engine
            injectable = cookies if engine == "edge" else cookie_store.to_injectable(cookie_store.load_cookies(tmp_path / "cookies.json"))
            page.set.cookies(injectable)
            actual = {c["name"]: c for c in page.run_cdp("Network.getAllCookies")["cookies"]}
            for expected in cookies:
                found = actual[expected["name"]]
                for key in ("domain", "path", "secure", "sameSite", "httpOnly", "partitionKey"):
                    if key in expected:
                        assert found[key] == expected[key]
                assert found["session"] == ("expires" not in expected)
                if "expires" in expected:
                    assert abs(found["expires"] - expires) < 2
            if engine == "edge":
                cookie_store.save_cookies(_extract_cookies(page), tmp_path / "cookies.json")
        finally:
            owner.close()
