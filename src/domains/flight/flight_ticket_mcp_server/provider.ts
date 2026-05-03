import type { RuntimeConfig } from "../../../config.js";
import type { DownstreamProviderDefinition } from "../../../types.js";

export const createFlightTicketProvider = (
  config: RuntimeConfig,
): DownstreamProviderDefinition => {
  return {
    domain: "flight",
    providerName: "flight_ticket_mcp_server",
    displayName: "Flight Ticket MCP Server",
    description: "Flight search, transfer, weather, and real-time flight tools.",
    enabled: true,
    retainInReadme: true,
    transport: {
      kind: "stdio",
      command: config.flightPythonCommand,
      args: ["-m", "flight_ticket_mcp_server"],
      cwd: config.flightProjectRoot,
      env: {
        ...config.inheritedEnv,
        MCP_TRANSPORT: "stdio",
        PYTHONUTF8: "1",
      },
    },
  };
};
