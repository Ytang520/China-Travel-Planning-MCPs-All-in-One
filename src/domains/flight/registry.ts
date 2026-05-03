import type { RuntimeConfig } from "../../config.js";
import type { DownstreamProviderDefinition } from "../../types.js";
import { createFlightTicketProvider } from "./flight_ticket_mcp_server/provider.js";

export const getFlightProviders = (
  config: RuntimeConfig,
): DownstreamProviderDefinition[] => {
  return [createFlightTicketProvider(config)];
};
