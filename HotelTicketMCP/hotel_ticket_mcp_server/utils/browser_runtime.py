"""Owned browser sessions and crash recovery; mirrored in the flight package."""

import json
import logging
import math
import os
import shutil
import signal
import socket
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import psutil

from .browser_discovery import BrowserDiscovery, BrowserError

logger = logging.getLogger(__name__)
_sessions = set()
_sessions_lock = threading.Lock()
_stopping = threading.Event()
_signal_number = None


def canonical(path):
    return os.path.normcase(os.path.realpath(path))


def argument(args, name):
    for index, arg in enumerate(args):
        if arg.startswith(name + "="):
            return arg[len(name) + 1:].strip('"')
        if arg == name and index + 1 < len(args):
            return args[index + 1].strip('"')
    return None


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(0.1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def validate_record(record, profile):
    if not isinstance(record, dict) or record.get("version") != 1 or record.get("profile") != canonical(profile):
        raise ValueError("Invalid ownership record")
    for key in ("owner_pid", "port"):
        if type(record.get(key)) is not int or record[key] <= 0:
            raise ValueError("Invalid process/port identity")
    if record["port"] > 65535 or record.get("state") not in {"launching", "running", "cleanup_pending"}:
        raise ValueError("Invalid startup state")
    for key in ("owner_created", "started"):
        value = record.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("Invalid process creation time")
    if "browser_pid" in record or "browser_created" in record:
        value = record.get("browser_created")
        if (type(record.get("browser_pid")) is not int or record["browser_pid"] <= 0
                or type(value) not in (int, float) or not math.isfinite(value) or value <= 0):
            raise ValueError("Incomplete browser identity")


class ProfileLock:
    def __init__(self, path, platform=None):
        self.path = Path(path)
        self.platform = platform or sys.platform
        self.stream = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(self.path, "a+b")
        try:
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if self.platform == "win32":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            stream.close()
            raise BrowserError("BROWSER_PROFILE_IN_USE", "浏览器 profile 正被另一实例使用") from exc
        self.stream = stream

    def release(self):
        if self.stream is not None:
            # Closing the descriptor releases the OS lock, including after crashes.
            self.stream.close()
            self.stream = None


class Processes:
    def identity(self, pid):
        try:
            proc = psutil.Process(pid)
            return proc, proc.create_time()
        except psutil.NoSuchProcess:
            return None, None

    def profile_processes(self, profile):
        result = []
        for proc in psutil.process_iter(["pid", "cmdline", "create_time"]):
            try:
                args = proc.info["cmdline"] or []
                value = argument(args, "--user-data-dir")
                if value and canonical(value) == canonical(profile):
                    result.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return result

    def owned(self, record):
        """PID reuse is not ownership; constructor failures use exact startup intent."""
        if record.get("browser_pid") is not None:
            proc, created = self.identity(record["browser_pid"])
            candidates = [proc] if proc and created == record["browser_created"] else []
        else:
            candidates = self.profile_processes(record["profile"])
        result = []
        for proc in candidates:
            try:
                args = proc.cmdline()
                profile = argument(args, "--user-data-dir")
                port = argument(args, "--remote-debugging-port")
                if (profile and canonical(profile) == record["profile"]
                        and port == str(record["port"])
                        and proc.create_time() >= record["started"] - 1):
                    result.append(proc)
                elif record.get("browser_pid") is not None:
                    raise BrowserError("BROWSER_PROFILE_IN_USE", "浏览器进程归属无法验证，未自动终止")
            except psutil.NoSuchProcess:
                continue
        return result

    def tree(self, roots):
        found = {}
        for proc in roots:
            try:
                for child in proc.children(recursive=True):
                    found[(child.pid, child.create_time())] = child
                found[(proc.pid, proc.create_time())] = proc
            except psutil.NoSuchProcess:
                continue
        return list(found.values())

    def wait(self, processes, deadline):
        _, alive = psutil.wait_procs(processes, timeout=max(0, deadline - time.monotonic()))
        return alive

    def finish(self, processes, deadline):
        # psutil's is_running/terminate/kill also check for PID reuse.
        alive = [p for p in processes if p.is_running()]
        for proc in alive:
            try:
                proc.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(alive, timeout=max(0, min(0.5, deadline - time.monotonic())))
        for proc in alive:
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(alive, timeout=max(0, min(0.5, deadline - time.monotonic())))
        return not alive


def bounded_quit(page, timeout):
    """quit's timeout doesn't bound all its internals; never block shutdown on it."""
    def quit_page():
        try:
            page.quit(timeout=min(1, timeout), force=False, del_data=False)
        except Exception:
            logger.warning("Browser graceful close failed; checking owned processes")
    worker = threading.Thread(target=quit_page, daemon=True)
    worker.start()
    worker.join(max(0, timeout))


def create_options(options_factory, path, profile, port, headless):
    options = options_factory()
    # new_env=True inherited from an INI would delete the explicit profile.
    options.new_env(False)
    options.use_system_user_path(False)
    options.existing_only(False)
    options.headless(bool(headless))
    options.set_local_port(port)
    options.set_user_data_path(str(profile))
    options.set_argument("--window-size", "1280,900")
    if not headless:
        for arg in ("--start-minimized", "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding", "--disable-background-timer-throttling"):
            options.set_argument(arg)
    if path is not None:
        options.set_browser_path(path)
    return options


class OwnedBrowser:
    def __init__(self, prefix, project_root, profile, *, temporary=False,
                 discovery=None, processes=None, lock=None):
        self.prefix = prefix
        self.profile = Path(profile).resolve()
        self.temporary = temporary
        self.discovery = discovery or BrowserDiscovery(project_root)
        self.processes = processes or Processes()
        self.lock = lock or ProfileLock(self.profile / ".travel-mcp.lock")
        self.record_path = self.profile / ".travel-mcp-owner.json"
        self.record = None
        self.page = None
        self.diagnostic = None
        self._operation = threading.RLock()
        self._closing = threading.Event()
        self._locked = False
        with _sessions_lock:
            # open() rejects shutdown and cleans an already allocated temporary profile.
            _sessions.add(self)

    def _save(self):
        temp = self.record_path.with_suffix(".tmp")
        with open(temp, "w", encoding="utf-8") as stream:
            json.dump(self.record, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.record_path)

    def _recover(self):
        if self.record_path.exists():
            try:
                record = json.loads(self.record_path.read_text(encoding="utf-8"))
                validate_record(record, self.profile)
                owner, created = self.processes.identity(record["owner_pid"])
                if (owner and created == record["owner_created"]
                        and record["owner_pid"] != os.getpid()):
                    raise BrowserError("BROWSER_PROFILE_IN_USE", "profile 所属服务仍在运行")
                self.record = record
                if not self._cleanup_attempt(time.monotonic() + 2):
                    raise BrowserError("BROWSER_CLEANUP_INCOMPLETE", "上次浏览器未确认退出，请检查后重试")
            except (ValueError, KeyError, TypeError, OSError, psutil.Error) as exc:
                raise BrowserError("BROWSER_PROFILE_IN_USE", "无法验证 profile 恢复记录，请人工检查") from exc
        if self.processes.profile_processes(self.profile):
            raise BrowserError("BROWSER_PROFILE_IN_USE", "profile 被未记录的浏览器占用，请先手动关闭该实例")

    def _cleanup_attempt(self, deadline):
        if self.record is None:
            return True
        try:
            roots = self.processes.owned(self.record)
            tree = self.processes.tree(roots)
            # Never send Browser.close to an unverified page/attached user browser.
            if self.page is not None and roots:
                graceful_deadline = min(deadline, time.monotonic() + 1)
                bounded_quit(self.page, max(0, graceful_deadline - time.monotonic()))
                tree = self.processes.wait(tree, graceful_deadline)
            finished = self.processes.finish(tree, deadline)
            if not finished or self.processes.owned(self.record) or port_open(self.record["port"]):
                self.record["state"] = "cleanup_pending"
                self._save()
                return False
            self.record_path.unlink(missing_ok=True)
            self.record = None
            self.page = None
            return True
        except (OSError, ValueError, KeyError, TypeError, psutil.Error, BrowserError):
            logger.warning("Browser ownership/cleanup could not be verified; retaining recovery record")
            return False

    def open(self, page_factory, options_factory, headless=False):
        with self._operation:
            try:
                if self._closing.is_set() or _stopping.is_set():
                    raise BrowserError("BROWSER_SHUTTING_DOWN", "服务正在关闭")
                resolution = self.discovery.resolve(self.prefix)
                self.lock.acquire()
                self._locked = True
                self._recover()
                attempts = [(resolution.path, resolution.source)]
                if resolution.path and resolution.source != "configured":
                    attempts.append((None, "drissionpage"))
                for index, (path, source) in enumerate(attempts):
                    if self._closing.is_set() or _stopping.is_set():
                        raise BrowserError("BROWSER_SHUTTING_DOWN", "服务正在关闭")
                    port = free_port()
                    _, created = self.processes.identity(os.getpid())
                    self.record = {
                        "version": 1, "profile": canonical(self.profile), "port": port,
                        "owner_pid": os.getpid(), "owner_created": created,
                        "started": time.time(), "state": "launching",
                    }
                    self._save()
                    try:
                        options = create_options(options_factory, path, self.profile, port, headless)
                        self.page = page_factory(options)
                        browser = self.page.browser
                        pid = browser.process_id
                        # psutil.Process(None) means this provider, not the browser.
                        # Keep the launching record intact for intent-based cleanup.
                        if type(pid) is not int or pid <= 0:
                            raise RuntimeError("Browser did not report a valid process ID")
                        _, browser_created = self.processes.identity(pid)
                        if browser_created is None:
                            raise RuntimeError("Browser exited during startup")
                        self.record.update(browser_pid=pid, browser_created=browser_created, state="running")
                        self._save()
                        if not self.processes.owned(self.record):
                            raise BrowserError("BROWSER_PROFILE_IN_USE", "启动后的浏览器归属无法验证")
                        if self._closing.is_set() or _stopping.is_set():
                            raise BrowserError("BROWSER_SHUTTING_DOWN", "浏览器启动期间服务已关闭")
                        actual = "unknown"
                        try:
                            process, _ = self.processes.identity(pid)
                            executable = os.path.basename(process.exe()).lower()
                            if "msedge" in executable or "microsoft edge" in executable:
                                actual = "edge"
                            elif "chrome" in executable or "chromium" in executable:
                                actual = "chrome"
                        except (AttributeError, OSError, psutil.Error):
                            pass
                        self.diagnostic = {"source": source, "requested_browser": resolution.requested_browser,
                                           "actual_browser": actual}
                        logger.info("%s browser started: source=%s, preference=%s, actual=%s", self.prefix, source,
                                    resolution.requested_browser, actual)
                        return self.page
                    except Exception as exc:
                        if not self._cleanup_attempt(time.monotonic() + 2):
                            raise BrowserError("BROWSER_CLEANUP_INCOMPLETE", "浏览器启动残留未清理，已停止重试") from exc
                        if isinstance(exc, BrowserError) or index == len(attempts) - 1:
                            if isinstance(exc, BrowserError):
                                raise
                            raise BrowserError(
                                "BROWSER_LAUNCH_FAILED",
                                f"浏览器启动失败 ({type(exc).__name__}, {source}); 请检查显示环境或提供 {self.prefix}_BROWSER_PATH",
                            ) from exc
                        logger.warning("Automatically discovered browser failed; trying DrissionPage discovery once")
            except BaseException:
                self.close(raise_on_failure=False)
                raise

    def close(self, budget=2, raise_on_failure=True):
        self._closing.set()
        deadline = time.monotonic() + budget
        if not self._operation.acquire(timeout=max(0, budget)):
            if raise_on_failure:
                raise BrowserError("BROWSER_CLEANUP_INCOMPLETE", "浏览器仍在启动或清理，已保留恢复记录")
            return False  # Constructor will observe _closing and clean its late result.
        complete = False
        try:
            try:
                complete = self._cleanup_attempt(deadline) if self._locked else self.record is None
            except Exception:
                logger.exception("Unexpected cleanup failure; retaining recovery record")
            finally:
                try:
                    if self._locked:
                        self.lock.release()
                        self._locked = False
                finally:
                    with _sessions_lock:
                        _sessions.discard(self)
            if complete and self.temporary and self.profile.exists():
                # Only the exact temporary directory allocated for this session.
                shutil.rmtree(self.profile)
        finally:
            self._operation.release()
        if not complete and raise_on_failure:
            raise BrowserError("BROWSER_CLEANUP_INCOMPLETE", "浏览器清理未完成，已保留恢复记录")
        return complete


def shutdown_browsers(budget=1.5):
    _stopping.set()
    with _sessions_lock:
        sessions = list(_sessions)
    deadline = time.monotonic() + budget
    workers = []
    for session in sessions:
        session._closing.set()
        worker = threading.Thread(target=session.close, kwargs={"budget": budget, "raise_on_failure": False}, daemon=True)
        worker.start()
        workers.append(worker)
    for worker in workers:
        worker.join(max(0, deadline - time.monotonic()))


@asynccontextmanager
async def browser_lifespan(server):
    try:
        yield
    finally:
        shutdown_browsers()


def install_shutdown_handlers():
    """Signals never wait for locks held by synchronous tools or constructors."""
    def request_stop(signum, frame):
        global _signal_number
        _signal_number = signum
        _stopping.set()

    def coordinate():
        _stopping.wait()
        if _signal_number is not None:
            shutdown_browsers()
            # A sync tool can outlive the event loop. Records make this recoverable.
            os._exit(128 + _signal_number)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, request_stop)
    threading.Thread(target=coordinate, daemon=True).start()
