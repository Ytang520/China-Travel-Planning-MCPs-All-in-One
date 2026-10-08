# Travel gateway tool reference

The current registered `inputSchema` returned by `get_tool_details` is the authority for structural validation. Defaults describe provider behavior when an argument is omitted; the gateway does not insert them. Use complete gateway names. External tools without a section here return `documentation_status: "schema_only"` with their original schema and description.

## get_tool_details

Read one currently registered tool without calling its provider, opening a browser, or searching. Required argument: `tool_name`, the exact gateway name, for example `hotel_ctrip_searchHotels`.

```json
{"tool_name":"hotel_ctrip_searchHotels"}
```

`status: "ready"` contains the original `inputSchema`, `description`, `documentation_status`, and `reference`. `complete` means a local reference section is available; `schema_only` means the upstream schema and description are available but local semantic documentation is absent. `reference` is then null. An unknown or disabled tool returns `UNKNOWN_TOOL`, `isError: true`, and the available names. A downstream short name such as `searchHotels` is not a gateway name.

## gateway_list_retained_tools

List connected provider tools grouped by domain, including gateway names and short parameter summaries. Omit `domain` for all five domains, or use `train`, `flight`, `hotel`, `map`, or `taxi`.

```json
{"domain":"hotel"}
```

The result is a domain-to-provider inventory. A disabled or unavailable provider contributes no tools. This does not run a health probe. Query `get_tool_details` with a returned `gatewayName` for full schemas and semantics. Gateway builtins are available directly by their names.

## gateway_get_config

Read the redacted runtime configuration with `{}`. Results include provider connections, interpreter selection, browser configuration, retained names, timeout budgets, and data-source notes. Secrets are reported only as set/unset. Absolute paths outside the workspace are redacted. This does not establish that a live search will succeed.

## gateway_health_check

Run lightweight probes for the requested optional `domain`, or all domains with `{}`. Train reads the current date; map geocodes 北京南站; taxi searches 北京南站. Flight and hotel report connectivity only and do not open browsers. Each row reports PASS/FAIL, provider information, and a sample or error. A connectivity-only PASS does not confirm login or scraping.

## flight_flight_ticket_mcp_server_searchFlightRoutes

Search direct flights by `departure_city`, `destination_city`, and `departure_date` (YYYY-MM-DD, today or later). Cities accept names, supported codes, or full forms such as 上海(SHA). `data_source_preference` is `auto` (default) or `default`; both search Ctrip first and try the Fliggy website once if Ctrip fails or returns no matching flights. Requires installed Chrome or Edge; both sources use an owned, logged-out browser.

Optional `earliestStartTime` / `latestStartTime` and `earliestArrivalTime` / `latestArrivalTime` filter local departure/arrival hours. Lower bounds are 0–23, inclusive; upper bounds are 1–24, exclusive. Arrival filters use the local clock hour, including next-day arrivals. Optional `limit` is a positive integer, default 200 **per tool call**. Agents may adjust it to 80, 300, or another positive integer; explicit null means no count limit. Each call has an independent limit: two calls with `limit: 80` may each return 80 flights. Fallback stays within the same call's limit; results from the two sites are not combined. Results retain page order, with filtering and deduplication before applying the limit. Statistics cover only returned flights. Agents pass `limit` as a JSON argument. The repository CLI also accepts `node scripts/mcp-test.mjs flight [YYYY-MM-DD] --limit 80` (default 200).

```json
{"departure_city":"上海","destination_city":"北京","departure_date":"2026-12-01","earliestStartTime":8,"latestStartTime":12,"limit":5}
```

`flights` contains Chinese field names for flight number, airline, local times, airports, terminals and fare. On success, `data_source` is `ctrip_web_scraping` or `fliggy_web_scraping`, and `data_source_name` is `携程` or `飞猪`. `source_attribution` gives a human-readable source statement; `source_url` is the official search link for the requested route/date, and `query_time` includes the local UTC offset. `formatted_output` starts with the same attribution, time, and link. The link opens a fresh search; it does not preserve the quoted price. `fallback_used` reports fallback use and `source_attempts` records each attempt's status, error and wait. Fliggy fares exclude taxes/fees (`price_basis` / `价格说明`: `不含税费`). Fliggy collects a stable rendered list without scrolling and excludes transfer recommendations. A verified empty list can return success with zero flights; blocked, unverified or unparseable pages return `SCRAPING_FAILED` when fallback also fails.

