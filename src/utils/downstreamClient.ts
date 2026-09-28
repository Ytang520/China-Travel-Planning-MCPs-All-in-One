import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

import { getRuntimeConfig } from "../config.js";
import type {
  DownstreamProviderDefinition,
  DownstreamToolDefinition,
  ProviderConnectionResult,
  RegisteredGatewayTool,
} from "../types.js";
import { jsonSchemaToZod } from "./jsonSchemaToZod.js";
import { normalizeToolResult } from "./toolResult.js";

const normalizeSegment = (value: string) => {
  return value.replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_+|_+$/g, "");
};

const buildGatewayToolName = (
  provider: DownstreamProviderDefinition,
  downstreamToolName: string,
) => {
  const domain = normalizeSegment(provider.domain);
  const providerName = normalizeSegment(provider.providerName);
  const toolName = normalizeSegment(downstreamToolName);

  return `${domain}_${providerName}_${toolName}`;
};

const shouldRetainTool = (
  provider: DownstreamProviderDefinition,
  toolName: string,
) => {
  if (provider.includeTools && provider.includeTools.length > 0) {
    return provider.includeTools.includes(toolName);
  }

  if (provider.excludeTools && provider.excludeTools.length > 0) {
    return !provider.excludeTools.includes(toolName);
  }

  return true;
};

const createTransport = (provider: DownstreamProviderDefinition) => {
  if (provider.transport.kind === "stdio") {
    return new StdioClientTransport({
      command: provider.transport.command,
      args: provider.transport.args,
      cwd: provider.transport.cwd,
      env: provider.transport.env,
      stderr: "inherit",
    });
  }

  return new StreamableHTTPClientTransport(new URL(provider.transport.url), {
    requestInit: provider.transport.requestHeaders
      ? {
          headers: provider.transport.requestHeaders,
        }
      : undefined,
  });
};

const createClient = () => {
  const { projectName, projectVersion } = getRuntimeConfig();

  return new Client({
    name: projectName,
    version: projectVersion,
  });
};

const toToolDefinition = (
  tool: Awaited<ReturnType<Client["listTools"]>>["tools"][number],
): DownstreamToolDefinition => {
  return {
    name: tool.name,
    description: tool.description,
    inputSchema: tool.inputSchema,
    title: tool.title,
    annotations: tool.annotations,
  };
};

const toToolDescription = (provider: DownstreamProviderDefinition, tool: DownstreamToolDefinition) => {
  const summary = tool.description?.trim() || `${provider.displayName} tool`;
  return `[${provider.domain}/${provider.providerName}] ${summary}`;
};

export const connectAndRegisterProvider = async (
  server: McpServer,
  provider: DownstreamProviderDefinition,
): Promise<ProviderConnectionResult | null> => {
  if (!provider.enabled) {
    return null;
  }

  const client = createClient();
  const transport = createTransport(provider);
  await client.connect(transport);

  const { tools } = await client.listTools();
  const retainedTools = tools
    .map(toToolDefinition)
    .filter((tool) => shouldRetainTool(provider, tool.name));

  const registeredTools: RegisteredGatewayTool[] = [];

  for (const tool of retainedTools) {
    const gatewayName = buildGatewayToolName(provider, tool.name);
    const inputSchema = jsonSchemaToZod(tool.inputSchema as Record<string, unknown>);

    server.registerTool(
      gatewayName,
      {
        title: tool.title ?? gatewayName,
        description: toToolDescription(provider, tool),
        inputSchema,
        annotations: tool.annotations,
      },
      async (args) => {
        const result = (await client.callTool(
          {
            name: tool.name,
            arguments: args as Record<string, unknown>,
          },
          undefined,
          { timeout: provider.requestTimeout },
        )) as CallToolResult | { toolResult: unknown; _meta?: Record<string, unknown> };

        return normalizeToolResult(result);
      },
    );

    registeredTools.push({
      gatewayName,
      downstreamName: tool.name,
      description: tool.description,
      inputSchema: tool.inputSchema,
    });
  }

  return {
    provider,
    tools: retainedTools,
    registeredTools,
    client,
  };
};

export const createInventorySchema = () =>
  z.object({
    domain: z.enum(["train", "flight", "map", "taxi"]).optional(),
  });

type JsonSchemaProperty = {
  type?: string | string[];
  description?: string;
  enum?: unknown[];
};

/**
 * Compress a downstream tool's JSON input schema into an agent-friendly
 * parameter summary so callers don't need to read source to learn arguments.
 */
export const summarizeInputSchema = (
  schema?: Record<string, unknown>,
  descriptionLimit = 160,
) => {
  const properties = (schema?.properties ?? {}) as Record<
    string,
    JsonSchemaProperty
  >;
  const required = Array.isArray(schema?.required)
    ? (schema.required as string[])
    : [];
  const requiredSet = new Set(required);
  const truncate = (value?: string) =>
    value && value.length > descriptionLimit
      ? `${value.slice(0, descriptionLimit)}…`
      : value;

  return {
    parameters: Object.entries(properties).map(([name, prop]) => ({
      name,
      type: Array.isArray(prop.type) ? prop.type.join("|") : prop.type ?? "any",
      required: requiredSet.has(name),
      ...(prop.enum ? { enum: prop.enum } : {}),
      ...(prop.description ? { description: truncate(prop.description) } : {}),
    })),
    required,
  };
};
