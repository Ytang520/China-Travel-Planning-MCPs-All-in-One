// Cross-platform post-install smoke test for the travel MCP gateway.
// Windows, macOS, and Linux:
//   npm run check
//   node scripts/mcp-test.mjs [health|config|train|flight|hotel|login|map|taxi]
//   node scripts/mcp-test.mjs flight [YYYY-MM-DD] [--limit N]
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { searchArguments, validateSearchResult } from "./search-checks.mjs";
import { hotelSearchWithLogin, loginAction } from "./hotel-interaction.mjs";
import { ElicitRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { createInterface } from "node:readline/promises";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const MODES = ["health", "config", "train", "flight", "hotel", "login", "map", "taxi"];
const NAMED_SECRETS = new Set(["AMAP_MAPS_API_KEY", "DIDI_MCP_KEY"]);

const unquote = (value) => {
  if (
    (value.startsWith('"') && value.endsWith('"') && value.length >= 2) ||
    (value.startsWith("'") && value.endsWith("'") && value.length >= 2)
  ) {
    return value.slice(1, -1);
  }
  return value;
};

const isSecretName = (name) => {
  return NAMED_SECRETS.has(name) || /(?:KEY|TOKEN|SECRET|PASSWORD)$/i.test(name);
};

const minimumSecretLength = () => {
  return 8;
};

const loadEnvFile = (filePath) => {
  const buffer = readFileSync(filePath);
  if (buffer.length >= 2 && buffer[0] === 0xff && buffer[1] === 0xfe) {
    throw new Error(".env is UTF-16. Save it as UTF-8 and run the check again.");
  }

  const parsed = {};
  const text = buffer.toString("utf8").replace(/^\uFEFF/, "");
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const match = trimmed.match(/^([A-Z0-9_]+)\s*=\s*(.*)$/);
    if (!match) {
      continue;
    }
    parsed[match[1]] = unquote(match[2].trim());
  }
  return parsed;
};

const collectSecrets = (fileEnv) => {
  const secrets = [];
  for (const [name, value] of Object.entries(fileEnv)) {
    if (typeof value !== "string" || !isSecretName(name) || value.length < minimumSecretLength()) {
      continue;
    }
    secrets.push(value);
    const encoded = encodeURIComponent(value);
    if (encoded !== value) {
      secrets.push(encoded);
    }
  }
  return secrets;
};

const pathVariants = (value) => {
  if (typeof value !== "string" || value.length < 3) {
    return [];
  }
  const forward = value.replaceAll("\\", "/");
  const backward = value.replaceAll("/", "\\");
  const base = [...new Set([value, forward, backward])];
  const variants = new Set(base);
  for (const item of base) {
    variants.add(item.replaceAll("\\", "\\\\"));
  }
  return [...variants];
};

const collectPrivatePaths = () => {
  const labeled = [
    [ROOT, "<repo>"],
    [homedir(), "<home>"],
    [process.env.USERPROFILE, "<home>"],
    [process.env.HOME, "<home>"],
  ];
  const needles = [];
  for (const [value, label] of labeled) {
    for (const variant of pathVariants(value)) {
      needles.push({ value: variant, label });
    }
  }
  needles.sort((left, right) => right.value.length - left.value.length);
  return needles;
};

const createRedactor = (secrets, privatePaths) => {
  return (text) => {
    let output = text;
    for (const secret of secrets) {
      output = output.split(secret).join("[redacted]");
    }
    for (const item of privatePaths) {
      output = output.split(item.value).join(item.label);
    }
    return output;
  };
};

const localDate = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const addDays = (dateStr, days) => {
  const [year, month, day] = dateStr.split("-").map(Number);
  const date = new Date(year, month - 1, day + days);
  return localDateFor(date);
};

const localDateFor = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const textOf = (result) => {
  return (result.content ?? [])
    .map((item) => (item.type === "text" ? item.text : JSON.stringify(item)))
    .join("\n");
};

const withNodeOnPath = (env) => {
  const nodeDir = dirname(process.execPath);
  const currentPath = Object.entries(env).find(([key]) => key.toLowerCase() === "path")?.[1] ?? "";
  const segments = currentPath.split(delimiter).filter(Boolean);
  const alreadyPresent = segments.some(
    (segment) => segment.toLowerCase() === nodeDir.toLowerCase(),
  );
  const nextPath = alreadyPresent ? currentPath : [nodeDir, ...segments].join(delimiter);
  const withoutPath = Object.fromEntries(
    Object.entries(env).filter(([key]) => key.toLowerCase() !== "path"),
  );
  return {
    ...withoutPath,
    PATH: nextPath,
  };
};

