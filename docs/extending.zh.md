# 扩展与工具参考

[返回主说明](../README.md)

本文说明仓库结构、当前聚合保留的工具列表、如何新增子 MCP，以及网关辅助能力与安全约定。

## 架构示意图

![出行 MCP 统一网关 总体架构](assets/workflow.png)

总体架构与「网关如何把工具暴露给模型」的说明见主文档 [README.md](../README.md) 中的「Gateway MCP Server 与模型上下文的关系」。

## 仓库布局

```text
.
├─ 12306-mcp/
├─ FlightTicketMCP/
├─ HotelTicketMCP/
├─ .opencode/
│  └─ opencode.json
├─ skill-templates/
│  └─ error-processing/
│     ├─ SKILL.md
│     └─ mcp-error-references.json
├─ scripts/
│  └─ install-agent-skill.mjs
├─ docs/
│  ├─ assets/
│  │  └─ workflow.png
│  └─ mcp-client-examples/
├─ src/
│  ├─ config.ts
│  ├─ index.ts
│  ├─ types.ts
│  ├─ utils/
│  └─ domains/
│     ├─ train/
│     │  ├─ registry.ts
│     │  └─ 12306/
│     │     └─ provider.ts
│     ├─ flight/
│     │  ├─ registry.ts
│     │  └─ flight_ticket_mcp_server/
│     │     └─ provider.ts
│     ├─ hotel/
│     │  ├─ registry.ts
│     │  └─ ctrip/
│     │     └─ provider.ts
│     ├─ map/
│     │  ├─ registry.ts
│     │  └─ amap/
│     │     └─ provider.ts
│     └─ taxi/
│        ├─ registry.ts
│        └─ didi/
│           └─ provider.ts
├─ .env.example
├─ package.json
└─ tsconfig.json
```

设计约定：

- `docs/agent-install.zh.md` / `docs/agent-install.md` 是面向 LLM Agent 的安装与验证指南
- `docs/mcp-client-examples/` 存放 Cursor / Claude Code / OpenCode 的 MCP 配置占位示例（见其中 `README.md`）
- `.opencode/opencode.json` 是 OpenCode 的项目级 MCP 配置示例
- `skill-templates/error-processing/` 是错误处理 skill 与参考索引的唯一维护源；`scripts/install-agent-skill.mjs` 按目标宿主安装项目级副本
- 生成的 `.opencode/skills/`、`.claude/skills/`、`.cursor/skills/` 由 `skills/` 忽略规则覆盖，不作为模板维护
- 一级目录按业务域固定为：`train`、`flight`、`hotel`、`map`、`taxi`
- 二级目录按具体子 MCP 划分，例如 `train/12306`、`hotel/ctrip`
- 每个业务域的 `registry.ts` 汇总该域下所有 provider

## 当前保留的工具

### `train/12306`

来自 `12306-mcp` 的查询类工具：

- `train_12306_get_current_date`
- `train_12306_get_stations_code_in_city`
- `train_12306_get_station_code_of_citys`
- `train_12306_get_station_code_by_names`
- `train_12306_get_station_by_telecode`
- `train_12306_get_tickets`
- `train_12306_get_interline_tickets`
- `train_12306_get_train_route_stations`

覆盖日期辅助、车站编码、余票、中转与经停站查询。联程路径已随 12306 上游改版修复（解析 `lc_search_url` 动态路径）。

### `flight/flight_ticket_mcp_server`

来自 `FlightTicketMCP` 的查询类工具：

- `flight_flight_ticket_mcp_server_searchFlightRoutes`
- `flight_flight_ticket_mcp_server_getCurrentDate`
- `flight_flight_ticket_mcp_server_getWeatherByLocation`
- `flight_flight_ticket_mcp_server_getWeatherByCity`
- `flight_flight_ticket_mcp_server_getFlightStatus`
- `flight_flight_ticket_mcp_server_getAirportFlights`
- `flight_flight_ticket_mcp_server_getFlightsInArea`
- `flight_flight_ticket_mcp_server_trackMultipleFlights`

覆盖航班搜索、天气与实时航班状态等。已隐藏 `getTransferFlightsByThreePlace`：抓取链路不稳定，网关予以排除（仅直达）。

### `hotel/ctrip`

来自 `HotelTicketMCP` 的查询类工具：

- `hotel_ctrip_searchHotels`
- `hotel_ctrip_login`

酒店搜索通过可见浏览器抓取需要登录态的携程酒店列表。需 `HOTEL_MCP_CONSENT=yes`（封禁风险同意开关）与携程登录态（`hotel_ctrip_login` 建立）；两次搜索之间自动等待随机 15s~3min。详见主文档「酒店搜索风险告知」。

### `map/amap`

与官方高德 MCP 对齐的地图与位置能力，默认不做二次裁剪。能力范围包括（具体 tool 名以官方当前版本为准）：

- 专属地图、导航、打车唤端
- 地理编码、逆地理编码、IP 定位
- 天气查询
- 骑行 / 步行 / 驾车 / 公交路径规划
- 距离测量、关键词 / 周边 / 详情搜索

