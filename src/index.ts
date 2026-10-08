import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { isAbsolute, relative, resolve } from "node:path";
import { PassThrough } from "node:stream";
import { detailsHint, gatewayToolDefinitions, registerToolDetails } from "./utils/toolDetails.js";

import { getRuntimeConfig } from "./config.js";
import { getFlightProviders } from "./domains/flight/registry.js";
import { getHotelProviders } from "./domains/hotel/registry.js";
import { HOTEL_LOGIN_INSTRUCTIONS } from "./domains/hotel/ctrip/loginInteraction.js";
import { getMapProviders } from "./domains/map/registry.js";
import { getTaxiProviders } from "./domains/taxi/registry.js";
import { getTrainProviders } from "./domains/train/registry.js";
import type {
  DomainName,
  DownstreamProviderDefinition,
  GatewayToolInventory,
  ProviderConnectionResult,
} from "./types.js";
import {
  connectAndRegisterProvider,
  closeDownstreamClients,
  ProviderInitializationCancelled,
  summarizeInputSchema,
} from "./utils/downstreamClient.js";

const config = getRuntimeConfig();

const server = new McpServer({
  name: config.projectName,
  version: config.projectVersion,
  description:
    "This gateway unifies train, flight, hotel, map, and taxi MCP tools. " +
    "Hotel search requires Ctrip login and explicit risk consent (HOTEL_MCP_CONSENT=yes). " +
    "For taxi fare estimates, always use taxi_didi_maps_textsearch before taxi_didi_taxi_estimate. " +
    "For other map and route tasks, prefer map_amap_* tools.",
}, { instructions: HOTEL_LOGIN_INSTRUCTIONS });

const getProviders = (): DownstreamProviderDefinition[] => {
  return [
    ...getTrainProviders(config),
    ...getFlightProviders(config),
    ...getHotelProviders(config),
    ...getMapProviders(config),
    ...getTaxiProviders(config),
  ];
};

const createEmptyInventory = (): GatewayToolInventory => {
  return {
    train: [],
    flight: [],
    hotel: [],
    map: [],
    taxi: [],
  };
};

const serializeInventory = (inventory: GatewayToolInventory) => {
  return Object.fromEntries(
    (
      Object.entries(inventory) as [
        DomainName,
        GatewayToolInventory[DomainName],
      ][]
    ).map(([domain, providers]) => [
      domain,
      providers.map((provider) => ({
        providerName: provider.providerName,
        displayName: provider.displayName,
        description: provider.description,
        tools: provider.tools.map((tool) => ({
          gatewayName: tool.gatewayName,
          downstreamName: tool.downstreamName,
          description: tool.description,
          ...summarizeInputSchema(tool.inputSchema),
        })),
      })),
    ]),
  );
};

const HEALTH_PROBES: Record<
  Exclude<DomainName, "flight" | "hotel">,
  { match: RegExp; args: Record<string, unknown>; hint: string }
> = {
  train: {
    match: /get[-_]current[-_]date$/i,
    args: {},
    hint: "12306 current-date tool",
  },
  map: {
    match: /maps_geo$/i,
    args: { address: "北京南站", city: "北京" },
    hint: "Amap geocoding",
  },
  taxi: {
    match: /maps_textsearch$/i,
    args: { keywords: "北京南站", city: "北京" },
    hint: "DiDi place search",
  },
};

