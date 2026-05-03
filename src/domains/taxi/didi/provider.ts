import type { RuntimeConfig } from "../../../config.js";
import type { DownstreamProviderDefinition } from "../../../types.js";

export const createDidiProvider = (
  config: RuntimeConfig,
): DownstreamProviderDefinition => {
  const endpointBase = "https://mcp.didichuxing.com/mcp-servers";

  return {
    domain: "taxi",
    providerName: "didi",
    displayName: "DiDi MCP",
    description: "DiDi taxi estimate tools with required upstream text search.",
    enabled: Boolean(config.didiMcpKey),
    retainInReadme: true,
    includeTools: ["maps_textsearch", "taxi_estimate"],
    readmeToolNames: ["maps_textsearch", "taxi_estimate"],
    transport: {
      kind: "streamable-http",
      url: `${endpointBase}?key=${config.didiMcpKey ?? "YOUR_DIDI_MCP_KEY"}`,
    },
  };
};
