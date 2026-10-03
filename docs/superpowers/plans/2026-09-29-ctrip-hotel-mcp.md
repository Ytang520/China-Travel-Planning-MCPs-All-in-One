# Ctrip 酒店搜索 MCP 实施计划（HotelTicketMCP + hotel 域）

> **后续修订（2026-09-29，方案 A）**：本文为实施时的历史记录。登录态流程最终按**两层**实现（注入 cookie 文件 → 失败则 LOGIN_REQUIRED 重登），浏览器**按次开关**（每次搜索/登录用完即关，`browser_session()` 上下文管理器），不再使用"三层流程 / 长驻浏览器单例"方案——详见 spec §4 的修订。文中其余内容仍与实现一致。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> 本会话执行方式：主代理内联实施 + 完成后派发子代理复查（用户指定，最多 3 轮修复）。

**Goal:** 为 travel-mcp-gateway 新增 hotel 域，通过新 Python 子项目 HotelTicketMCP（DrissionPage + Edge）抓取携程酒店列表，含登录态三层流程、防封限速与人性化滚动、风险同意 gate。

**Architecture:** 镜像 flight 模式：`HotelTicketMCP/` Python 包（FastMCP，stdio）+ 网关 `src/domains/hotel/` provider。纯逻辑模块（限速/cookie/城市字典/登录判定/URL 构造/卡片解析）走 TDD 单测；浏览器相关逻辑以真实环境 smoke 验证。

**Tech Stack:** Python ≥3.11（uv 项目级 .venv，阿里云 PyPI 镜像）、FastMCP、DrissionPage 4.1.x、TypeScript（网关）、PowerShell（残留进程清理）。

**Spec:** `docs/superpowers/specs/2026-09-29-ctrip-hotel-mcp-design.md`

---

## 文件结构

```
HotelTicketMCP/
├─ pyproject.toml, requirements.txt, .env.example, README.md
├─ hotel_ticket_mcp_server/
│  ├─ __init__.py, __main__.py, main.py          # transport/logging/env（镜像 flight）
│  ├─ tools/hotel_search_tools.py                # searchHotels 全流程
│  ├─ tools/hotel_login_tools.py                 # ctripHotelLogin
│  └─ utils/
│     ├─ rate_limiter.py      # 15~180s 随机间隔（纯逻辑）
│     ├─ cookie_store.py      # cookie 文件读写/注入映射（纯逻辑）
│     ├─ cities_dict.py       # 城市/地标字典（纯逻辑）
│     ├─ url_builder.py       # 参数→URL（纯逻辑）
│     ├─ login_state.py       # 反转型登录判定（纯逻辑）
│     └─ browser_factory.py   # 浏览器单例/端口/残留清理（浏览器逻辑）
├─ tests/ (test_rate_limiter / test_cookie_store / test_cities_dict / test_url_builder / test_login_state / test_card_parser)
├─ .browser-profile/          # 运行时生成（gitignored）
└─ ctrip-hotel-cookies.json   # 运行时生成（gitignored）

src/domains/hotel/ctrip/provider.ts, src/domains/hotel/registry.ts   # 新增
src/{types.ts, config.ts, index.ts}, src/utils/downstreamClient.ts   # 修改
FlightTicketMCP/flight_ticket_mcp_server/tools/flight_search_tools.py # 加固（2 处小改）
scripts/mcp-test.mjs, .env.example, .gitignore, README{,.en}.md, docs/{extending,agent-install}{,.en,..zh}.md, CHANGELOG.md
```

---

## Task 1: HotelTicketMCP 脚手架

**Files:** Create: `HotelTicketMCP/pyproject.toml`, `requirements.txt`, `.env.example`, `hotel_ticket_mcp_server/__init__.py`, `__main__.py`, `main.py`

- [ ] **Step 1: 写 pyproject.toml**（name=hotel-ticket-mcp-server, requires-python>=3.11, deps: fastmcp>=2.8.0, DrissionPage>=4.0.0, pydantic>=2.0.0, requests>=2.31.0）
- [ ] **Step 2: 写 requirements.txt**（同上 4 个依赖）
- [ ] **Step 3: 写 .env.example**：MCP_TRANSPORT/日志变量 + HOTEL_MCP_BROWSER=edge、HOTEL_MCP_BROWSER_PATH（注释）、HOTEL_MCP_HEADLESS（注释，默认不启用）、HOTEL_MCP_MIN_DELAY=15、HOTEL_MCP_MAX_DELAY=180、HOTEL_MCP_CONSENT=no（注释说明风险）
- [ ] **Step 4: 写 main.py**（镜像 FlightTicketMCP/main.py：load_env_file→get_transport_config→setup_logging（logs/ 在 HotelTicketMCP/logs/）→register_tools→mcp.run()；工具注册 searchHotels 与 ctripHotelLogin，consent gate 在工具内实现）
- [ ] **Step 5: 写 __init__.py / __main__.py**（`from .main import main; main()`）
- [ ] **Step 6: 建 venv 并装依赖**
  ```bash
  cd HotelTicketMCP && uv venv && uv pip install --index-url https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt pytest
  ```
