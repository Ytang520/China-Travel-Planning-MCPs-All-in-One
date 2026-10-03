# HotelTicketMCP

基于模型上下文协议（MCP）的携程酒店搜索服务器（[出行 MCP 统一网关](../README.md) 的 `hotel` 域下游）。

## ⚠ 风险提示（重要）

本服务器通过浏览器模拟真人浏览并抓取**需要登录态**的携程酒店数据，**存在账号被封禁的风险**：

- 必须显式同意风险条款（`HOTEL_MCP_CONSENT=yes`）才会启用工具；**选择启用即表示自愿承担该风险，作者概不负责**；
- 为降低风险，两次搜索之间自动等待随机 15 秒 ~ 3 分钟（`HOTEL_MCP_MIN_DELAY`/`HOTEL_MCP_MAX_DELAY` 可调），滚动采集采用随机步幅与停顿的人性化行为。

## 功能

- `searchHotels`（网关注册名 `hotel_ctrip_searchHotels`）：携程酒店搜索——城市/地标、入住退房日期、人数、价格/星级/评分/房型/住宿类型筛选与排序（smart/price_asc/distance/score_desc）。
- `login`（网关注册名 `hotel_ctrip_login`）：携程登录助手——打开可见浏览器窗口，等待用户手动登录后把 cookie 保存到 gitignored 文件供后续搜索复用。

参数与结果约定通过网关的 `get_tool_details({"tool_name":"hotel_ctrip_searchHotels"})` 查询，详见[工具参考](../docs/tool-reference.md)。`city` 填城市（武汉），`location` 填城市内地点（梨园地铁站），URL 中 `cityName`、`destName` 都是城市，`searchWord` 是地点。

查询按“城市内已验证缓存 → 关键词页面验证 → 一次候选解析”执行。缓存有效期 24 小时、最多 256 条，每次复用仍验证页面；地铁线路和出入口不合并，同名的其他城市不共享 ID。多候选返回 `LOCATION_AMBIGUOUS` 及候选详情；无法确认地点或排序时返回明确错误。`location_resolution.applied` 和 `sorting.applied` 表示实际应用状态，输入回显和 `sort=D` 不能证明成功。

| 参数 | 支持选项 |
| --- | --- |
| `room_type` | 大床房、双床房、单人床房、三床房、特大床房 |
| `accommodation_type` | 酒店、民宿、青年旅馆、酒店公寓、公寓 |

两项均为可选单值，省略或传 `null` 表示不限；其他值会被拒绝。筛选编码和页面选中标签均通过核验后才确认生效。早餐筛选暂不支持，传值会返回未应用警告。距离排序必须指定 `location`，并确认页面显示目标地点的直线距离及由近到远顺序。

## 登录态流程（按次开关浏览器）

浏览器在每次搜索/登录完成后立即关闭（无长驻进程），登录态完全由 cookie 文件承载：

1. 搜索时注入 `ctrip-hotel-cookies.json`（含 HttpOnly cookie）→ 重新导航 → 检测登录态；
2. 缺少或失效的 cookie → 返回 `LOGIN_REQUIRED`，调用登录工具发起客户端原生提问；不支持 elicitation 的客户端由 Agent 使用 AskUserQuestion 或等价工具提问。用户选择打开后直接进入携程登录页，验证成功后以原参数重试一次。详见[登录交互约定](../docs/hotel-login.md)。

## 安装与测试

统一网关安装时，在仓库根目录按[运行指南](../docs/browser-runtime.md)安装两个 provider 到根 `.venv`。

独立安装时，在本项目目录执行 `uv venv .venv --python 3.11`，随后执行 `uv pip install --python <解释器路径> -e ".[dev]"`。Windows 解释器为 `.venv/Scripts/python.exe`，macOS/Linux 为 `.venv/bin/python`。

启动：`uv run --no-project --python <解释器路径> python -m hotel_ticket_mcp_server`。

浏览器支持按平台自动发现和最终一次 DrissionPage 兜底。退出时校验进程归属，保留 profile/cookie，下一次启动恢复已确认的遗留浏览器。

## 环境变量

见 [.env.example](.env.example)：`HOTEL_MCP_BROWSER`（edge 默认/chrome）、`HOTEL_MCP_BROWSER_PATH`、`HOTEL_MCP_HEADLESS`（不推荐）、`HOTEL_MCP_CONSENT`（风险同意开关）、`HOTEL_MCP_MIN_DELAY`/`HOTEL_MCP_MAX_DELAY`、`HOTEL_MCP_COOKIE_FILE`。

## 隐私

登录 cookie 保存在 `ctrip-hotel-cookies.json`（已被 .gitignore 忽略），浏览器 profile 保存在 `.browser-profile/`（同样被忽略）——两者都**严禁提交**到版本控制。
