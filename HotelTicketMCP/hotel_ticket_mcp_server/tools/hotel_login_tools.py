"""User-prompted login in the hotel's owned browser; no credentials enter MCP."""
import asyncio
import logging
import os
import queue
import threading
import time
import uuid
from datetime import date, timedelta
from urllib.parse import urlencode, urlsplit
import anyio

from ..utils import consent, cookie_store, login_state, cities_dict, url_builder
from ..utils.browser_factory import SEARCH_LOCK, browser_session

logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 1
OBSERVATION_TIMEOUT_SECONDS = 3
OBSERVATION_RECOVERY_SECONDS = 20
CONNECTION_PROBE_TIMEOUT_SECONDS = 2
TOTAL_TIMEOUT_SECONDS = 930  # Gateway downstream budget is 960 seconds.
LOGIN_URL = "https://passport.ctrip.com/user/login"
LOGIN_QUESTION = "当前酒店查询需要携程登录。选择“打开登录页”后，请在浏览器中完成登录；系统会自动检测，随后继续原酒店查询。"


def _env_int(name, default):
    try:
        return max(1, min(840, int((os.environ.get(name) or str(default)).strip())))
    except (TypeError, ValueError):
        return default


LOGIN_TIMEOUT_SECONDS = _env_int("HOTEL_MCP_LOGIN_TIMEOUT", 840)


def _error(code, message):
    return {"status": "error", "error_code": code, "message": message, "data_source": "ctrip_web_scraping"}


def _interaction_required(return_url=None):
    return {**_error("USER_INTERACTION_REQUIRED", "请先使用 AskUserQuestion 或客户端原生提问工具提醒用户，并等待回答。"),
            "user_action": {"question": LOGIN_QUESTION, "options": ["打开登录页", "取消本次酒店查询"],
                            "accept_arguments": {**({"return_url": return_url} if return_url else {}), "user_action": "open_login"},
                            "cancel_arguments": {"user_action": "cancel"}}}


def verification_url(return_url=None):
    if return_url:
        try:
            parsed = urlsplit(return_url)
            if (parsed.scheme == "https" and parsed.hostname == "hotels.ctrip.com"
                    and parsed.port in (None, 443) and not parsed.username and not parsed.password
                    and parsed.path.rstrip("/") == "/hotels/list"):
                return return_url
        except ValueError:
            pass
        raise ValueError("登录返回地址必须是携程官方酒店列表页面")
    today = date.today()
    return url_builder.build_list_url("武汉", cities_dict.get_city_ids("武汉"),
                                      str(today + timedelta(days=7)), str(today + timedelta(days=9)))["url"]


def _extract_cookies(page):
    result = page.run_cdp("Network.getAllCookies")
    raw = result.get("cookies", []) if isinstance(result, dict) else []
    return cookie_store.to_injectable(raw)


class LoginControl:
    def __init__(self):
        self.stopped = threading.Event()
        self.browser = None
        self.events = queue.SimpleQueue()
        self.commit_lock = threading.Lock()
        self.login_id = uuid.uuid4().hex[:8]
        self.stage = "preparing"
        self.tab_id = None
        self.browser_opened = False
        self.started = time.monotonic()

    def diagnostic(self, event, *, level=logging.INFO, **fields):
        # Callers pass only classifications/counts, never URLs, DOM or exception
        # messages: browser exceptions can embed account data and cookie values.
        details = " ".join(f"{key}={value}" for key, value in fields.items())
        logger.log(level, "hotel_login id=%s stage=%s event=%s %s",
                   self.login_id, self.stage, event, details)

    def set_stage(self, stage):
        if self.stage != stage:
            self.stage = stage
            self.diagnostic("stage_changed")

    def notify(self, message):
        self.events.put(message)
        logger.info("hotel_login id=%s stage=%s %s", self.login_id, self.stage, message)

    def stop(self, reason="client_cancelled"):
        # Linearize cancellation against the final atomic cookie replacement.
        with self.commit_lock:
            if not self.stopped.is_set():
                self.stopped.set()
                self.diagnostic("stop_requested", reason=reason)

    def cancel(self):
        self.stop()
        if self.browser is not None:
            try:
                self.browser.quit()
            except Exception as exc:
                self.diagnostic("cancel_cleanup_failed", level=logging.WARNING,
                                exception_type=type(exc).__name__)


