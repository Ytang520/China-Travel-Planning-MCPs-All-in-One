# Agent Installation Guide

This guide is for LLM agents. The goal is to finish Travel MCP Gateway dependency installation, environment setup, and build verification in this folder, then give the user MCP client configuration they can copy.

## Steps:

### 1. Check the runtime

Confirm the following with the user before starting. **The agent must not echo live secrets. Do not commit `.env`, logs, or machine-local absolute paths. The user may supply keys through a local command, interactive input, or a question tool.**

#### (1) MCP host (confirm first)

Before installation, use **AskUserQuestion** (or the host's equivalent `question` tool) to ask **1** question about which app will run this MCP (§7 branches on that answer):

- **OpenCode** / **Cursor** / **Claude Code** / **Other**
- If **Other**: ask for the **exact product name**. Fetch that product's **official MCP configuration docs** (config path, root field names, and the `stdio` `command`/`args` shape) before writing config. **Do not guess** (for example, do not write OpenCode's `environment` / `command` array into a host that only accepts `mcpServers` + `env`).

#### (2) Check the runtime

From the repository root:

```bash
node --version
npm --version
python --version
```

If the user wants `uv` for Python:

```bash
uv --version
```

If Node.js, npm, or Python is missing, **do not guess install paths**. Follow "Official install pointers when something is missing" below, ask the user to reopen the terminal, then rerun the commands in this section.

Official install pointers when something is missing:

