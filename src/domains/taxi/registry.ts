import type { RuntimeConfig } from "../../config.js";
import type { DownstreamProviderDefinition } from "../../types.js";
import { createDidiProvider } from "./didi/provider.js";

export const getTaxiProviders = (
  config: RuntimeConfig,
): DownstreamProviderDefinition[] => {
  return [createDidiProvider(config)];
};
