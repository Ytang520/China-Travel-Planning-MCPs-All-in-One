# Changelog

本项目重要变更记录。格式接近 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

发布 GitHub Release：

1. 把 `## [Unreleased]` 下的内容改写为 `## [x.y.z] - YYYY-MM-DD`，并让根目录 `package.json` 的 `version` 与 `x.y.z` 一致。
2. 提交后打标签并推送：`git tag vX.Y.Z`，然后 `git push origin vX.Y.Z`。
3. [Release 工作流](.github/workflows/release.yml) 会读取该版本段落，创建 [GitHub Release](https://github.com/Ytang520/China-Travel-Planning-MCPs-All-in-One/releases)。

## [Unreleased]

## [0.2.2] - 2026-10-08

航班查询在携程网页没有可用结果时，自动用未登录的飞猪网页再查一次。同时补充真实使用案例，以及与其他出行方案的差异说明。

### 航班查询

- `auto` / `default` 仍优先抓取携程网页。携程抓取失败，或没有符合条件的航班时，等待搜索间隔后自动尝试一次飞猪网页（`fliggy_web_scraping`）。
- 飞猪查询不登录、不滚动；中转推荐不计入直达结果。票价不含税费，结果用 `price_basis` 标明。成功结果会区分来源是携程还是飞猪，并带查询链接与时间。
- `limit` 按单次查询计数，同一次查询转到飞猪不会另加额度。同一进程内的航班网页搜索串行执行，默认间隔 15–45 秒（`FLIGHT_MCP_MIN_DELAY` / `FLIGHT_MCP_MAX_DELAY`），切换飞猪也计入该间隔。

### 使用案例与方案比较

- [cases](cases/)：安装网关的 token 与费用，以及武汉酒店收集案例和结果表。
- [与已有方案的差异](docs/cn-travel-mcp-comparison.zh.md)：对照 codex-china-travel-suite、Go-Home、china-travel-assistant、Dida-hotel-MCP-CN、trvl，并说明不采用飞猪 API、改为网页 fallback 的原因。

[完整文件差异：v0.2.1 → v0.2.2](https://github.com/Ytang520/China-Travel-Planning-MCPs-All-in-One/compare/v0.2.1..v0.2.2)

## [0.2.1] - 2026-10-02

本版新增携程酒店搜索与交互式登录，完善浏览器与 Python 环境发现、登录恢复及进程清理，并提供可重复执行的安装验收脚本。

### 与 v0.2.0 的主要差别

| 项目 | v0.2.0 | v0.2.1 |
| --- | --- | --- |
| 业务域 | 火车、航班、地图、打车 | 新增携程酒店搜索与登录，共五个业务域 |
| 浏览器发现 | 显式路径或 Windows 常见安装路径 | 支持 Windows、macOS、Linux 的本机发现、路径校验和受控回退 |
| Python 解释器 | 默认使用 `python` 或显式指定命令 | 校验显式命令，或依次探测项目根目录及 provider 的 `.venv`，检查版本与依赖 |
| 安装验收 | 按安装指南手工调用工具 | 新增分域测试脚本，校验实际查询结果、日期、字段及记录数量 |

### 新增功能

- `hotel_ctrip_searchHotels`：支持城市或地标、入住/退房日期、人数、价格、星级、评分、房型与住宿类型筛选，以及智能、价格、距离、评分排序，最多返回 50 条记录。
- `hotel_ctrip_login`：通过可见浏览器完成携程登录，验证登录态后原子保存包含 HttpOnly 的 cookies，供后续查询及新浏览器会话复用。
- 酒店登录前使用 MCP 原生用户选择；客户端不支持时返回明确的用户操作请求。命令行支持交互选择及外部已确认的登录操作，登录成功后可恢复原查询一次。
- 酒店查询提供 `HOTEL_MCP_CONSENT` 同意开关、可配置的随机查询间隔，以及同一 profile 的跨进程互斥。
- 网关工具清单、配置诊断及健康检查覆盖酒店域；航班和酒店健康检查只检查连通性，实际查询由专项测试校验。

### 稳定性与诊断

- 登录跳转期间页面读取异常支持有时间上限的恢复等待，分别判断浏览器退出、标签页关闭、控制连接中断和暂时无法判断的登录态。
- 登录默认等待上限为 840 秒，支持进度通知和取消；成功流程在关闭浏览器前完成 cookie 保存，取消流程防止后台迟到写入。
- 登录诊断按请求关联阶段、恢复次数、保存结果和结束原因，便于定位提前关窗、超时与连接异常。
- 航班查询使用独立临时 profile；航班和酒店通过进程身份、profile 及端口检查清理本次拥有的浏览器。网关退出、宿主断开或 provider 初始化失败时回收下游连接。
- 网关支持 Python 工具参数中的 JSON Schema `null` 类型，避免可空参数在转发前被错误拒绝。

### 配置、隐私与升级

- 新增 `npm run check` 和 `scripts/mcp-test.mjs` 的分域验收入口；输出对密钥及本机路径进行脱敏。中英文安装指南、客户端示例和浏览器排障文档同步更新。
- `.gitignore` 覆盖本地密钥配置、酒店 cookies、浏览器 profile、运行日志、测试临时文件及凭据备份文件；登录诊断不记录 cookie 值、账号文本或完整页面 URL。
- 浏览器服务要求 Python 3.11+、DrissionPage 4.1.1.4+ 和 psutil 5.9+。已有安装请按[安装指南](https://github.com/Ytang520/China-Travel-Planning-MCPs-All-in-One/blob/v0.2.1/docs/agent-install.zh.md)更新项目虚拟环境中的依赖并重新构建网关。
- 配置入口：MCP 客户端通过环境变量启动网关，测试脚本读取根目录 `.env`；酒店 cookies 默认保存在 `HotelTicketMCP/ctrip-hotel-cookies.json`，可由 `HOTEL_MCP_COOKIE_FILE` 指定位置。

### 验证

- TypeScript 构建通过，Node 测试 37 项通过。
- Python 测试 164 项通过；默认跳过的 3 项 Edge 集成测试已在 Windows Edge 环境单独通过。
- 已验证真实扫码登录、关闭浏览器前保存 cookies，以及新浏览器会话复用登录态并完成酒店查询。
- macOS/Linux 的发现与运行时分支通过模拟测试；原生浏览器验收环境为 Windows Edge。

[完整文件差异：v0.2.0 → v0.2.1](https://github.com/Ytang520/China-Travel-Planning-MCPs-All-in-One/compare/v0.2.0..v0.2.1)

## [0.2.0] - 2026-09-28

### Added

- `gateway_get_config`：脱敏运行态配置（各 provider 连接状态、保留工具数、浏览器策略、入口命令；密钥仅显示 set/unset）。
- `gateway_health_check`：按域轻量探测（train: 当前日期；map: 地理编码；taxi: 地点搜索；flight: 仅连通性，不做抓取）。
- `gateway_list_retained_tools` 现返回每个工具的参数摘要（参数名/类型/必填/枚举/描述）与下游工具名。
- 航班浏览器内核安装期选择 A/B：`FLIGHT_MCP_BROWSER=edge|chrome`（默认 edge），`FLIGHT_MCP_BROWSER_PATH` 仍可显式覆盖。
- 航班抓取默认「最小化窗口」（任务栏可见 + 关闭后台节流），不再抢占前台焦点。

### Changed

- `12306-mcp`：`getLCQueryPath` 改为携带浏览器头（UA/Accept-Language/Referer + 登录前 cookie 链）并用宽松正则解析 `lc_search_url`（页面缩进混用制表符/空格，旧字面量正则无法匹配），保留非致命降级；联程接口路径随上游改版修复（`/lcquery/queryG`）。
- `12306-mcp`：`get-tickets` 改为从 `leftTicket/init` 动态读取 `CLeftTicketUrl`（回移上游 0.3.10 行为），不再硬编码 `leftTicket/query`。
- `make12306Request` 默认携带浏览器 UA / Accept-Language，并增加 20s 超时（避免网络异常时阻塞启动）。
- 安装文档 §8 修正工具名与参数示例，新增打车测试与 Windows 绝对路径注意事项。

### Removed

- VariFlight 备选数据源（原因：信息不全，字段缺失且与主数据源结果不一致）：删除 `variflight_tools.py`，移除两个工具模块中的回退分支、`VARIFLIGHT_API_KEY` 及相关文档与排障索引条目。
- `data_source_preference` 不再接受 `variflight`，传入时返回 `DATA_SOURCE_REMOVED` 明确报错。

### Hidden (gateway `excludeTools`)

- `flight_flight_ticket_mcp_server_getTransferFlightsByThreePlace`：与「航班仅直达」产品口径一致，抓取链路不稳定。

### Docs

- README（中/英）：新增「浏览器依赖」「直达与中转说明」章节；环境变量表补充浏览器变量；移除 VariFlight 表述。
- agent-install（中/英）：新增浏览器内核 A/B 选择步骤、Windows 绝对路径注意事项、§8 工具名与参数修正、新增打车测试。
- extending（中/英）：保留工具列表与内置辅助工具同步更新。
