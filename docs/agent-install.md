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
6. **Browser engine (flight + hotel scraping)**: Ctrip's anti-bot WAF requires a visible browser. At install time, ask the user to pick **A = Edge (default) / B = Chrome**, or provide a custom browser path (see item C in §4.1). The choice applies to both flight and hotel scraping.
7. **Hotel search risk consent (important)**: Hotel search scrapes login-gated Ctrip hotel data while mimicking human browsing, which **carries an account-ban risk**. You must explicitly ask the user whether to enable it (see item D in §4.1); **enabling means the user accepts the risk voluntarily and the author takes no responsibility**.

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

## 3.6 Install hotel provider dependencies

Same approach as the flight provider: **uv first**, pip only when the user insists.

```bash
cd HotelTicketMCP
uv venv
uv pip install -r requirements.txt
cd ..
```

If `uv` is unavailable, use `pip`:

```bash
cd HotelTicketMCP
pip install -r requirements.txt
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

> **MUST collect keys interactively**: Do **not** pause and wait for the user to fill in keys themselves—use the `question` tool to collect each key, and only guide to application links when a key is missing. Then write the collected values to `.env`. Do not proceed to §8 functional testing until both keys are collected (otherwise the map/taxi domains FAIL because the keys are empty).

### 4.1 Interactive key collection

Use the `question` tool in this order:

> **`question` tool constraints**: One call can contain at most 4 questions; **every question needs at least 2 options** (single-option questions are rejected outright—do not construct single-option questions, and do not invent filler options); **ask all questions in the user's language**. Key values are free text—have the user enter them via the question's built-in **Other** option; once received, write keys to `.env` and **never echo real keys in replies**.

**A. AMAP Maps API Key**

```
question: "Do you have an AMAP (Amap/Gaode) Maps API Key? (If you have one, choose Other and paste the key; ⚠ do not paste it in chat)"
options:
  - "I have a key, I'll enter it" → user inputs the value; write to .env as AMAP_MAPS_API_KEY
  - "I don't have a key, need to apply" → output application links:
    - Official: https://lbs.amap.com/api/mcp-server/summary
    - Video guide: https://www.bilibili.com/video/BV1qwZqYJEUG/
    - Wait for user to obtain a key before continuing
```

**B. DIDI MCP Key**

```
question: "Do you have a DiDi (Didi Chuxing) MCP Key? (If you have one, choose Other and paste the key; ⚠ do not paste it in chat)"
options:
  - "I have a key, I'll enter it" → user inputs the value; write to .env as DIDI_MCP_KEY
  - "I don't have a key, need to apply" → output application links:
    - Official: https://mcp.didichuxing.com/
    - Video guide: https://www.bilibili.com/video/BV1vpb7zaECv/
    - Wait for user to obtain a key before continuing
```

**C. Browser engine choice (flight + hotel scraping, A/B)**

```
question: "Which browser engine should flight/hotel scraping use? (Ctrip anti-bot requires a visible browser; one choice covers both)"
options:
  - "A. Edge (default, ships with Windows)" → set FLIGHT_MCP_BROWSER=edge and HOTEL_MCP_BROWSER=edge
  - "B. Chrome" → set FLIGHT_MCP_BROWSER=chrome and HOTEL_MCP_BROWSER=chrome
  - "Custom path" → set FLIGHT_MCP_BROWSER_PATH and HOTEL_MCP_BROWSER_PATH=<absolute browser path>
Note: searches open a minimized window (taskbar-visible, no foreground focus); headless mode is blocked by Ctrip and disabled by default.
```

**D. Hotel search risk consent (important, must ask)**

```
question: "Enable Ctrip hotel search (hotel domain)? ⚠ This feature mimics human browsing and scrapes login-gated Ctrip hotel data, which carries a risk of account bans. Enabling it means you understand and voluntarily accept the risk; the author takes no responsibility."
options:
  - "Enable, I accept the risk" → set HOTEL_MCP_CONSENT=yes
  - "Disable" → do not set HOTEL_MCP_CONSENT (or set no); hotel tools return CONSENT_REQUIRED
