export type DomainName = "train" | "flight" | "map" | "taxi";

export type StdioTransportConfig = {
  kind: "stdio";
  command: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
};

export type StreamableHttpTransportConfig = {
  kind: "streamable-http";
  url: string;
  requestHeaders?: Record<string, string>;
};

export type ProviderTransportConfig =
  | StdioTransportConfig
  | StreamableHttpTransportConfig;

export type DownstreamToolDefinition = {
  name: string;
  description?: string;
  inputSchema: {
    type: "object";
    properties?: Record<string, unknown>;
    required?: string[];
    [key: string]: unknown;
  };
  title?: string;
  annotations?: {
    title?: string;
    readOnlyHint?: boolean;
    destructiveHint?: boolean;
    idempotentHint?: boolean;
    openWorldHint?: boolean;
  };
};

export type DownstreamProviderDefinition = {
  domain: DomainName;
  providerName: string;
  displayName: string;
  description: string;
  enabled: boolean;
  retainInReadme: boolean;
  transport: ProviderTransportConfig;
  /** MCP request timeout in ms for tool calls. Default: 60000 (60s). Set higher for long-running tools like flight scraping. */
  requestTimeout?: number;
  includeTools?: string[];
  excludeTools?: string[];
  readmeToolNames?: string[];
};

export type RegisteredGatewayTool = {
  gatewayName: string;
  downstreamName: string;
  description?: string;
};

export type ProviderConnectionResult = {
  provider: DownstreamProviderDefinition;
  tools: DownstreamToolDefinition[];
  registeredTools: RegisteredGatewayTool[];
};

export type GatewayToolInventory = Record<
  DomainName,
  Array<{
    providerName: string;
    displayName: string;
    description: string;
    tools: RegisteredGatewayTool[];
  }>
>;