class LoginFlowError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _check_active(control, deadline):
    if control.stopped.is_set():
        raise LoginFlowError("LOGIN_CANCELLED", "登录请求已取消。")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LoginFlowError("LOGIN_TIMEOUT", "等待登录超时，请重新发起登录。")
    return remaining


def _navigate(page, url, control, deadline, timeout=30):
    remaining = _check_active(control, deadline)
    # DrissionPage otherwise retries failed navigation three times by default.
    try:
        loaded = page.get(url, retry=0, timeout=min(timeout, remaining))
    except Exception as exc:
        _check_active(control, deadline)
        control.diagnostic("navigation_failed", level=logging.WARNING, exception_type=type(exc).__name__)
        raise LoginFlowError("LOGIN_PAGE_UNAVAILABLE", "携程页面加载失败，请重试。") from exc
    _check_active(control, deadline)
    if loaded is False:
        control.diagnostic("navigation_failed", level=logging.WARNING, reason="load_incomplete")
        raise LoginFlowError("LOGIN_PAGE_UNAVAILABLE", "携程页面加载失败，请重试。")


def _observe_login(page, control, deadline):
    """Recover navigation races, using independent evidence before declaring closure."""
    recovery_deadline = None
    attempts = missing = 0
    health = "unknown"
    while True:
        remaining = _check_active(control, deadline)
        if recovery_deadline is not None:
            remaining = min(remaining, recovery_deadline - time.monotonic())
            if remaining <= 0:
                if health == "connection_lost":
                    raise LoginFlowError("LOGIN_CONNECTION_LOST", "登录浏览器控制连接中断，请重试。")
                raise LoginFlowError("LOGIN_STATE_UNKNOWN", "无法可靠读取登录状态，请检查页面后重试。")
        try:
            state = login_state.observe(page, timeout=min(OBSERVATION_TIMEOUT_SECONDS, remaining))
        except Exception as exc:
            _check_active(control, deadline)
            if recovery_deadline is None:
                recovery_deadline = min(deadline, time.monotonic() + OBSERVATION_RECOVERY_SECONDS)
            probe_budget = min(_check_active(control, deadline), recovery_deadline - time.monotonic())
            if probe_budget <= 0:
                continue
            try:
                health = control.browser.connection_status(
                    control.tab_id, timeout=min(CONNECTION_PROBE_TIMEOUT_SECONDS, probe_budget))
            except Exception as probe_exc:
                health = "unknown"
                control.diagnostic("probe_failed", level=logging.WARNING, exception_type=type(probe_exc).__name__)
            _check_active(control, deadline)
            attempts += 1
            missing = missing + 1 if health == "page_closed" else 0
            control.diagnostic("observation_failed", level=logging.WARNING,
                               exception_type=type(exc).__name__, connection=health, attempt=attempts)
            if health == "browser_closed":
                raise LoginFlowError("LOGIN_BROWSER_CLOSED", "本次登录浏览器已退出。") from exc
            if missing >= 2:
                raise LoginFlowError("LOGIN_BROWSER_CLOSED", "本次登录标签页已关闭。") from exc
            if isinstance(exc, login_state.LoginObservationError) and health == "alive":
                raise LoginFlowError("LOGIN_STATE_UNKNOWN", "登录状态检测失败，请重试。") from exc
            if attempts == 1:
                control.notify("正在重新确认登录页面，请保持窗口打开…")
            control.stopped.wait(min(POLL_INTERVAL_SECONDS, _check_active(control, deadline),
                                     max(0, recovery_deadline - time.monotonic())))
        else:
            _check_active(control, deadline)
            if attempts:
                control.diagnostic("observation_recovered", attempts=attempts)
            return state