- [ ] **Step 7: 验证包可导入并 commit**
  ```bash
  .venv/Scripts/python.exe -c "import hotel_ticket_mcp_server" && cd .. && git add HotelTicketMCP && git commit -m "feat(hotel): scaffold HotelTicketMCP package"
  ```

## Task 2: rate_limiter（TDD）

**Files:** Create: `HotelTicketMCP/hotel_ticket_mcp_server/utils/rate_limiter.py`, `HotelTicketMCP/tests/test_rate_limiter.py`

```python
# rate_limiter.py
"""搜索间隔限速：两次搜索之间等待随机 15~180 秒（首次不等待）。"""
import os
import random
import time

DEFAULT_MIN_DELAY = 15.0
DEFAULT_MAX_DELAY = 180.0


class SearchRateLimiter:
    def __init__(self, min_delay=None, max_delay=None, clock=time.monotonic, sleep=time.sleep, rng=None):
        self.min_delay = float(min_delay if min_delay is not None else os.environ.get("HOTEL_MCP_MIN_DELAY", DEFAULT_MIN_DELAY))
        self.max_delay = float(max_delay if max_delay is not None else os.environ.get("HOTEL_MCP_MAX_DELAY", DEFAULT_MAX_DELAY))
        if self.min_delay < 0 or self.max_delay < self.min_delay:
            raise ValueError("invalid delay range")
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._lock = __import__("threading").Lock()
        self._last_search_at = None

    def wait_if_needed(self):
        """返回 dict: {"waited_seconds": float, "reason": "first_search"|"rate_limit", "delay_seconds": float}"""
        with self._lock:
            now = self._clock()
            if self._last_search_at is None:
                self._last_search_at = now
                return {"waited_seconds": 0.0, "reason": "first_search", "delay_seconds": 0.0}
            delay = self._rng.uniform(self.min_delay, self.max_delay)
            elapsed = now - self._last_search_at
            remaining = max(0.0, delay - elapsed)
            if remaining > 0:
                self._sleep(remaining)
            self._last_search_at = self._clock()
            return {"waited_seconds": remaining, "reason": "rate_limit", "delay_seconds": delay}
```

测试（FakeClock/FakeSleep 注入）：首次不等待；第二次按 rng=Random(0) 的 delay 等待剩余；min>max 抛错。运行 `HotelTicketMCP/.venv/Scripts/python.exe -m pytest tests/test_rate_limiter.py -v` 后 commit。

## Task 3: cookie_store（TDD）

**Files:** Create: `utils/cookie_store.py`, `tests/test_cookie_store.py`

```python
# cookie_store.py
"""登录 cookie 的持久化读写与注入映射（cookie 保存在 gitignored 的文件中）。"""
import json
import os
from pathlib import Path

DEFAULT_FILENAME = "ctrip-hotel-cookies.json"


def default_cookie_path():
    env_path = os.environ.get("HOTEL_MCP_COOKIE_FILE")
    if env_path:
        return Path(env_path)
    return Path(__file__).resolve().parent.parent.parent / DEFAULT_FILENAME


def load_cookies(path=None):
    p = Path(path) if path else default_cookie_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    cookies = data.get("cookies", data) if isinstance(data, dict) else data
    return [c for c in cookies if isinstance(c, dict) and c.get("name")]


def save_cookies(cookies, path=None):
    p = Path(path) if path else default_cookie_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"cookies": cookies, "saved_at": __import__("datetime").datetime.now().isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def to_injectable(cookies):
    """cookie dict → DrissionPage set.cookies 格式（含 httpOnly，domain 缺省 .ctrip.com）。"""
    out = []
    for c in cookies:
        out.append({
            "name": c["name"], "value": c["value"],
            "domain": c.get("domain") or ".ctrip.com",
            "path": c.get("path") or "/",
            "httpOnly": bool(c.get("httpOnly")),
        })
    return out
```

