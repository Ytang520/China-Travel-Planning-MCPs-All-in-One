import type { RuntimeConfig } from "../../../config.js";
import type { DownstreamProviderDefinition } from "../../../types.js";

export const createFlightTicketProvider = (
  config: RuntimeConfig,
): DownstreamProviderDefinition => {
  return {
    domain: "flight",
    providerName: "flight_ticket_mcp_server",
    displayName: "Flight Ticket MCP Server",
    description: "Flight search, weather, and real-time flight tools.",
    enabled: true,
    retainInReadme: true,
    // Hidden: direct flights only; the transfer tool relies on an unstable
    // selenium scraping chain.
    excludeTools: ["getTransferFlightsByThreePlace"],
    requestTimeout: 600_000, // 10 min — Ctrip scraping via visible browser can take 3-8 min
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
