import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

mkdirSync(".validation", { recursive: true });

const startGateway = (context, stall) => {
  const directory = mkdtempSync(resolve(".validation", "gateway-shutdown-"));
  const ready = resolve(directory, "ready.pid");
  const entry = resolve(directory, "provider.mjs");
  writeFileSync(entry, `
import { writeFileSync } from 'node:fs';
import { setTimeout as delay } from 'node:timers/promises';
// A bounded failsafe prevents a failed regression from leaving this test child alive.
setTimeout(() => process.exit(90), 20000).unref();
${stall ? `
process.stdin.once('data', () => writeFileSync(${JSON.stringify(ready)}, String(process.pid)));
process.stdin.once('end', () => process.exit(0));
process.stdin.resume();
` : `
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
await delay(200);
const server = new McpServer({ name: 'shutdown-test', version: '1' });
process.stdin.once('end', () => process.exit(0));
await server.connect(new StdioServerTransport());
writeFileSync(${JSON.stringify(ready)}, String(process.pid));
`}
`);
  const child = spawn(process.execPath, ["--import", "tsx", "src/index.ts"], {
    cwd: process.cwd(), windowsHide: true, stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env, TRAIN_12306_ENTRY: entry,
      FLIGHT_MCP_PYTHON_COMMAND: resolve(directory, "missing-python"),
      HOTEL_MCP_PYTHON_COMMAND: resolve(directory, "missing-python"),
      AMAP_MAPS_API_KEY: "", DIDI_MCP_KEY: "" },
  });
  let output = "";
  let errors = "";
  child.stdout.on("data", (chunk) => { output += chunk; });
  child.stderr.on("data", (chunk) => { errors += chunk; });
  const exited = new Promise((done) => child.once("close", (code, signal) => done({ code, signal })));
  context.after(async () => {
    child.stdin.end();
    if (child.exitCode === null && child.signalCode === null) child.kill();
    await exited;
  });
  return { child, ready, exited, output: () => output, errors: () => errors };
};

const until = async (predicate, milliseconds = 6000) => {
  const deadline = Date.now() + milliseconds;
  while (!predicate() && Date.now() < deadline) await delay(25);
  assert.ok(predicate(), "Timed out waiting for gateway/provider progress");
};

test("host EOF during provider startup closes the pending child", { timeout: 12000 }, async (context) => {
  const run = startGateway(context, true);
  await until(() => existsSync(run.ready));
  const pid = Number(readFileSync(run.ready, "utf8"));
  run.child.stdin.end();
  await until(() => run.child.exitCode !== null);
  assert.equal((await run.exited).code, 0, run.errors());
  assert.throws(() => process.kill(pid, 0), "Downstream process survived host EOF");
});

test("initialization sent during startup remains buffered until the gateway is ready", { timeout: 12000 }, async (context) => {
  const run = startGateway(context, false);
  run.child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: {
    protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "early-client", version: "1" },
  } }) + "\n");
  await until(() => run.output().includes('"id":1'));
  const response = run.output().split("\n").filter(Boolean).map((line) => JSON.parse(line)).find((item) => item.id === 1);
  assert.equal(response.result.serverInfo.name, "travel-mcp-gateway");
  const pid = Number(readFileSync(run.ready, "utf8"));
  run.child.stdin.end();
  await until(() => run.child.exitCode !== null);
  assert.equal((await run.exited).code, 0, run.errors());
  assert.throws(() => process.kill(pid, 0));
});
