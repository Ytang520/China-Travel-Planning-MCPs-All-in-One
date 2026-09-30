"""Run both independently installed packages against the same platform contracts."""
import importlib
import json
import os
import posixpath
import plistlib
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(params=["flight_ticket_mcp_server", "hotel_ticket_mcp_server"])
def modules(request, monkeypatch):
    discovery = importlib.import_module(request.param + ".utils.browser_discovery")
    runtime = importlib.import_module(request.param + ".utils.browser_runtime")
    runtime._stopping.clear()
    monkeypatch.setattr(runtime, "port_open", lambda port: False)
    yield discovery, runtime
    runtime._stopping.clear()
    runtime._sessions.clear()


def detector(module, platform, files=(), env=None, commands=None):
    win = platform == "win32"
    instance = module.BrowserDiscovery(
        "D:\\repo" if win else "/repo", platform=platform,
        home="D:\\Users\\Test" if win else "/users/test", env=env or {},
        isfile=lambda path: path in files, executable=lambda path: path in files,
        which=lambda command: (commands or {}).get(command),
    )
    instance.registered = lambda browser: iter(())
    return instance


@pytest.mark.parametrize("platform,path,command", [
    ("win32", "E:\\Apps\\Edge\\msedge.exe", "msedge.exe"),
    ("darwin", "/custom/edge", "microsoft-edge"),
    ("linux", "/custom/edge", "microsoft-edge-stable"),
])
def test_targeted_which_and_custom_install(modules, platform, path, command):
    d, _ = modules
    instance = detector(d, platform, [path], commands={command: path})
    calls = []
    original = instance.which
    instance.which = lambda name: calls.append(name) or original(name)
    result = instance.resolve("TEST")
    assert result.path == path and result.source == "which"
    assert set(calls) <= set(instance.commands("edge"))


@pytest.mark.parametrize("platform,path", [
    ("win32", "F:\\Programs\\Microsoft\\Edge\\Application\\msedge.exe"),
    ("linux", "/opt/microsoft/msedge/msedge"),
])
def test_common_paths_do_not_assume_system_drive(modules, platform, path):
    d, _ = modules
    instance = detector(d, platform, [path], env={"ProgramFiles": "F:\\Programs"})
    assert instance.resolve("TEST").path == path


def test_mac_registered_bundle_and_common_bundle(modules):
    d, _ = modules
    binary = "/external/Microsoft Edge.app/Contents/MacOS/ActualBinary"
    instance = detector(d, "darwin", [binary])
    instance.bundle_executable = lambda bundle: bundle + "/Contents/MacOS/ActualBinary"
    instance.registered = lambda browser: iter([("/external/Microsoft Edge.app", "bundle")])
    assert instance.resolve("TEST").path == binary
    instance.registered = lambda browser: iter(())
    instance.isfile = lambda path: path == "/Applications/Microsoft Edge.app/Contents/MacOS/ActualBinary"
    instance.executable = instance.isfile
    assert instance.resolve("TEST").source == "common"


def test_explicit_invalid_is_terminal_and_posix_requires_execution(modules):
    d, _ = modules
    instance = detector(d, "linux", ["/browser"], env={"TEST_BROWSER_PATH": "/browser"})
    instance.executable = lambda path: False
    instance.which = lambda command: pytest.fail("Explicit path must not trigger automatic discovery")
    with pytest.raises(d.BrowserError, match="TEST_BROWSER_PATH"):
        instance.resolve("TEST")


def test_preferred_browser_and_no_path_enumeration(modules):
    d, _ = modules
    class NarrowEnv(dict):
        def __iter__(self):
            pytest.fail("Environment must not be enumerated")
        def get(self, name, default=None):
            assert name != "PATH"
            return super().get(name, default)
    instance = detector(d, "linux", ["/chrome"], env=NarrowEnv(TEST_BROWSER="chrome"),
                        commands={"google-chrome": "/chrome"})
    assert instance.resolve("TEST").path == "/chrome"
    instance.isfile = lambda path: False
    assert instance.resolve("TEST").source == "drissionpage"


def test_windows_registry_views_are_queried_without_registry_enumeration(modules, monkeypatch):
    d, _ = modules
    calls = []
    class Key:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def open_key(hive, key, reserved, access):
        calls.append((hive, key, access))
        if hive != 2 or access != 17:
            raise FileNotFoundError()
        return Key()
    monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(
        HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2, KEY_WOW64_64KEY=8,
        KEY_WOW64_32KEY=16, KEY_READ=1, REG_EXPAND_SZ=2,
        OpenKey=open_key, QueryValueEx=lambda *args: ("E:\\Apps\\msedge.exe", 1),
    ))
    instance = detector(d, "win32", ["E:\\Apps\\msedge.exe"])
    instance.registered = d.BrowserDiscovery.registered.__get__(instance)
    assert instance.resolve("TEST").source == "registry"
    assert len(calls) == 4
    assert all(key.endswith("App Paths\\msedge.exe") for _, key, _ in calls)


