"""登录 cookie 的持久化读写与注入映射。

cookie 保存在 gitignored 的文件中（默认 HotelTicketMCP/ctrip-hotel-cookies.json），
由登录工具写入、搜索工具读取注入，实现"登录一次、后续复用"。
"""

import json
import os
import tempfile
import time
import math
from urllib.parse import urlsplit
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


def to_injectable(cookies, *, now=None):
    """Map stored CDP cookies without losing scope, SameSite or session semantics."""
    now = time.time() if now is None else now
    out = []
    for c in cookies:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str) or not c["name"] or not isinstance(c.get("value"), str):
            continue
        domain = c.get("domain") or ".ctrip.com"
        if not isinstance(domain, str) or not (domain.lstrip(".") == "ctrip.com" or domain.endswith(".ctrip.com")):
            continue
        cookie = {"name": c["name"], "value": c["value"], "domain": domain,
                  "path": c.get("path") or "/", "httpOnly": bool(c.get("httpOnly")),
                  "secure": bool(c.get("secure"))}
        if not isinstance(cookie["path"], str) or not cookie["path"].startswith("/"):
            continue
        expires = c.get("expires", c.get("expirationDate"))
        if c.get("session") is not True and expires not in (None, -1):
            if isinstance(expires, bool) or not isinstance(expires, (int, float)) or not math.isfinite(expires) or expires <= now:
                continue
            cookie["expires"] = expires
        same_site = c.get("sameSite")
        if same_site is not None:
            normalized = {"strict": "Strict", "lax": "Lax", "none": "None", "no_restriction": "None", "unspecified": None}.get(str(same_site).lower())
            if normalized is None and str(same_site).lower() != "unspecified":
                continue
            if normalized:
                cookie["sameSite"] = normalized
        if c.get("partitionKeyOpaque"):
            # An opaque partition cannot be reconstructed in another browser.
            continue
        if "partitionKey" in c:
            partition = c["partitionKey"]
            if not isinstance(partition, dict):
                continue
            site = partition.get("topLevelSite", "")
            try:
                valid_site = urlsplit(site).scheme in ("https", "http") and bool(urlsplit(site).hostname)
            except ValueError:
                valid_site = False
            if not valid_site or not isinstance(partition.get("hasCrossSiteAncestor"), bool):
                continue
            cookie["partitionKey"] = {"topLevelSite": site, "hasCrossSiteAncestor": partition["hasCrossSiteAncestor"]}
        for key, values in (("priority", ("Low", "Medium", "High")), ("sourceScheme", ("Unset", "NonSecure", "Secure"))):
            if c.get(key) in values:
                cookie[key] = c[key]
        if isinstance(c.get("sourcePort"), int) and -1 <= c["sourcePort"] <= 65535:
            cookie["sourcePort"] = c["sourcePort"]
        out.append(cookie)
    return out
