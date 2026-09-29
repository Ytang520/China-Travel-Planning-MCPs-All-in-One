# Ctrip 酒店搜索 MCP 设计文档（HotelTicketMCP + 网关 hotel 域）

日期：2026-09-29 · 状态：已确认（含用户反馈修正）

## 1. 目标与背景

为出行 MCP 统一网关新增**酒店（hotel）域**，通过新下游 MCP 子项目 `HotelTicketMCP/`（Python）抓取携程酒店列表（hotels.ctrip.com），实现与 flight 域一致的能力接入方式。

实测结论（2026-09-28/29，DrissionPage 4.1.1.4 + 系统 Edge，用户 Edge 运行中）：

- 酒店列表页**游客态强制 302 到 passport 登录页**——登录是硬需求（与 flight 不同）。
- DrissionPage 默认（无 `user_data_path`）自动使用 PortFinder 管理的临时 profile，`--user-data-dir` 对 Edge 与 Chrome 同样生效；行为验证：用户 Edge 运行中启动的抓取实例完全未登录。
- `set_user_data_path()` 单独使用会崩（`_auto_port=False` 但 address 为空）；正确用法：`set_local_port(空闲端口)` + `set_user_data_path(path)`。
- `set.cookies()` 直接支持 `httpOnly: True`（cticket/_udl 注入成功，无需 CDP 兜底）；注入后页面恢复会员态。
- 登录 cookie 是 session cookie，**重启后不会随 profile 持久化**——登录态持久化的可靠载体是 cookie 文件（跨浏览器重启注入已实测有效，2026-09-29）。
- 最终采用**方案 A（按次开关浏览器）**：每次搜索/登录用完即关闭浏览器进程；登录态由 cookie 文件注入承载（两层流程），无长驻浏览器。
- 同一 profile 二次启动（首个实例存活）→ `BrowserConnectError`（Edge 将新启动转交旧进程）。必须单飞锁 + 按 profile 路径精确清理自身残留进程（PowerShell 过滤 CommandLine，已验证）。

## 2. 架构

```
HotelTicketMCP/
├─ hotel_ticket_mcp_server/
│  ├─ main.py                    # transport/日志/.env 加载（镜像 flight）
│  ├─ tools/hotel_search_tools.py
│  ├─ tools/hotel_login_tools.py
│  └─ utils/{rate_limiter,cookie_store,cities_dict,browser_factory,login_state}.py
├─ tests/                        # 纯逻辑单测（无浏览器）
├─ requirements.txt / pyproject.toml / .env.example / README.md
├─ .browser-profile/             # 专用持久 profile（gitignored）
└─ ctrip-hotel-cookies.json      # 登录 cookie（gitignored）
```

网关：`src/domains/hotel/ctrip/provider.ts`（stdio 子进程 `python -m hotel_ticket_mcp_server`，cwd=HotelTicketMCP，requestTimeout 600s）+ `registry.ts`；`src/types.ts` DomainName 加 `hotel`；`src/index.ts` / `src/config.ts` / `utils/downstreamClient.ts` 相应接线。工具名：`hotel_ctrip_searchHotels`、`hotel_ctrip_login`。

## 3. 工具与参数

- `searchHotels`：city/checkin/checkout 必填；location、adults/children/rooms、price_min/price_max、star_min/star_max、min_score、room_type、accommodation_type、breakfast、sort（smart/price_asc/distance/score_desc，默认 smart）、limit（默认 20，最大 50）。
- `ctripHotelLogin`：无参数；打开可见窗口等用户手动登录（≤5 分钟轮询），成功后用 CDP `Network.getAllCookies` 提取（保留 httpOnly 标志）写入 cookie 文件。
- 返回：status + hotels[] + warnings + data_source + query_time + formatted_output。

## 4. 登录态流程（方案 A：按次开关浏览器）

浏览器在每次搜索/登录完成后立即关闭（无长驻进程）；登录态完全由 cookie 文件承载：

1. **注入 `ctrip-hotel-cookies.json`**（`set.cookies` 含 httpOnly）→ 重新导航到目标页 → 检测；
2. **仍失败** → 返回 `LOGIN_REQUIRED` → Agent stop 通知用户 → 用户调用 `hotel_ctrip_login`（可见窗口手动登录，保存 cookie 后浏览器关闭）→ 会话继续，下次搜索注入新文件。

**登录态检测（用户反馈修正）**：以"非登录态标记"为主——

