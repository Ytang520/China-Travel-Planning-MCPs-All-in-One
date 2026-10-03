"""Live manual Chrome login, cookie persistence and independent-browser reuse.

Run with the project environment. --login-action=open_login records an explicit
user request to open the login window; passwords/QR verification stay in Ctrip.
Cookie files remain under the ignored .validation directory after the check.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import uuid

from hotel_ticket_mcp_server import main as bootstrap
from hotel_ticket_mcp_server.tools import hotel_login_tools as login
from hotel_ticket_mcp_server.tools import hotel_search_tools as search
from hotel_ticket_mcp_server.utils import consent, cookie_store, login_state
from hotel_ticket_mcp_server.utils.browser_factory import BrowserSingleton

ROOT = Path(__file__).resolve().parents[1]


def emit(event, **details):
    print(json.dumps({"event": event, **details}, ensure_ascii=False), flush=True)


class CheckedBrowser(BrowserSingleton):
    def __init__(self, engine, record, *, visible=False):
        self.engine = engine
        self.record = record
        self.observed = False
        profile = ROOT / ".validation" / ("cs-" + uuid.uuid4().hex[:10])
        super().__init__(profile_dir=profile, visible=visible)

    def get(self):
        page = super().get()
        self._session.temporary = True
        if not self.observed:
            actual = self._session.diagnostic.get("actual_browser")
            self.record["actual_browser"] = actual
            self.record["profile_id"] = self.profile_dir.name
            if actual != self.engine:
                raise RuntimeError("Requested browser identity did not match")
            raw = page.run_cdp("Network.getAllCookies", _timeout=5).get("cookies", [])
            initial = sum(1 for cookie in raw if cookie.get("domain", "").lstrip(".") == "ctrip.com"
                          or cookie.get("domain", "").endswith(".ctrip.com"))
            self.record["initial_ctrip_cookie_count"] = initial
            if initial:
                raise RuntimeError("The independent browser profile is not empty")
            self.observed = True
            emit("browser_opened", case=self.record["case"], actual_browser=actual,
                 profile_id=self.profile_dir.name, initial_ctrip_cookie_count=initial)
        return page

    def quit(self):
        super().quit()
        if self.observed:
            self.record["browser_closed"] = True
            self.record["profile_removed"] = not self.profile_dir.exists()


def cookie_metadata(path):
    cookies = cookie_store.load_cookies(path)
    return {"saved_cookie_count": len(cookies),
            "injectable_cookie_count": len(cookie_store.to_injectable(cookies)),
            "http_only_count": sum(bool(cookie.get("httpOnly")) for cookie in cookies),
            "secure_count": sum(bool(cookie.get("secure")) for cookie in cookies),
            "same_site_count": sum("sameSite" in cookie for cookie in cookies),
            "persistent_count": sum("expires" in cookie for cookie in cookies)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login-action", choices=["open_login", "cancel"])
    parser.add_argument("--reuse-only", action="store_true")
    parser.add_argument("--cookie-file", type=Path)
    args = parser.parse_args()
    if args.reuse_only and not args.cookie_file:
        parser.error("--reuse-only requires --cookie-file")
    if not args.reuse_only and args.login_action != "open_login":
        emit("login_choice_required", error_code="USER_INTERACTION_REQUIRED" if not args.login_action else "LOGIN_CANCELLED")
        return 2
    if not consent.is_consented():
        emit("consent_required", error_code=consent.CONSENT_ERROR.get("error_code"))
        return 2
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    run_dir = ROOT / ".validation" / ("chrome-session-" + stamp)
    run_dir.mkdir(parents=True)
    cookie_file = args.cookie_file.resolve() if args.cookie_file else run_dir / "chrome-cookies.json"
    report_file = run_dir / "report.json"
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "running", "cases": [],
              "cookie_file": str(cookie_file), "source": "existing_cookie_file" if args.reuse_only else "fresh_manual_chrome_login"}

    def save_report():
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    @contextmanager
    def owned(engine, record, *, visible=False):
        os.environ["HOTEL_MCP_BROWSER"] = engine
        os.environ.pop("HOTEL_MCP_BROWSER_PATH", None)
        os.environ["HOTEL_MCP_HEADLESS"] = "0"
        browser = CheckedBrowser(engine, record, visible=visible)
        try:
            yield browser
        finally:
            browser.quit()
            save_report()

    target = login.verification_url()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    # Existing provider logs contain classifications/counts, never cookie values.
    os.environ["HOTEL_MCP_COOKIE_FILE"] = str(cookie_file)
    emit("check_started", report_file=str(report_file), cookie_file=str(cookie_file), source=report["source"])
    try:
        if not args.reuse_only:
            record = {"case": "chrome_fresh_login_and_save", "requested_browser": "chrome", "status": "running"}
            report["cases"].append(record)

            @contextmanager
            def login_session(*, visible=False):
                with owned("chrome", record, visible=visible) as browser:
                    yield browser

            original_factory = login.browser_session
            login.browser_session = login_session
            try:
                result = login.ctripHotelLogin("open_login", target)
            finally:
                login.browser_session = original_factory
            record.update(status=result.get("status", "error"), error_code=result.get("error_code"))
            if result.get("status") != "success":
                emit("login_failed", error_code=result.get("error_code"), message=result.get("message"))
                report["status"] = "failed"
                return 1
            record.update(cookie_metadata(cookie_file))
            if not record["saved_cookie_count"] or not record["injectable_cookie_count"]:
                raise RuntimeError("The verified login did not persist injectable cookies")
            emit("login_saved", **{key: value for key, value in record.items() if key != "profile_id"})
        elif not cookie_store.to_injectable(cookie_store.load_cookies(cookie_file)):
            raise RuntimeError("The reuse file contains no injectable cookies")

        original_bytes = hashlib.sha256(cookie_file.read_bytes()).digest()
        edge_cookie_file = run_dir / "edge-cookies.json"
        for case, engine, source_file in (
            ("chrome_to_new_chrome", "chrome", cookie_file),
            ("chrome_to_new_edge", "edge", cookie_file),
            ("edge_to_new_chrome_roundtrip", "chrome", edge_cookie_file),
        ):
            record = {"case": case, "requested_browser": engine, "status": "running"}
            report["cases"].append(record)
            if not source_file.exists():
                record.update(status="skipped", error_code="SOURCE_COOKIES_UNAVAILABLE")
                continue
            os.environ["HOTEL_MCP_COOKIE_FILE"] = str(source_file)
            try:
                with owned(engine, record) as browser:
                    page = browser.get()
                    error = search._ensure_logged_in(page, target)
                    if error:
                        record.update(status="failed", error_code=error.get("error_code"))
                    else:
                        state = login_state.observe(page)
                        cards = search._snapshot_cards(page)
                        record.update(login_state=state["state"], hotel_card_count=len(cards))
                        if state["state"] != "logged_in" or not cards:
                            record.update(status="failed", error_code="PROTECTED_HOTEL_LIST_NOT_VERIFIED")
                        else:
                            record["status"] = "success"
                            if engine == "edge":
                                cookie_store.save_cookies(login._extract_cookies(page), edge_cookie_file)
                                record["exported_cookie_count"] = len(cookie_store.load_cookies(edge_cookie_file))
            except Exception as error:
                record.update(status="failed", error_code=type(error).__name__)
            emit("reuse_checked", **record)
            save_report()
        report["chrome_cookie_file_unchanged_during_reuse"] = hashlib.sha256(cookie_file.read_bytes()).digest() == original_bytes
        report["status"] = "success" if all(case["status"] == "success" for case in report["cases"]) and report["chrome_cookie_file_unchanged_during_reuse"] else "failed"
        return 0 if report["status"] == "success" else 1
    except Exception as error:
        report.update(status="failed", error_code=type(error).__name__)
        emit("check_failed", error_code=type(error).__name__)
        return 1
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_report()
        emit("check_finished", status=report["status"], report_file=str(report_file), cookie_file=str(cookie_file))


if __name__ == "__main__":
    sys.exit(main())
