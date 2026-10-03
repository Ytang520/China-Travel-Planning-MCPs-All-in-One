import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { RegisteredGatewayTool, ToolDetails } from "../types.js";

export const detailsHint = (name: string) => `Use get_tool_details({tool_name: "${name}"}) for parameters, examples, and result semantics.`;
const domainSchema = z.object({ domain: z.enum(["train", "flight", "hotel", "map", "taxi"]).optional() });
export const gatewayToolDefinitions = {
  gateway_list_retained_tools: {
    description: "Return retained provider tools grouped by domain with parameter summaries.",
    inputSchema: domainSchema,
  },
  gateway_get_config: {
    description: "Return redacted runtime configuration. Secrets are reported only as set/unset.",
    inputSchema: z.object({}),
  },
  gateway_health_check: {
    description: "Run lightweight provider probes; flight and hotel check connectivity only, without scraping.",
    inputSchema: domainSchema,
  },
  get_tool_details: {
    description: "Read one registered tool's exact input schema, reference, examples, and result/error semantics. Use its full gateway name.",
    inputSchema: z.object({ tool_name: z.string().min(1).describe("Exact publicly registered gateway tool name") }).strict(),
  },
};

/** Ignore section headings inside fenced examples. */
export function referenceSection(markdown: string, name: string): string | undefined {
  const lines = markdown.split(/\r?\n/);
  let fence = "", start = -1;
  for (let index = 0; index < lines.length; index++) {
    const marker = lines[index].match(/^\s*(`{3,}|~{3,})/);
    if (marker) {
      if (!fence) fence = marker[1];
      else if (marker[1][0] === fence[0] && marker[1].length >= fence.length) fence = "";
      continue;
    }
    if (fence) continue;
    const heading = lines[index].match(/^##\s+(.+?)\s*$/);
    if (!heading) continue;
    if (start >= 0) return lines.slice(start, index).join("\n").trim();
    if (heading[1] === name) start = index;
  }
  return start < 0 ? undefined : lines.slice(start).join("\n").trim();
}

export class ToolDetailsRegistry {
  private readonly tools = new Map<string, RegisteredGatewayTool>();
  constructor(private readonly referencePath = fileURLToPath(new URL("../../docs/tool-reference.md", import.meta.url))) {}
  register(tool: RegisteredGatewayTool) { this.tools.set(tool.gatewayName, tool); }
  get(name: string): ToolDetails {
    const tool = this.tools.get(name);
    if (!tool) return { status: "error", error_code: "UNKNOWN_TOOL", tool_name: name,
      available_tools: [...this.tools.keys()].sort() };
    let reference: string | undefined;
    try { reference = referenceSection(readFileSync(this.referencePath, "utf8"), name); }
    catch (error) {
      if (!["ENOENT", "EACCES"].includes((error as NodeJS.ErrnoException).code ?? "")) throw error;
    }
    return { status: "ready", tool_name: name, documentation_status: reference ? "complete" : "schema_only",
      description: tool.description ?? "", inputSchema: tool.inputSchema ?? { type: "object" },
      reference: reference ?? null };
  }
}

export function registerToolDetails(server: McpServer, providerTools: RegisteredGatewayTool[]) {
  const registry = new ToolDetailsRegistry();
  for (const tool of providerTools) registry.register(tool);
  for (const [name, definition] of Object.entries(gatewayToolDefinitions)) {
    registry.register({ gatewayName: name, downstreamName: name, description: definition.description,
      inputSchema: z.toJSONSchema(definition.inputSchema) as RegisteredGatewayTool["inputSchema"] });
  }
  server.registerTool("get_tool_details", {
    ...gatewayToolDefinitions.get_tool_details,
    annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
  }, async ({ tool_name }) => {
    const details = registry.get(tool_name);
    return { content: [{ type: "text", text: JSON.stringify(details, null, 2) }],
      ...(details.status === "error" ? { isError: true } : {}) };
  });
  return registry;
}
