import type { DownstreamProviderDefinition } from "../../../types.js";
import type { RuntimeConfig } from "../../../config.js";

export const createTrain12306Provider = (
  config: RuntimeConfig,
): DownstreamProviderDefinition => {
  return {
    domain: "train",
    providerName: "12306",
    displayName: "12306 MCP",
    description: "12306 train ticket search and route tools.",
    enabled: true,
    retainInReadme: true,
    transport: {
      kind: "stdio",
      command: "node",
      args: [config.train12306Entry],
      cwd: config.workspaceRoot,
      env: config.inheritedEnv,
    },
  };
};