def test_mac_bundle_metadata_and_registration_timeout(modules, tmp_path, monkeypatch):
    d, _ = modules
    instance = detector(d, "darwin")
    bundle = tmp_path / "Browser.app"
    (bundle / "Contents").mkdir(parents=True)
    (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": "ActualBrowser"}))
    assert instance.bundle_executable(str(bundle)).endswith("Contents/MacOS/ActualBrowser")
    def timeout(args, **kwargs):
        assert args[:3] == ["/usr/bin/osascript", "-l", "JavaScript"]
        assert kwargs["timeout"] == 2
        raise d.subprocess.TimeoutExpired(args, 2)
    monkeypatch.setattr(d.subprocess, "run", timeout)
    instance.registered = d.BrowserDiscovery.registered.__get__(instance)
    assert instance.resolve("TEST").source == "drissionpage"


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_posix_process_ownership_uses_exact_case_sensitive_paths(modules, monkeypatch, platform):
    _, r = modules
    monkeypatch.setattr(r, "canonical", lambda path: posixpath.normpath(str(path)))
    process = FakeProcess(600, ["browser", "--user-data-dir=/Users/Test/profile",
                               "--remote-debugging-port=9223"], created=50)
    processes = r.Processes()
    monkeypatch.setattr(processes, "identity", lambda pid: (process, 50))
    record = {"browser_pid": 600, "browser_created": 50, "started": 49,
              "profile": "/Users/Test/profile", "port": 9223}
    assert processes.owned(record) == [process]
    with pytest.raises(r.BrowserError):
        processes.owned({**record, "profile": "/users/test/profile"})


class Options:
    def __init__(self):
        self.path = None
        self.headless_value = None
        self.new_environment = self.system_profile = self.attach_only = True
    def new_env(self, value): self.new_environment = value
    def use_system_user_path(self, value): self.system_profile = value
    def existing_only(self, value): self.attach_only = value
    def headless(self, value): self.headless_value = value
    def set_local_port(self, port): self.port = port
    def set_user_data_path(self, path): self.profile = path
    def set_argument(self, *args): pass
    def set_browser_path(self, path): self.path = path


class FakeProcess:
    def __init__(self, pid, args=(), created=None):
        self.pid, self.args = pid, list(args)
        self.created = time.time() if created is None else created
        self.alive = True
    def create_time(self): return self.created
    def cmdline(self): return self.args
    def is_running(self): return self.alive
    def children(self, recursive=False): return []


def runtime_setup(modules, tmp_path, monkeypatch, source="common", path="/browser"):
    d, r = modules
    class Processes(r.Processes):
        def __init__(self):
            self.procs = {os.getpid(): FakeProcess(os.getpid())}
            self.stopped = []
            self.block_cleanup = False
        def identity(self, pid):
            proc = self.procs.get(pid)
            return (proc, proc.created) if proc and proc.alive else (None, None)
        def profile_processes(self, profile):
            return [p for p in self.procs.values() if p.alive and
                    r.argument(p.args, "--user-data-dir") and
                    r.canonical(r.argument(p.args, "--user-data-dir")) == r.canonical(profile)]
        def finish(self, processes, deadline):
            if self.block_cleanup:
                return False
            for proc in processes:
                self.stopped.append(proc.pid)
                proc.alive = False
            return True
        def wait(self, processes, deadline):
            return [proc for proc in processes if proc.alive]
    processes = Processes()
    discovery = SimpleNamespace(resolve=lambda prefix: d.BrowserResolution(path, source, "edge"))
    session = r.OwnedBrowser("TEST", tmp_path, tmp_path / "profile", discovery=discovery, processes=processes)
    calls = []
    def launch(options):
        calls.append(options)
        proc = FakeProcess(700 + len(calls), ["browser", "--user-data-dir=" + options.profile,
                                            "--remote-debugging-port=" + str(options.port)])
        processes.procs[proc.pid] = proc
        return SimpleNamespace(browser=SimpleNamespace(process_id=proc.pid),
                               quit=lambda **kwargs: setattr(proc, "alive", False))
    return session, processes, calls, launch


def test_auto_launch_failure_final_fallback_once(modules, tmp_path, monkeypatch):
    session, processes, calls, launch = runtime_setup(modules, tmp_path, monkeypatch)
    def fail_first(options):
        page = launch(options)
        if len(calls) == 1:
            raise RuntimeError("constructor failed after process creation")
        return page
    session.open(fail_first, Options)
    assert [co.path for co in calls] == ["/browser", None]
    assert all(co.headless_value is False for co in calls)
    assert all(not co.new_environment and not co.system_profile and not co.attach_only for co in calls)
    assert 701 in processes.stopped
    session.close()
    assert not session.record_path.exists()
    assert session.profile.exists()  # Hotel data is persistent.


@pytest.mark.parametrize("source,path", [("configured", "/browser"), ("drissionpage", None)])
def test_terminal_attempts_are_not_retried(modules, tmp_path, monkeypatch, source, path):
    d, _ = modules
    session, _, calls, launch = runtime_setup(modules, tmp_path, monkeypatch, source, path)
    def fail(options):
        launch(options)
        raise RuntimeError("startup failed")
    with pytest.raises(d.BrowserError) as err:
        session.open(fail, Options)
    assert err.value.code == "BROWSER_LAUNCH_FAILED" and len(calls) == 1


def test_failed_cleanup_stops_fallback_and_preserves_data(modules, tmp_path, monkeypatch):
    d, _ = modules
    session, processes, calls, launch = runtime_setup(modules, tmp_path, monkeypatch)
    def fail(options):
        launch(options)
        processes.block_cleanup = True
        raise RuntimeError("startup failed")
    with pytest.raises(d.BrowserError) as err:
        session.open(fail, Options)
    assert err.value.code == "BROWSER_CLEANUP_INCOMPLETE"
    assert len(calls) == 1 and session.record_path.exists()


@pytest.mark.parametrize("block_cleanup", [False, True])
def test_missing_browser_pid_preserves_valid_launch_intent(modules, tmp_path, monkeypatch, block_cleanup):
    d, r = modules
    session, processes, calls, launch = runtime_setup(modules, tmp_path, monkeypatch, source="configured")
    identity = processes.identity
    identity_calls = []
    def psutil_identity(pid):
        identity_calls.append(pid)
        return identity(os.getpid() if pid is None else pid)
    processes.identity = psutil_identity
    processes.block_cleanup = block_cleanup
    def missing_pid(options):
        page = launch(options)
        page.browser.process_id = None
        page.quit = lambda **kwargs: None
        return page
    with pytest.raises(d.BrowserError) as error:
        session.open(missing_pid, Options)
    assert None not in identity_calls
    assert len(calls) == 1 and os.getpid() not in processes.stopped
    if block_cleanup:
        assert error.value.code == "BROWSER_CLEANUP_INCOMPLETE"
        record = json.loads(session.record_path.read_text())
        r.validate_record(record, session.profile)
        assert "browser_pid" not in record
    else:
        assert error.value.code == "BROWSER_LAUNCH_FAILED"
        assert 701 in processes.stopped and not session.record_path.exists()


def test_crash_recovery_and_pid_reuse(modules, tmp_path, monkeypatch):
    _, r = modules
    session, processes, calls, launch = runtime_setup(modules, tmp_path, monkeypatch)
    session.open(launch, Options)
    record = dict(session.record)
    session.lock.release()  # Simulate abrupt owner death: no context manager cleanup.
    session._locked = False
    record.update(owner_pid=42, owner_created=1)
    processes.procs[42] = FakeProcess(42, created=2)  # Reused owner PID is not old owner.
    session.record_path.write_text(json.dumps(record))
    fresh = r.OwnedBrowser("TEST", tmp_path, session.profile, discovery=session.discovery, processes=processes)
    fresh.open(launch, Options)
    assert 701 in processes.stopped and 42 not in processes.stopped
    fresh.close()


def test_reused_browser_pid_is_never_killed(modules, tmp_path, monkeypatch):
    _, r = modules
    session, processes, _, launch = runtime_setup(modules, tmp_path, monkeypatch)
    session.open(launch, Options)
    processes.procs[701] = FakeProcess(701, ["personal-browser"], created=time.time() + 30)
    session.close()
    assert 701 not in processes.stopped


def test_profile_lock_excludes_another_instance(modules, tmp_path):
    d, r = modules
    first = r.ProfileLock(tmp_path / "profile.lock")
    second = r.ProfileLock(tmp_path / "profile.lock")
    first.acquire()
    try:
        with pytest.raises(d.BrowserError): second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_posix_file_lock_adapter_is_simulated(modules, tmp_path, monkeypatch, platform):
    _, r = modules
    calls = []
    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(LOCK_EX=1, LOCK_NB=2,
                         flock=lambda fd, flags: calls.append((fd, flags))))
    lock = r.ProfileLock(tmp_path / "simulated.lock", platform=platform)
    lock.acquire()
    lock.release()
    assert len(calls) == 1 and calls[0][1] == 3


