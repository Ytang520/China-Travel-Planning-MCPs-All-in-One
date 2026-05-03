import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

import { getRuntimeConfig } from "./config.js";
import { getFlightProviders } from "./domains/flight/registry.js";
import { getMapProviders } from "./domains/map/registry.js";
import { getTaxiProviders } from "./domains/taxi/registry.js";
import { getTrainProviders } from "./domains/train/registry.js";
import type {
  DomainName,
  DownstreamProviderDefinition,
  GatewayToolInventory,
} from "./types.js";
import {
  connectAndRegisterProvider,
  createInventorySchema,
} from "./utils/downstreamClient.js";

const config = getRuntimeConfig();

const server = new McpServer({
  name: config.projectName,
  version: config.projectVersion,
  description:
    "This gateway unifies train, flight, map, and taxi MCP tools. " +
    "For taxi fare estimates, always use taxi_didi_maps_textsearch before taxi_didi_taxi_estimate. " +
    "For other map and route tasks, prefer map_amap_* tools.",
});

const getProviders = (): DownstreamProviderDefinition[] => {
  return [
    ...getTrainProviders(config),
    ...getFlightProviders(config),
    ...getMapProviders(config),
    ...getTaxiProviders(config),
  ];
};

const createEmptyInventory = (): GatewayToolInventory => {
  return {
    train: [],
    flight: [],
    map: [],
    taxi: [],
  };
};

const registerInventoryFeatures = (inventory: GatewayToolInventory) => {
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
            text: JSON.stringify(inventory, null, 2),
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
      description:
        "Return the retained gateway tools grouped by train, flight, map, and taxi domains.",
      inputSchema: createInventorySchema(),
      annotations: {
        readOnlyHint: true,
        idempotentHint: true,
      },
    },
    async (args) => {
      if (args.domain) {
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  [args.domain]: inventory[args.domain as DomainName],
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
            text: JSON.stringify(inventory, null, 2),
          },
        ],
      };
    },
  );
};

const start = async () => {
  const providers = getProviders();
  const inventory = createEmptyInventory();

  for (const provider of providers) {
    try {
      const connection = await connectAndRegisterProvider(server, provider);
      if (!connection) {
        continue;
      }

      inventory[provider.domain].push({
        providerName: provider.providerName,
        displayName: provider.displayName,
        description: provider.description,
        tools: connection.registeredTools,
      });
    } catch (error) {
      console.error(
        `[gateway] failed to connect provider ${provider.domain}/${provider.providerName}:`,
        error,
      );
    }
  }

  registerInventoryFeatures(inventory);

  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("[gateway] travel MCP gateway running on stdio");
};

start().catch((error) => {
  console.error("[gateway] fatal startup error:", error);
  process.exit(1);
});
