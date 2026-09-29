# HotelTicketMCP

基于模型上下文协议（MCP）的携程酒店搜索服务器（[出行 MCP 统一网关](../README.md) 的 `hotel` 域下游）。

## ⚠ 风险提示（重要）

本服务器通过浏览器模拟真人浏览并抓取**需要登录态**的携程酒店数据，**存在账号被封禁的风险**：

- 必须显式同意风险条款（`HOTEL_MCP_CONSENT=yes`）才会启用工具；**选择启用即表示自愿承担该风险，作者概不负责**；
- 为降低风险，两次搜索之间自动等待随机 30 秒 ~ 5 分钟（`HOTEL_MCP_MIN_DELAY`/`HOTEL_MCP_MAX_DELAY` 可调），滚动采集采用随机步幅与停顿的人性化行为。

## 功能

- `searchHotels`（网关注册名 `hotel_ctrip_searchHotels`）：携程酒店搜索——城市/地标、入住退房日期、人数、价格/星级/评分/房型/住宿类型筛选与排序（smart/price_asc/distance/score_desc）。
- `login`（网关注册名 `hotel_ctrip_login`）：携程登录助手——打开可见浏览器窗口，等待用户手动登录后把 cookie 保存到 gitignored 文件供后续搜索复用。

## 登录态流程（按次开关浏览器）

浏览器在每次搜索/登录完成后立即关闭（无长驻进程），登录态完全由 cookie 文件承载：

1. 搜索时注入 `ctrip-hotel-cookies.json`（含 HttpOnly cookie）→ 重新导航 → 检测登录态；
2. 仍未恢复 → 返回 `LOGIN_REQUIRED`，由 Agent 停止并通知用户调用登录工具重新登录。

## 安装与测试

```bash
uv venv
uv pip install -r requirements.txt
uv pip install pytest   # 开发测试用
.venv/Scripts/python.exe -m pytest tests/ -v
```

启动（stdio）：

```bash
.venv/Scripts/python.exe -m hotel_ticket_mcp_server
```

## 环境变量

见 [.env.example](.env.example)：`HOTEL_MCP_BROWSER`（edge 默认/chrome）、`HOTEL_MCP_BROWSER_PATH`、`HOTEL_MCP_HEADLESS`（不推荐）、`HOTEL_MCP_CONSENT`（风险同意开关）、`HOTEL_MCP_MIN_DELAY`/`HOTEL_MCP_MAX_DELAY`、`HOTEL_MCP_COOKIE_FILE`。

## 隐私

登录 cookie 保存在 `ctrip-hotel-cookies.json`（已被 .gitignore 忽略），浏览器 profile 保存在 `.browser-profile/`（同样被忽略）——两者都**严禁提交**到版本控制。
