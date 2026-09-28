# Unified Travel MCP Gateway

**Languages:** [中文](README.md)

English README for **[出行 MCP 统一网关](README.md)** — a single **stdio MCP entrypoint** for travel workflows in China. One connection aggregates **train** (12306), **flight** (FlightTicketMCP), **map** (official Amap MCP), and **ride-hailing fare estimates** (DiDi). Domains are fixed as `train`, `flight`, `map`, and `taxi` so providers stay easy to extend.

## Architecture overview

![Unified Travel MCP Gateway overview](docs/assets/workflow.png)

## Feature overview

- **Single gateway**: Run **one** MCP server process and reach train ticketing (12306), flights (FlightTicketMCP), maps (Amap MCP), and DiDi fare tools—fewer processes and configs for desktop hosts such as Cursor, Claude Code, or OpenCode.
- **Easy extension**: Downstream integrations register under fixed domains via each domain’s `registry.ts`; add providers under `src/domains/` (see [docs/extending.md](docs/extending.md)).
- **Operations-friendly troubleshooting**: The OpenCode **error-processing** skill ([SKILL.md](.opencode/skills/error-processing/SKILL.md)) works with [mcp-error-references.json](.opencode/skills/error-processing/mcp-error-references.json) to semantically match public docs for Amap, DiDi, and related failures—without ever dumping secrets—covering MCP connectivity, auth, schemas, and response-shape issues.
- **No source reading required**: the gateway ships `gateway_get_config` (redacted runtime config), `gateway_health_check` (per-domain light probes), and `gateway_list_retained_tools` (with parameter summaries) so agents can inspect capabilities without reading source code.

## Let an agent install it

Copy this into your LLM agent session:

```text
Install and configure Travel MCP Gateway by following the instructions here:
https://raw.githubusercontent.com/Ytang520/China-Travel-Planning-MCPs-All-in-One/main/docs/agent-install.md
```

You can also read the [Agent installation guide](docs/agent-install.md).

## Quick start

```bash
npm install
```

Install flight provider dependencies (example with `uv`):

```bash
cd FlightTicketMCP
uv venv
uv pip install -r requirements.txt
```

Or with pip: `pip install -r requirements.txt` or `pip install -e .`

Create `.env` from the template, fill in your keys, then:

```bash
cp .env.example .env
```