参考：[高德官方 MCP Server 概述](https://lbs.amap.com/api/mcp-server/summary)

### `taxi/didi`

仅保留：

- `taxi_didi_maps_textsearch`
- `taxi_didi_taxi_estimate`

不接入订单类工具，例如：`taxi_create_order`、`taxi_cancel_order`、`taxi_query_order`、`taxi_get_driver_location`、`taxi_generate_ride_app_link`。

## 如何新增子 MCP

### 1. 选择一级目录

- 火车 → `src/domains/train/`
- 航班 → `src/domains/flight/`
- 酒店 → `src/domains/hotel/`
- 地图 → `src/domains/map/`
- 打车 → `src/domains/taxi/`

### 2. 新建子目录

使用稳定、可辨识的名称（如 `map/baidu`），避免临时命名或混合多个来源。

### 3. 实现 `provider.ts`

每个子 MCP 至少提供一个 `provider.ts`，返回 `DownstreamProviderDefinition`，包含：

- `domain`、`providerName`、`displayName`、`description`
- 是否启用、传输方式
- 可选的 `includeTools` / `excludeTools`

可选：同目录下增加 `config.ts` 存放额外配置。

### 4. 在域 `registry.ts` 中注册

例如新增 `map/baidu/provider.ts` 后，在 `src/domains/map/registry.ts` 中加入该 provider。根入口 `src/index.ts` 不直接依赖各子 MCP 细节。

### 5. 工具名前缀

聚合后的工具名为：

```text
{domain}_{providerName}_{toolName}
```

例如：`train_12306_get_tickets`、`map_amap_maps_geo`、`taxi_didi_taxi_estimate`。

### 6. 传输方式

本地 `stdio` 子进程：

```ts
transport: {
  kind: "stdio",
  command: "node",
  args: ["./path/to/server.js"],
  cwd: workspaceRoot,
  env: inheritedEnv
}
```

远程 `streamable-http`：

```ts
transport: {
  kind: "streamable-http",
  url: "https://example.com/mcp"
}
```

需要时可在 `requestHeaders` 中传入 header。

### 7. 限制暴露的工具

使用 `includeTools` / `excludeTools`。当前 `taxi/didi` 仅保留 `maps_textsearch` 与 `taxi_estimate`。

### 8. 验证

1. `npm run build`
2. 启动网关
3. 调用 `gateway_list_retained_tools`，确认新工具为 `{domain}_{provider}_{tool}` 形式
4. 实际调用 1～2 个工具确认参数与返回

### 9. 示例：新增 `map/baidu`

1. 新建 `src/domains/map/baidu/provider.ts`，`domain: "map"`
2. 在 `src/domains/map/registry.ts` 中注册
3. 按需填写 `includeTools`
4. 构建、启动后用 `gateway_list_retained_tools` 确认出现 `map_baidu_*`

## 网关内置辅助

- 资源：`gateway://inventory`
- 工具：`gateway_list_retained_tools`（含每个工具的参数摘要）
- 工具：`gateway_get_config`（脱敏运行态配置，密钥仅 set/unset）
- 工具：`gateway_health_check`（按域轻量探测，可选 `domain` 参数）

用于在不读源码的前提下查看已启用的 provider、保留工具、浏览器策略与各域健康状态。

## 按宿主安装错误处理 Skill

- OpenCode 示例配置位于 `.opencode/opencode.json`，只配置统一网关 `travel-mcp-gateway`
- Agent 安装指南位于 `docs/agent-install.zh.md` / `docs/agent-install.md`，用于让 Agent 完成依赖安装、环境模板复制、构建验证和客户端配置
- 通用模板为 [SKILL.md](../skill-templates/error-processing/SKILL.md) 与 [mcp-error-references.json](../skill-templates/error-processing/mcp-error-references.json)，引用资源相对 skill 目录解析
- 安装器复用安装流程的宿主选择：`--agent opencode` → `.opencode/skills/error-processing/`，`--agent claude-code` → `.claude/skills/error-processing/`，`--agent cursor` → `.cursor/skills/error-processing/`
- 默认目标是 MCP 仓库；`--project-root` 可指定 Agent 实际工作项目。未知宿主不能自动回退；其它产品须核对官方 skills 文档
- 安装前校验源文件；相同内容不重复写入，存在不同内容时报告冲突并保留用户文件。`--check` 只读检查，退出码 0 表示与模板一致，非零表示缺失、冲突或校验失败
- 安装器会提示项目内其它同名副本，避免兼容目录产生发现歧义；它不删除副本，也不验证宿主已加载。宿主发现方法见 [安装指南](agent-install.zh.md)
- MCP 出错时，由宿主中的 Agent 根据参考索引 `description` / `usage` 及错误上下文选择 1–2 个相关公开来源；`triggers` 为可选别名。这是提示词工作流，不是 embedding、向量数据库或已知错误案例检索引擎
- Agent 在对话中输出“错误摘要 / 已检查 / 判断 / 下一步”，仅在用户要求保存时写入文档；网关没有自动触发此 skill 的代码
- 用户可以输入密钥，Agent 可以按授权写入本地配置；排障回复和日志不得主动回显真实密钥、token、完整环境变量或私人账号数据

修改模板后，运行 `node --test tests/install-agent-skill.test.mjs` 验证宿主路径、跨目录安装、重复安装和冲突保护。已有定制副本需审查差异后合并，不通过安装器强制更新。

## 安全说明

- 不要提交 `.env`、日志或本机绝对路径
- 不要把个人笔记、地址、通勤数据、运行缓存纳入公开仓库
- 本仓库不开放滴滴订单创建相关工具，仅保留费用预估
- 酒店登录 cookie（`HotelTicketMCP/ctrip-hotel-cookies.json`）与浏览器 profile（`HotelTicketMCP/.browser-profile/`）已被 `.gitignore` 忽略，**严禁取消忽略或提交**
- 文档和 skill 只保存公开参考链接，不保存真实密钥或私人配置

## 参考与致谢

- [滴滴 MCP 文档](https://mcp.didichuxing.com/api?tap=api)
- [高德官方 MCP Server 概述](https://lbs.amap.com/api/mcp-server/summary)
- [FlightTicketMCP](https://github.com/xiaonieli7/FlightTicketMCP)
- [12306-mcp](https://github.com/Joooook/12306-mcp)