def _fallback_login(page, control, deadline):
    _navigate(page, "https://hotels.ctrip.com/hotels/", control, deadline)
    link = page.ele('css:a[href*="passport.ctrip.com"]', timeout=min(5, _check_active(control, deadline)))
    if not link:
        raise LoginFlowError("LOGIN_PAGE_UNAVAILABLE", "未找到携程登录入口，请重试。")
    # Navigate its official href ourselves to retain the retry/deadline budget.
    href = link.attr("href")
    parsed = urlsplit(href or "")
    if parsed.scheme != "https" or parsed.hostname != "passport.ctrip.com":
        raise LoginFlowError("LOGIN_PAGE_UNAVAILABLE", "未找到有效的携程登录入口。")
    _navigate(page, href, control, deadline)


def _on_hotel_list(url):
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname == "hotels.ctrip.com"
            and parsed.path.rstrip("/") == "/hotels/list")


def ctripHotelLogin(user_action=None, return_url=None, *, control=None):
    control = control or LoginControl()
    control.diagnostic("started")
    result = _run_login(user_action, return_url, control=control)
    reason = result.get("error_code", result["status"])
    control.diagnostic("finished", status=result["status"], close_reason=reason,
                       browser_opened=control.browser_opened,
                       elapsed_seconds=round(time.monotonic() - control.started, 1))
    return result


def _run_login(user_action, return_url, *, control):
    if not consent.is_consented():
        return consent.CONSENT_ERROR
    if user_action == "cancel":
        return _error("LOGIN_CANCELLED", "本次酒店登录已取消。")
    if user_action != "open_login":
        return _interaction_required(return_url)
    try:
        target = verification_url(return_url)
    except ValueError as exc:
        return _error("INVALID_PARAMS", str(exc))
    if control.stopped.is_set():
        return _error("LOGIN_CANCELLED", "登录请求已取消。")
    if not SEARCH_LOCK.acquire(blocking=False):
        return _error("HOTEL_BROWSER_BUSY", "已有酒店搜索或登录正在进行，请等待其结束。")
    deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS
    try:
        control.set_stage("opening_browser")
        with browser_session(visible=True) as browser:
            control.browser = browser
            if control.stopped.is_set():
                return _error("LOGIN_CANCELLED", "登录请求已取消。")
            control.notify("正在打开携程登录页…")
            try:
                _check_active(control, deadline)
                page = browser.get()
                control.browser_opened = True
                control.tab_id = page.tab_id
                _check_active(control, deadline)
                page.set.window.max()
            except Exception as exc:
                _check_active(control, deadline)
                control.diagnostic("browser_open_failed", level=logging.WARNING, exception_type=type(exc).__name__)
                return _error(getattr(exc, "code", "LOGIN_PAGE_UNAVAILABLE"), "无法打开携程登录页，请重试。")

            control.set_stage("opening_login_page")
            fallback_used = False
            try:
                _navigate(page, LOGIN_URL + "?" + urlencode({"backurl": target}), control, deadline, 45)
            except LoginFlowError as exc:
                if exc.code != "LOGIN_PAGE_UNAVAILABLE":
                    raise
                fallback_used = True
                _fallback_login(page, control, deadline)

            ready_deadline = min(deadline, time.monotonic() + 15)
            last_url = ""
            waiting = False
            user_deadline = deadline
            while time.monotonic() < min(deadline, user_deadline):
                if control.stopped.is_set():
                    return _error("LOGIN_CANCELLED", "登录请求已取消。")
                state = _observe_login(page, control, min(deadline, user_deadline))

                if state["state"] == "logged_in":
                    control.set_stage("verifying_login")
                    control.notify("正在验证酒店登录态…")
                    if not _on_hotel_list(state["url"]):
                        _navigate(page, target, control, min(deadline, user_deadline))
                        control.stopped.wait(2)
                        state = _observe_login(page, control, min(deadline, user_deadline))
                        if state["state"] == "logged_in" and not _on_hotel_list(state["url"]):
                            return _error("LOGIN_VERIFICATION_FAILED", "未能进入酒店列表验证登录态，请重试。")
                    if state["state"] == "logged_in" and _on_hotel_list(state["url"]):
                        control.set_stage("saving_cookies")
                        cookies = _extract_cookies(page)
                        _check_active(control, min(deadline, user_deadline))
                        if not cookies:
                            return _error("LOGIN_VERIFICATION_FAILED", "未能取得有效登录cookie，请重试。")
                        saved = cookie_store.save_cookies(cookies, commit_lock=control.commit_lock,
                                                          cancelled=control.stopped)
                        if saved is None:
                            return _error("LOGIN_CANCELLED", "登录请求已取消。")
                        control.diagnostic("cookies_saved", cookie_count=len(cookies))
                        control.notify("登录成功，登录态已保存，可继续原酒店查询。")
                        return {"status": "success", "message": "登录成功，请原样重试先前的酒店查询一次。",
                                "cookie_count": len(cookies), "data_source": "ctrip_web_scraping"}

                # A successful login may land on the hotel homepage. Verify on the protected list.
                host = urlsplit(state["url"]).hostname
                if host == "hotels.ctrip.com" and state["ready"] and state["url"] != target and state["url"] != last_url:
                    last_url = state["url"]
                    control.set_stage("verifying_login")
                    _navigate(page, target, control, min(deadline, user_deadline))
                    continue
                if host == "passport.ctrip.com" and state["ready"] and state["login_form"]:
                    control.set_stage("waiting_for_login")
                    if not waiting:
                        waiting = True
                        user_deadline = min(deadline - 30, time.monotonic() + LOGIN_TIMEOUT_SECONDS)
                        control.notify("携程登录页已打开，请在浏览器中扫码或输入账号完成登录；完成后系统会自动检测。")
                elif not waiting and time.monotonic() >= ready_deadline:
                    if fallback_used:
                        return _error("LOGIN_PAGE_UNAVAILABLE", "未能展示携程登录表单，请检查浏览器页面后重试。")
                    fallback_used = True
                    _fallback_login(page, control, deadline)
                    ready_deadline = min(deadline, time.monotonic() + 15)
                control.stopped.wait(POLL_INTERVAL_SECONDS)
            return _error("LOGIN_TIMEOUT", "等待登录超时，窗口已关闭。请重新发起登录。")
    except LoginFlowError as exc:
        return _error(exc.code, str(exc))
    except Exception as exc:
        control.diagnostic("failed", level=logging.ERROR, exception_type=type(exc).__name__)
        return _error("LOGIN_CANCELLED" if control.stopped.is_set() else "LOGIN_VERIFICATION_FAILED",
                      "登录已取消。" if control.stopped.is_set() else "登录验证失败，请重试。")
    finally:
        control.browser = None
        SEARCH_LOCK.release()


