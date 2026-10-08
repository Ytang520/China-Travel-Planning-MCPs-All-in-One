# Browser runtime and installation checks

## Python environments

Both providers require Python 3.11 or newer and DrissionPage 4.1.1.4 or newer. Run these commands from the repository root. Reuse a suitable existing `.venv`; create one only if needed:

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

For each provider the gateway checks an explicit `FLIGHT_MCP_PYTHON_COMMAND` or `HOTEL_MCP_PYTHON_COMMAND` first. With no override it tries the root `.venv`, then that provider's existing `.venv`. A candidate must run Python 3.11+, import its dependencies, and provide the required DrissionPage version and browser APIs. An unusable root environment does not hide a usable provider environment. No implicit system Python fallback or automatic installation occurs at runtime.

Explicit overrides are single executables, not shell commands with arguments. An explicitly supplied command name such as `python` is supported and verified; an invalid override fails that provider without selecting a different interpreter. Prefer absolute paths: Windows uses `.venv/Scripts/python.exe`; macOS/Linux use `.venv/bin/python`. Relative interpreter paths resolve against the provider root. Relative project roots and the train entry resolve against the repository root, independent of the host's working directory.

The gateway reads its launching process environment. `scripts/mcp-test.mjs` loads the repository `.env`; running `node build/index.js` directly does not. Supply variables through the MCP client's `env`/`environment` settings for normal use. A provider's own `.env` is loaded after its interpreter has already been chosen. `gateway_get_config` reports the selected interpreter source with private paths redacted.

## Browser discovery

The same rules apply to `FLIGHT_MCP_*` and `HOTEL_MCP_*`:

1. A nonempty `*_BROWSER_PATH` is authoritative. It must point to an executable file; macOS `.app` paths are resolved through `Info.plist`. Invalid overrides stop the query.
2. Prefer `*_BROWSER` (`edge` by default, or `chrome`). Inspect that browser's registered installation, then named commands with `shutil.which()`, then a finite set of common locations. If absent, inspect the other browser in the same order.
3. Windows registration uses App Paths in HKCU/HKLM and both registry views. Common locations derive from system directory variables. macOS uses NSWorkspace bundle lookup and `/Applications` / `~/Applications`. Linux checks named Edge/Chrome/Chromium commands and finite locations in `/usr/bin`, `/usr/local/bin`, `/snap/bin`, `~/.local/bin`, and `/opt`.
4. If discovery is exhausted, or an automatically selected browser fails to start and its residual process is safely cleaned up, invoke DrissionPage once without setting a browser path. Its built-in discovery and internal retries are unrestricted. There are no additional application-level retries. Explicit-path failures do not trigger this fallback.
5. Final failure stops the query and identifies the provider's browser-path variable. Supply the installed executable path and retry; the server does not install a browser or scan the disk.

Application discovery never enumerates or dumps PATH. It calls `shutil.which()` only for the specific browser command names. This restriction does not change ordinary subprocess environment inheritance or DrissionPage's own discovery.

Both searches use DrissionPage. Flight `auto`/`default` searches Ctrip first and tries the Fliggy website once if Ctrip fails or returns no matching flights; both sources use the same owned, logged-out browser. Fliggy waits for stable rendered results without scrolling. Flight page searches run serially per provider process with a default random 15–45 second gap after each attempt, including fallback (`FLIGHT_MCP_MIN_DELAY` / `FLIGHT_MCP_MAX_DELAY`). Hotel searches use Ctrip with project login cookies. Both providers default to a visible, minimized browser and explicitly configure headless mode only when `*_HEADLESS=1`. A Linux visible session requires a working graphical display. Browser discovery cannot guarantee a website will accept headless automation, a login, or a particular browser version.

## Shutdown and recovery

Hotel queries and login sessions hold a cross-process profile lock. Startup records identify the owner process, browser PID and creation time, exact profile, and debugging port. Windows, macOS, and Linux use the same ownership checks through `psutil`. An active owner's profile is never reclaimed, and unknown processes are never terminated by executable name or command-line substring.

Each query cleans up its browser before returning. Constructor failures use the same cleanup. Hotel cookies and the persistent profile are retained; flight sessions use their own temporary profiles. Shutdown refuses new launches, coordinates late constructors, and tries bounded cleanup. MCP hosts may forcibly terminate a server before cleanup completes. The next hotel startup recovers verified orphan processes from the durable record. Uncertain ownership, denied process access, or incomplete cleanup stops startup instead of launching another browser.

