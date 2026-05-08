# Agent Installation Guide

This guide is for LLM agents. The goal is to install dependencies, configure environment files, build the Travel MCP Gateway, and prepare MCP client configuration for the user.

![Unified Travel MCP Gateway overview](assets/workflow.png)

## Questions for the user

Ask for everything below **before** making changes. **Never paste live secrets** into chat. Do **not** commit `.env`, logs, or machine-local paths.

### MCP host (pick one before configuring clients)

Ask where this MCP will run:

- **OpenCode** / **Cursor** / **Claude Code** / **Other**
- If **Other**: capture the **exact product name**, fetch its official MCP configuration docs (paths, root JSON keys, stdio command shape), then author config—**never guess** incompatible keys (for example, do not paste OpenCode `environment` into hosts that only accept `mcpServers[].env`).

### Runtimes (guide installs when missing)

1. **Node.js and npm**: From the repo root, try `node --version` and `npm --version`. If either fails, ask the user to install **Node.js LTS** from **[https://nodejs.org/](https://nodejs.org/)** (npm ships with it), then **restart the terminal** and re-run these checks.
2. **Python**: Try `python --version`, `python3 --version`, or on Windows `py -V`. If unavailable, ask the user to install Python from **[https://www.python.org/downloads/](https://www.python.org/downloads/)** (enable **Add python.exe to PATH** on Windows), restart the terminal, and verify again.

### Python dependency tooling

3. **Prefer uv**: Recommend **[uv](https://docs.astral.sh/uv/)** for the `FlightTicketMCP` virtual environment—it resolves installs quickly and keeps environments reproducible. Help install uv if needed; otherwise fall back to `pip install -r requirements.txt` or `pip install -e .`.

### API keys (help users obtain keys when absent)

4. **`AMAP_MAPS_API_KEY` (Amap maps MCP)**: If missing, point users to **[Amap MCP Server overview](https://lbs.amap.com/api/mcp-server/summary)**. Reference walk-through video (Chinese): [Bilibili · Amap MCP (BV1qwZqYJEUG)](https://www.bilibili.com/video/BV1qwZqYJEUG/).
5. **`DIDI_MCP_KEY` (DiDi MCP)**: If missing, point users to **[DiDi MCP](https://mcp.didichuxing.com/)**. Reference walk-through video (Chinese): [Bilibili · DiDi MCP (BV1vpb7zaECv)](https://www.bilibili.com/video/BV1vpb7zaECv/).
6. **`VARIFLIGHT_API_KEY` (optional flight fallback)**: If VariFlight fallback is desired but no key exists, ask users to apply via **[VariFlight MCP](https://mcp.variflight.com/)**. Leaving it unset still allows the Ctrip-first path described in FlightTicketMCP.

## 1. Check the runtime

Run these commands from the repository root:

```bash
node --version
npm --version
python --version
```

If the user wants `uv`:

```bash
uv --version
```

If Node.js, npm, or Python is missing, **do not guess paths**: follow the installation guidance in **Questions for the user**, ask the user to restart the terminal, then rerun this section’s checks.

## 2. Install root dependencies

```bash
npm install
```

## 3. Install flight provider dependencies

Stay aligned with **Prefer uv** above: **try uv first**; fall back to pip only when the user insists.

```bash
cd FlightTicketMCP
uv venv
uv pip install -r requirements.txt
cd ..
```

If `uv` is unavailable, use `pip`:

```bash
cd FlightTicketMCP
pip install -r requirements.txt
cd ..
```

Depending on the user's Python environment, this is also valid:

```bash
cd FlightTicketMCP
pip install -e .
cd ..
```

## 3.5 Install and build 12306-mcp sub-project

> ⚠️ **Known issue**: 12306-mcp's `npm run build` uses `run-script-os` for OS-specific prebuild steps. On Windows, `prebuild:win32` runs `del /q /s build\* >nul 2>&1`, which fails on first build when the `build/` directory does not exist (no files match), returning a non-zero exit code and skipping the `tsc` step.
> **Workaround**: Use `npx tsc` directly, ensuring the `build/` directory exists first.

```bash
cd 12306-mcp
npm install
# Ensure build directory exists before running tsc
if (!(Test-Path build)) { New-Item -ItemType Directory -Path build | Out-Null }
npx tsc
cd ..
```

On macOS / Linux, use `npm run build` if it works; otherwise:

```bash
cd 12306-mcp
npm install
mkdir -p build
npx tsc
cd ..
```

## 4. Collect API keys and create environment files

> **MUST collect keys interactively**: Do **not** pause and wait for the user to fill in keys themselves—use the `question` tool to collect each key, and only guide to application links when a key is missing. Then write the collected values to `.env`.

### 4.1 Interactive key collection

Use the `question` tool in this order:

**A. AMAP Maps API Key**

```
question: "Do you have an AMAP (Amap/Gaode) Maps API Key? (⚠ Do not paste it in chat)"
options:
  - "I have a key, I'll enter it" → user inputs the value; write to .env as AMAP_MAPS_API_KEY
  - "I don't have a key, need to apply" → output application links:
    - Official: https://lbs.amap.com/api/mcp-server/summary
    - Video guide: https://www.bilibili.com/video/BV1qwZqYJEUG/
    - Wait for user to obtain a key before continuing
```

**B. DIDI MCP Key**

```
question: "Do you have a DiDi (Didi Chuxing) MCP Key? (⚠ Do not paste it in chat)"
options:
  - "I have a key, I'll enter it" → user inputs the value; write to .env as DIDI_MCP_KEY
  - "I don't have a key, need to apply" → output application links:
    - Official: https://mcp.didichuxing.com/
    - Video guide: https://www.bilibili.com/video/BV1vpb7zaECv/
    - Wait for user to obtain a key before continuing
```

**C. VARIFLIGHT API Key (optional)**

```
question: "Do you have a VariFlight API Key? (optional, for flight data fallback)"
options:
  - "I have a key" → user inputs the value; also write to FlightTicketMCP/.env as VARIFLIGHT_API_KEY
  - "Skip, don't use VariFlight" → skip; flights default to Ctrip web data source
```

### 4.2 Generate .env files

After collecting all keys, create .env files from templates and fill in the values:

Create the root `.env` from the template:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

Then write the user's real values to `.env`:

```dotenv
AMAP_MAPS_API_KEY=user_amap_key
DIDI_MCP_KEY=user_didi_key

# Optional overrides
TRAIN_12306_ENTRY=./12306-mcp/build/index.js
FLIGHT_MCP_PROJECT_ROOT=./FlightTicketMCP
FLIGHT_MCP_PYTHON_COMMAND=python
```

If the user provided a VariFlight key, also copy the template:

Windows PowerShell:

```powershell
Copy-Item FlightTicketMCP/.env.example FlightTicketMCP/.env
```

macOS / Linux:

```bash
cp FlightTicketMCP/.env.example FlightTicketMCP/.env
```

Then set:

```dotenv
VARIFLIGHT_API_KEY=user_variflight_key
```

> **Security**: **Never print real keys** in chat; verify `.env` is in `.gitignore` after writing.

## 5. Build the gateway and verify

```bash
npm run build
```

Verify the server entrypoint starts (confirm 12306-mcp was also built, see §3.5):

```bash
node build/index.js
```

This is a stdio MCP server. It will usually wait for MCP client messages; verify there are no immediate errors like missing dependencies (`Cannot find module .../12306-mcp/build/index.js`), syntax errors, or environment-loading errors. If the 12306-mcp build file is missing, return to §3.5.

Expected startup logs should include at minimum:
- `12306 MCP Server running on stdio`
- `Flight Ticket MCP Server logging initialized`
- `[gateway] travel MCP gateway running on stdio`

## 6. MCP client configuration

After §5, branch on the **MCP host** answer. **OpenCode** uses `mcp.*` with `environment` and `command` as a string array; **Cursor** and **Claude Code** project `.mcp.json` typically use **`mcpServers` + `env`**—do not mix schemas.

Copy-ready placeholders live under **[docs/mcp-client-examples/](mcp-client-examples/)** (see `mcp-client-examples/README.md` for the index and canonical doc links).

### 6.1 Shared rules

- The gateway is a **stdio** server: `node` + `build/index.js`.
- Keep env names aligned with `.env` / host injection: `AMAP_MAPS_API_KEY`, `DIDI_MCP_KEY`, `FLIGHT_MCP_PYTHON_COMMAND`; optional `TRAIN_12306_ENTRY`, `FLIGHT_MCP_PROJECT_ROOT` (see [.env.example](../.env.example)).
- If the host **cwd is not the repo root**, switch `./build/index.js` (and `./12306-mcp`, `./FlightTicketMCP`) to **absolute paths**.

### 6.2 Cursor

1. Read [Cursor · MCP](https://cursor.com/docs/context/mcp).
2. Use [cursor.mcp.json.example](mcp-client-examples/cursor.mcp.json.example) to create or merge **`.cursor/mcp.json`** at the project root (and/or merge user-global config per docs).
3. Replace placeholders (or load secrets from host storage); restart/reload MCP per Cursor guidance.

### 6.3 Claude Code

1. Read [Connect Claude Code to tools via MCP](https://docs.claude.com/en/docs/claude-code/mcp.md).
2. Copy [claude-code.mcp.json.example](mcp-client-examples/claude-code.mcp.json.example) to repo-root **`.mcp.json`**, or run `claude mcp add --transport stdio ... --scope project` (sample command in [mcp-client-examples/README.md](mcp-client-examples/README.md)).
3. Respect approval flows and `--` option ordering from the docs.
4. Replace placeholders like §6.2.

### 6.4 OpenCode

1. OpenCode **does not** use the Desktop-style root **`mcpServers`** block. Use **`mcp.<serverId>`** with **`environment`** (not `env`) and **`command`** as a **string array**—see [.opencode/opencode.json](../.opencode/opencode.json).
2. Merge [opencode.mcp.fragment.json](mcp-client-examples/opencode.mcp.fragment.json) under the user’s **`mcp` object**.
3. Optionally set `$schema` to `https://opencode.ai/config.json`. Replace placeholders like §6.2.

### 6.5 Other hosts

1. Search official docs using the **exact product name** the user provided.
2. Verify config path, root JSON shape, and stdio fields before editing files.
3. Deliver minimal working snippets for the user to paste locally—never commit live secrets to this repo.

## 7. Troubleshooting

For MCP connection, authentication, schema, or response-format issues:

1. Check that `.env` and the client config use the same variable names.
2. Check that `npm run build` succeeds.
3. Check that `FlightTicketMCP` dependencies are installed.
4. For Amap, DiDi, and VariFlight key issues, consult `.opencode/skills/error-processing/mcp-error-references.json`.
5. Never print full environment dumps, tokens, real secrets, or private account data.

## 8. Post-deployment smoke test

After configuration is complete, verify the four domains (train / flight / map / taxi) are working. Use the gateway MCP tools for the following tests.

### 8.1 Get today's date

Call `travel-mcp-gateway_train_12306_get_current_date` (or `travel-mcp-gateway_flight_flight_ticket_mcp_server_getCurrentDate`) to retrieve the current date in `yyyy-MM-dd` format.

### 8.2 Test train ticket search (train domain)

Query high-speed trains from **Shanghai** to **Beijing** for today:

- Tool: `travel-mcp-gateway_train_12306_get_tickets`
- Params: `date` = today, `fromStation` = "上海", `toStation` = "北京", `trainFilterFlags` = "G", `limitedNum` = 3
- Format: `text`

Expected: A list of high-speed train options. If it fails or `station_code` resolution has issues, check `TRAIN_12306_ENTRY` in `.env` points to the correct `12306-mcp/build/index.js`.

### 8.3 Test flight search (flight domain)

Query flights from **Shanghai** to **Beijing** for today:

- Tool: `travel-mcp-gateway_flight_flight_ticket_mcp_server_searchFlightRoutes`
- Params: `departure_city` = "上海", `destination_city` = "北京", `departure_date` = today
- Format: `text`

Expected: A list of flights. If it fails, check `FlightTicketMCP/.venv` exists and `FLIGHT_MCP_PYTHON_COMMAND` is correct.

### 8.4 Test map geocoding (map domain)

Call `travel-mcp-gateway_map_amap_maps_geo` to geocode "北京南站":

- Params: `address` = "北京南站", `city` = "北京"

Expected: Latitude/longitude coordinates. If it fails, check that `AMAP_MAPS_API_KEY` is valid.

### 8.5 Report results

Report the four test results in this format:

```
| Domain | Tool                          | Status | Notes              |
|--------|-------------------------------|--------|--------------------|
| train  | get_tickets (Shanghai→Beijing) | ✅/❌  | N trains found     |
| flight | searchFlightRoutes (Shanghai→Beijing) | ✅/❌ | N flights found    |
| map    | maps_geo (Beijing South)     | ✅/❌  | coords: lng, lat   |
```

If all domains pass, the installation was successful. If any domain fails, consult §7.
