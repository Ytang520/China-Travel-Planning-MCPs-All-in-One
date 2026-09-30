import json
import pytest

from hotel_ticket_mcp_server.utils import cookie_store

SAMPLE = [
    {"name": "cticket", "value": "AAA", "domain": ".ctrip.com", "httpOnly": True},
    {"name": "login_uid", "value": "BBB", "domain": ".ctrip.com"},
    {"name": "DUID", "value": "CCC"},
]


def test_load_missing_file_returns_empty(tmp_path):
    assert cookie_store.load_cookies(tmp_path / "nope.json") == []


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "c.json"
    cookie_store.save_cookies(SAMPLE, path)
    loaded = cookie_store.load_cookies(path)
    assert [c["name"] for c in loaded] == ["cticket", "login_uid", "DUID"]
    assert loaded[0]["httpOnly"] is True


def test_load_corrupted_file_returns_empty(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert cookie_store.load_cookies(path) == []


@pytest.mark.parametrize("raw", [b"\xff\xfe", json.dumps(SAMPLE).encode("utf-16")],
                         ids=["invalid-utf8", "utf16"])
def test_unreadable_cookie_encoding_returns_empty(tmp_path, raw):
    path = tmp_path / "bad-encoding.json"
    path.write_bytes(raw)
    assert cookie_store.load_cookies(path) == []


def test_to_injectable_maps_fields():
    out = cookie_store.to_injectable(SAMPLE)
    assert out[0] == {
        "name": "cticket",
        "value": "AAA",
        "domain": ".ctrip.com",
        "path": "/",
        "httpOnly": True,
        "secure": False,
    }
    # domain 缺省为 .ctrip.com；httpOnly/secure 缺省为 False
    assert out[2]["domain"] == ".ctrip.com"
    assert out[2]["httpOnly"] is False
    assert out[2]["secure"] is False
    assert out[2]["path"] == "/"


def test_save_writes_utf8(tmp_path):
    path = cookie_store.save_cookies(SAMPLE, tmp_path / "c.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "cookies" in data and "saved_at" in data
