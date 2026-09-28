# Changelog

本项目重要变更记录。格式接近 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

发布 GitHub Release：

1. 把 `## [Unreleased]` 下的内容改写为 `## [x.y.z] - YYYY-MM-DD`，并让根目录 `package.json` 的 `version` 与 `x.y.z` 一致。
2. 提交后打标签并推送：`git tag vX.Y.Z`，然后 `git push origin vX.Y.Z`。
3. [Release 工作流](.github/workflows/release.yml) 会读取该版本段落，创建 [GitHub Release](https://github.com/Ytang520/China-Travel-Planning-MCPs-All-in-One/releases)。

## [Unreleased]

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