def test_shutdown_during_constructor_cleans_late_result(modules, tmp_path, monkeypatch):
    d, r = modules
    session, processes, _, launch = runtime_setup(modules, tmp_path, monkeypatch)
    def late(options):
        page = launch(options)
        session._closing.set()
        return page
    with pytest.raises(d.BrowserError) as err:
        session.open(late, Options)
    assert err.value.code == "BROWSER_SHUTTING_DOWN"
    assert not processes.procs[701].alive
    assert session.close() and session.close()


def test_cleanup_does_not_wait_forever_for_quit(modules, tmp_path, monkeypatch):
    _, r = modules
    session, processes, _, launch = runtime_setup(modules, tmp_path, monkeypatch)
    page = session.open(launch, Options)
    release = threading.Event()
    page.quit = lambda **kwargs: release.wait(10)
    start = time.monotonic()
    try:
        assert session.close(budget=0.05)
        assert time.monotonic() - start < 1
        assert 701 in processes.stopped
    finally:
        release.set()


def test_mirrored_helpers_are_identical():
    root = Path(__file__).resolve().parents[1]
    for name in ("browser_discovery.py", "browser_runtime.py"):
        flight = root / "FlightTicketMCP/flight_ticket_mcp_server/utils" / name
        hotel = root / "HotelTicketMCP/hotel_ticket_mcp_server/utils" / name
        assert flight.read_bytes() == hotel.read_bytes()


