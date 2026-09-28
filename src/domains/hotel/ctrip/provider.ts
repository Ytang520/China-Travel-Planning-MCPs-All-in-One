import type { RuntimeConfig } from "../../../config.js";
import type { DownstreamProviderDefinition } from "../../../types.js";

export const createCtripHotelProvider = (
  config: RuntimeConfig,
): DownstreamProviderDefinition => {
  return {
    domain: "hotel",
    providerName: "ctrip",
    displayName: "Ctrip Hotel MCP Server",
    description:
      "Ctrip hotel search via web scraping. Requires Ctrip login and explicit risk consent (HOTEL_MCP_CONSENT=yes); searches are throttled by a random 30s-5min interval to reduce ban risk.",
    enabled: true,
    retainInReadme: true,
    requestTimeout: 600_000, // 10 min — browser scraping + optional rate-limit wait
    transport: {
      kind: "stdio",
      command: config.hotelPythonCommand,
      args: ["-m", "hotel_ticket_mcp_server"],
      cwd: config.hotelProjectRoot,
      env: {
        ...config.inheritedEnv,
        MCP_TRANSPORT: "stdio",
        PYTHONUTF8: "1",
      },
    },
  };
};