```bash
npm run build
node build/index.js
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `AMAP_MAPS_API_KEY` | Obtain a key from [Amap MCP Server](https://lbs.amap.com/api/mcp-server/summary) for `map/amap` |
| `DIDI_MCP_KEY` | Obtain a key from [DiDi MCP](https://mcp.didichuxing.com/) for `taxi/didi` (place search + fare estimate) |
| `FLIGHT_MCP_PYTHON_COMMAND` | Python executable for FlightTicketMCP (default: `python`; with uv point it at `.venv/Scripts/python.exe`) |
| `TRAIN_12306_ENTRY` | Optional path to 12306 MCP entry script |
| `FLIGHT_MCP_PROJECT_ROOT` | Optional path to `FlightTicketMCP` root |
| `FLIGHT_MCP_BROWSER` | Browser engine for flight scraping: A=`edge` (default) / B=`chrome` |
| `FLIGHT_MCP_BROWSER_PATH` | Optional explicit browser executable path (takes precedence over `FLIGHT_MCP_BROWSER`) |
| `FLIGHT_MCP_HEADLESS` | Optional: `1` enables headless mode (not recommended—Ctrip whaleguard blocks it) |

Additional flight-related variables are documented in `FlightTicketMCP/.env.example`.

> **Windows path note**: subprocesses run with `FLIGHT_MCP_PROJECT_ROOT` as cwd, so relative paths resolve against the child cwd. Use absolute paths for `FLIGHT_MCP_PYTHON_COMMAND`, `TRAIN_12306_ENTRY`, and `FLIGHT_MCP_BROWSER_PATH`.

### Browser requirements

Ctrip (flights.ctrip.com) uses a whaleguard anti-bot WAF that blocks headless browsers (HTTP 432) and browser-less HTTP requests, so **flight search requires Chrome or Edge to be installed**:

- Choose the engine at install time: **A = Edge (default) / B = Chrome**, configured via `FLIGHT_MCP_BROWSER`;
- Searches open a **minimized window** by default (visible in the taskbar), never stealing foreground focus;
- Headless mode (`FLIGHT_MCP_HEADLESS=1`) is off by default and is blocked by Ctrip when enabled.

### Direct and transfer routes

- Train: **direct** and **interline/transfer** are supported (`train_12306_get_interline_tickets`, with the 12306 interline path fixed after the upstream site rework);
- Flight: **direct only** — `flight_flight_ticket_mcp_server_getTransferFlightsByThreePlace` relies on an unstable scraping chain and is hidden from the gateway.

## MCP client configuration

Host-specific copy/paste examples live under **[docs/mcp-client-examples/README.md](docs/mcp-client-examples/README.md)** (Cursor, Claude Code, OpenCode).

Minimal **`mcpServers`** snippet compatible with **Cursor** when the MCP subprocess cwd is the repo root—otherwise use an absolute path for `build/index.js`:

```json
{
  "mcpServers": {
    "travel-mcp-gateway": {
      "command": "node",
      "args": ["./build/index.js"],
      "env": {
        "AMAP_MAPS_API_KEY": "YOUR_AMAP_MAPS_API_KEY",
        "DIDI_MCP_KEY": "YOUR_DIDI_MCP_KEY",
        "FLIGHT_MCP_PYTHON_COMMAND": "python",
        "TRAIN_12306_ENTRY": "./12306-mcp/build/index.js",
        "FLIGHT_MCP_PROJECT_ROOT": "./FlightTicketMCP"
      }
    }
  }
}
```

## OpenCode

Example: [.opencode/opencode.json](.opencode/opencode.json). Replace placeholders with your real keys.

The project-level error-processing skill lives at [.opencode/skills/error-processing/SKILL.md](.opencode/skills/error-processing/SKILL.md), with MCP troubleshooting references in [.opencode/skills/error-processing/mcp-error-references.json](.opencode/skills/error-processing/mcp-error-references.json).

## Other

### Tool naming

Aggregated tools are named `{domain}_{providerName}_{toolName}`, for example `train_12306_get_tickets`, `map_amap_maps_geo`, `taxi_didi_taxi_estimate`. Each provider declares local **stdio** subprocess or remote **streamable-http** in its `provider.ts`.

### DiDi taxi fare estimate chain

Call tools in this order:

1. `taxi_didi_maps_textsearch`
2. `taxi_didi_taxi_estimate`

Coordinates for `estimate` must come from DiDi `maps_textsearch` (see [DiDi MCP](https://mcp.didichuxing.com/)). **Do not use coordinates returned by the Amap MCP.**

For geocoding, POI search, routing, weather, and other non–fare-estimate map tasks, prefer **`map/amap`**. See [Amap MCP Server overview](https://lbs.amap.com/api/mcp-server/summary).

### Flight search

Flight routes default to **`auto`** (equivalent to `default`): scraping **Ctrip** listings through a **minimized visible browser** (taskbar-visible; see "Browser requirements" above). Queries take 3–8 minutes and support direct flights only.

### Gateway MCP Server and model context

On startup the gateway calls `connectAndRegisterProvider` for each registered provider and exposes retained downstream tools on **one** MCP server (`src/index.ts`). Failed connections omit that provider’s tools (stderr shows `[gateway] failed to connect provider`). Host apps—not this gateway—decide whether to truncate or fold the global tool list; models typically choose calls from tool metadata plus conversation text rather than receiving entire MCP manuals verbatim.

## Documentation

- **Agent installation guide:** [docs/agent-install.md](docs/agent-install.md) (English) · [docs/agent-install.zh.md](docs/agent-install.zh.md) (中文)
- **Tool list, layout, provider extension, OpenCode, and error-processing skill:** [docs/extending.md](docs/extending.md) (English) · [docs/extending.zh.md](docs/extending.zh.md) (中文)

## Releases

Changes are recorded in [CHANGELOG.md](CHANGELOG.md). Pushing a `vX.Y.Z` tag publishes the matching [GitHub Release](https://github.com/Ytang520/China-Travel-Planning-MCPs-All-in-One/releases).

## Acknowledgements

This project builds on or references the following upstream repositories and materials (see each repo for its license):

- **Repositories**
  - [12306-mcp](https://github.com/Joooook/12306-mcp)
  - [FlightTicketMCP](https://github.com/xiaonieli7/FlightTicketMCP)
- **Other reference materials**
  - [Bilibili · BV1xFhrzpEDd](https://www.bilibili.com/video/BV1xFhrzpEDd/)
  - [Bilibili · BV1AoYZzKEvb](https://www.bilibili.com/video/BV1AoYZzKEvb/)
