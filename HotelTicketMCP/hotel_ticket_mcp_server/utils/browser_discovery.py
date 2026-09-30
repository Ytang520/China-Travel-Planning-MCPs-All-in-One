"""Bounded browser discovery. Keep in sync with the flight package (contract-tested)."""

import logging
import ntpath
import os
import plistlib
import posixpath
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class BrowserError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class BrowserResolution:
    path: str | None
    source: str
    requested_browser: str


class BrowserDiscovery:
    """OS operations are injectable so POSIX behavior can be tested on Windows."""

    def __init__(self, project_root, *, platform=None, env=None, home=None,
                 which=None, isfile=None, executable=None):
        self.platform = platform or sys.platform
        self.env = os.environ if env is None else env
        self.home = str(Path.home()) if home is None else home
        self.paths = ntpath if self.platform == "win32" else posixpath
        self.root = str(project_root)
        self.which = which or shutil.which
        self.isfile = isfile or os.path.isfile
        self.executable = executable or (lambda p: os.access(p, os.X_OK))

    def normalize(self, value):
        value = str(value).strip().strip('"')
        if value == "~" or value.startswith(("~/", "~\\")):
            value = self.paths.join(self.home, value[2:]) if len(value) > 1 else self.home
        if not self.paths.isabs(value):
            value = self.paths.join(self.root, value)
        return self.paths.normpath(value)

    def bundle_executable(self, bundle):
        with open(self.paths.join(bundle, "Contents", "Info.plist"), "rb") as stream:
            name = plistlib.load(stream).get("CFBundleExecutable")
        if not isinstance(name, str) or self.paths.basename(name) != name:
            raise ValueError("Invalid CFBundleExecutable")
        return self.paths.join(bundle, "Contents", "MacOS", name)

    def valid_path(self, value):
        if not value:
            return None
        try:
            path = self.normalize(value)
            if self.platform == "darwin" and path.endswith(".app"):
                path = self.bundle_executable(path)
            if self.isfile(path) and (self.platform == "win32" or self.executable(path)):
                return path
        except (OSError, ValueError, plistlib.InvalidFileException):
            pass
        return None

    def registered(self, browser):
        if self.platform == "win32":
            import winreg

            executable = "msedge.exe" if browser == "edge" else "chrome.exe"
            key = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + executable
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                    try:
                        with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as handle:
                            value, kind = winreg.QueryValueEx(handle, None)
                            if kind == winreg.REG_EXPAND_SZ:
                                value = winreg.ExpandEnvironmentStrings(value)
                            yield value, "registry"
                    except OSError:
                        continue
        elif self.platform == "darwin":
            bundle = "com.microsoft.edgemac" if browser == "edge" else "com.google.Chrome"
            script = ("ObjC.import('AppKit'); "
                      f"var u = $.NSWorkspace.sharedWorkspace.URLForApplicationWithBundleIdentifier('{bundle}'); "
                      "u.isNil() ? '' : ObjC.unwrap(u.path);")
            try:
                result = subprocess.run(
                    ["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
                    capture_output=True, text=True, timeout=2, check=True,
                )
                if result.stdout.strip():
                    yield result.stdout.strip(), "bundle"
            except (OSError, subprocess.SubprocessError):
                return

    def commands(self, browser):
        if self.platform == "win32":
            return ("msedge.exe",) if browser == "edge" else ("chrome.exe",)
        if self.platform == "darwin":
            return (("microsoft-edge", "Microsoft Edge") if browser == "edge"
                    else ("google-chrome", "Google Chrome"))
        return (("microsoft-edge", "microsoft-edge-stable") if browser == "edge"
                else ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"))

    def common_paths(self, browser):
        join = self.paths.join
        if self.platform == "win32":
            relative = (("Microsoft", "Edge", "Application", "msedge.exe") if browser == "edge"
                        else ("Google", "Chrome", "Application", "chrome.exe"))
            for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
                base = self.env.get(key)
                if base:
                    yield join(base, *relative)
        elif self.platform == "darwin":
            app = "Microsoft Edge.app" if browser == "edge" else "Google Chrome.app"
            for base in ("/Applications", join(self.home, "Applications")):
                yield join(base, app)
        else:
            for base in ("/usr/bin", "/usr/local/bin", "/snap/bin", join(self.home, ".local", "bin")):
                for command in self.commands(browser):
                    yield join(base, command)
            yield "/opt/microsoft/msedge/msedge" if browser == "edge" else "/opt/google/chrome/chrome"

    def resolve(self, prefix):
        browser = (self.env.get(prefix + "_BROWSER") or "edge").strip().lower()
        if browser not in {"edge", "chrome"}:
            logger.warning("Unknown %s_BROWSER; using edge preference", prefix)
            browser = "edge"
        explicit = (self.env.get(prefix + "_BROWSER_PATH") or "").strip()
        if explicit:
            path = self.valid_path(explicit)
            if not path:
                raise BrowserError("BROWSER_PATH_INVALID", f"请提供有效的 {prefix}_BROWSER_PATH 浏览器可执行文件路径")
            return BrowserResolution(path, "configured", browser)
        for candidate_browser in (browser, "chrome" if browser == "edge" else "edge"):
            for value, source in self.registered(candidate_browser):
                path = self.valid_path(value)
                if path:
                    return BrowserResolution(path, source, browser)
            # Do not enumerate PATH. Only ask which() for these browser commands.
            for command in self.commands(candidate_browser):
                path = self.valid_path(self.which(command))
                if path:
                    return BrowserResolution(path, "which", browser)
            for value in self.common_paths(candidate_browser):
                path = self.valid_path(value)
                if path:
                    return BrowserResolution(path, "common", browser)
        return BrowserResolution(None, "drissionpage", browser)
