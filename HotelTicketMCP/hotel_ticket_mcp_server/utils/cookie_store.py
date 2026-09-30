"""登录 cookie 的持久化读写与注入映射。

cookie 保存在 gitignored 的文件中（默认 HotelTicketMCP/ctrip-hotel-cookies.json），
由登录工具写入、搜索工具读取注入，实现"登录一次、后续复用"。
"""

import json
import os
import tempfile
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

DEFAULT_FILENAME = "ctrip-hotel-cookies.json"


def default_cookie_path():
    env_path = os.environ.get("HOTEL_MCP_COOKIE_FILE")
    if env_path:
        return Path(env_path)
    # <package>/utils/cookie_store.py -> <HotelTicketMCP>/ctrip-hotel-cookies.json
    return Path(__file__).resolve().parent.parent.parent / DEFAULT_FILENAME


def load_cookies(path=None):
    """读取 cookie 文件，返回 cookie dict 列表；文件缺失/损坏时返回 []。"""
    p = Path(path) if path else default_cookie_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    cookies = data.get("cookies", data) if isinstance(data, dict) else data
    if not isinstance(cookies, list):
        return []
    return [c for c in cookies if isinstance(c, dict) and c.get("name")]


def save_cookies(cookies, path=None, *, commit_lock=None, cancelled=None):
    """把 cookie dict 列表写入文件（UTF-8，含保存时间），返回文件路径。"""
    p = Path(path) if path else default_cookie_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cookies": cookies,
        "saved_at": datetime.now().isoformat(),
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=p.parent,
                                         prefix=f".{p.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        with commit_lock if commit_lock is not None else nullcontext():
            if cancelled is not None and cancelled.is_set():
                return None
            os.replace(temporary, p)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return p


def to_injectable(cookies):
    """cookie dict 列表 → DrissionPage set.cookies 可接受的格式（含 httpOnly/secure）。"""
    out = []
    for c in cookies:
        out.append(
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain") or ".ctrip.com",
                "path": c.get("path") or "/",
                "httpOnly": bool(c.get("httpOnly")),
                "secure": bool(c.get("secure")),
            }
        )
    return out
