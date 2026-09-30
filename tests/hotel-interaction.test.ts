import test from "node:test";
import assert from "node:assert/strict";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { ElicitRequestSchema, type ClientCapabilities, type ElicitResult } from "@modelcontextprotocol/sdk/types.js";
import { jsonSchemaToZod } from "../src/utils/jsonSchemaToZod.js";
import { prepareHotelLogin, withHotelRecovery, hotelPayload, LOGIN_OPTIONS } from "../src/domains/hotel/ctrip/loginInteraction.js";
import { hotelSearchWithLogin, loginAction } from "../scripts/hotel-interaction.mjs";

const result = (data: object) => ({ content: [{ type: "text" as const, text: JSON.stringify(data) }] });

async function peer(capabilities: ClientCapabilities, answer: ElicitResult = { action: "accept", content: { action: LOGIN_OPTIONS[0] } }) {
  const server = new McpServer({ name: "test-hotel", version: "1" });
  const client = new Client({ name: "test-client", version: "1" }, { capabilities });
  const events: string[] = [];
  if (capabilities.elicitation) client.setRequestHandler(ElicitRequestSchema, async request => {
    assert.equal(request.params.mode, "form");
    events.push("question");
    return answer;
  });
  server.registerTool("login", { inputSchema: {
    user_action: jsonSchemaToZod({ anyOf: [{ type: "string", enum: ["open_login", "cancel"] }, { type: "null" }] }).optional(),
    return_url: jsonSchemaToZod({ anyOf: [{ type: "string" }, { type: "null" }] }).optional(),
  } }, async (args, extra) => {
    const prepared = await prepareHotelLogin(server, args, extra);
    if (prepared.result) return prepared.result;
    assert.equal(prepared.args?.user_action, "open_login");
    events.push("browser");
    return result({ status: "success" });
  });
  const [left, right] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(left), client.connect(right)]);
  return { client, events, close: async () => { await client.close(); await server.close(); } };
}

for (const elicitation of [{ form: {} }, {}]) {
  test(`native question precedes browser (capability ${JSON.stringify(elicitation)})`, async () => {
    const p = await peer({ elicitation });
    try {
      const response = await p.client.callTool({ name: "login", arguments: {} });
      assert.equal(hotelPayload(response as any)?.status, "success");
      assert.deepEqual(p.events, ["question", "browser"]);
    } finally { await p.close(); }
  });
}

for (const answer of [{ action: "decline" }, { action: "cancel" }, { action: "accept", content: { action: LOGIN_OPTIONS[1] } }] as ElicitResult[]) {
  test(`cancel/decline never opens browser: ${JSON.stringify(answer)}`, async () => {
    const p = await peer({ elicitation: { form: {} } }, answer);
    try {
      const response = await p.client.callTool({ name: "login", arguments: {} });
      assert.equal(hotelPayload(response as any)?.error_code, "LOGIN_CANCELLED");
      assert.deepEqual(p.events, ["question"]);
    } finally { await p.close(); }
  });
}

for (const capabilities of [{}, { elicitation: { url: {} } }]) {
  test(`unsupported form UI requires host question: ${JSON.stringify(capabilities)}`, async () => {
    const p = await peer(capabilities);
    try {
      const response = await p.client.callTool({ name: "login", arguments: {} });
      assert.equal(hotelPayload(response as any)?.error_code, "USER_INTERACTION_REQUIRED");
      assert.deepEqual(p.events, []);
      await p.client.callTool({ name: "login", arguments: { user_action: "open_login" } });
      assert.deepEqual(p.events, ["browser"]);
    } finally { await p.close(); }
  });
}

test("explicit host answer does not trigger a duplicate prompt", async () => {
  const p = await peer({ elicitation: { form: {} } });
  try {
    await p.client.callTool({ name: "login", arguments: { user_action: "cancel" } });
    assert.deepEqual(p.events, []);
    await p.client.callTool({ name: "login", arguments: { user_action: "open_login" } });
    assert.deepEqual(p.events, ["browser"]);
  } finally { await p.close(); }
});

test("failed dialog is never interpreted as user acceptance", async () => {
  const prepared = await prepareHotelLogin({ server: { getClientCapabilities: () => ({ elicitation: { form: {} } }) } } as any,
    {}, { signal: new AbortController().signal, sendRequest: async () => { throw new Error("unsupported UI"); } } as any);
  assert.equal(hotelPayload(prepared.result!)?.error_code, "USER_INTERACTION_REQUIRED");
});

test("recovery preserves all original search arguments and retries once", async () => {
  const args = { city: "武汉", checkin: "2026-10-07", checkout: "2026-10-09", adults: 1, rooms: 2, min_score: 4.5 };
  const required = withHotelRecovery(result({ status: "error", error_code: "LOGIN_REQUIRED", return_url: "https://hotels.ctrip.com/hotels/list/?city=477" }), args);
  assert.deepEqual((hotelPayload(required)?.resume_request as any).arguments, args);
  const calls: unknown[] = [];
  const response = await hotelSearchWithLogin(async (name: string, params: unknown) => {
    calls.push([name, params]);
    return name === "hotel_ctrip_login" ? result({ status: "success" }) : required;
  }, args);
  assert.equal(hotelPayload(response)?.error_code, "LOGIN_REQUIRED");
  assert.deepEqual(calls, [["hotel_ctrip_searchHotels", args], ["hotel_ctrip_login", { return_url: "https://hotels.ctrip.com/hotels/list/?city=477" }], ["hotel_ctrip_searchHotels", args]]);
});

test("a cancelled login never resumes hotel search", async () => {
  const calls: string[] = [];
  const response = await hotelSearchWithLogin(async (name: string) => {
    calls.push(name);
    return result({ status: "error", error_code: name.endsWith("login") ? "LOGIN_CANCELLED" : "LOGIN_REQUIRED" });
  }, { city: "武汉" });
  assert.equal(hotelPayload(response)?.error_code, "LOGIN_CANCELLED");
  assert.deepEqual(calls, ["hotel_ctrip_searchHotels", "hotel_ctrip_login"]);
});

test("CLI has no implicit user answer", () => {
  assert.equal(loginAction([]), undefined);
  assert.equal(loginAction(["--login-action=open_login"]), "open_login");
  assert.throws(() => loginAction(["--login-action=bad"]));
  assert.throws(() => loginAction(["--login-action=cancel", "--login-action=open_login"]));
});

test("nullable Python arguments reject invalid values before prompting", async () => {
  const p = await peer({ elicitation: { form: {} } });
  try {
    for (const args of [{ user_action: "invalid" }, { return_url: 42 }]) {
      const response = await p.client.callTool({ name: "login", arguments: args });
      assert.equal(response.isError, true);
    }
    assert.deepEqual(p.events, []);
  } finally { await p.close(); }
});

test("host fallback retains the protected return URL", async () => {
  const url = "https://hotels.ctrip.com/hotels/list/?city=477";
  const prepared = await prepareHotelLogin({ server: { getClientCapabilities: () => ({}) } } as any,
    { return_url: url }, {} as any);
  assert.deepEqual((hotelPayload(prepared.result!)?.user_action as any).accept_arguments,
    { return_url: url, user_action: "open_login" });
});
