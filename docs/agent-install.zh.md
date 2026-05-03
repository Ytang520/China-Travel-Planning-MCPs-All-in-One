# Agent 安装指南

本文写给 LLM Agent。目标是在本地完成 Travel MCP Gateway 的依赖安装、环境配置、构建验证，并给用户生成可复制到 MCP 客户端的配置。

![出行 MCP 统一网关 总体架构](assets/workflow.png)

## 给用户的确认问题

开始前向用户确认以下信息。**不要在回复中打印真实密钥；不要提交 `.env`、日志或本机绝对路径。**

### MCP 宿主应用（必须先确认）

在开始安装前，确认用户将在何种应用中启用本 MCP（§6 将按该项分支编写配置）：

- **OpenCode** / **Cursor** / **Claude Code** / **其它**
- 若选 **其它**：请用户提供 **准确产品名称**。你必须检索该产品 **官方 MCP 配置文档**（配置文件路径、根字段名、`stdio` 的 `command`/`args` 形态等），再生成配置；**禁止臆测**（例如勿把 OpenCode 的 `environment`/`command` 数组写入仅支持 `mcpServers` + `env` 的宿主）。

### 运行时（缺失时请引导官方安装）

1. **Node.js 与 npm**：请在仓库根目录尝试 `node --version`、`npm --version`。若命令不存在或报错，引导用户从 **[Node.js 官网](https://nodejs.org/)** 下载并安装 **LTS**（安装程序自带 npm）；安装完成后建议 **重新打开终端** 再验证。
2. **Python**：尝试 `python --version`（部分环境为 `py -V` 或 `python3 --version`）。若不可用，引导用户从 **[Python 官网](https://www.python.org/downloads/)** 下载安装包；Windows 安装时建议勾选 **Add python.exe to PATH**，完成后重新打开终端再验证。

### Python 依赖安装方式

3. **优先建议使用 uv**：推荐通过 **[uv](https://docs.astral.sh/uv/)** 为 `FlightTicketMCP` 创建虚拟环境并安装依赖（解析与安装速度快、环境更易复现）。若用户尚未安装 uv，可协助其按官方文档安装；若用户坚持使用传统方式，则改用 `pip install -r requirements.txt` 或 `pip install -e .`。

### API Key（用户暂未持有时请引导申请）

4. **`AMAP_MAPS_API_KEY`（高德地图 MCP）**：若用户暂无密钥，引导其在 **[高德 MCP Server 概述](https://lbs.amap.com/api/mcp-server/summary)** 按官方流程申请与配置。可让其参考讲解视频：[哔哩哔哩 · 高德 MCP（BV1qwZqYJEUG）](https://www.bilibili.com/video/BV1qwZqYJEUG/)。
5. **`DIDI_MCP_KEY`（滴滴出行 MCP）**：若用户暂无密钥，引导其在 **[滴滴 MCP 开放平台](https://mcp.didichuxing.com/)** 申请。可让其参考讲解视频：[哔哩哔哩 · 滴滴出行 MCP（BV1vpb7zaECv）](https://www.bilibili.com/video/BV1vpb7zaECv/)。
6. **`VARIFLIGHT_API_KEY`（可选，航班备选数据源）**：若用户需要 VariFlight 备选而暂无密钥，引导其在 **[VariFlight MCP](https://mcp.variflight.com/)** 申请；未配置时仍可优先走携程网页数据源（见 FlightTicketMCP 行为说明）。

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

缺少 Node.js、npm 或 Python 时，**勿猜测安装路径**：请先完成上文「给用户的确认问题」中的官方安装指引，让用户重新打开终端后，再重复本节命令验证。

## 2. 安装根项目依赖

```bash
npm install
```

## 3. 安装航班子项目依赖

建议与上文「Python 依赖安装方式」一致：**优先使用 uv**；仅在用户明确要求时使用 pip。

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

在完成 §5 构建后，按用户在 **「MCP 宿主应用」** 中的选择执行本节。**OpenCode** 使用字段 `mcp` / `environment` / `command`（数组）；**Cursor** 与 **Claude Code**（`.mcp.json`）通常使用 **`mcpServers` + `env`**，三者勿混用。

可复制占位示例见目录 **[docs/mcp-client-examples/](mcp-client-examples/)**（与本文同级：`mcp-client-examples/README.md` 含索引与官方文档链接）。

### 6.1 通用约定

- 网关为 **stdio** 进程：`node` + `build/index.js`。
- 环境变量名应与 `.env` / 宿主侧注入保持一致：`AMAP_MAPS_API_KEY`、`DIDI_MCP_KEY`、`FLIGHT_MCP_PYTHON_COMMAND`；可选 `TRAIN_12306_ENTRY`、`FLIGHT_MCP_PROJECT_ROOT`（见 [.env.example](../.env.example)）。
- 若宿主拉起 MCP 时 **cwd 不是仓库根**：将 `./build/index.js`（及相关 `./12306-mcp`、`./FlightTicketMCP`）改为 **绝对路径**。

### 6.2 Cursor

1. 阅读官方文档：[Cursor · MCP](https://cursor.com/docs/context/mcp)。
2. 基于 [cursor.mcp.json.example](mcp-client-examples/cursor.mcp.json.example) 在项目根创建或合并 **`.cursor/mcp.json`**（或与用户目录全局配置合并，优先级以文档为准）。
3. 替换占位密钥（或由宿主从安全存储读取）；保存后按 Cursor 说明重启或刷新 MCP。

### 6.3 Claude Code

1. 阅读官方文档：[Connect Claude Code to tools via MCP](https://docs.claude.com/en/docs/claude-code/mcp.md)。
2. 将 [claude-code.mcp.json.example](mcp-client-examples/claude-code.mcp.json.example) 复制为仓库根 **`.mcp.json`**（project scope），或按文档使用 `claude mcp add --transport stdio ... --scope project`（示例命令见 [mcp-client-examples/README.md](mcp-client-examples/README.md)）。
3. 注意 Claude Code 对 project MCP 的 **审批与 `--` 选项顺序**；引导用户完成 IDE 内授权。
4. 占位密钥处理方式同 §6.2。

### 6.4 OpenCode

1. OpenCode **不使用**与 Cursor 相同的顶层 **`mcpServers`**。请在配置文件中使用 **`mcp.<serverId>`**，并使用 **`environment`**（不是 `env`）、**`command`** 为 **字符串数组**（参见 [.opencode/opencode.json](../.opencode/opencode.json)）。
2. 将 [opencode.mcp.fragment.json](mcp-client-examples/opencode.mcp.fragment.json) **合并到用户的 `mcp` 对象内**（与现有条目并列）。
3. 可选用 `$schema`: `https://opencode.ai/config.json`。占位密钥处理方式同 §6.2。

### 6.5 其它宿主

1. 用用户给出的 **准确产品名** 检索其官方 MCP / 插件配置说明。
2. 核对：**配置文件路径**、**根 JSON 结构**、`stdio` 服务器字段名（是否与 `mcpServers` 一致）。
3. 生成最小可用配置交给用户粘贴到本地；**勿**将含真实密钥的片段提交到本仓库。

## 7. 排障

遇到 MCP 连接、鉴权、schema 或返回格式问题时：

1. 检查 `.env` 和客户端配置中的变量名是否一致。
2. 检查 `npm run build` 是否成功。
3. 检查 `FlightTicketMCP` 依赖是否已安装。
4. 高德、滴滴、VariFlight 的 Key 问题参考 `.opencode/skills/error-processing/mcp-error-references.json`。
5. 不要输出完整环境变量、token、真实密钥或私人账号数据。