const mode = process.argv[2] ?? "health";
let explicitLoginAction;
try { explicitLoginAction = loginAction(process.argv.slice(3)); }
catch (error) { process.stderr.write(`${error.message}\n`); process.exit(1); }
const dateArgs = process.argv.slice(3).filter(arg => !arg.startsWith("--login-action="));
if (!MODES.includes(mode)) {
  process.stderr.write(
    `usage: node scripts/mcp-test.mjs [${MODES.join("|")}]\n`,
  );
  process.exit(1);
}

const envPath = resolve(ROOT, ".env");
// Validate only these two examples before starting the gateway or any browser.
let searchRequest;
if (mode === "flight" || mode === "hotel") {
  try {
    searchRequest = searchArguments(mode, dateArgs);
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exit(1);
  }
}
if (!existsSync(envPath)) {
  process.stderr.write("missing .env in the repository root. Copy .env.example and fill it in.\n");
  process.exit(1);
}

const fileEnv = loadEnvFile(envPath);
const childEnv = withNodeOnPath(
  Object.fromEntries(
    Object.entries({ ...process.env, ...fileEnv }).filter(
      (entry) => typeof entry[1] === "string",
    ),
  ),
);
const secrets = collectSecrets(childEnv);
const privatePaths = collectPrivatePaths();
const redact = createRedactor(secrets, privatePaths);
let stderrBuffer = "";
const secretCarry = [...secrets, ...privatePaths.map((item) => item.value)].reduce(
  (max, secret) => Math.max(max, secret.length),
  0,
);

const drainStderr = (force) => {
  stderrBuffer = redact(stderrBuffer);
  if (force || secretCarry === 0) {
    if (stderrBuffer) {
      process.stderr.write(stderrBuffer);
    }
    stderrBuffer = "";
    return;
  }
  const keep = secretCarry - 1;
  if (stderrBuffer.length <= keep) {
    return;
  }
  process.stderr.write(stderrBuffer.slice(0, stderrBuffer.length - keep));
  stderrBuffer = stderrBuffer.slice(stderrBuffer.length - keep);
};

const printText = (text, limit = 4000) => {
  process.stdout.write(`${redact(text).slice(0, limit)}\n`);
};

const transport = new StdioClientTransport({
  command: process.execPath,
  args: [resolve(ROOT, "build", "index.js")],
  cwd: ROOT,
  env: childEnv,
  stderr: "pipe",
});

transport.stderr?.on("data", (chunk) => {
  stderrBuffer += chunk.toString("utf8");
  drainStderr(false);
});
transport.stderr?.on("end", () => {
  drainStderr(true);
});

const canPrompt = Boolean(process.stdin.isTTY && process.stdout.isTTY) || explicitLoginAction !== undefined;
const client = new Client({ name: "install-check", version: "0.0.1" }, {
  capabilities: canPrompt ? { elicitation: { form: {} } } : {},
});
if (canPrompt) client.setRequestHandler(ElicitRequestSchema, async (request, extra) => {
  if (request.params.mode === "url") return { action: "decline" };
  printText(request.params.message, 1000);
  let choice = explicitLoginAction;
  if (choice === undefined) {
    const terminal = createInterface({ input: process.stdin, output: process.stdout });
    try {
      const answer = await terminal.question("1. 打开登录页  2. 取消本次酒店查询 [1/2]: ", {
        signal: AbortSignal.any([extra.signal, AbortSignal.timeout(115000)]),
      });
      choice = answer.trim() === "1" ? "open_login" : "cancel";
    } catch { choice = "cancel"; }
    finally { terminal.close(); }
  }
  printText(choice === "open_login" ? "用户已选择打开携程登录页。" : "用户已取消登录。", 100);
  return choice === "open_login"
    ? { action: "accept", content: { action: "打开登录页" } }
    : { action: "decline" };
});
let failed = false;

const callTool = async (name, args, timeout, recordFailure = true) => {
  const result = await client.callTool({ name, arguments: args }, undefined, {
    timeout,
    onprogress: progress => { if (progress.message) printText(progress.message, 500); },
  });
  const text = textOf(result);
  if (recordFailure && (result.isError || /"status"\s*:\s*"error"/.test(text))) {
    failed = true;
  }
  return { result, text };
};

