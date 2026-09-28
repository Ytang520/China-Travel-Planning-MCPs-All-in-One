// Cross-platform post-install smoke test for the travel MCP gateway.
// Windows, macOS, and Linux:
//   npm run check
//   node scripts/mcp-test.mjs [health|config|train|flight|map|taxi]
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const MODES = ["health", "config", "train", "flight", "hotel", "map", "taxi"];
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
if (!MODES.includes(mode)) {
  process.stderr.write(
    `usage: node scripts/mcp-test.mjs [${MODES.join("|")}]\n`,
  );
  process.exit(1);
}

const envPath = resolve(ROOT, ".env");
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

const client = new Client({ name: "install-check", version: "0.0.1" });
let failed = false;

const callTool = async (name, args, timeout) => {
  const result = await client.callTool({ name, arguments: args }, undefined, {
    timeout,
  });
  const text = textOf(result);
  if (result.isError || /"status"\s*:\s*"error"/.test(text)) {
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

  if (mode === "flight") {
    const date = localDate();
    printText(`date: ${date}`, 40);
    const { text } = await callTool(
      "flight_flight_ticket_mcp_server_searchFlightRoutes",
      {
        departure_city: "上海",
        destination_city: "北京",
        departure_date: date,
        data_source_preference: "default",
      },
      540000,
    );
    printText(text, 4000);
  }

  if (mode === "hotel") {
    const checkin = addDays(localDate(), 7);
    const checkout = addDays(localDate(), 9);
    printText(`checkin: ${checkin} / checkout: ${checkout}`, 80);
    const { text } = await callTool(
      "hotel_ctrip_searchHotels",
      {
        city: "武汉",
        checkin,
        checkout,
        limit: 5,
      },
      900000,
    );
    printText(text, 4000);
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
