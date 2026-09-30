import { after, test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { DownstreamProviderDefinition } from "../src/types.js";
import { connectAndRegisterProvider, closeDownstreamClients } from "../src/utils/downstreamClient.js";

mkdirSync(".validation", { recursive: true });
const temp = mkdtempSync(resolve(".validation", "downstream-test-"));
const pidFile = resolve(temp, "child.pid");
const script = `
import { writeFileSync } from 'node:fs';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
writeFileSync(process.argv[1], String(process.pid));
const server = new McpServer({name:'test',version:'1'});
for (const name of ['a','b']) server.registerTool(name, {}, () => ({content:[]}));
await server.connect(new StdioServerTransport());
`;
const provider = (): DownstreamProviderDefinition => ({
  domain: "flight", providerName: "test", displayName: "test", description: "test",
  enabled: true, retainInReadme: false,
  transport: { kind: "stdio", command: process.execPath,
    args: ["--input-type=module", "-e", script, pidFile], cwd: process.cwd() },
});
after(closeDownstreamClients);

test("Python preflight failure is isolated before spawning a downstream client", async () => {
  const broken = provider();
  broken.python = { workspaceRoot: process.cwd(), projectRoot: process.cwd(),
    variable: "FLIGHT_MCP_PYTHON_COMMAND", modules: [], explicitCommand: resolve(temp, "missing-python") };
  await assert.rejects(connectAndRegisterProvider({} as McpServer, broken), /PYTHON_INTERPRETER_UNAVAILABLE/);
  assert.equal(existsSync(pidFile), false);
});

test("partial registration failure removes tools and closes the child process", async () => {
  let registered = 0;
  let removed = 0;
  const server = { registerTool: () => {
    if (++registered === 2) throw new Error("registration failed");
    return { remove: () => { removed++; } };
  } } as unknown as McpServer;
  await assert.rejects(connectAndRegisterProvider(server, provider()), /registration failed/);
  assert.equal(removed, 1);
  const pid = Number(readFileSync(pidFile, "utf8"));
  assert.throws(() => process.kill(pid, 0));
});