try {
  await client.connect(transport);

  if (mode === "health") {
    const { text } = await callTool("gateway_health_check", {}, 180000);
    printText(text, 8000);
    try {
      const rows = JSON.parse(text);
      if (!Array.isArray(rows) || rows.some((row) => row?.status === "FAIL")) {
        failed = true;
      }
    } catch {
      failed = true;
    }
  }

  if (mode === "config") {
    const { text } = await callTool("gateway_get_config", {}, 180000);
    printText(text, 12000);
  }

  if (mode === "train") {
    const date = process.argv[3] ?? localDate();
    printText(`date: ${date}`, 40);
    const { text } = await callTool(
      "train_12306_get_tickets",
      {
        date,
        fromStation: "上海",
        toStation: "北京",
        trainFilterFlags: "G",
        limitedNum: 3,
        format: "text",
      },
      60000,
    );
    printText(text, 3000);
  }

  if (mode === "flight" || mode === "hotel") {
    const flight = mode === "flight";
    printText(`request: ${JSON.stringify(searchRequest)}`, 500);
    const result = flight
      ? (await callTool("flight_flight_ticket_mcp_server_searchFlightRoutes", searchRequest, 540000)).result
      : await hotelSearchWithLogin(async (name, args) =>
          (await callTool(name, args, name === "hotel_ctrip_login" ? 1110000 : 990000, false)).result,
          searchRequest, message => printText(message, 500));
    const text = textOf(result);
    // Print complete flight records/JSON for the requested limit.
    printText(text, flight ? Infinity : 4000);
    const count = validateSearchResult(mode, result, searchRequest);
    printText(`PASS ${mode}: browser search returned ${count} records (${process.platform})`, 150);
  }

  if (mode === "login") {
    printText(
      "携程登录流程：请先回答登录提示；选择打开后，在浏览器中完成登录，系统会自动检测。",
      120,
    );
    const { text } = await callTool("hotel_ctrip_login", {}, 1110000);
    printText(text, 4000);

    let loggedIn = false;
    try {
      loggedIn = JSON.parse(text)?.status === "success";
    } catch {
      loggedIn = false;
    }
    if (!loggedIn) {
      printText("登录未成功，请重新运行 login 模式。", 60);
      failed = true;
    } else {
      // 登录成功后自动复跑酒店搜索，验证 cookie 已保存复用
      const verifyRequest = searchArguments("hotel", []);
      printText(
        `登录成功，复跑酒店搜索验证：checkin: ${verifyRequest.checkin} / checkout: ${verifyRequest.checkout}`,
        120,
      );
      const { text: hotelText, result: hotelResult } = await callTool(
        "hotel_ctrip_searchHotels",
        verifyRequest,
        990000,
      );
      printText(hotelText, 4000);
      const count = validateSearchResult("hotel", hotelResult, verifyRequest);
      printText(`PASS hotel login: browser search returned ${count} records (${process.platform})`, 150);
    }
  }

  if (mode === "map") {
    const { text } = await callTool(
      "map_amap_maps_geo",
      { address: "北京南站", city: "北京" },
      60000,
    );
    printText(text, 3000);
  }

  if (mode === "taxi") {
    const search = await callTool(
      "taxi_didi_maps_textsearch",
      { keywords: "天安门", city: "北京" },
      60000,
    );
    let destination = null;
    try {
      const parsed = JSON.parse(search.text);
      const first = Array.isArray(parsed) ? parsed[0] : parsed;
      destination = first?.location ?? null;
      printText(`textsearch sample: ${JSON.stringify(first)}`, 300);
    } catch {
      failed = true;
      printText(search.text, 3000);
    }

    if (destination?.lng != null && destination?.lat != null) {
      const estimate = await callTool(
        "taxi_didi_taxi_estimate",
        {
          from_name: "北京南站",
          from_lng: "116.37901",
          from_lat: "39.86499",
          to_name: "天安门",
          to_lng: String(destination.lng),
          to_lat: String(destination.lat),
        },
        60000,
      );
      printText(estimate.text, 3000);
    } else {
      failed = true;
    }
  }
} catch (error) {
  const message = error instanceof Error ? (error.stack ?? error.message) : String(error);
  process.stderr.write(`${redact(message)}\n`);
  failed = true;
} finally {
  await client.close().catch((error) => {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`${redact(message)}\n`);
    failed = true;
  });
  drainStderr(true);
}

process.exit(failed ? 1 : 0);