def test_shutdown_rejects_start_and_cleans_allocated_temporary_profile(modules, tmp_path, monkeypatch):
    d, r = modules
    session, _, calls, launch = runtime_setup(modules, tmp_path, monkeypatch)
    session.temporary = True
    session.profile.mkdir()
    r._stopping.set()
    with pytest.raises(d.BrowserError) as err:
        session.open(launch, Options)
    assert err.value.code == "BROWSER_SHUTTING_DOWN"
    assert not calls and not session.profile.exists()


def test_real_drissionpage_options_override_destructive_ini_flags(modules, tmp_path):
    from DrissionPage import ChromiumOptions
    _, r = modules
    def inherited_options():
        options = ChromiumOptions(read_file=False)
        options.new_env(True)
        options.use_system_user_path(True)
        options.existing_only(True)
        options.headless(True)
        return options
    options = r.create_options(inherited_options, None, tmp_path, 12345, False)
    assert options._new_env is False  # DP uses this flag to delete the profile.
    assert options.system_user_path is False
    assert options.is_existing_only is False
    assert options.is_headless is False
    assert options.user_data_path == str(tmp_path)


def test_quick_close_acknowledgement_allows_graceful_process_exit(modules, tmp_path, monkeypatch):
    session, processes, _, launch = runtime_setup(modules, tmp_path, monkeypatch)
    page = session.open(launch, Options)
    page.quit = lambda **kwargs: None  # CDP acknowledges before the process exits.
    def exit_during_grace(procs, deadline):
        assert deadline - time.monotonic() > 0.5
        for proc in procs: proc.alive = False
        return []
    processes.wait = exit_during_grace
    assert session.close()
    assert processes.stopped == []


def test_malformed_record_retains_data_but_releases_profile_lock(modules, tmp_path, monkeypatch):
    d, r = modules
    session, processes, _, launch = runtime_setup(modules, tmp_path, monkeypatch)
    session.open(launch, Options)
    record = dict(session.record)
    del record["browser_created"]
    session.record_path.write_text(json.dumps(record))
    session.lock.release()
    session._locked = False
    fresh = r.OwnedBrowser("TEST", tmp_path, session.profile, discovery=session.discovery, processes=processes)
    with pytest.raises(d.BrowserError) as err:
        fresh.open(launch, Options)
    assert err.value.code == "BROWSER_PROFILE_IN_USE"
    assert fresh.record_path.exists() and not processes.stopped
    check = r.ProfileLock(fresh.profile / ".travel-mcp.lock")
    check.acquire()
    check.release()
    assert fresh not in r._sessions


def test_repeated_failed_cleanup_never_deletes_live_temporary_profile(modules, tmp_path, monkeypatch):
    session, processes, _, launch = runtime_setup(modules, tmp_path, monkeypatch)
    session.temporary = True
    page = session.open(launch, Options)
    page.quit = lambda **kwargs: None
    processes.block_cleanup = True
    assert not session.close(raise_on_failure=False)
    assert not session.close(raise_on_failure=False)
    assert session.record_path.exists() and session.profile.exists()