测试：空/缺失文件→[]；roundtrip；to_injectable 的 domain 缺省与 httpOnly 保真。commit。

## Task 4: cities_dict + url_builder（TDD）

**Files:** Create: `utils/cities_dict.py`, `utils/url_builder.py`, `tests/test_cities_dict.py`, `tests/test_url_builder.py`

cities_dict：`CITY_IDS`（~50 城市 cityId/provinceId/countryId，含武汉 477/20/1、北京 1/1/1、上海 2/2/1 等）+ `LANDMARKS`（含 `"武汉站-东出口": ("10", "13306087", "30.6076444|114.4256694")`）+ `get_city_ids(city)` / `get_landmark(word)`。

url_builder：`build_list_url(city, checkin, checkout, landmark=None, rooms=1, adults=2, children=0, price=None, star=None, sort=None)` → 完整 URL。city-only 时 searchWord=city、不带 searchType/searchValue；有地标时带 searchType=T 与 searchValue（格式 `10|{id}*10*{lat|lng}|{name}|{id}`）。价格→`15~Range*15~{min}~{max}`；星级→`17~{n}*17*{n}`；sort 映射 `{"smart": None, "price_asc": "S", "distance": "D", "score_desc": "R"}` 之外枚举报错。返回 dict（url 与 warnings）便于测试。commit。

## Task 5: login_state（TDD，反转型判定）

**Files:** Create: `utils/login_state.py`, `tests/test_login_state.py`

```python
# login_state.py
"""登录态判定：以「非登录态标记」为准——命中任何未登录标记即未登录；不命中则视为已登录。"""
def detect_login_state(url, header_text):
    url = url or ""
    if "passport" in url:
        return "guest"
    text = header_text or ""
    if "登录" in text and "注册" in text:
        return "guest"
    return "logged_in"
```

测试：passport URL→guest；header 含 登录+注册→guest；两者皆无（会员身份任意，含/不含"黄金贵宾"）→logged_in。commit。

## Task 6: browser_factory（浏览器单例）

**Files:** Create: `utils/browser_factory.py`

内容（镜像 flight 的路径解析 + 本设计修正）：
- `EDGE_CANDIDATES`/`CHROME_CANDIDATES` + `resolve_browser_path()`（`HOTEL_MCP_BROWSER_PATH` > `HOTEL_MCP_BROWSER` edge 默认 > 兜底探测另一内核）；
- `free_port()`（socket bind 0）；
- `cleanup_stale_profile_processes(profile_dir)`：仅 Windows——PowerShell `Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where CommandLine -like '*{profile_dir}*' | Stop-Process -Force`；其它平台返回 0；
- `create_options(browser_path, profile_dir, headless)`：`set_local_port(free_port())` + `set_user_data_path(profile_dir)` + 最小化/防节流四件套（同 flight）+ `auto_port()` 一律不用；
- `BrowserSingleton`：`get()` 惰性创建并缓存 `ChromiumPage`；创建前 `cleanup_stale_profile_processes`；`quit()` 关闭并重置。

commit（浏览器逻辑由 Task 13 smoke 验证）。

## Task 7: hotel_search_tools（核心）

**Files:** Create: `tools/hotel_search_tools.py`, `tests/test_card_parser.py`