**Required final-answer attribution:** agents must explicitly name the actual successful source, 携程 (Ctrip) or 飞猪 (Fliggy), in the user-facing answer, cite `source_url`, and state `query_time`. Use `data_source_name` / `source_attribution`; retain the taxes/fees exclusion for Fliggy fares. For example: “数据来源：飞猪；查询时间：…；票价不含税费。” When combining several calls, attribute each group of results to its own source. `auto`, `default`, and `fallback_used` alone are not proof of a successful source. A successful empty result identifies the query source, not any available fares.

On an error, `data_source_name`, `source_url`, and `source_attribution` are null. `last_attempted_data_source` / `last_attempted_data_source_name` identify the last attempted site, or are null if no page search occurred. The legacy `data_source` then serves only as a diagnostic identifier (the last attempted source, or `system`). Report failed attempts as failures; do not claim that flights were obtained from them. Schema validation failures may instead return an MCP tool error.

Page searches run serially within each provider process, leaving a random 15–45 second gap after the previous attempt finishes, including switching to Fliggy. Configure `FLIGHT_MCP_MIN_DELAY` / `FLIGHT_MCP_MAX_DELAY` in seconds. The first attempt has no interval wait. Invalid inputs fail before browser launch. Browsers close after each tool call.

## hotel_ctrip_searchHotels

Search Ctrip hotels. Requires existing project login cookies and `HOTEL_MCP_CONSENT=yes`. Queries use an owned browser and wait a random 15 seconds to 3 minutes between searches. The browser closes after each request.

Call `get_tool_details({"tool_name":"hotel_ctrip_searchHotels"})` for the current types, nullability, required fields, bounds, and defaults. `city`, `checkin`, and `checkout` are required. Dates use YYYY-MM-DD; check-in cannot be in the past and checkout must be later. Example dates below must be moved into the future when necessary.

| Argument | Meaning |
| --- | --- |
| `city` | City name, such as 武汉. Never put the landmark here. |
| `location` | Optional location within the city, preferably the complete name, such as 梨园地铁站 or 武汉站-东出口. For ambiguity, reuse a returned candidate name with its line/exit detail. Omitted/null means a city search. |
| `adults`, `children`, `rooms` | Occupancy; adults and rooms at least 1, children at least 0. Defaults 2, 0, 1. |
| `price_min`, `price_max` | Optional per-night CNY range; nonnegative, minimum no greater than maximum. |
| `star_min`, `star_max` | Optional 1–5 star/diamond range; minimum no greater than maximum. Ctrip combines levels 1 and 2 into a single “2 and below” bucket. A requested boundary that cannot separate them returns a warning. |
| `min_score` | Optional 0–5 minimum score applied after collection. Hotels with unknown scores retain an empty score. |
| `room_type` | Optional single value: 大床房, 双床房, 单人床房, 三床房, or 特大床房. Omitted/null means no room-type filter. Other values are rejected. |
| `accommodation_type` | Optional single value: 酒店, 民宿, 青年旅馆, 酒店公寓, or 公寓. Omitted/null means no accommodation-type filter. Other values are rejected. |
| `breakfast` | No verified filter. A supplied value produces a warning and is not applied. |
| `sort` | `smart` (default), `price_asc`, `distance`, or `score_desc`. Distance requires an explicit location and a confirmed distance anchor. |
| `limit` | Maximum returned records, 1–50, default 20. Filtering or availability may yield fewer. |

```json
{"city":"武汉","location":"梨园地铁站","checkin":"2026-11-09","checkout":"2026-11-10","sort":"distance","price_min":200,"price_max":500,"room_type":"双床房","limit":5}
```

`cityName` and `destName` in the browser URL both contain the city; `searchWord` contains the location. Agents supply semantic arguments above and do not need to construct URLs or find landmark IDs in source code.

