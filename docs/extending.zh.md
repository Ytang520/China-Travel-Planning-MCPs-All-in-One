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
├─ .opencode/
│  ├─ opencode.json
│  └─ skills/
│     └─ error-processing/
│        ├─ SKILL.md
│        └─ mcp-error-references.json
├─ docs/
│  └─ assets/
│     └─ workflow.png
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
- `.opencode/opencode.json` 是 OpenCode 的项目级 MCP 配置示例
- `.opencode/skills/error-processing/` 存放项目级错误处理 skill 及 MCP 排障参考索引
- 一级目录按业务域固定为：`train`、`flight`、`map`、`taxi`
- 二级目录按具体子 MCP 划分，例如 `train/12306`、`map/amap`
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

覆盖日期辅助、车站编码、余票、中转与经停站查询。

### `flight/flight_ticket_mcp_server`

来自 `FlightTicketMCP` 的查询类工具：

- `flight_flight_ticket_mcp_server_searchFlightRoutes`
- `flight_flight_ticket_mcp_server_getCurrentDate`
- `flight_flight_ticket_mcp_server_getTransferFlightsByThreePlace`
- `flight_flight_ticket_mcp_server_getWeatherByLocation`
- `flight_flight_ticket_mcp_server_getWeatherByCity`
- `flight_flight_ticket_mcp_server_getFlightStatus`
- `flight_flight_ticket_mcp_server_getAirportFlights`
- `flight_flight_ticket_mcp_server_getFlightsInArea`
- `flight_flight_ticket_mcp_server_trackMultipleFlights`

覆盖航班搜索、联程中转、天气与实时航班状态等。

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
- 工具：`gateway_list_retained_tools`

用于查看已启用的 provider 与聚合后保留的工具列表。

## OpenCode 与错误处理 Skill

- OpenCode 示例配置位于 `.opencode/opencode.json`，只配置统一网关 `travel-mcp-gateway`
- Agent 安装指南位于 `docs/agent-install.zh.md` / `docs/agent-install.md`，用于让 Agent 完成依赖安装、环境模板复制、构建验证和客户端配置
- 错误处理 skill 位于 `.opencode/skills/error-processing/SKILL.md`
- MCP 排障参考索引位于 `.opencode/skills/error-processing/mcp-error-references.json`
- 当出现 MCP 连接、鉴权、schema 或返回格式问题时，skill 会优先根据参考索引中的 `description` / `usage` 语义匹配公开文档；`triggers` 仅作为环境变量、provider id、工具名和中文名的可选别名
- 排障时不应输出密钥、token、完整环境变量或私人账号数据

## 安全说明

- 不要提交 `.env`、日志或本机绝对路径
- 不要把个人笔记、地址、通勤数据、运行缓存纳入公开仓库
- 本仓库不开放滴滴订单创建相关工具，仅保留费用预估
- 文档和 skill 只保存公开参考链接，不保存真实密钥或私人配置

## 参考与致谢

- [滴滴 MCP 文档](https://mcp.didichuxing.com/api?tap=api)
- [高德官方 MCP Server 概述](https://lbs.amap.com/api/mcp-server/summary)
- [FlightTicketMCP](https://github.com/xiaonieli7/FlightTicketMCP)
- [12306-mcp](https://github.com/Joooook/12306-mcp)