- 模块级 `_SINGLETON = BrowserSingleton(...)`、`_SEARCH_LOCK = threading.Lock()`、`_RATE_LIMITER = SearchRateLimiter()`；
- `parse_cards(raw_cards)`：纯函数。输入为 JS 快照 dict 列表（与已捕获的真实快照同构：`{name, stars, score, reviews, distance, room, price}` 或原始文本行），清洗 stars/score/reviews/distance/room/price（复用已验证的提取规则：最后 ¥ 为起价、`N条点评`、`距...`去掉"查看地图"、room 含房/床且非"热卖"）；
- `snapshot_js`：与验证版一致的 `div.hotel-list` 子元素快照 JS；
- `_scroll_and_collect(page, limit)`：人性化滚动——步幅 `viewport*uniform(0.55,0.9)*(1±0.1 jitter)` 且 ≥0.45 视口；轮间 `uniform(0.8,2.2)s`；每 3~5 轮 30% 回滚 `0.2~0.4` 视口；随机鼠标 `move_to`（30%）；判底 = `bottom_gap ≤ 0.15*viewport` 且连续 3 轮 scrollHeight 与卡片数双零增长；到底不足 limit 返回已有 + warning；
- `searchHotels(city, checkin, checkout, ...)` 流程：consent gate（`HOTEL_MCP_CONSENT != "yes"` → `CONSENT_REQUIRED`）→ 参数校验（日期格式/非过去/checkout>checkin/limit≤50）→ 限速等待 → `_SEARCH_LOCK` → 确保浏览器 → 构造 URL（未知城市 `resolve_city_via_ui`：首页表单输入城市名搜索→从重定向 URL 提取 cityId 缓存→失败报 `CITY_NOT_FOUND`）→ 打开 → `detect_login_state`（header 文本取 body 前 600 字）→ guest 则注入 cookie_store 再检 → 仍 guest 报 `LOGIN_REQUIRED`（含操作指引）→ 首屏随机停驻 → 滚动采集 → 解析 → 返回 `{status, hotels, count, warnings, data_source, query_time, formatted_output}`；
- 错误码统一：`CONSENT_REQUIRED`/`LOGIN_REQUIRED`/`RATE_LIMIT_WAIT`/`SCRAPING_FAILED`/`EMPTY_RESULTS`/`INVALID_PARAMS`/`CITY_NOT_FOUND`。

测试：`test_card_parser.py` 用真实捕获的 20 家快照样本断言解析正确。commit。

## Task 8: hotel_login_tools

**Files:** Create: `tools/hotel_login_tools.py`

`ctripHotelLogin()`：consent gate → `_SEARCH_LOCK` → 确保浏览器 → `page.set.window.max()` 恢复可见 → 打开 `https://hotels.ctrip.com/` → 若 `detect_login_state` 已是 logged_in 直接提取；否则循环（每 3s 检测，最长 300s，期间用户手动登录）→ 成功后 `page.run_cdp("Network.getAllCookies")` 过滤 `.ctrip.com`，转成 `{name,value,domain,path,httpOnly}` → `cookie_store.save_cookies` → 窗口最小化还原 → 返回成功 JSON（含保存路径）；超时返回 `LOGIN_TIMEOUT` 错误。commit。

## Task 9: flight 加固（2 处小改）

**Files:** Modify: `FlightTicketMCP/flight_ticket_mcp_server/tools/flight_search_tools.py`

- `__init__`：`co.auto_port()` 替换为 `co.set_local_port(_free_port())` + `co.set_user_data_path(tempfile.mkdtemp(prefix="flightctrip-profile-"))`（顶部 import socket/tempfile；新增 `_free_port()` 助手）；创建页面后 `self.page.run_cdp("Network.clearBrowserCookies")`（try/except + warning 日志）；
- `close()`：追加 `shutil.rmtree(self._profile_dir, ignore_errors=True)`。

验证：`python -m py_compile` 通过 + `git diff` 审阅。commit（备注：flight 行为不变，仅 profile 更显式）。

## Task 10: 网关接线

**Files:** Modify: `src/types.ts`, `src/config.ts`, `src/utils/downstreamClient.ts`, `src/index.ts`; Create: `src/domains/hotel/registry.ts`, `src/domains/hotel/ctrip/provider.ts`

- types.ts：`DomainName = "train" | "flight" | "hotel" | "map" | "taxi"`；
- config.ts：`hotelProjectRoot`（`HOTEL_MCP_PROJECT_ROOT` ?? `resolve(workspaceRoot, "HotelTicketMCP")`）、`hotelPythonCommand`（`HOTEL_MCP_PYTHON_COMMAND` ?? "python"）；
- provider.ts：`{domain:"hotel", providerName:"ctrip", displayName:"Ctrip Hotel MCP Server", description:"Ctrip hotel search (web scraping; login required; ban-risk — consented via HOTEL_MCP_CONSENT=yes)", enabled:true, retainInReadme:true, requestTimeout:600_000, transport:{kind:"stdio", command:config.hotelPythonCommand, args:["-m","hotel_ticket_mcp_server"], cwd:config.hotelProjectRoot, env:{...config.inheritedEnv, MCP_TRANSPORT:"stdio", PYTHONUTF8:"1"}}}`；
- index.ts：getProviders 加 `...getHotelProviders(config)`；createEmptyInventory 加 `hotel: []`；`HEALTH_PROBES` 类型改为 `Exclude<DomainName, "flight" | "hotel">` 并新增 hotel 分支（与 flight 相同 connectivity-only）；description 提及 hotel；gateway_get_config 的 browser 段加 hotel 引擎/无头读取与 dataSourceNotes 加 hotel 行；
- downstreamClient.ts：`createInventorySchema` 的 `z.enum` 加 `"hotel"`。

