import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { registerToolDetails, referenceSection, ToolDetailsRegistry } from "../src/utils/toolDetails.js";

test("reference extraction does not leak neighboring sections or stop at example headings", () => {
  const doc = "## a\nfirst\n```md\n## b\n```\nlast\n## b\nsecret\n";
  assert.equal(referenceSection(doc, "a"), "## a\nfirst\n```md\n## b\n```\nlast");
  assert.equal(referenceSection(doc, "missing"), undefined);
});

test("unknown tools and undocumented external tools have distinct honest results", () => {
  const path = join(mkdtempSync(join(tmpdir(), "travel-reference-")), "reference.md");
  writeFileSync(path, "## hotel_ctrip_searchHotels\nHotel documentation");
  const registry = new ToolDetailsRegistry(path);
  const inputSchema = { type: "object" as const, properties: { nullable: { anyOf: [{ type: "string" }, { type: "null" }], default: null } } };
  registry.register({ gatewayName: "external_tool", downstreamName: "tool", description: "Upstream description", inputSchema });
  const details = registry.get("external_tool");
  assert.equal(details.status, "ready");
  if (details.status !== "ready") return;
  assert.equal(details.documentation_status, "schema_only");
  assert.equal(details.reference, null);
  assert.deepEqual(details.inputSchema, inputSchema);
  assert.deepEqual(registry.get("tool"), { status: "error", error_code: "UNKNOWN_TOOL", tool_name: "tool", available_tools: ["external_tool"] });
});

test("get_tool_details is callable over MCP and covers builtins and providers", async () => {
  const server = new McpServer({ name: "details-test", version: "1" });
  const client = new Client({ name: "test", version: "1" });
  registerToolDetails(server, [{ gatewayName: "hotel_ctrip_searchHotels", downstreamName: "searchHotels",
    inputSchema: { type: "object", required: ["city"], properties: { city: { type: "string" } } } },
  { gatewayName: "flight_flight_ticket_mcp_server_searchFlightRoutes", downstreamName: "searchFlightRoutes",
    inputSchema: { type: "object", properties: {} } }]);
  const [a, b] = InMemoryTransport.createLinkedPair();
  await server.connect(a);
  await client.connect(b);
  try {
    for (const name of ["get_tool_details", "gateway_get_config", "gateway_list_retained_tools", "gateway_health_check", "hotel_ctrip_searchHotels", "flight_flight_ticket_mcp_server_searchFlightRoutes"]) {
      const result = await client.callTool({ name: "get_tool_details", arguments: { tool_name: name } });
      const details = JSON.parse((result.content as any)[0].text);
      assert.equal(details.status, "ready");
      assert.equal(details.documentation_status, "complete");
      assert.equal(details.inputSchema.type, "object");
      assert.ok(details.reference.startsWith("## " + name));
      if (name === "flight_flight_ticket_mcp_server_searchFlightRoutes") {
        assert.match(details.reference, /default 200 \*\*per tool call\*\*/);
        assert.match(details.reference, /Agents may adjust it to 80, 300/);
        assert.match(details.reference, /Required final-answer attribution/);
        assert.match(details.reference, /data_source_name/);
        assert.match(details.reference, /last_attempted_data_source/);
        assert.doesNotMatch(details.reference, /## hotel_ctrip_searchHotels/);
      }
    }
    assert.equal((await client.callTool({ name: "get_tool_details", arguments: { tool_name: "absent" } })).isError, true);
  } finally { await client.close(); await server.close(); }
});
