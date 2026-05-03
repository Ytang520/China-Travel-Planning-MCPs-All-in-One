import type { RuntimeConfig } from "../../config.js";
import type { DownstreamProviderDefinition } from "../../types.js";
import { createAmapProvider } from "./amap/provider.js";

export const getMapProviders = (
  config: RuntimeConfig,
): DownstreamProviderDefinition[] => {
  return [createAmapProvider(config)];
};