验证：`npm run build` 零错误 + `node scripts/mcp-test.mjs config`（需 .env，见 Task 12）。commit。

## Task 11: mcp-test.mjs + .env/.gitignore

**Files:** Modify: `scripts/mcp-test.mjs`, `.env.example`, `.gitignore`

- mcp-test.mjs：`MODES` 加 `"hotel"`；新增 hotel 分支调用 `hotel_ctrip_searchHotels`（city=武汉、checkin/checkout=今天+7/+9、limit=5、timeout 540000）；加 `addDays(dateStr, n)` 助手；
- `.env.example`：追加 `HOTEL_MCP_PROJECT_ROOT=./HotelTicketMCP`、`HOTEL_MCP_PYTHON_COMMAND=python`、`HOTEL_MCP_BROWSER=edge`、`HOTEL_MCP_BROWSER_PATH`（注释）、`HOTEL_MCP_HEADLESS`（注释）、`# HOTEL_MCP_CONSENT=yes（启用酒店搜索前必须同意封禁风险条款）`；
- `.gitignore`：追加 `HotelTicketMCP/.venv/`、`HotelTicketMCP/.browser-profile/`、`HotelTicketMCP/ctrip-hotel-cookies.json`、`HotelTicketMCP/logs/`、`ctrip-cookies.json`、`edge_hotels.json`；
- 本地 `.env`（gitignored，仅本机）：追加 hotel 变量（`HOTEL_MCP_PYTHON_COMMAND` 指向 HotelTicketMCP/.venv 绝对路径、`HOTEL_MCP_CONSENT=yes`）。

commit（不含 .env——它本就被忽略）。

## Task 12: 端到端 smoke

- 从根 `ctrip-cookies.json` 的 `cookies` 数组转换生成 `HotelTicketMCP/ctrip-hotel-cookies.json`（产品化位置的种子数据）；
- `npm run build` → `node scripts/mcp-test.mjs hotel`（预期：返回武汉酒店列表 ≥5 家，含会员价）；
- `node scripts/mcp-test.mjs health`（预期 hotel=connectivity-only PASS）；
- 临时验证 consent 拒绝：以 `HOTEL_MCP_CONSENT=no` 启动网关调用 hotel 工具 → `CONSENT_REQUIRED`。

## Task 13: 文档 + CHANGELOG

**Files:** Modify: `README.md`, `README.en.md`, `docs/extending.zh.md`, `docs/extending.md`, `docs/agent-install.zh.md`, `docs/agent-install.md`, `CHANGELOG.md`

- README：功能概要加 hotel；环境变量表加 `HOTEL_MCP_*`（含 consent 风险说明）；浏览器依赖注明酒店需登录+同意条款；快速开始加 HotelTicketMCP 依赖安装；工具命名/更新记录同步；
- extending：仓库布局/保留工具/一级目录加 hotel；"如何新增子 MCP"的域列表同步；
- agent-install：§3.6 安装 HotelTicketMCP 依赖；§4.1 新增 **D. 酒店搜索风险同意**（明确封禁风险文案与自愿承担声明）与浏览器内核选择扩展为航班+酒店共用；§4.2 .env 追加；§7 排障加酒店项；§8.7 hotel 测试；启动日志预期加 hotel 行；
- CHANGELOG Unreleased：Added/Changed/Security 段落。

commit。

## Task 14: 最终验证 + 子代理复查循环（最多 3 轮）

1. 全量自检：`npm run build`、pytest 全绿、py_compile（HotelTicketMCP + 修改后的 flight 文件）、`node scripts/mcp-test.mjs hotel` smoke、`git status` 确认无越界文件；
2. 派发 powerful 子代理（code-reviewer，opus）复查本次全部改动（以 `git diff main` 为范围），输出问题清单；
3. 主代理按清单修复 → 重新自检 → 再次派发复查；**最多 3 轮**；
4. 写 `log.txt`（对比设计 + 实施步骤 + 复查结论）；本地 commit（**不 push**）。

## 硬约束

- 不 push 到 GitHub；不修改系统环境变量；不触碰本仓库之外的文件；需改系统环境时停下通知用户。
- Python 一律用项目内 .venv（uv + 阿里云镜像）；浏览器仅最小化可见模式启动。
