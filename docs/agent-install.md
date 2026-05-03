# Agent Installation Guide

This guide is for LLM agents. The goal is to install dependencies, configure environment files, build the Travel MCP Gateway, and prepare MCP client configuration for the user.

## Questions for the user

Before changing anything, ask the user for:

1. Whether Node.js and npm are installed.
2. Whether Python is installed.
3. Whether to use `uv` for `FlightTicketMCP` dependencies; if not available, use `pip`.
4. Amap key: `AMAP_MAPS_API_KEY`.
5. DiDi key: `DIDI_MCP_KEY`.
6. Optional VariFlight key: `VARIFLIGHT_API_KEY`, used as a fallback flight data source.

Do not print real secrets in chat. Do not commit `.env`, logs, or machine-specific absolute paths.

## 1. Check the runtime

Run these commands from the repository root:

```bash
node --version
npm --version
python --version
```

If the user wants `uv`:

```bash
uv --version
```

If Node.js, npm, or Python is missing, ask the user to install it before continuing.

## 2. Install root dependencies

```bash
npm install
```

## 3. Install flight provider dependencies

Prefer `uv`:

```bash
cd FlightTicketMCP
uv venv
uv pip install -r requirements.txt
cd ..
```

If `uv` is unavailable, use `pip`:

```bash
cd FlightTicketMCP
pip install -r requirements.txt
cd ..
```

Depending on the user's Python environment, this is also valid:

```bash
cd FlightTicketMCP
pip install -e .
cd ..
```

## 4. Create environment files

Create the root `.env` from the template:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

Then write the user's real values to `.env`:

```dotenv
AMAP_MAPS_API_KEY=user_amap_key
DIDI_MCP_KEY=user_didi_key

# Optional overrides
TRAIN_12306_ENTRY=./12306-mcp/build/index.js
FLIGHT_MCP_PROJECT_ROOT=./FlightTicketMCP
FLIGHT_MCP_PYTHON_COMMAND=python
```

The optional flight fallback is configured in `FlightTicketMCP/.env`. If the user provides `VARIFLIGHT_API_KEY`, copy the template:

Windows PowerShell:

```powershell
Copy-Item FlightTicketMCP/.env.example FlightTicketMCP/.env
```

macOS / Linux:

```bash
cp FlightTicketMCP/.env.example FlightTicketMCP/.env
```

Then set:

```dotenv
VARIFLIGHT_API_KEY=user_variflight_key
```

If the user does not have a VariFlight key, leave it unset. Flight search tries Ctrip web flight listings first.

## 5. Build and verify

```bash
npm run build
```

Verify that the server entrypoint starts:

```bash
node build/index.js
```

This is a stdio MCP server. During manual verification it may wait for MCP client messages; the important part is that it does not immediately fail because of missing dependencies, syntax errors, or environment-loading errors.

## 6. MCP client configuration

If the client starts from the repository root, relative paths are fine:

```json
{
  "mcpServers": {
    "travel-mcp-gateway": {
      "command": "node",
      "args": ["./build/index.js"],
      "env": {
        "AMAP_MAPS_API_KEY": "YOUR_AMAP_MAPS_API_KEY",
        "DIDI_MCP_KEY": "YOUR_DIDI_MCP_KEY",
        "FLIGHT_MCP_PYTHON_COMMAND": "python"
      }
    }
  }
}
```

If the client does not use the repository root as its working directory, change `args` to the absolute path of `build/index.js`.

The OpenCode project example lives at `.opencode/opencode.json`. Replace placeholders with real keys, or register the same MCP in the user's OpenCode config.

## 7. Troubleshooting

For MCP connection, authentication, schema, or response-format issues:

1. Check that `.env` and the client config use the same variable names.
2. Check that `npm run build` succeeds.
3. Check that `FlightTicketMCP` dependencies are installed.
4. For Amap, DiDi, and VariFlight key issues, consult `.opencode/skills/error-processing/mcp-error-references.json`.
5. Never print full environment dumps, tokens, real secrets, or private account data.