- URL 含 `passport` → 未登录；
- 页面顶部同时出现「登录」与「注册」→ 未登录；
- **不匹配任何未登录标记 → 视为已登录**（不依赖"黄金贵宾"等具体身份文本）；
- 无任何标记且 `.hotel-list` 缺失 → 判定为被拦截/结构变化（SCRAPING_FAILED），不做登录处理。

## 5. 防封设计

- **搜索间隔**：进程内 `random.uniform(30, 300)` 秒（首次不等待；`HOTEL_MCP_MIN_DELAY`/`HOTEL_MCP_MAX_DELAY` 可调）；仅酒店，flight 不动。
- **人性化滚动**：步幅 = 视口 × uniform(0.55, 0.9) ± 10% jitter，下限 0.45 视口（防止步幅过小→数据不更新→误判到底）；轮间 uniform(0.8, 2.2)s；每 3~5 轮 30% 概率回滚 0.2~0.4 视口；判底 = bottom_gap ≤ 15% 视口且连续 3 轮 scrollHeight 与卡片数双指标零增长；到底但不足 limit → 返回已有 + warning。
- 随机鼠标移动（30% 概率）、首屏随机停驻 uniform(1.5, 4)s、最小化窗口 + 防节流三件套（`--start-minimized`、`--disable-backgrounding-occluded-windows`、`--disable-renderer-backgrounding`、`--disable-background-timer-throttling`，同 flight）。
- **按次开关浏览器 + 单飞锁**：每次搜索/登录用完即关（`browser_session` 上下文管理器，finally 必关）；同进程一次只一个浏览器操作；启动前按 profile 路径过滤 CommandLine 精确清理自身残留 msedge 进程（不碰用户浏览器）。
- **flight 永远不登录（加固）**：`FlightRouteSearcher` 改用 `set_local_port(空闲端口)` + `set_user_data_path(mkdtemp())` 显式全新临时 profile，并在初始化时 `Network.clearBrowserCookies` 兜底。

## 6. 风险同意机制

- 安装指南新增交互问题：明确"模拟真人浏览 + 登录态抓取存在账号封禁风险；选择启用即自愿承担风险，作者概不负责"→ 写 `HOTEL_CTRIP_CONSENT=yes/no` 入 .env。
- 服务器 gate：consent ≠ yes 时酒店工具返回 `CONSENT_REQUIRED`（含说明文案）；工具 description 内嵌风险提示。

## 7. 参数→URL 映射

city → cityId 内置字典（~50 主要城市）+ 地标坐标表（武汉站-东出口=13306087 等）；价格 `15~Range*15~min~max`、星级 `17~n`、房型 `29~` 等编码（实施时按真实页面逐项验证并记录）；排序编码实测抓取；字典未覆盖 → UI 表单回退（失败报 `CITY_NOT_FOUND`）。

## 8. 错误处理

`LOGIN_REQUIRED` / `CONSENT_REQUIRED` / `RATE_LIMIT_WAIT` / `SCRAPING_FAILED` / `EMPTY_RESULTS` / `INVALID_PARAMS` / `CITY_NOT_FOUND`，统一含 data_source / query_time。

## 9. 测试、文档与关联文件

- `scripts/mcp-test.mjs` 加 `hotel` 模式；`gateway_health_check` hotel = connectivity-only。
- `.gitignore` 新增：`HotelTicketMCP/.venv/`、`HotelTicketMCP/.browser-profile/`、`HotelTicketMCP/ctrip-hotel-cookies.json`、`ctrip-cookies.json`、`edge_hotels.json`。
- `.env.example`（根 + HotelTicketMCP）、README（中/英）、extending（中/英）、agent-install（中/英）、CHANGELOG。

## 10. 验证清单（验收标准）

1. `npm run build` 通过；`python -m hotel_ticket_mcp_server` 可启动并注册两个工具。
2. 纯逻辑单测（rate_limiter/cookie_store/cities_dict/login 判定/URL 构造/解析）通过。
3. 端到端：网关 `hotel_ctrip_searchHotels` 真实返回武汉酒店列表（含登录注入链路）。
4. consent=no 时返回 CONSENT_REQUIRED。
5. 子代理代码复查通过（最多 3 轮修复）。

## 11. 硬约束

- 不 push 到 GitHub（仅本地提交）。
- 不修改系统环境变量；不改动本仓库之外的任何文件。
- 需要改动系统环境时停止并通知用户。