async def login_with_progress(user_action, return_url, ctx):
    """Keep browser work off the event loop so progress and cancellation can flow."""
    control = LoginControl()
    worker = asyncio.create_task(asyncio.to_thread(ctripHotelLogin, user_action, return_url, control=control))
    progress = 0
    message = "正在准备酒店登录…"
    next_heartbeat = 0
    operation = "waiting_for_worker"
    try:
        while not worker.done():
            changed = False
            while not control.events.empty():
                message = control.events.get_nowait()
                changed = True
            if changed or time.monotonic() >= next_heartbeat:
                progress += 1
                operation = "reporting_progress"
                await ctx.report_progress(progress, message=message)
                operation = "waiting_for_worker"
                next_heartbeat = time.monotonic() + 15
            await asyncio.sleep(0.2)
        result = await worker
        operation = "reporting_result"
        await ctx.report_progress(progress + 1, message=result.get("message", "登录流程结束"))
        return result
    except BaseException as exc:
        reason = "client_cancelled" if isinstance(exc, asyncio.CancelledError) else "async_failure"
        control.diagnostic("interrupted", level=logging.WARNING, reason=reason,
                           operation=operation, exception_type=type(exc).__name__)
        control.stop(reason)
        # A dedicated thread can close a blocked browser even when the default
        # executor is saturated. AnyIO shielding handles MCP's level cancellation.
        cleanup = threading.Thread(target=control.cancel, daemon=True)
        cleanup.start()
        with anyio.CancelScope(shield=True):
            with anyio.move_on_after(50):
                while not worker.done() or cleanup.is_alive():
                    await asyncio.sleep(0.05)
                try:
                    await worker
                except (Exception, asyncio.CancelledError):
                    pass
        raise
