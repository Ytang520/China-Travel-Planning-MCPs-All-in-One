# Unified Travel MCP Gateway

**Languages:** [中文](README.md)

English README for **[出行 MCP 统一网关](README.md)** — a single **stdio MCP entrypoint** for travel workflows in China. One connection aggregates **train** (12306), **flight** (FlightTicketMCP), **hotel** (HotelTicketMCP), **map** (official Amap MCP), and **ride-hailing fare estimates** (DiDi). Domains are fixed as `train`, `flight`, `hotel`, `map`, and `taxi` so providers stay easy to extend.

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

Both Python providers use Python 3.11+ in the repository root `.venv`. Reuse an existing suitable environment; otherwise create it from the repository root:

```sh
uv venv .venv --python 3.11
```

Windows PowerShell:

```powershell
uv pip install --python .venv/Scripts/python.exe -e "./FlightTicketMCP[dev]" -e "./HotelTicketMCP[dev]"
```

macOS / Linux:

```sh
uv pip install --python .venv/bin/python -e "./FlightTicketMCP[dev]" -e "./HotelTicketMCP[dev]"
```

Create `.env` from the template, fill in your keys, then:

```bash
cp .env.example .env
```

```bash
npm run build
node scripts/mcp-test.mjs config
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `AMAP_MAPS_API_KEY` | Obtain a key from [Amap MCP Server](https://lbs.amap.com/api/mcp-server/summary) for `map/amap` |
| `DIDI_MCP_KEY` | Obtain a key from [DiDi MCP](https://mcp.didichuxing.com/) for `taxi/didi` (place search + fare estimate) |
| `FLIGHT_MCP_PYTHON_COMMAND` | Python executable for FlightTicketMCP (auto: usable root `.venv`, then provider `.venv`; explicit override supported) |
| `TRAIN_12306_ENTRY` | Optional path to 12306 MCP entry script |
| `FLIGHT_MCP_PROJECT_ROOT` | Optional path to `FlightTicketMCP` root |
| `FLIGHT_MCP_BROWSER` | Browser engine for flight scraping: A=`edge` (default) / B=`chrome` |
| `FLIGHT_MCP_BROWSER_PATH` | Optional explicit browser executable path (takes precedence over `FLIGHT_MCP_BROWSER`) |
| `FLIGHT_MCP_HEADLESS` | Optional: `1` enables headless mode (not recommended—Ctrip whaleguard blocks it) |
| `HOTEL_MCP_PROJECT_ROOT` | Optional path to `HotelTicketMCP` root |
| `HOTEL_MCP_PYTHON_COMMAND` | Python executable for HotelTicketMCP (auto: usable root `.venv`, then provider `.venv`; explicit override supported) |
| `HOTEL_MCP_BROWSER` | Browser engine for hotel scraping: `edge` (default) / `chrome` (same as flight) |
| `HOTEL_MCP_BROWSER_PATH` | Optional explicit browser executable path (takes precedence over `HOTEL_MCP_BROWSER`) |
| `HOTEL_MCP_CONSENT` | ⚠ Risk-consent switch for hotel search: tools only work with `yes` (see "Hotel search risk notice") |
| `HOTEL_MCP_MIN_DELAY` / `HOTEL_MCP_MAX_DELAY` | Optional random interval between hotel searches, in seconds (default 30~300) |
| `HOTEL_MCP_COOKIE_FILE` | Optional cookie file location (default `HotelTicketMCP/ctrip-hotel-cookies.json`, gitignored) |

Additional flight-related variables are documented in `FlightTicketMCP/.env.example`.

> **Paths and configuration**: project roots/train entry resolve against the repository; interpreter/browser paths against the provider root. Prefer absolute overrides. The gateway reads host environment variables; the test script loads root `.env`. Windows interpreters use `.venv/Scripts/python.exe`; macOS/Linux use `.venv/bin/python`.

### Browser requirements

Ctrip (flights.ctrip.com) uses a whaleguard anti-bot WAF that blocks headless browsers (HTTP 432) and browser-less HTTP requests, so **flight search requires Chrome or Edge to be installed**:

- Choose the engine at install time: **A = Edge (default) / B = Chrome**, configured via `FLIGHT_MCP_BROWSER`;
- Searches open a **minimized window** by default (visible in the taskbar), never stealing foreground focus;
- Headless mode (`FLIGHT_MCP_HEADLESS=1`) is off by default and is blocked by Ctrip when enabled;
- Flight scraping always uses a **fresh temporary profile** and clears cookies, so flight search is always logged out.

**Hotel search (hotels.ctrip.com) also requires Chrome or Edge** (engine via `HOTEL_MCP_BROWSER`, same default as flight) and **requires a Ctrip login** (guests are redirected to the login page):

- `hotel_ctrip_login` first requests a native user choice, then opens Ctrip's login page directly in a visible browser. Verified cookies are saved for reuse and the original search is retried once. Clients can use MCP elicitation or the documented AskUserQuestion/native-input fallback. **Each search/login closes its browser when finished.** See the [hotel login interaction contract](docs/hotel-login.md).

### Hotel search risk notice (important)

Hotel search drives a real browser that mimics human browsing and scrapes login-gated Ctrip hotel data. **This carries a risk of account bans**:

- Hotel tools are only enabled after explicit consent at install time (`HOTEL_MCP_CONSENT=yes`); **enabling means you accept the risk voluntarily, and the author takes no responsibility**;
- To reduce risk, searches wait a random 30 s – 5 min interval between calls (tunable via `HOTEL_MCP_MIN_DELAY`/`HOTEL_MCP_MAX_DELAY`) and scroll with randomized steps and pauses;
- Flight search is unaffected by hotel login state (independent fresh profile) and does not gain this rate limit.

### Direct and transfer routes

- Train: **direct** and **interline/transfer** are supported (`train_12306_get_interline_tickets`, with the 12306 interline path fixed after the upstream site rework);
- Flight: **direct only** — `flight_flight_ticket_mcp_server_getTransferFlightsByThreePlace` relies on an unstable scraping chain and is hidden from the gateway;
- Hotel: `hotel_ctrip_searchHotels` supports city/landmark, dates, guest counts, price/star/score/room-type filters, and sorting (`smart`/`price_asc`/`distance`/`score_desc`); `hotel_ctrip_login` establishes the login state. See "Hotel search risk notice" above.

### Live browser checks after installation

Run these same examples on Windows, macOS, or Linux:

```sh
node scripts/mcp-test.mjs flight
node scripts/mcp-test.mjs hotel
```

Defaults use Asia/Shanghai: Shanghai → Beijing flights seven days ahead; Wuhan hotels with check-in/check-out seven/nine days ahead. Optional dates: `flight YYYY-MM-DD` or `hotel checkin checkout`. Checks require nonempty meaningful records and matching metadata/counts. Empty results, login requirements and site blocks cannot pass. Flight/hotel rows from `npm run check` establish connectivity only.

Browser discovery checks explicit paths, registered installations, named `shutil.which()` calls and finite common locations before one final unrestricted DrissionPage discovery attempt. Hotel shutdown/recovery supports all three platform branches and preserves login data. See the [runtime guide](docs/browser-runtime.md). Simulated macOS/Linux tests do not establish native execution.

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
        "HOTEL_MCP_CONSENT": "yes",
        "TRAIN_12306_ENTRY": "./12306-mcp/build/index.js",
        "FLIGHT_MCP_PROJECT_ROOT": "./FlightTicketMCP",
        "HOTEL_MCP_PROJECT_ROOT": "./HotelTicketMCP"
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

### Hotel search

Hotel search uses `hotel_ctrip_searchHotels` to scrape Ctrip hotel listings: a Ctrip login is required (see "Hotel search risk notice"), the browser opens minimized by default, and scroll collection uses randomized steps and pauses; searches wait a random 30 s – 5 min interval between calls. A query takes roughly 1–2 minutes (excluding the rate-limit wait).

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