const registerInventoryFeatures = (
  inventory: GatewayToolInventory,
  connections: ProviderConnectionResult[],
) => {
  server.registerResource(
    "gateway-inventory",
    "gateway://inventory",
    {
      title: "Gateway Inventory",
      description:
        "Lists enabled domains, providers, and the retained tool names exposed by this travel MCP gateway.",
      mimeType: "application/json",
    },
    async (uri) => {
      return {
        contents: [
          {
            uri: uri.href,
            text: JSON.stringify(serializeInventory(inventory), null, 2),
            mimeType: "application/json",
          },
        ],
      };
    },
  );

  server.registerTool(
    "gateway_list_retained_tools",
    {
      title: "List Retained Tools",
      ...gatewayToolDefinitions.gateway_list_retained_tools,
      description: `${gatewayToolDefinitions.gateway_list_retained_tools.description} ${detailsHint("gateway_list_retained_tools")}`,
      annotations: {
        readOnlyHint: true,
        idempotentHint: true,
      },
    },
    async (args) => {
      const serialized = serializeInventory(inventory);
      if (args.domain) {
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  [args.domain]: serialized[args.domain as DomainName],
                },
                null,
                2,
              ),
            },
          ],
        };
      }

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(serialized, null, 2),
          },
        ],
      };
    },
  );

  server.registerTool(
    "gateway_get_config",
    {
      title: "Gateway Runtime Config",
      ...gatewayToolDefinitions.gateway_get_config,
      description: `${gatewayToolDefinitions.gateway_get_config.description} ${detailsHint("gateway_get_config")}`,
      annotations: {
        readOnlyHint: true,
        idempotentHint: true,
      },
    },
    async () => {
      const env = process.env;
      const connectionByProvider = new Map(
        connections.map((c) => [
          `${c.provider.domain}/${c.provider.providerName}`,
          c,
        ]),
      );
      const providers = getProviders().map((provider) => {
        const connection = connectionByProvider.get(
          `${provider.domain}/${provider.providerName}`,
        );
        return {
          domain: provider.domain,
          providerName: provider.providerName,
          displayName: provider.displayName,
          enabled: provider.enabled,
          transportKind: provider.transport.kind,
          connected: Boolean(connection),
          retainedToolCount: connection?.registeredTools.length ?? 0,
          retainedTools:
            connection?.registeredTools.map((t) => t.gatewayName) ?? [],
          hiddenTools: provider.excludeTools ?? [],
          includeTools: provider.includeTools,
          requestTimeoutMs: provider.requestTimeout ?? 60000,
        };
      });

      const toPublicPath = (target: string) => {
        if (!isAbsolute(target)) {
          return target.replaceAll("\\", "/");
        }
        const relativePath = relative(resolve(config.workspaceRoot), resolve(target));
        if (relativePath === "") {
          return ".";
        }
        if (relativePath.startsWith("..") || isAbsolute(relativePath)) {
          return "<outside-workspace>";
        }
        return relativePath.replaceAll("\\", "/");
      };

      const pythonFor = (domain: string, fallback: string) => {
        const provider = connections.find((c) => c.provider.domain === domain)?.provider;
        return {
          command: provider?.transport.kind === "stdio" ? provider.transport.command : fallback,
          source: provider?.python?.resolvedSource ?? "unavailable",
        };
      };
      const flightPython = pythonFor("flight", config.flightPythonCommand);
      const hotelPython = pythonFor("hotel", config.hotelPythonCommand);
      const payload = {
        project: {
          name: config.projectName,
          version: config.projectVersion,
          workspaceRoot: ".",
        },
        command: {
          node: process.version,
          flightPythonSource: flightPython.source,
          hotelPythonSource: hotelPython.source,
          flightPythonCommand: toPublicPath(flightPython.command),
          hotelPythonCommand: toPublicPath(hotelPython.command),
          train12306Entry: toPublicPath(config.train12306Entry),
        },
        browser: {
          engine: (env.FLIGHT_MCP_BROWSER ?? "edge").toLowerCase(),
          headless: env.FLIGHT_MCP_HEADLESS === "1",
          browserPathOverride: env.FLIGHT_MCP_BROWSER_PATH ? "set" : "unset",
          note: "Ctrip (flights.ctrip.com) blocks headless browsers (whaleguard HTTP 432); default is a silent, non-focused visible window.",
        },
        hotelBrowser: {
          browserPathOverride: env.HOTEL_MCP_BROWSER_PATH ? "set" : "unset",
          engine: (env.HOTEL_MCP_BROWSER ?? "edge").toLowerCase(),
          headless: env.HOTEL_MCP_HEADLESS === "1",
          consent: (env.HOTEL_MCP_CONSENT ?? "no").toLowerCase() === "yes" ? "yes" : "no",
          note: "hotels.ctrip.com requires Ctrip login (guest is redirected to passport); searches are rate-limited by a random 15s-3min interval.",
        },
        secrets: {
          AMAP_MAPS_API_KEY: config.amapApiKey ? "set" : "unset",
          DIDI_MCP_KEY: config.didiMcpKey ? "set" : "unset",
        },
        dataSourceNotes: [
          "flight: Ctrip web scraping with Fliggy website fallback (visible browser, logged-out); searches are serialized per process with a default 15-45s gap, including fallback; Fliggy fares exclude taxes and fees",
          "hotel: Ctrip web scraping, login required (HOTEL_MCP_CONSENT=yes to enable); random 15s-3min interval between searches",
          "train: 12306 direct + interline tickets (interline uses the lc_search_url-resolved path)",
          "taxi: call taxi_didi_maps_textsearch before taxi_didi_taxi_estimate",
        ],
        providers,
      };

      return {
        content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
      };
    },
  );

  server.registerTool(
    "gateway_health_check",
    {
      title: "Gateway Health Check",
      ...gatewayToolDefinitions.gateway_health_check,
      description: `${gatewayToolDefinitions.gateway_health_check.description} ${detailsHint("gateway_health_check")}`,
      annotations: {
        readOnlyHint: true,
      },
    },
    async (args) => {
      const domains: DomainName[] = args.domain
        ? [args.domain as DomainName]
        : ["train", "flight", "hotel", "map", "taxi"];

      const results: Array<Record<string, unknown>> = [];
      for (const domain of domains) {
        const connection = connections.find(
          (c) => c.provider.domain === domain,
        );
        if (!connection) {
          results.push({
            domain,
            status: "FAIL",
            error: "provider disabled or not connected",
          });
          continue;
        }

        if (domain === "flight") {
          results.push({
            domain,
            status: "PASS",
            mode: "connectivity-only",
            provider: connection.provider.providerName,
            retainedToolCount: connection.registeredTools.length,
            note: "live flight search needs a visible browser and takes minutes",
          });
          continue;
        }

        if (domain === "hotel") {
          results.push({
            domain,
            status: "PASS",
            mode: "connectivity-only",
            provider: connection.provider.providerName,
            retainedToolCount: connection.registeredTools.length,
            note: "hotel search needs Ctrip login (HOTEL_MCP_CONSENT=yes) and a visible browser; searches are rate-limited 15s-3min",
          });
          continue;
        }

        const probe = HEALTH_PROBES[domain];
        const downstreamTool = connection.tools.find((t) =>
          probe.match.test(t.name),
        );
        if (!downstreamTool) {
          results.push({
            domain,
            status: "FAIL",
            provider: connection.provider.providerName,
            error: "probe tool not exposed by provider",
          });
          continue;
        }

        const startedAt = Date.now();
        try {
          const result = await connection.client.callTool(
            { name: downstreamTool.name, arguments: probe.args },
            undefined,
            {
              timeout: Math.min(
                connection.provider.requestTimeout ?? 60000,
                30000,
              ),
            },
          );
          const text = (
            (result.content ?? []) as Array<{ type?: string; text?: string }>
          )
            .map((c) =>
              c.type === "text" && c.text !== undefined
                ? c.text
                : JSON.stringify(c),
            )
            .join("\n");
          const ok =
            !result.isError && !/"status"\s*:\s*"error"/.test(text);
          results.push({
            domain,
            status: ok ? "PASS" : "FAIL",
            provider: connection.provider.providerName,
            tool: downstreamTool.name,
            elapsedMs: Date.now() - startedAt,
            sample: text.slice(0, 300),
          });
        } catch (error) {
          results.push({
            domain,
            status: "FAIL",
            provider: connection.provider.providerName,
            tool: downstreamTool.name,
            error: String(error),
          });
        }
      }

      return {
        content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
      };
    },
  );
};

