# Travel MCP Gateway

**Languages:** [中文](README_ZH.md)

A single MCP server that aggregates travel-related downstream MCPs in China: **train** (12306), **flight** (FlightTicketMCP), **map** (official Amap MCP), and **taxi fare estimate** (DiDi). Clients connect to one stdio gateway; providers are grouped under fixed domains: `train`, `flight`, `map`, `taxi`.

## Features

- One MCP entrypoint over **stdio** (Cursor, Claude Desktop, OpenCode, and similar clients)
- **Flight** search (default `auto`): tries **Ctrip** flight listings first (web scrape); if that fails or scrape dependencies are missing, it can fall back to **VariFlight** when `VARIFLIGHT_API_KEY` is set in `FlightTicketMCP/.env`
- Add new providers by domain registries under `src/domains/` (see [docs/extending.md](docs/extending.md))

## Prerequisites

- **Node.js** (npm)
- **Python** environment for `FlightTicketMCP` (subprocess)

## Let an Agent Install It

Copy this into your LLM agent session (Cursor, Claude Desktop, OpenCode, or similar). The agent will install dependencies, configure keys, build the project, and prepare MCP client config:

```text
Install and configure Travel MCP Gateway by following the instructions here:
https://raw.githubusercontent.com/Ytang520/China-Travel-Planning-MCPs-All-in-One/main/docs/agent-install.md
```

You can also read the [Agent Installation Guide](docs/agent-install.md).

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
| `FLIGHT_MCP_PYTHON_COMMAND` | Python executable for FlightTicketMCP (default: `python`) |
| `TRAIN_12306_ENTRY` | Optional path to 12306 MCP entry script |
| `FLIGHT_MCP_PROJECT_ROOT` | Optional path to `FlightTicketMCP` root |

Additional flight-related variables (including `VARIFLIGHT_API_KEY` for the VariFlight fallback) are documented in `FlightTicketMCP/.env.example`; apply for access via [VariFlight MCP](https://mcp.variflight.com/).

## MCP client configuration

```json
{
  "mcpServers": {
    "travel-mcp-gateway": {
      "command": "node",
      "args": ["./build/index.js"],
      "env": {
        "AMAP_MAPS_API_KEY": "YOUR_AMAP_MAPS_API_KEY",
        "DIDI_MCP_KEY": "YOUR_DIDI_MCP_KEY",
        "FLIGHT_MCP_PYTHON_COMMAND": "python"
      }
    }
  }
}
```

Adjust `args` to an absolute path if your client does not use the repo root as cwd.

## OpenCode

Example: [.opencode/opencode.json](.opencode/opencode.json). Replace placeholders with your real keys.

The project-level error-processing skill lives at [.opencode/skills/error-processing/SKILL.md](.opencode/skills/error-processing/SKILL.md), with MCP troubleshooting references in [.opencode/skills/error-processing/mcp-error-references.json](.opencode/skills/error-processing/mcp-error-references.json).

## Other: DiDi taxi fare estimate chain

For fare estimation you **must** call tools in this order:

1. `taxi_didi_maps_textsearch`
2. `taxi_didi_taxi_estimate`

Coordinates for `estimate` must come from DiDi `maps_textsearch` (keys and API details: [DiDi MCP](https://mcp.didichuxing.com/)). **Do not use coordinates returned by the Amap MCP.**

For geocoding, POI, routing, weather, and other **non–fare-estimate** map tasks, prefer **`map/amap`**. See [Amap MCP Server overview](https://lbs.amap.com/api/mcp-server/summary).

## Documentation

- **Agent installation guide:** [docs/agent-install.md](docs/agent-install.md) (English) · [docs/agent-install.zh.md](docs/agent-install.zh.md) (中文)
- **Tool list, layout, provider extension, OpenCode, and error-processing skill:** [docs/extending.md](docs/extending.md) (English) · [docs/extending.zh.md](docs/extending.zh.md) (中文)
