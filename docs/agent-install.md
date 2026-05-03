# Agent Installation Guide

This guide is for LLM agents. The goal is to install dependencies, configure environment files, build the Travel MCP Gateway, and prepare MCP client configuration for the user.

![Unified Travel MCP Gateway overview](assets/workflow.png)

## Questions for the user

Ask for everything below **before** making changes. **Never paste live secrets** into chat. Do **not** commit `.env`, logs, or machine-local paths.

### Runtimes (guide installs when missing)

1. **Node.js and npm**: From the repo root, try `node --version` and `npm --version`. If either fails, ask the user to install **Node.js LTS** from **[https://nodejs.org/](https://nodejs.org/)** (npm ships with it), then **restart the terminal** and re-run these checks.
2. **Python**: Try `python --version`, `python3 --version`, or on Windows `py -V`. If unavailable, ask the user to install Python from **[https://www.python.org/downloads/](https://www.python.org/downloads/)** (enable **Add python.exe to PATH** on Windows), restart the terminal, and verify again.

### Python dependency tooling

3. **Prefer uv**: Recommend **[uv](https://docs.astral.sh/uv/)** for the `FlightTicketMCP` virtual environment—it resolves installs quickly and keeps environments reproducible. Help install uv if needed; otherwise fall back to `pip install -r requirements.txt` or `pip install -e .`.

### API keys (help users obtain keys when absent)

4. **`AMAP_MAPS_API_KEY` (Amap maps MCP)**: If missing, point users to **[Amap MCP Server overview](https://lbs.amap.com/api/mcp-server/summary)**. Reference walk-through video (Chinese): [Bilibili · Amap MCP (BV1qwZqYJEUG)](https://www.bilibili.com/video/BV1qwZqYJEUG/?spm_id_from=333.337.search-card.all.click&vd_source=142b6836e6a2c5bbefbe6f7d373be844).
5. **`DIDI_MCP_KEY` (DiDi MCP)**: If missing, point users to **[DiDi MCP](https://mcp.didichuxing.com/)**. Reference walk-through video (Chinese): [Bilibili · DiDi MCP (BV1vpb7zaECv)](https://www.bilibili.com/video/BV1vpb7zaECv/?spm_id_from=333.337.search-card.all.click&vd_source=142b6836e6a2c5bbefbe6f7d373be844).
6. **`VARIFLIGHT_API_KEY` (optional flight fallback)**: If VariFlight fallback is desired but no key exists, ask users to apply via **[VariFlight MCP](https://mcp.variflight.com/)**. Leaving it unset still allows the Ctrip-first path described in FlightTicketMCP.

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

If Node.js, npm, or Python is missing, **do not guess paths**: follow the installation guidance in **Questions for the user**, ask the user to restart the terminal, then rerun this section’s checks.

## 2. Install root dependencies

```bash
npm install
```

## 3. Install flight provider dependencies

Stay aligned with **Prefer uv** above: **try uv first**; fall back to pip only when the user insists.

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