const start = async () => {
  const providers = getProviders();
  const inventory = createEmptyInventory();
  const connections: ProviderConnectionResult[] = [];

  for (const provider of providers) {
    if (stopping) break;
    try {
      const connection = await connectAndRegisterProvider(server, provider);
      if (!connection) {
        continue;
      }
      connections.push(connection);

      inventory[provider.domain].push({
        providerName: provider.providerName,
        displayName: provider.displayName,
        description: provider.description,
        tools: connection.registeredTools,
      });
    } catch (error) {
      if (error instanceof ProviderInitializationCancelled) {
        console.error(`[gateway] provider ${provider.domain}/${provider.providerName}: ${error.message}`);
        break;
      }
      console.error(
        `[gateway] failed to connect provider ${provider.domain}/${provider.providerName}:`,
        error,
      );
    }
  }

  if (stopping) return;
  registerInventoryFeatures(inventory, connections);
  registerToolDetails(server, connections.flatMap((connection) => connection.registeredTools));
  const transport = new StdioServerTransport(gatewayInput);
  await server.connect(transport);
  console.error("[gateway] travel MCP gateway running on stdio");
};

let stopping = false;
let shutdownPromise: Promise<void> | undefined;
const gatewayInput = new PassThrough();
const shutdown = (reason = "shutdown") => {
  if (!stopping) console.error(`[gateway] shutting down: ${reason}`);
  stopping = true;
  shutdownPromise ??= (async () => {
    process.stdin.unpipe(gatewayInput);
    await closeDownstreamClients(reason);
    await server.close();
    gatewayInput.destroy();
  })();
  return shutdownPromise;
};

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.once(signal, () => {
    void shutdown(signal).finally(() => process.exit(signal === "SIGINT" ? 130 : 143));
  });
}
process.stdin.once("end", () => { void shutdown("host stdin EOF"); });
process.stdin.once("close", () => { void shutdown("host stdin closed"); });
process.stdin.once("error", () => { void shutdown("host stdin error"); });
// Consume host input immediately so EOF during provider startup is observable.
// The transport consumes buffered initialization messages once startup finishes.
process.stdin.pipe(gatewayInput);

start().catch(async (error) => {
  console.error("[gateway] fatal startup error:", error);
  await shutdown("fatal startup error");
  process.exit(1);
});