Note: hotel searches wait a random 30s–5min between calls to reduce risk. Hotel data requires a Ctrip login; when a search returns LOGIN_REQUIRED, call hotel_ctrip_login so the user can log in.
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
# Browser engine: A=edge (default) / B=chrome (shared by flight and hotel)
FLIGHT_MCP_BROWSER=edge
HOTEL_MCP_PROJECT_ROOT=./HotelTicketMCP
HOTEL_MCP_PYTHON_COMMAND=python
HOTEL_MCP_BROWSER=edge
# Custom browser path (optional, takes precedence over the engine vars)
# FLIGHT_MCP_BROWSER_PATH=C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe
# HOTEL_MCP_BROWSER_PATH=C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe
# Headless mode (not recommended: blocked by Ctrip whaleguard)
# FLIGHT_MCP_HEADLESS=1
# HOTEL_MCP_HEADLESS=1
# ⚠ Hotel search risk consent (uncomment and set yes only if the user chose "Enable" in §4.1 D)
# HOTEL_MCP_CONSENT=yes
# Random interval between hotel searches in seconds (default 30~300)
# HOTEL_MCP_MIN_DELAY=30
# HOTEL_MCP_MAX_DELAY=300
```

> **Windows path note**: relative paths in gateway-injected env vars resolve against the **child process cwd** (e.g. a relative `FLIGHT_MCP_PYTHON_COMMAND` is joined under `FLIGHT_MCP_PROJECT_ROOT`). Use **absolute paths** for `FLIGHT_MCP_PYTHON_COMMAND`, `HOTEL_MCP_PYTHON_COMMAND`, `TRAIN_12306_ENTRY`, `FLIGHT_MCP_BROWSER_PATH`, and `HOTEL_MCP_BROWSER_PATH` (e.g. `C:/Users/xxx/.../HotelTicketMCP/.venv/Scripts/python.exe`).

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
- `Hotel Ticket MCP Server starting...` (expected when §4.1 D was enabled)
- `[gateway] travel MCP gateway running on stdio`

## 6. MCP client configuration

After §5, branch on the **MCP host** answer. **OpenCode** uses `mcp.*` with `environment` and `command` as a string array; **Cursor** and **Claude Code** project `.mcp.json` typically use **`mcpServers` + `env`**—do not mix schemas.

Copy-ready placeholders live under **[docs/mcp-client-examples/](mcp-client-examples/)** (see `mcp-client-examples/README.md` for the index and canonical doc links).

### 6.1 Shared rules

- The gateway is a **stdio** server: `node` + `build/index.js`.
- Keep env names aligned with `.env` / host injection: `AMAP_MAPS_API_KEY`, `DIDI_MCP_KEY`, `FLIGHT_MCP_PYTHON_COMMAND`; optional `TRAIN_12306_ENTRY`, `FLIGHT_MCP_PROJECT_ROOT`, `HOTEL_MCP_PYTHON_COMMAND`, `HOTEL_MCP_PROJECT_ROOT`, `HOTEL_MCP_CONSENT` (see [.env.example](../.env.example)). Note: inject `HOTEL_MCP_CONSENT=yes` **only after the user accepted the risk terms in §4.1 D**; otherwise keep `no` (hotel tools return `CONSENT_REQUIRED`).
- If the host **cwd is not the repo root**, switch `./build/index.js` (and `./12306-mcp`, `./FlightTicketMCP`, `./HotelTicketMCP`) to **absolute paths**.

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
3. Check that `FlightTicketMCP` and `HotelTicketMCP` dependencies are installed.
4. For Amap and DiDi key issues, consult `.opencode/skills/error-processing/mcp-error-references.json`.
5. For flight failures, call `gateway_get_config` first to inspect provider connectivity and browser strategy (engine, headless flag, path override). Common browser-related causes: no Chrome/Edge installed, wrong `FLIGHT_MCP_BROWSER` engine, or `FLIGHT_MCP_HEADLESS=1` being blocked by Ctrip.
6. Hotel search returning `CONSENT_REQUIRED`: the user has not consented to the risk terms (`.env` `HOTEL_MCP_CONSENT` is not `yes`); re-ask per §4.1 D.
7. Hotel search returning `LOGIN_REQUIRED`: no login state and cookie injection failed. **Stop the current test and notify the user to log in**: run `node scripts/mcp-test.mjs login` (calls `hotel_ctrip_login`, which opens a visible browser window), and have the user log in manually (QR or password; waits up to 14 minutes by default, adjustable via `HOTEL_MCP_LOGIN_TIMEOUT`). **The login window stays open until login completes or times out — do not close the window or kill the process hosting it during this period**, or the user cannot finish logging in. Cookies are saved automatically on success, and the `login` mode re-runs a hotel search to verify; after that no further login is needed (searches inject the saved cookies).
8. Never print full environment dumps, tokens, real secrets, or private account data.

## 8. Post-deployment smoke test

After configuration is complete, verify the five domains (train / flight / hotel / map / taxi) are working. **Do not write a new test script.** Use the repo script `scripts/mcp-test.mjs` (same command on Windows, macOS, and Linux). From the repository root:

```bash
npm run check
```

That runs `health` (`gateway_health_check`; the process exits 1 if any probe is FAIL). Other modes:

```bash
node scripts/mcp-test.mjs config
node scripts/mcp-test.mjs train
node scripts/mcp-test.mjs flight
node scripts/mcp-test.mjs hotel
node scripts/mcp-test.mjs login
node scripts/mcp-test.mjs map
node scripts/mcp-test.mjs taxi
```

`flight` and `hotel` open a visible browser and usually take several minutes. The script reads the root `.env` and does not print secrets. Secret values are replaced with `[redacted]`; the user home directory and repository absolute path are replaced with `<home>` and `<repo>`. `config` calls `gateway_get_config`, which reports secrets only as set/unset and paths only relative to the repository. Do not commit script output. Manual per-domain checks follow.

> Tool naming: gateway tool names use the `{domain}_{provider}_{tool}` form (e.g. `train_12306_get_tickets`); hosts may display an extra prefix (`mcp__travel-mcp-gateway__` in Claude Code). Use the `gatewayName` values returned by `gateway_list_retained_tools`.

### 8.1 Get today's date

Call `train_12306_get_current_date` (or `flight_flight_ticket_mcp_server_getCurrentDate`) to retrieve the current date in `yyyy-MM-dd` format.

### 8.2 Test train ticket search (train domain)

Query high-speed trains from **Shanghai** to **Beijing** for today:

- Tool: `train_12306_get_tickets`
- Params: `date` = today, `fromStation` = "上海", `toStation` = "北京", `trainFilterFlags` = "G", `limitedNum` = 3, `format` = "text"

Expected: A list of high-speed train options. If it fails or `station_code` resolution has issues, check `TRAIN_12306_ENTRY` in `.env` points to the correct `12306-mcp/build/index.js`. Interline/transfer queries are available via `train_12306_get_interline_tickets` (path fixed after the 12306 site rework).

### 8.3 Test flight search (flight domain)

Query flights from **Shanghai** to **Beijing** for today:

- Tool: `flight_flight_ticket_mcp_server_searchFlightRoutes`
- Params: `departure_city` = "上海", `destination_city` = "北京", `departure_date` = today, `data_source_preference` = "default" (or `auto`; there is **no `format` parameter**); optional hour filters: `earliestStartTime` / `latestStartTime` (0-23) / `earliestArrivalTime` / `latestArrivalTime`
- Returns: JSON text with `status`, `flight_count`, `flights`, `formatted_output`, etc.

Expected: A list of flights (takes 1–8 minutes; a **minimized browser window** appears briefly in the taskbar without stealing focus). If it fails, check: Chrome/Edge installed, `FLIGHT_MCP_BROWSER` engine choice, `FLIGHT_MCP_HEADLESS` must not be 1 (blocked by Ctrip), `FlightTicketMCP/.venv` exists, and `FLIGHT_MCP_PYTHON_COMMAND` is correct. Note: the flight transfer tool is intentionally absent.

### 8.4 Test hotel search (hotel domain)

Query future dates for Wuhan hotels (first search has no interval wait):

- Tool: `hotel_ctrip_searchHotels`
- Params: `city` = "武汉", `checkin`/`checkout` = today +7/+9 days, `limit` = 5

Expected: A hotel list (`status: success`, `count`, `hotels[]`; takes ~1–2 minutes with a minimized browser window). If it returns `CONSENT_REQUIRED`, check `HOTEL_MCP_CONSENT=yes` in `.env` and the §4.1 D consent flow; if `LOGIN_REQUIRED`, **stop the test and notify the user to log in** — run `node scripts/mcp-test.mjs login`, which opens a visible browser window and waits for the user (up to 14 minutes by default); **do not close the window or interrupt the process** during this period. On success the mode automatically re-runs a hotel search to verify (login state is saved for reuse). Note: hotel searches are separated by a random 30s–5min interval, so a second consecutive test will wait.

### 8.5 Test map geocoding (map domain)

Call `map_amap_maps_geo` to geocode "北京南站":

- Params: `address` = "北京南站", `city` = "北京"

Expected: Latitude/longitude coordinates. If it fails, check that `AMAP_MAPS_API_KEY` is valid.

### 8.6 Test taxi (taxi domain)

Call in order:

1. `taxi_didi_maps_textsearch`: params `keywords` = "北京南站", `city` = "北京" (both required)
2. `taxi_didi_taxi_estimate`: params `from_name`/`from_lng`/`from_lat`/`to_name`/`to_lng`/`to_lat` — coordinates MUST come from the textsearch result in step 1, never assumed

Expected: fare estimates for multiple ride types (estimate only — no booking).

### 8.7 Report results

Report the test results in this format:

```
| Domain | Tool                          | Status | Notes              |
|--------|-------------------------------|--------|--------------------|
| train  | get_tickets (Shanghai→Beijing) | ✅/❌  | N trains found     |
| flight | searchFlightRoutes (Shanghai→Beijing) | ✅/❌ | N flights found    |
| hotel  | searchHotels (Wuhan)          | ✅/❌  | N hotels found     |
| map    | maps_geo (Beijing South)     | ✅/❌  | coords: lng, lat   |
| taxi   | maps_textsearch (Beijing South) | ✅/❌ | N places found    |
```

If all domains pass, the installation was successful. If any domain fails, consult §7.
