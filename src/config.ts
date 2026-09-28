import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentFilePath = fileURLToPath(import.meta.url);
const currentDir = dirname(currentFilePath);

const normalizeEnv = (
  env: NodeJS.ProcessEnv | Record<string, string | undefined>,
) => {
  return Object.fromEntries(
    Object.entries(env).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
};

export type RuntimeConfig = {
  workspaceRoot: string;
  projectName: string;
  projectVersion: string;
  inheritedEnv: Record<string, string>;
  train12306Entry: string;
  flightProjectRoot: string;
  flightPythonCommand: string;
  hotelProjectRoot: string;
  hotelPythonCommand: string;
  amapApiKey?: string;
  didiMcpKey?: string;
};

const readProjectVersion = (workspaceRoot: string) => {
  const packageJsonPath = resolve(workspaceRoot, "package.json");
  const packageJson = JSON.parse(readFileSync(packageJsonPath, "utf8")) as {
    version?: string;
  };

  if (!packageJson.version) {
    throw new Error(`Missing version in ${packageJsonPath}`);
  }

  return packageJson.version;
};

export const getRuntimeConfig = (): RuntimeConfig => {
  const workspaceRoot = resolve(currentDir, "..");

  return {
    workspaceRoot,
    projectName: "travel-mcp-gateway",
    projectVersion: readProjectVersion(workspaceRoot),
    inheritedEnv: normalizeEnv(process.env),
    train12306Entry:
      process.env.TRAIN_12306_ENTRY ??
      resolve(workspaceRoot, "12306-mcp", "build", "index.js"),
    flightProjectRoot:
      process.env.FLIGHT_MCP_PROJECT_ROOT ??
      resolve(workspaceRoot, "FlightTicketMCP"),
    flightPythonCommand: process.env.FLIGHT_MCP_PYTHON_COMMAND ?? "python",
    hotelProjectRoot:
      process.env.HOTEL_MCP_PROJECT_ROOT ??
      resolve(workspaceRoot, "HotelTicketMCP"),
    hotelPythonCommand: process.env.HOTEL_MCP_PYTHON_COMMAND ?? "python",
    amapApiKey: process.env.AMAP_MAPS_API_KEY,
    didiMcpKey: process.env.DIDI_MCP_KEY,
  };
};
