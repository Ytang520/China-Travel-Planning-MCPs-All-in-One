# 出行 MCP 统一网关

**语言:** [English](README.en.md)

面向出行场景的单一 MCP 入口：在一条 stdio 连接上聚合 **火车**（12306）、**航班**（FlightTicketMCP）、**地图**（官方高德 MCP）与 **打车费用预估**（滴滴）。业务域固定为 `train`、`flight`、`map`、`taxi`，便于继续扩展。

## 架构概览

![出行 MCP 统一网关 总体架构](docs/assets/workflow.png)

## 功能概要

- **统一网关**：客户端只需拉起一个stdio MCP 进程，即可使用火车票务（12306）、航班（FlightTicketMCP）、地图（高德官方 MCP）与网约车费用预估（滴滴）等能力，降低多进程与多配置心智负担。
- **易于扩展**：下游能力按固定域划分并在各域 `registry.ts` 注册；新增 provider 时遵循 `src/domains/` 约定即可（详见 [docs/extending.zh.md](docs/extending.zh.md)）。
- **排障辅助**：提供 OpenCode 项目级 error-processing skill（[SKILL.md](.opencode/skills/error-processing/SKILL.md)），并结合 [mcp-error-references.json](.opencode/skills/error-processing/mcp-error-references.json) 对高德、滴滴、VariFlight 等场景的公开文档做语义索引；在不泄露密钥的前提下，辅助归类 MCP 连接、鉴权、schema 与返回格式等问题。

## 让 Agent 安装

把下面内容复制给你的 LLM Agent（Cursor、Claude Code、OpenCode 等），让它按指南完成依赖安装、密钥配置、构建验证和 MCP 客户端配置：

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

按宿主拆分的可复制示例见 **[docs/mcp-client-examples/README.md](docs/mcp-client-examples/README.md)**（Cursor、Claude Code、OpenCode）。

以下为与 **Cursor** 等项目级 **`mcpServers`** 配置兼容的最小片段（假定宿主将 MCP 子进程的 cwd 设为仓库根；否则请将 `args` 改为 `build/index.js` 的绝对路径）：

```json
{
  "mcpServers": {
    "travel-mcp-gateway": {
      "command": "node",
      "args": ["./build/index.js"],
      "env": {
        "AMAP_MAPS_API_KEY": "YOUR_AMAP_MAPS_API_KEY",
        "DIDI_MCP_KEY": "YOUR_DIDI_MCP_KEY",
        "FLIGHT_MCP_PYTHON_COMMAND": "python",
        "TRAIN_12306_ENTRY": "./12306-mcp/build/index.js",
        "FLIGHT_MCP_PROJECT_ROOT": "./FlightTicketMCP"
      }
    }
  }
}
```

## 其他

### 工具命名约定

聚合后的工具名形如：`{domain}_{providerName}_{toolName}`，例如 `train_12306_get_tickets`、`map_amap_maps_geo`、`taxi_didi_taxi_estimate`。下游可为本地 **stdio** 子进程或远程 **streamable-http**，由各 `provider.ts` 声明。

### 滴滴打车费用预估链路

费用预估按顺序调用：

1. `taxi_didi_maps_textsearch`
2. `taxi_didi_taxi_estimate`

`estimate` 使用的经纬度须来自滴滴 `maps_textsearch`（密钥与接口说明见 [滴滴 MCP](https://mcp.didichuxing.com/)）。不使用高德 MCP 返回的坐标。

对于地理编码、POI、路径、天气等非打车预估场景优先使用 `map/amap`。参考：[高德 MCP Server 概述](https://lbs.amap.com/api/mcp-server/summary)。

### 航班查询

航班查询（默认 `auto`）：优先抓取携程网页航班列表；失败或缺少抓取依赖时，若已在 `FlightTicketMCP/.env` 配置 `VARIFLIGHT_API_KEY`，可回退到 VariFlight MCP

### Gateway MCP Server 与模型上下文的关系

网关进程启动时会遍历各业务域的 provider，调用 `connectAndRegisterProvider`，把已成功连接且按规则保留的下游工具，统一注册到同一个 MCP Server（见 `src/index.ts`）

若某个下游连接失败，该 provider 的工具不会出现在清单里（启动日志会有 `[gateway] failed to connect provider`）。

## 致谢

本仓库在能力与设计上参考或继承了下列开源项目与公开材料（上游许可证以其各自仓库为准）：

- **仓库**
  - [12306-mcp](https://github.com/Joooook/12306-mcp)
  - [FlightTicketMCP](https://github.com/xiaonieli7/FlightTicketMCP)
- **其他参考材料**
  - [哔哩哔哩 · BV1xFhrzpEDd](https://www.bilibili.com/video/BV1xFhrzpEDd/)
  - [哔哩哔哩 · BV1AoYZzKEvb](https://www.bilibili.com/video/BV1AoYZzKEvb/)