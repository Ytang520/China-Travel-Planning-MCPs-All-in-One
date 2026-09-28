import type { RuntimeConfig } from "../../config.js";
import type { DownstreamProviderDefinition } from "../../types.js";
import { createCtripHotelProvider } from "./ctrip/provider.js";

export const getHotelProviders = (
  config: RuntimeConfig,
): DownstreamProviderDefinition[] => {
  return [createCtripHotelProvider(config)];
};
