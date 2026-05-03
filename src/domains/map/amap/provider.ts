import type { RuntimeConfig } from "../../../config.js";
import type { DownstreamProviderDefinition } from "../../../types.js";

export const createAmapProvider = (
  config: RuntimeConfig,
): DownstreamProviderDefinition => {
  return {
    domain: "map",
    providerName: "amap",
    displayName: "Amap Official MCP",
    description: "Official Amap MCP tools for geocoding, routes, POI, weather, and trip map actions.",
    enabled: Boolean(config.amapApiKey),
    retainInReadme: true,
    transport: {
      kind: "stdio",
      command: "npx",
      args: ["-y", "@amap/amap-maps-mcp-server"],
      cwd: config.workspaceRoot,
      env: {
        ...config.inheritedEnv,
        ...(config.amapApiKey
          ? {
              AMAP_MAPS_API_KEY: config.amapApiKey,
            }
          : {}),
      },
    },
  };
};
