# Agent 安装指南

本文写给 LLM Agent。目标是在本地完成 Travel MCP Gateway 的依赖安装、环境配置、构建验证，并给用户生成可复制到 MCP 客户端的配置。

## 给用户的确认问题

开始前，先向用户确认以下信息：

1. 是否已安装 Node.js 与 npm。
2. 是否已安装 Python。
3. 是否优先使用 `uv` 安装 `FlightTicketMCP` 依赖；如果没有 `uv`，改用 `pip`。
4. 高德 Key：`AMAP_MAPS_API_KEY`。
5. 滴滴 Key：`DIDI_MCP_KEY`。
6. 可选：VariFlight Key：`VARIFLIGHT_API_KEY`，用于航班查询备选数据源。

不要在回复中打印真实密钥。不要提交 `.env`、日志或本机绝对路径。

## 1. 检查运行环境

在仓库根目录运行：

```bash
node --version
npm --version
python --version
```

如果用户希望使用 `uv`：

```bash
uv --version
```

缺少 Node.js、npm 或 Python 时，先让用户安装对应工具，再继续。

## 2. 安装根项目依赖

```bash
npm install
```

## 3. 安装航班子项目依赖

优先使用 `uv`：

```bash
cd FlightTicketMCP
uv venv
uv pip install -r requirements.txt
cd ..
```

如果没有 `uv`，使用 `pip`：

```bash
cd FlightTicketMCP
pip install -r requirements.txt
cd ..
```

也可以按用户环境使用：

```bash
cd FlightTicketMCP
pip install -e .
cd ..
```

## 4. 生成环境变量文件

从模板生成根目录 `.env`：

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

macOS / Linux：

```bash
cp .env.example .env
```

然后把用户提供的真实值写入 `.env`：

```dotenv
AMAP_MAPS_API_KEY=用户提供的高德Key
DIDI_MCP_KEY=用户提供的滴滴Key

# Optional overrides
TRAIN_12306_ENTRY=./12306-mcp/build/index.js
FLIGHT_MCP_PROJECT_ROOT=./FlightTicketMCP
FLIGHT_MCP_PYTHON_COMMAND=python
```

航班备选数据源需要单独配置 `FlightTicketMCP/.env`。如果用户提供了 `VARIFLIGHT_API_KEY`，从模板复制：

Windows PowerShell：

```powershell
Copy-Item FlightTicketMCP/.env.example FlightTicketMCP/.env
```

macOS / Linux：

```bash
cp FlightTicketMCP/.env.example FlightTicketMCP/.env
```

再写入：

```dotenv
VARIFLIGHT_API_KEY=用户提供的VariFlightKey
```

如果用户没有 VariFlight Key，可以跳过该值；航班查询会优先尝试携程网页航班列表。

## 5. 构建并验证

```bash
npm run build
```

验证服务入口存在：

```bash
node build/index.js
```

这是 stdio MCP 服务。启动后通常会等待 MCP 客户端通信；手动验证时确认没有立即抛出缺失依赖、语法错误或环境读取错误即可。

## 6. MCP 客户端配置

如果客户端工作目录就是仓库根目录，可以使用相对路径：

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

如果客户端不是从仓库根目录启动，把 `args` 改成 `build/index.js` 的绝对路径。

OpenCode 项目级配置示例位于 `.opencode/opencode.json`。将其中占位符替换为真实密钥，或在用户级 OpenCode 配置里注册同一个 MCP。

## 7. 排障

遇到 MCP 连接、鉴权、schema 或返回格式问题时：

1. 检查 `.env` 和客户端配置中的变量名是否一致。
2. 检查 `npm run build` 是否成功。
3. 检查 `FlightTicketMCP` 依赖是否已安装。
4. 高德、滴滴、VariFlight 的 Key 问题参考 `.opencode/skills/error-processing/mcp-error-references.json`。
5. 不要输出完整环境变量、token、真实密钥或私人账号数据。
