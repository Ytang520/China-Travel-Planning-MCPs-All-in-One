# Travel MCP Gateway

**语言:** [English](README.md)

面向出行场景的 **单一 MCP 入口**：在一条 stdio 连接上聚合 **火车**（12306）、**航班**（FlightTicketMCP）、**地图**（官方高德 MCP）与 **打车费用预估**（滴滴）。业务域固定为 `train`、`flight`、`map`、`taxi`，便于继续扩展。

## 功能概要

- 客户端只配置 **一个** MCP 进程（适合 Cursor、Claude Desktop、OpenCode 等）
- **航班**查询（默认 `auto`）：优先抓取 **携程** 网页航班列表；失败或缺少抓取依赖时，若已在 `FlightTicketMCP/.env` 配置 `VARIFLIGHT_API_KEY`，可回退到 **VariFlight**
- 新增下游能力时按域在 `src/domains/` 注册（详见 [docs/extending.zh.md](docs/extending.zh.md)）

## 环境要求

- **Node.js**（npm）
- **Python** 及 `FlightTicketMCP` 依赖（航班子进程）

## 让 Agent 安装

把下面内容复制给你的 LLM Agent（Cursor、Claude Desktop、OpenCode 等），让它按指南完成依赖安装、密钥配置、构建验证和 MCP 客户端配置：

```text
Install and configure Travel MCP Gateway by following the instructions here:
https://raw.githubusercontent.com/Ytang520/China-Travel-Planning-MCPs-All-in-One/main/docs/agent-install.zh.md
```

也可以直接阅读 [Agent 安装指南](docs/agent-install.zh.md)。

## 快速开始

```bash
npm install
```

安装航班子项目依赖（示例使用 `uv`）：

```bash
cd FlightTicketMCP
uv venv
uv pip install -r requirements.txt
```

或使用 `pip install -r requirements.txt` / `pip install -e .`。

从模板生成 `.env`，填写密钥，然后：

```bash
cp .env.example .env
```

```bash
npm run build
node build/index.js
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `AMAP_MAPS_API_KEY` | 于 [高德 MCP Server](https://lbs.amap.com/api/mcp-server/summary) 处申请 Key，用于 `map/amap` |
| `DIDI_MCP_KEY` | 于 [滴滴 MCP](https://mcp.didichuxing.com/) 处申请 Key，用于 `taxi/didi`（地点搜索 + 费用预估） |
| `FLIGHT_MCP_PYTHON_COMMAND` | 运行 FlightTicketMCP 的 Python（默认 `python`） |
| `TRAIN_12306_ENTRY` | 可选，12306 MCP 入口脚本路径 |
| `FLIGHT_MCP_PROJECT_ROOT` | 可选，`FlightTicketMCP` 根目录 |

航班相关补充变量（含 VariFlight 备选所需的 `VARIFLIGHT_API_KEY`）见 `FlightTicketMCP/.env.example`，申请方式参考 [VariFlight MCP](https://mcp.variflight.com/)。


## MCP 客户端配置示例

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

若客户端工作目录不是仓库根目录，请将 `args` 改为 `build/index.js` 的绝对路径。

## OpenCode

示例文件：[.opencode/opencode.json](.opencode/opencode.json)，将占位符替换为真实密钥即可。

项目级错误处理 skill 位于 [.opencode/skills/error-processing/SKILL.md](.opencode/skills/error-processing/SKILL.md)，MCP 排障参考索引位于 [.opencode/skills/error-processing/mcp-error-references.json](.opencode/skills/error-processing/mcp-error-references.json)。

## 其他 (滴滴打车费用估计链路)

费用预估必须按顺序调用：

1. `taxi_didi_maps_textsearch`
2. `taxi_didi_taxi_estimate`

`estimate` 使用的经纬度须来自滴滴 `maps_textsearch`（密钥与接口说明见 [滴滴 MCP](https://mcp.didichuxing.com/)）。**不使用高德 MCP 返回的坐标**。

对于地理编码、POI、路径、天气等 **非打车预估** 场景优先使用 **`map/amap`**。参考：[高德 MCP Server 概述](https://lbs.amap.com/api/mcp-server/summary)。


## 文档

- **Agent 安装指南：** [docs/agent-install.zh.md](docs/agent-install.zh.md)（中文）· [docs/agent-install.md](docs/agent-install.md)（English）
- **完整工具列表、目录约定、如何新增子 MCP、OpenCode 与错误处理 skill：** [docs/extending.zh.md](docs/extending.zh.md)（中文）· [docs/extending.md](docs/extending.md)（English）