## Cross-platform post-install checks

With dependencies installed, the gateway built, and a root `.env` configured, run the same commands on Windows, macOS, or Linux:

```sh
node scripts/mcp-test.mjs flight
node scripts/mcp-test.mjs hotel
```

The flight example is Shanghai → Beijing, seven days ahead, with `limit: 200` by default. The limit applies independently to each query; agents can choose any positive integer, including values above 200, through the MCP `limit` argument or CLI `--limit N`. Explicit MCP null means no count limit. Ctrip stops further scrolling once enough valid, unique flights satisfy the filters; Fliggy fallback reads a stable list without scrolling and respects the same query limit. Fewer flights are allowed. Results follow page collection order, and statistics cover only returned records. Flight mode prints complete results rather than a character-truncated preview. Agents must identify the actual successful source, Ctrip (携程) or Fliggy (飞猪), using `data_source_name` / `source_attribution`, cite `source_url` and `query_time`, and retain Fliggy's taxes/fees exclusion. Attribute separate queries individually. The hotel example is Wuhan, check-in seven days ahead and check-out nine days ahead, at most five hotels. Default query dates use `Asia/Shanghai`, independent of host timezone. Optional dates and flight limit:

```text
node scripts/mcp-test.mjs flight YYYY-MM-DD [--limit N]
node scripts/mcp-test.mjs hotel YYYY-MM-DD YYYY-MM-DD
```

The checks validate complete JSON/structured results, success status, source, route/city, dates, matching counts, nonempty records, and meaningful flight/hotel fields. Missing prices or fewer records than the requested limit are allowed; exceeding that limit fails acceptance. Empty results, login requirements, website blocks, malformed output and count mismatches return a nonzero exit code. They do not prove the browser query works merely because MCP connected.

`npm run check` still runs the lightweight health check; flight/hotel health rows are connectivity-only. Run the two commands above for browser-search acceptance. Hotel live testing requires the existing explicit risk consent and a valid login. If necessary, use the existing `login` mode and complete login manually, then rerun the hotel example.

## Hotel location and browser acceptance

Use `get_tool_details({"tool_name":"hotel_ctrip_searchHotels"})` for the input schema and [tool reference](tool-reference.md) for result semantics. City and landmark have separate fields. Nearby and distance-sorted claims require `location_resolution.applied`, supporting page evidence, and `sorting.applied`; a URL or echoed input alone is insufficient.

Opt-in Windows checks with installed Edge and Chrome use owned temporary profiles and assert the actual browser identity. They never migrate personal default profiles. Set `HOTEL_MCP_RUN_COOKIE_TRANSFER=1` for synthetic cookie attribute transfer, or `HOTEL_MCP_RUN_LOCATION_LIVE=1` for Ctrip location resolution, ID replay, filtered distance sorting, and project Edge-login cookies restored in Chrome. Live checks require valid project cookies and existing consent. Dates are generated seven days ahead. See [cookie reuse](hotel-login.md).

```text
uv run --no-project --python .venv/Scripts/python.exe python -m pytest HotelTicketMCP/tests/test_cookie_transfer.py -q
uv run --no-project --python .venv/Scripts/python.exe python -m pytest HotelTicketMCP/tests/test_location_live.py -q
```

Without the opt-in environment variables these browser tests are skipped. Normal `npm test` and Python regression tests do not perform these live queries.

## Developer checks and evidence

Hotel login always uses a visible browser and enters the official Passport login page directly. The gateway requests a native user choice before launching it; hosts without MCP elicitation must use their user-input tool when `USER_INTERACTION_REQUIRED` is returned. See the [login interaction contract](hotel-login.md) for CLI handling, isolated profiles, cancellation and timeout budgets.

```sh
npm test
npm run build
```

Python checks use the root environment, with the platform-specific interpreter path:

```text
uv run --no-project --python .venv/Scripts/python.exe python -m pytest -q
uv run --no-project --python .venv/bin/python python -m pytest -q
```

The discovery adapters, filesystem semantics, registry/bundle lookups, process ownership, locks, and shutdown scenarios are injectable. macOS/Linux branches can be simulated on Windows without changing `os.name`. Simulated passes are not native-platform or live-Ctrip acceptance. A native live run on either platform remains a separate verification when an environment becomes available.
