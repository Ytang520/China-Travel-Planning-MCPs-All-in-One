import type { RuntimeConfig } from "../../config.js";
import type { DownstreamProviderDefinition } from "../../types.js";
import { createTrain12306Provider } from "./12306/provider.js";

export const getTrainProviders = (
  config: RuntimeConfig,
): DownstreamProviderDefinition[] => {
  return [createTrain12306Provider(config)];
};
