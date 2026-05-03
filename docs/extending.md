# Extending and tool reference

[Back to main README](../README.en.md)

This document describes repository layout, retained aggregated tools, how to add a new sub-MCP, gateway helpers, and security notes.

## Architecture diagram

![Unified Travel MCP Gateway overview](assets/workflow.png)

For how the gateway exposes tools to the model, see **Gateway MCP Server and model context** in [README.en.md](../README.en.md). The Chinese README [README.md](../README.md) has the same explanation under **Gateway MCP Server 与模型上下文的关系**.

## Repository layout

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
│     ├─ flight/
│     ├─ map/
│     └─ taxi/
├─ .env.example
├─ package.json
└─ tsconfig.json
```

Conventions:

- `docs/agent-install.zh.md` / `docs/agent-install.md` are agent-facing installation and verification guides
- `docs/mcp-client-examples/` hosts MCP JSON placeholders for Cursor, Claude Code, and OpenCode (see its `README.md`)
- `.opencode/opencode.json` is the project-level OpenCode MCP configuration example
- `.opencode/skills/error-processing/` stores the project-level error-processing skill and MCP troubleshooting reference index
- Top-level domains are fixed: `train`, `flight`, `map`, `taxi`
- Each child folder is one downstream MCP provider (e.g. `train/12306`)
- Each domain has a `registry.ts` that lists its providers

## Retained tools

### `train/12306`

Query tools from `12306-mcp`:

- `train_12306_get_current_date`
- `train_12306_get_stations_code_in_city`
- `train_12306_get_station_code_of_citys`
- `train_12306_get_station_code_by_names`
- `train_12306_get_station_by_telecode`
- `train_12306_get_tickets`
- `train_12306_get_interline_tickets`
- `train_12306_get_train_route_stations`

### `flight/flight_ticket_mcp_server`

Query tools from `FlightTicketMCP`:

- `flight_flight_ticket_mcp_server_searchFlightRoutes`
- `flight_flight_ticket_mcp_server_getCurrentDate`
- `flight_flight_ticket_mcp_server_getTransferFlightsByThreePlace`
- `flight_flight_ticket_mcp_server_getWeatherByLocation`
- `flight_flight_ticket_mcp_server_getWeatherByCity`
- `flight_flight_ticket_mcp_server_getFlightStatus`
- `flight_flight_ticket_mcp_server_getAirportFlights`
- `flight_flight_ticket_mcp_server_getFlightsInArea`
- `flight_flight_ticket_mcp_server_trackMultipleFlights`

### `map/amap`

Official Amap MCP map/location capabilities without extra filtering. Exact tool names follow the current official release. Capabilities include geocoding, POI search, routing, weather, distance, and trip-map features.

Reference: [Amap Official MCP Server Summary](https://lbs.amap.com/api/mcp-server/summary)

### `taxi/didi`

Only:

- `taxi_didi_maps_textsearch`
- `taxi_didi_taxi_estimate`

Order-related tools are not integrated, for example: `taxi_create_order`, `taxi_cancel_order`, `taxi_query_order`, `taxi_get_driver_location`, `taxi_generate_ride_app_link`.

## How to add a new sub-MCP

### 1. Pick the domain

- Train → `src/domains/train/`
- Flight → `src/domains/flight/`
- Map → `src/domains/map/`
- Taxi → `src/domains/taxi/`

### 2. Create a child folder

Use a stable name (e.g. `map/baidu`). Do not mix multiple sources in one folder.

### 3. Add `provider.ts`

Implement `DownstreamProviderDefinition` with `domain`, `providerName`, `displayName`, `description`, enablement, transport, and optional `includeTools` / `excludeTools`. Optional `config.ts` for extra settings.

### 4. Register in `registry.ts`

For example, register `map/baidu/provider.ts` in `src/domains/map/registry.ts`. The root `src/index.ts` does not hard-code individual providers.

### 5. Tool naming

Exposed tools are named:

```text
{domain}_{providerName}_{toolName}
```

Examples: `train_12306_get_tickets`, `map_amap_maps_geo`, `taxi_didi_taxi_estimate`.

### 6. Transport

Local `stdio`:

```ts
transport: {
  kind: "stdio",
  command: "node",
  args: ["./path/to/server.js"],
  cwd: workspaceRoot,
  env: inheritedEnv
}
```

Remote `streamable-http`:

```ts
transport: {
  kind: "streamable-http",
  url: "https://example.com/mcp"
}
```

Use `requestHeaders` when headers are required.

### 7. Filter tools

Use `includeTools` / `excludeTools`. `taxi/didi` keeps only `maps_textsearch` and `taxi_estimate`.

### 8. Validate

1. `npm run build`
2. Start the gateway
3. Call `gateway_list_retained_tools` and confirm `{domain}_{provider}_{tool}` names
4. Run one or two real tool calls

### 9. Example: add `map/baidu`

1. Add `src/domains/map/baidu/provider.ts` with `domain: "map"`
2. Register it in `src/domains/map/registry.ts`
3. Set `includeTools` if needed
4. Build, start, and verify `map_baidu_*` via `gateway_list_retained_tools`

## Built-in gateway helpers

- Resource: `gateway://inventory`
- Tool: `gateway_list_retained_tools`

Use these to inspect enabled providers and retained tools.

## OpenCode and error-processing skill

- OpenCode example config lives at `.opencode/opencode.json` and configures only the unified `travel-mcp-gateway`
- Agent installation guides live at `docs/agent-install.zh.md` / `docs/agent-install.md` for dependency installation, environment template copying, build verification, and client configuration
- The error-processing skill lives at `.opencode/skills/error-processing/SKILL.md`
- MCP troubleshooting references live at `.opencode/skills/error-processing/mcp-error-references.json`
- For MCP connection, authentication, schema, or response-format issues, the skill first semantically matches public references by `description` / `usage`; `triggers` are only optional aliases for environment variables, provider ids, tool names, and Chinese names
- Troubleshooting must not print secrets, tokens, full environment dumps, or private account data

## Security

- Do not commit `.env`, logs, or machine-specific absolute paths
- Do not publish personal notes, commuting data, or local caches
- DiDi order-creation tools stay disabled; only fare estimation is exposed
- Docs and skills store only public reference links, not real secrets or private config

## References and credits

- [DiDi MCP Documentation](https://mcp.didichuxing.com/api?tap=api)
- [Amap Official MCP Server Summary](https://lbs.amap.com/api/mcp-server/summary)
- [FlightTicketMCP](https://github.com/xiaonieli7/FlightTicketMCP)
- [12306-mcp](https://github.com/Joooook/12306-mcp)