- **Node.js and npm**: From the repo root, try `node --version` and `npm --version`. If either command is missing or errors, point the user to the **[Node.js website](https://nodejs.org/)** to install the **LTS** build (npm is included). After installation, **reopen the terminal** and verify again.
- **Python**: Try `python --version` (some environments use `py -V` or `python3 --version`). If unavailable, point the user to the **[Python downloads page](https://www.python.org/downloads/)**. On Windows, enable **Add python.exe to PATH**. Reopen the terminal and verify again.
- **Prefer uv**: Recommend **[uv](https://docs.astral.sh/uv/)** to create the virtual environment and install `FlightTicketMCP` dependencies. Help install uv from the official docs if it is missing. If the user insists on the traditional path, use `pip install -r requirements.txt` or `pip install -e .`.

#### (3) Install the troubleshooting skill for the target host

Reuse the **MCP host** confirmed above. The target is the app where the user will use this MCP, which may differ from the agent performing the install. Do not ask again when the choice is already clear. Finish this step after Node.js is available and before `npm install`, so later install failures can use the skill.

Determine the **agent working project root**: it defaults to this MCP repository. If the user will use the MCP from another project, use that project directory. Ask only when the context does not determine it. Paths in the table below are relative to the agent working project. MCP source, `.venv`, and `.env` stay in this repository.

| User choice | `--agent` value | Skill directory |
| --- | --- | --- |
| OpenCode | `opencode` | `.opencode/skills/error-processing/` |
| Claude Code | `claude-code` | `.claude/skills/error-processing/` |
| Cursor | `cursor` | `.cursor/skills/error-processing/` |

From the MCP repository root, run **one** command for the selected host. Do not install every host by default:

```sh
node scripts/install-agent-skill.mjs --agent opencode
node scripts/install-agent-skill.mjs --agent claude-code
node scripts/install-agent-skill.mjs --agent cursor
```

If the agent working project is another directory, add `--project-root "<absolute path of the agent working project>"` to the chosen command. When omitted, the destination is always the MCP repository that contains the installer, not the shell's current directory. That directory must already exist. The installer needs no npm dependencies and does not write to a user-global directory.

The installer copies `SKILL.md` and `mcp-error-references.json` from the [shared template](../skill-templates/error-processing/SKILL.md). Identical content can be installed again. Different content returns `conflict` and a nonzero exit code and leaves the existing files in place. Review the diff, keep user customizations, and merge by hand. Do not force an overwrite. A same-named skill in another directory is listed in `otherCopies`; check which copy the host actually discovers, and do not delete it automatically. Resolve an unknown host, an invalid template, or a path conflict before continuing.

Add `--check` to the same command for a read-only check: `current` means the files match the template; `missing` / `conflict` exit 1. A hand-customized skill that differs from the template keeps reporting `conflict`; that does not mean the customized skill is unusable. `hostDiscovery: not-verified` means the script did not verify that the host loaded the skill.

After the files are installed, check in the **target host and target working project** that `error-processing` can be discovered and read:

- OpenCode: inspect available skills and refresh the session if that host version requires it. See [OpenCode Skills](https://opencode.ai/docs/skills/).
- Claude Code: check `/error-processing`. If a new directory is not discovered, use `/reload-skills` as documented. See [Claude Code Skills](https://code.claude.com/docs/en/skills).
- Cursor: check Customize → Skills. See [Cursor Skills](https://cursor.com/docs/skills).

If the target host cannot be started now, report "files installed; host discovery still pending." Do not claim the skill is loaded. Installing the skill does not run MCP functional tests. For **Other**, look up that product's official **skills** support and project directory. Deploy the template under its rules only after support is confirmed. If it cannot be confirmed, report that the skill is not installed for that host. Do not guess a directory or fall back to OpenCode.

This skill tells the agent to pick references from the error context and the reference descriptions, then reply with "error summary / checks performed / diagnosis / next step." It does not include a vector search engine. The gateway does not run the skill automatically and does not save a handling document.

### 2. Install root dependencies

```bash
npm install
```

### 3. Install flight and hotel Python dependencies

Both Python providers use the repository-root `.venv`. Python must be 3.11+. Reuse a working environment when one exists; otherwise create it from the repository root:

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

### 4. Install and build the 12306-mcp subproject

> ⚠️ **Known issue**: 12306-mcp's `npm run build` uses `run-script-os` to run an OS-specific prebuild script. On Windows, `prebuild:win32` runs `del /q /s build\* >nul 2>&1`. When `build/` does not exist (a first build), no files match and the command can exit nonzero, which skips the later `tsc` step.
> **Workaround**: Run `npx tsc` directly, and make sure `build/` exists.

```bash
cd 12306-mcp
npm install
# Ensure the build directory exists before tsc
if (!(Test-Path build)) { New-Item -ItemType Directory -Path build | Out-Null }
npx tsc
cd ..
```

On macOS / Linux, `npm run build` is enough when it succeeds. If the same problem appears, run:

```bash
cd 12306-mcp
npm install
mkdir -p build
npx tsc
cd ..
```

### 5. Collect API keys and other settings, then write the environment file

> **Collect keys**: Prefer the `question` tool, one item at a time, and give application links when a key is missing. The user may also supply a key through a local command or interactive input. Reuse a valid local configuration instead of asking again. After the user authorizes it, finish the `.env` setup. Do not keep switching write methods because a tool call might be recorded. Configure both keys before the full health check and the §8 functional tests (otherwise the map/taxi domains FAIL because the keys are empty).

### 5.1 Interactive collection

Then use the `question` tool to ask the following 4 questions, in order:

**A. AMAP Maps API Key**

```
question: "你有高德地图 MCP 的 API Key 吗？（可使用本问题的自由文本输入、交互输入或本地命令提供；Agent 不会主动回显密钥）"
options:
  - "我有 Key，我会输入" → after the user provides the value, write it to AMAP_MAPS_API_KEY in .env
  - "我没有 Key，需要申请" → output the application links:
    - Official: https://lbs.amap.com/api/mcp-server/summary
    - Video: https://www.bilibili.com/video/BV1qwZqYJEUG/
    - Continue after the user has the key
```

**B. DIDI MCP Key**

```
question: "你有滴滴出行 MCP 的 API Key 吗？（可使用本问题的自由文本输入、交互输入或本地命令提供；Agent 不会主动回显密钥）"
options:
  - "我有 Key，我会输入" → after the user provides the value, write it to DIDI_MCP_KEY in .env
  - "我没有 Key，需要申请" → output the application links:
    - Official: https://mcp.didichuxing.com/
    - Video: https://www.bilibili.com/video/BV1vpb7zaECv/
    - Continue after the user has the key
```

**C. Browser engine (shared by flight and hotel scraping)**

```
question: "选择航班/酒店抓取使用的浏览器内核？（携程反爬需要可见浏览器；航班与酒店共用该选择）"
options:
  - "A. Edge（默认，Windows 自带即可）" → write FLIGHT_MCP_BROWSER=edge and HOTEL_MCP_BROWSER=edge
  - "B. Chrome" → write FLIGHT_MCP_BROWSER=chrome and HOTEL_MCP_BROWSER=chrome
  - "自定义路径" → write FLIGHT_MCP_BROWSER_PATH and HOTEL_MCP_BROWSER_PATH=<absolute browser path>
Note: queries open a minimized window (visible in the taskbar, without taking foreground focus). Headless mode is blocked by Ctrip and stays off by default.
```

**D. Hotel search risk consent (required)**

```
question: "是否启用携程酒店搜索（hotel 域）？⚠ 该功能通过浏览器模拟真人浏览并抓取需要登录的携程酒店数据，存在账号被封禁的风险。选择启用即表示你已了解并自愿承担该风险，作者概不负责。"
options:
  - "启用，我自愿承担风险" → write HOTEL_MCP_CONSENT=yes
  - "不启用" → do not write HOTEL_MCP_CONSENT (or write no). Hotel tools then return CONSENT_REQUIRED
Note: hotel searches wait a random 15s–3min between calls. On LOGIN_REQUIRED, call hotel_ctrip_login and let the native MCP question ask whether to open the login page. On USER_INTERACTION_REQUIRED, call AskUserQuestion or the host's native question tool, wait for the real answer, then pass user_action. See [Hotel login interaction](hotel-login.md).
```

### 5.2 Create the .env file

After every key is collected, create the file from the template and fill in the real values.

Create the root `.env` from the template.

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

Then write the user's real values into `.env`:

```dotenv
AMAP_MAPS_API_KEY=user_amap_key
DIDI_MCP_KEY=user_didi_key

# Optional overrides
TRAIN_12306_ENTRY=./12306-mcp/build/index.js
FLIGHT_MCP_PROJECT_ROOT=./FlightTicketMCP
# FLIGHT_MCP_PYTHON_COMMAND=/absolute/path/to/python
# Browser engine: A=edge (default) / B=chrome (shared by flight and hotel)
FLIGHT_MCP_BROWSER=edge
HOTEL_MCP_PROJECT_ROOT=./HotelTicketMCP
# HOTEL_MCP_PYTHON_COMMAND=/absolute/path/to/python
HOTEL_MCP_BROWSER=edge
# Custom browser path (optional; takes precedence over FLIGHT_MCP_BROWSER / HOTEL_MCP_BROWSER)
# FLIGHT_MCP_BROWSER_PATH=/absolute/path/to/msedge.exe
# HOTEL_MCP_BROWSER_PATH=/absolute/path/to/msedge.exe
# Headless mode (not recommended: blocked by Ctrip whaleguard)
# FLIGHT_MCP_HEADLESS=1
# HOTEL_MCP_HEADLESS=1
# ⚠ Hotel search risk consent (uncomment and set yes only when §5.1 D chose "enable"; otherwise the hotel domain stays unavailable)
# HOTEL_MCP_CONSENT=yes
# Random interval between hotel searches, in seconds (default 15–180)
# HOTEL_MCP_MIN_DELAY=15
# HOTEL_MCP_MAX_DELAY=180
```

> Project directories and the train entry resolve against the repository. Interpreter paths resolve against the provider directory. Windows uses `.venv/Scripts/python.exe`; macOS/Linux uses `.venv/bin/python`. Prefer absolute paths for explicit overrides.

> **Key input and output**: The user may provide API keys through a local command, interactive input, or a question tool. The agent may use an authorized key and write it to local configuration. The agent must not echo a real key in a natural-language reply, example, debug output, or log. Configuration checks show only `set/unset` or `[redacted]`. A value the user typed, and the handoff required to finish an authorized configuration, is not a prohibited echo. Environment variables, heredocs, and file-edit tools do not guarantee that the host will leave their contents unrecorded. Do not describe the question tool, or any write method, as an unrecorded channel. Confirm configuration with a redacted check. Do not print the whole `.env`.

### 6. Build the root gateway and verify

Confirm that 12306-mcp was built in §4 and that both keys were configured in §5, then run from the repository root:

```sh
npm run build
```

Finish the build first. Run the connectivity checks below after the user chooses testing in §8. Reuse an existing explicit testing authorization.

```sh
node scripts/mcp-test.mjs health
node scripts/mcp-test.mjs config
```

The test script reads the root `.env`, passes that configuration to the gateway, and keeps stdin connected through initialization and tool calls before closing the connection. Every domain in `health` should be PASS. Any FAIL makes the script exit 1. `config` checks redacted configuration, providers, and tool info. Flight and hotel health checks only verify connectivity. Browser queries still need the real searches in §8.

`node build/index.js` by itself reads process environment variables and does not load the root `.env`. The host must inject those variables when it starts the server. Do not treat `node build/index.js < /dev/null`, a background run that closes stdin, or a fixed 20-second wait followed by grepping startup logs as acceptance. stdin EOF on stdio starts a normal shutdown. If that happens during provider initialization, initialization is cancelled. Exit code 0 in that case only means the process exited normally.

| Diagnostic | Meaning and next step |
| --- | --- |
| `shutting down: host stdin EOF`, then `initialization cancelled` | The client closed the input stream. Verify with the MCP test script above. |
| `failed to connect provider` / `Connection closed`, without an intentional session close | Read the child process stderr and the failure stage. This error alone does not prove a network fault. |
| A real `spawn ENOENT`, a missing module, or a syntax error | Check the start command, entrypoint, and dependencies. A stack that merely contains `cross-spawn/lib/enoent.js` is not itself ENOENT. |
| DNS, TLS, HTTP, or request timeout errors | Check that upstream and the network. 12306 also fetches station data at startup. |

Service logs go to stderr. stdout carries MCP messages. Logs help diagnosis; matching a fixed startup sentence is not required. A provider printing its own startup line does not mean the MCP handshake finished. If `12306-mcp/build/index.js` is missing, go back to §4 and build it.

### 7. MCP client configuration

After the §6 build, follow the **§1 (1) MCP host** choice. **OpenCode** uses `mcp` / `environment` / `command` (an array). **Cursor** and **Claude Code** (`.mcp.json`) usually use **`mcpServers` + `env`**. Do not mix the two shapes.

Copy-ready placeholders are in **[docs/mcp-client-examples/](mcp-client-examples/)** (same directory as this file; `mcp-client-examples/README.md` has the index and official doc links).

#### 7.1 Shared rules

- Project-level client config belongs in the agent working project confirmed in **§1 (3)** (for example `.mcp.json` or `.cursor/mcp.json` inside it). If that project is not the MCP repository, point at the repository entry and providers with absolute paths.
- The gateway is a **stdio** process: `node` + `build/index.js`.
- Environment variable names must match `.env` and the host injection: `AMAP_MAPS_API_KEY`, `DIDI_MCP_KEY`, `FLIGHT_MCP_PYTHON_COMMAND`; optional `TRAIN_12306_ENTRY`, `FLIGHT_MCP_PROJECT_ROOT`, `HOTEL_MCP_PYTHON_COMMAND`, `HOTEL_MCP_PROJECT_ROOT`, `HOTEL_MCP_CONSENT` (see [.env.example](../.env.example)). Inject `HOTEL_MCP_CONSENT=yes` **only after the user accepted the risk terms in §5.1 D**. Otherwise keep `no` (hotel tools return `CONSENT_REQUIRED`).
- If the host starts the MCP process with a **cwd other than the repository root**, change `./build/index.js` (and the related `./12306-mcp`, `./FlightTicketMCP`, `./HotelTicketMCP` paths) to **absolute paths**.

#### 7.2 Per agent host

(1) Cursor:

(a) Read the official docs: [Cursor · MCP](https://cursor.com/docs/context/mcp).
(b) Create or merge **`.cursor/mcp.json`** at the project root from [cursor.mcp.json.example](mcp-client-examples/cursor.mcp.json.example) (or merge it with the user-global config; precedence follows the docs).
(c) Replace placeholder keys (or let the host read them from secure storage). Restart or refresh MCP as Cursor documents.

(2) Claude Code:

(a) Read the official docs: [Connect Claude Code to tools via MCP](https://docs.claude.com/en/docs/claude-code/mcp.md).
(b) Copy or merge [claude-code.mcp.json.example](mcp-client-examples/claude-code.mcp.json.example) to **`.mcp.json` at the agent working project root** (project scope), or from that project run `claude mcp add --transport stdio ... --scope project` as documented (sample command in [mcp-client-examples/README.md](mcp-client-examples/README.md)).
(c) Follow Claude Code's project-MCP **approval flow and `--` option order**, and have the user finish the in-IDE authorization.
(d) Handle placeholder keys the same way as §7.2 (1).

(3) OpenCode

(a) OpenCode **does not** use the same top-level **`mcpServers`** object as Cursor. Use **`mcp.<serverId>`**, **`environment`** (not `env`), and **`command`** as a **string array** (see [.opencode/opencode.json](../.opencode/opencode.json)).
(b) **Merge** [opencode.mcp.fragment.json](mcp-client-examples/opencode.mcp.fragment.json) into the user's `mcp` object, beside existing entries.
(c) `$schema` may be `https://opencode.ai/config.json`. Handle placeholder keys the same way as §7.2 (1).

(4) Other hosts

(a) Search that product's official MCP or plugin configuration docs using the **exact product name** the user gave.
(b) Check the **config file path**, the **root JSON shape**, and the `stdio` server field names (whether they match `mcpServers`).
(c) Give the user a minimal working config to paste locally. **Do not** commit a snippet that contains real keys to this repository.

### 8. Functional test after deployment

After configuration, **ask with AskUserQuestion or the host's native question tool whether to run the functional tests**. Reuse a testing choice the user already made. After the user picks the recommended answer 「是」, verify the five domains (train / flight / hotel / map / taxi). **Do not write a new test script.** Ask the question and options in Chinese. Put the recommended option first.

```
question: "是否现在执行部署后功能测试？"
options:
  - "是" → recommended. Continue this section and run the tests below.
  - "否" → Do not run any test in this section. Tell the user installation and configuration are done, and that they can verify later by following this section.
```

If the host marks the recommended option in the label, write the first option as 「是（推荐）」. The recommended choice is still 「是」. Do not run `npm run check` or `scripts/mcp-test.mjs` before the user chooses 「是」.

After the user chooses 「是」, use `scripts/mcp-test.mjs` from the repository (the same commands on Windows, macOS, and Linux). From the repository root:

```bash
npm run check
```

This runs `health` (it calls `gateway_health_check`; the process exits 1 if any item is FAIL). Other modes:

```bash
node scripts/mcp-test.mjs config
node scripts/mcp-test.mjs train
node scripts/mcp-test.mjs flight
node scripts/mcp-test.mjs hotel
node scripts/mcp-test.mjs login
node scripts/mcp-test.mjs map
node scripts/mcp-test.mjs taxi
```

`flight` and `hotel` open a visible browser and usually take several minutes. The script reads the root `.env` and does not print keys. Secret values become `[redacted]`. The user home directory and the repository absolute path become `<home>` and `<repo>`. `config` corresponds to `gateway_get_config`: keys are shown only as set/unset, and paths stay relative to the repository. The per-domain manual checks follow.

> Tool names: the gateway returns `{domain}_{provider}_{tool}` (for example `train_12306_get_tickets`). The host UI may add a prefix (`mcp__travel-mcp-gateway__` in Claude Code). Use the `gatewayName` values from `gateway_list_retained_tools`.

### 8.1 Get today's date

Call `train_12306_get_current_date` (or `flight_flight_ticket_mcp_server_getCurrentDate`) and use that `yyyy-MM-dd` date for the later queries.

### 8.2 Test train tickets (train)

Query high-speed trains from **Shanghai** to **Beijing** for today:

- Tool: `train_12306_get_tickets`
- Arguments: `date` = today, `fromStation` = "上海", `toStation` = "北京", `trainFilterFlags` = "G", `limitedNum` = 3, `format` = "text"

Expected: a list of high-speed trains. If the connection fails or `station_code` resolution is wrong, check that `TRAIN_12306_ENTRY` in `.env` points at `12306-mcp/build/index.js`. Interline queries use `train_12306_get_interline_tickets` (the 12306 interline path was fixed after the upstream site change).

### 8.3 Test flight search (flight)

Query flights from **Shanghai** to **Beijing** seven days after today in the Shanghai time zone:

- Tool: `flight_flight_ticket_mcp_server_searchFlightRoutes`
- Arguments: `departure_city` = "上海", `destination_city` = "北京", `departure_date` = Shanghai-time today + 7 days, `data_source_preference` = "default" (also accepts `auto`), `limit` = 5. There is no `format` argument. Optional time filters: `earliestStartTime` / `earliestArrivalTime` (0–23) and `latestStartTime` / `latestArrivalTime` (1–24).
- Returns: JSON text with `status`, `flight_count`, `flights`, `formatted_output`, `requested_limit`, `collection_stop_reason`, and `statistics_scope`.

The install test collects at most five valid, deduplicated flights and stops scrolling at that cap. If fewer than five exist, it returns the actual count. Results follow page collection order. Price and airline statistics cover only the returned sample, not every flight that day and not the lowest fare. `flight_count` must equal the length of `flights`. An empty result does not pass install acceptance. `flight` mode prints the full result and does not truncate by character count. An ordinary tool call may omit `limit`, which means no count cap.

Expected: a flight list (1–8 minutes; a **minimized browser window** appears on the taskbar and does not take foreground focus). If it fails, check that Chrome or Edge is installed, that `FLIGHT_MCP_BROWSER` matches the engine, that `FLIGHT_MCP_HEADLESS` is not `1` (Ctrip blocks it), that the root `.venv` or `FlightTicketMCP/.venv` exists, and that `FLIGHT_MCP_PYTHON_COMMAND` is correct. The gateway **does not** expose a flight transfer tool.

### 8.4 Test hotel search (hotel)

Query Wuhan hotels for future dates (the first search does not wait for the interval; a logged-in session returns directly):

- Tool: `hotel_ctrip_searchHotels`
- Arguments: `city` = "武汉", `checkin` / `checkout` = today +7 / +9 days, `limit` = 5

Expected: a hotel list (`status: success`, `count`, and `hotels[]`; about 1–2 minutes). `CONSENT_REQUIRED` means the risk-consent setting needs to be checked. When login state is missing, `hotel` mode asks for a login interaction. A non-interactive terminal returns `USER_INTERACTION_REQUIRED`; the agent must call the host question tool and wait for the answer. After the user chooses to open the page, the login page is shown directly. On success, retry the original query once. `LOGIN_STATE_UNKNOWN` means page load or blocking is unclear; do not treat it as an expired login. Consecutive searches wait a random 15s–3min.

### 8.5 Test map tools (map)

Call `map_amap_maps_geo` to resolve "北京南站" to coordinates:

- Arguments: `address` = "北京南站", `city` = "北京"

Expected: longitude and latitude. If it fails, check that `AMAP_MAPS_API_KEY` is valid.

### 8.6 Test ride-hailing (taxi)

Call in order:

1. `taxi_didi_maps_textsearch`: `keywords` = "北京南站", `city` = "北京" (both required)
2. `taxi_didi_taxi_estimate`: `from_name` / `from_lng` / `from_lat` / `to_name` / `to_lng` / `to_lat`. Coordinates must come from the textsearch result in step 1. Do not invent them.

Expected: fare estimates for several vehicle types (estimate only; it does not place an order).

### 8.7 Test report

Report results to the user in this shape:

```
| Domain | Tool                              | Status | Notes              |
|--------|-----------------------------------|--------|--------------------|
| train  | get_tickets (Shanghai→Beijing)    | ✅/❌  | N trains returned  |
| flight | searchFlightRoutes (Shanghai→Beijing) | ✅/❌ | N flights returned |
| hotel  | searchHotels (Wuhan)              | ✅/❌  | N hotels returned  |
| map    | maps_geo (Beijing South)          | ✅/❌  | coords: lng, lat   |
| taxi   | maps_textsearch (Beijing South)   | ✅/❌  | N places returned  |
```

If every domain passes, installation succeeded. If any domain fails, follow **Error Handling**.

## Error Handling

For MCP connection, authentication, schema, or response-format problems:

1. Check that variable names in `.env` and the client config match.
2. Check that `npm run build` succeeded.
3. Check that `FlightTicketMCP` and `HotelTicketMCP` dependencies are installed.
4. Use the `error-processing` skill actually installed for the host chosen in §1 (3), and read `mcp-error-references.json` in that skill's directory. If installation is not finished yet, read the template and index under the repository `skill-templates/error-processing/` directly. Do not assume an OpenCode directory exists.
5. On a flight failure, call `gateway_get_config` first and inspect provider connectivity and browser strategy (engine, headless flag, browser path override). Common browser causes: Chrome/Edge is not installed, `FLIGHT_MCP_BROWSER` selects the wrong engine, or `FLIGHT_MCP_HEADLESS=1` is blocked by Ctrip.
6. Hotel search returns `CONSENT_REQUIRED`: the user has not accepted the risk terms (`.env` `HOTEL_MCP_CONSENT` is not `yes`). Ask again using §5.1 D.
7. Hotel search returns `LOGIN_REQUIRED`: call `hotel_ctrip_login`. The native MCP question asks whether to open the login page or cancel. On `USER_INTERACTION_REQUIRED`, the agent must use AskUserQuestion or the host's native question tool, wait for the real answer, then pass `user_action=open_login` or `cancel`. Choosing open shows the Ctrip login page directly. Scanning a code or typing an account happens in the browser. The default wait is 14 minutes (`HOTEL_MCP_LOGIN_TIMEOUT`: 1–840 seconds). On success, retry the original query once. Cancel, closing the window, or failure stops the flow. An interactive terminal can run `node scripts/mcp-test.mjs login`. A non-interactive terminal may use `--login-action=open_login` only after the user has already chosen to open the page. See [Hotel login interaction](hotel-login.md).
8. Do not print full environment variables, tokens, real keys, or private account data.

## Notes

1. When calling **AskUserQuestion** (or the host's equivalent `question` tool), questions and options **default to Chinese**.
2. **AskUserQuestion / `question` tool constraints**: one call contains at most 4 questions; **each question needs at least 2 options** (a single-option question is rejected as a whole—do not build a single-option question, and do not pad options); **questions and options default to Chinese**. Keys are free text. Use the question's free-text input (such as **Other**), or a local command or interactive input. Write the value to `.env` only with the user's authorization. **The agent must not echo a real key on its own.**
3. Browser acceptance must run `node scripts/mcp-test.mjs flight` and `node scripts/mcp-test.mjs hotel`. Both check a nonempty business result on every platform. A successful connection is not a passed query. Environment discovery order, shutdown recovery, and simulated-test limits are in the [runtime guide](browser-runtime.md).