The provider first tries a city-scoped verified cache/known seed, then a keyword search. If the page does not confirm the requested location, it reads visible suggestions, selects a unique candidate, submits search, and extracts Ctrip's real ID. Candidate parsing is limited to one attempt and a 45-second budget. Ambiguous candidates are returned for clarification. Only exact, verified location names enter the 24-hour, 256-entry process cache. Cache entries are rechecked on each use; shortened aliases and other cities do not inherit a previous selection.

Successful results contain `city`, `location`, dates, `count`, `hotels`, `warnings`, `formatted_output`, `query_time`, `data_source`, and rate-limit information. `location` preserves the request. Use `location_resolution` for the applied state:

- `requested`: original location; `resolved_name`: the confirmed name or null.
- `source`: `city`, `keyword`, `seed`, `cache`, or `candidate`.
- `landmark_id`: a provider ID when resolved, otherwise null. A keyword query can be verified without an ID.
- `applied` and `status`: whether the current page confirms the location; input text alone is insufficient.
- `evidence`: page city, selected location chips, card distance anchors, and an available URL location ID.
- `candidates` / `reason`: details for ambiguous or unavailable resolution.

`sorting` contains `requested`, `actual`, `applied`, `label`, and the distance `anchor`. Distance success requires the page's distance sort control, distances to the confirmed location, and increasing straight-line distances. A `sort=D` URL alone is insufficient. Existing `hotels[].distance` strings retain the website's distance wording.

| Error/status | Next action |
| --- | --- |
| `INVALID_PARAMS` | Correct arguments; do not repeat unchanged. |
| `LOGIN_REQUIRED` | Follow `hotel_ctrip_login` interaction and retry the original search once after success. |
| `LOGIN_STATE_UNKNOWN` | Page is blocked/unloaded or login cannot be confirmed; inspect connectivity or retry later. |
| `LOCATION_AMBIGUOUS` | Present returned names/details, clarify the intended location, then use the fuller location string. |
| `LOCATION_NOT_FOUND`, `LOCATION_UNAVAILABLE` | Use a fuller place name or retry later; no confirmed nearby result is available. |
| `LOCATION_NOT_APPLIED`, `QUERY_NOT_APPLIED` | A resolved object or requested conditions were not verified on the result page. |
| `SORT_NOT_APPLIED`, `RESULTS_NOT_VERIFIED` | Requested order or collected distance evidence could not be confirmed. |
| `SEARCH_STATE_UNKNOWN`, `SCRAPING_FAILED` | Browser/DOM/page state could not be reliably read. |
| `status: "empty"`, `EMPTY_RESULTS` | Query state was verified, but no matching hotels were returned; location/sorting metadata remains available. |

Room and accommodation filters require both the expected URL encoding and the corresponding selected page label. If Ctrip does not apply a requested filter, the provider returns `QUERY_NOT_APPLIED`. Warnings describe unsupported breakfast filtering and shortened result sets; do not describe an unsupported breakfast filter as applied.

## hotel_ctrip_login

Open the project's visible browser for the user to log in directly on Ctrip. Requires `HOTEL_MCP_CONSENT=yes`. Never collect passwords or verification codes in chat. Read the [login interaction contract](hotel-login.md).

Arguments: optional `user_action` (`open_login` or `cancel`) and `return_url` (the official hotel list URL returned by search). On a login requirement, call the tool with the search recovery arguments; the gateway first asks the user through native elicitation. If it returns `USER_INTERACTION_REQUIRED`, ask using the host's input tool and wait for the answer before passing `user_action`. User cancellation ends the query. An earlier explicit user choice can be passed directly.

```json
{"user_action":"open_login"}
```

On success the provider verifies the logged-in official hotel page and atomically saves project cookies. Resume the original search once. `LOGIN_STATE_UNKNOWN` is not a success; `LOGIN_BROWSER_CLOSED` and `LOGIN_CONNECTION_LOST` distinguish window closure from lost control. The default manual login wait is 14 minutes, bounded by the configured timeout. See [browser configuration](browser-runtime.md) for Edge/Chrome cookie reuse with independent profiles.
