import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { ErrorCode, McpError, type CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

import { getRuntimeConfig } from "../config.js";
import type {
  DownstreamProviderDefinition,
  DownstreamToolDefinition,
  ProviderConnectionResult,
  RegisteredGatewayTool,
} from "../types.js";
import { jsonSchemaToZod } from "./jsonSchemaToZod.js";
import { detailsHint } from "./toolDetails.js";
import { normalizeToolResult } from "./toolResult.js";
import { resolvePythonInterpreter } from "./pythonInterpreter.js";
import { prepareHotelLogin, withHotelRecovery } from "../domains/hotel/ctrip/loginInteraction.js";

const activeClients = new Set<Client>();
let closing = false;
let closingReason = "shutdown";
const initializations = new Set<{ controller: AbortController; phase: string }>();

// A distinct cancellation reason survives the SDK's request cancellation handling.
// ConnectionClosed on its own can also mean a real provider crash.
export class ProviderInitializationCancelled extends McpError {
  constructor(reason: string, phase: string) {
    super(ErrorCode.ConnectionClosed, `initialization cancelled during ${phase}: ${reason}`);
  }
}

export const closeDownstreamClients = async (reason = "shutdown") => {
  if (!closing) closingReason = reason;
  closing = true;
  for (const { controller, phase } of initializations) {
    controller.abort(new ProviderInitializationCancelled(closingReason, phase));
  }
  await Promise.allSettled([...activeClients].map((client) => client.close()));
  activeClients.clear();
};

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
  return `[${provider.domain}/${provider.providerName}] ${summary}\n${detailsHint(buildGatewayToolName(provider, tool.name))}`;
};

export const connectAndRegisterProvider = async (
  server: McpServer,
  provider: DownstreamProviderDefinition,
): Promise<ProviderConnectionResult | null> => {
  if (!provider.enabled) {
    return null;
  }

  if (provider.python && provider.transport.kind === "stdio") {
    const resolved = await resolvePythonInterpreter(provider.python);
    provider.transport.command = resolved.command;
    provider.python.resolvedSource = resolved.source;
  }
  if (closing) throw new ProviderInitializationCancelled(closingReason, "preflight");

  const client = createClient();
  const transport = createTransport(provider);
  const registrations: ReturnType<McpServer["registerTool"]>[] = [];
  const initialization = { controller: new AbortController(), phase: "initialize" };
  const { signal } = initialization.controller;
  initializations.add(initialization);
  activeClients.add(client);
  try {
    await client.connect(transport, { signal });
    signal.throwIfAborted();

    initialization.phase = "tools/list";
    const { tools } = await client.listTools(undefined, { signal });
    signal.throwIfAborted();
    const retainedTools = tools
      .map(toToolDefinition)
      .filter((tool) => shouldRetainTool(provider, tool.name));

    const registeredTools: RegisteredGatewayTool[] = [];

    for (const tool of retainedTools) {
      const gatewayName = buildGatewayToolName(provider, tool.name);
      const inputSchema = jsonSchemaToZod(tool.inputSchema as Record<string, unknown>);

      const registration = server.registerTool(
        gatewayName,
        {
          title: tool.title ?? gatewayName,
          description: toToolDescription(provider, tool),
          inputSchema,
          annotations: tool.annotations,
        },
        async (args, extra) => {
          let forwardedArgs = args as Record<string, unknown>;
          const hotel = provider.domain === "hotel" && provider.providerName === "ctrip";
          if (hotel && tool.name === "login") {
            const prepared = await prepareHotelLogin(server, forwardedArgs, extra);
            if (prepared.result) return prepared.result;
            forwardedArgs = prepared.args!;
          }
          const result = (await client.callTool(
            {
              name: tool.name,
              arguments: forwardedArgs,
            },
            undefined,
            { timeout: provider.requestTimeout, signal: extra.signal,
              ...(extra._meta?.progressToken !== undefined ? { onprogress: async (progress) => {
                await extra.sendNotification({ method: "notifications/progress", params: {
                  ...progress, progressToken: extra._meta!.progressToken!,
                } }).catch(() => undefined);
              } } : {}),
            },
          )) as CallToolResult | { toolResult: unknown; _meta?: Record<string, unknown> };

          const normalized = normalizeToolResult(result);
          return hotel && tool.name === "searchHotels" ? withHotelRecovery(normalized, forwardedArgs) : normalized;
        },
      );
      registrations.push(registration);

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
  } catch (error) {
    for (const registration of registrations) registration.remove();
    await client.close().catch(() => undefined);
    await transport.close().catch(() => undefined);
    activeClients.delete(client);
    throw error;
  } finally {
    initializations.delete(initialization);
  }
};

export const createInventorySchema = () =>
  z.object({
    domain: z.enum(["train", "flight", "hotel", "map", "taxi"]).optional(),
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
