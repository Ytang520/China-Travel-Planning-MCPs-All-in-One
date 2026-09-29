"""浏览器工厂：路径解析、空闲端口、残留清理、ChromiumOptions 构造（按次使用，用完即关）。

设计要点（均经 2026-09-29 实测验证）：
- 未设 user_data_path 时 DrissionPage 会用 PortFinder 管理的临时 profile；
  酒店需要自己的持久 profile（保持浏览器指纹稳定），因此显式 set_local_port + set_user_data_path
  （set_user_data_path 单独使用会因 address 为空而崩溃）。
- 同一 profile 目录被已存活的浏览器实例锁定时，新启动会 BrowserConnectError；
  因此启动前按 profile 路径精确清理本工具遗留的进程（绝不触碰用户自己的浏览器）。
- 方案 A：browser_session() 上下文管理器保证每次搜索/登录结束即关闭浏览器；
  登录态不依赖浏览器存活，由 cookie 文件注入承载。
"""

import logging
import os
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from DrissionPage import ChromiumPage, ChromiumOptions

    DRISSION_PAGE_AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖缺失时由上层返回明确错误
    ChromiumPage = None
    ChromiumOptions = None
    DRISSION_PAGE_AVAILABLE = False

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

DEFAULT_PROFILE_DIR = (
    Path(__file__).resolve().parent.parent.parent / ".browser-profile"
)

# 共享串行锁：搜索与登录共用，保证同一时刻只有一个浏览器操作
SEARCH_LOCK = threading.Lock()


def resolve_browser_path():
    """优先级：HOTEL_MCP_BROWSER_PATH > HOTEL_MCP_BROWSER(edge 默认/chrome) > 探测另一内核。"""
    env_path = os.environ.get("HOTEL_MCP_BROWSER_PATH")
    if env_path:
        return env_path

    engine = (os.environ.get("HOTEL_MCP_BROWSER") or "edge").strip().lower()
    if engine not in {"edge", "chrome"}:
        logger.warning("未知 HOTEL_MCP_BROWSER=%r，回退为 'edge'", engine)
        engine = "edge"

    primary, secondary = (
        (EDGE_CANDIDATES, CHROME_CANDIDATES)
        if engine == "edge"
        else (CHROME_CANDIDATES, EDGE_CANDIDATES)
    )
    for path in primary:
        if os.path.exists(path):
            return path
    for path in secondary:
        if os.path.exists(path):
            logger.warning("HOTEL_MCP_BROWSER=%s 未找到，回退使用 %s", engine, path)
            return path
    return None


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def cleanup_stale_profile_processes(profile_dir):
    """按 profile 路径过滤 CommandLine，终止本工具遗留的浏览器进程（不碰用户浏览器）。

    注意：PowerShell -like 通配符中 `\\` 匹配两个字面反斜杠，因此路径中的
    单反斜杠必须原样保留，只对单引号做转义。
    """
    if os.name != "nt":
        return 0
    needle = str(profile_dir).replace("'", "''")
    killed = 0
    for exe in ("msedge.exe", "chrome.exe"):
        ps_cmd = (
            f'Get-CimInstance Win32_Process -Filter "Name=\'{exe}\'" | '
            f"Where-Object {{ $_.CommandLine -like '*{needle}*' }} | "
            "ForEach-Object { "
            "Write-Output ('kill ' + $_.ProcessId); "
            "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                timeout=30,
                check=False,
            )
            killed += len(proc.stdout.splitlines())
        except Exception as e:  # pragma: no cover - 清理失败不阻断启动
            logger.warning("清理残留浏览器进程失败: %s", e)
    return killed


def create_options(browser_path, profile_dir, headless=False):
    co = ChromiumOptions()
    if headless:
        co.headless()
        co.set_argument("--window-size", "1280,900")
    else:
        # 后台打开：最小化启动、任务栏可见、不抢前台；关闭后台节流防懒加载失效
        co.set_argument("--start-minimized")
        co.set_argument("--window-size", "1280,900")
        co.set_argument("--disable-backgrounding-occluded-windows")
        co.set_argument("--disable-renderer-backgrounding")
        co.set_argument("--disable-background-timer-throttling")
    # 显式空闲端口 + 显式 profile（auto_port 与 set_user_data_path 不可混用）
    co.set_local_port(free_port())
    co.set_user_data_path(str(profile_dir))
    if browser_path:
        co.set_browser_path(browser_path)
    return co


class BrowserSingleton:
    """按次使用的浏览器实例：每次搜索/登录用完即关（方案 A）。

    登录态不依赖浏览器存活——由 cookie 文件承载，跨会话注入恢复（已实测）。
    启动前仍会清理上次异常退出遗留的残留进程。
    """

    def __init__(self, profile_dir=None):
        self.profile_dir = Path(profile_dir) if profile_dir else DEFAULT_PROFILE_DIR
        self._page = None
        self._lock = threading.Lock()

    def get(self):
        if not DRISSION_PAGE_AVAILABLE:
            raise RuntimeError("DrissionPage 未安装，无法使用酒店搜索功能")
        with self._lock:
            if self._page is not None:
                return self._page
            browser_path = resolve_browser_path()
            if not browser_path:
                raise RuntimeError(
                    "未找到可用浏览器（Edge/Chrome），请安装浏览器或设置 HOTEL_MCP_BROWSER_PATH"
                )
            headless = os.environ.get("HOTEL_MCP_HEADLESS", "0") == "1"
            killed = cleanup_stale_profile_processes(self.profile_dir)
            if killed:
                logger.info("清理了 %s 个残留浏览器进程", killed)
                time.sleep(1)  # 等待 profile 锁释放
            co = create_options(browser_path, self.profile_dir, headless)
            try:
                self._page = ChromiumPage(co)
            except Exception:
                # profile 可能仍被锁：再清一次后重试
                cleanup_stale_profile_processes(self.profile_dir)
                co = create_options(browser_path, self.profile_dir, headless)
                self._page = ChromiumPage(co)
            return self._page

    def reset(self):
        with self._lock:
            try:
                if self._page is not None:
                    self._page.quit()
            except Exception:  # pragma: no cover - quit 异常不影响重建
                pass
            self._page = None

    def quit(self):
        self.reset()


_default_singleton = None


def get_default_singleton():
    global _default_singleton
    if _default_singleton is None:
        _default_singleton = BrowserSingleton()
    return _default_singleton


@contextmanager
def browser_session():
    """按次开关浏览器：with 块退出时无论成败都关闭浏览器进程。

    配合 SEARCH_LOCK 使用：`with SEARCH_LOCK, browser_session() as singleton:`。
    """
    singleton = get_default_singleton()
    try:
        yield singleton
    finally:
        singleton.quit()
