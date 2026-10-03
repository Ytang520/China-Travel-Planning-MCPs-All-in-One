import type { RuntimeConfig } from "../../../config.js";
import type { DownstreamProviderDefinition } from "../../../types.js";

export const createCtripHotelProvider = (
  config: RuntimeConfig,
): DownstreamProviderDefinition => {
  return {
    python: {
      workspaceRoot: config.workspaceRoot,
      projectRoot: config.hotelProjectRoot,
      explicitCommand: config.inheritedEnv.HOTEL_MCP_PYTHON_COMMAND,
      variable: "HOTEL_MCP_PYTHON_COMMAND",
      modules: ["fastmcp", "pydantic", "requests", "DrissionPage", "psutil"],
    },
    domain: "hotel",
    providerName: "ctrip",
    displayName: "Ctrip Hotel MCP Server",
    description:
      "Ctrip hotel search via web scraping. Requires Ctrip login and explicit risk consent (HOTEL_MCP_CONSENT=yes); searches are throttled by a random 15s-3min interval to reduce ban risk.",
    enabled: true,
    retainInReadme: true,
    requestTimeout: 960_000, // Login has its own 930s budget; search is a separate tool call.
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
