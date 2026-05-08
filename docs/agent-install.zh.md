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

## 3.5 安装并构建 12306-mcp 子项目

> ⚠️ **已知问题**：12306-mcp 的 `npm run build` 通过 `run-script-os` 执行 OS 特定预构建脚本。Windows 上 `prebuild:win32` 运行 `del /q /s build\* >nul 2>&1`，当 `build/` 目录不存在（如首次构建）时可能因无匹配文件而返回非零退出码，导致后续 `tsc` 步骤被跳过。
> **解决方案**：直接使用 `npx tsc` 构建，并确保 `build/` 目录存在。

```bash
cd 12306-mcp
npm install
# 确保 build 目录存在后再运行 tsc
if (!(Test-Path build)) { New-Item -ItemType Directory -Path build | Out-Null }
npx tsc
cd ..
```

macOS / Linux 下若 npm run build 正常则无需额外处理，但若遇到同样问题可手动运行：

```bash
cd 12306-mcp
npm install
mkdir -p build
npx tsc
cd ..
```

## 4. 收集 API Key 并生成环境变量文件

> **必须交互式收集 Key**：**不要直接中断**等用户自行填写——先通过 `question` 工具逐项向用户收集，缺 Key 时引导申请链接。收集完成后写入 `.env`。

### 4.1 交互式收集 Key

按以下顺序使用 `question` 工具询问用户：

**A. AMAP Maps API Key（高德地图）**

```
question: "你有高德地图 MCP 的 API Key 吗？（⚠ 不要粘贴在聊天里）"
选项: 
  - "我有 Key，我会输入" → 用户输入值后，你将该值写入 .env 的 AMAP_MAPS_API_KEY
  - "我没有 Key，需要申请" → 输出申请链接：
    - 官方：https://lbs.amap.com/api/mcp-server/summary
    - 视频教程：https://www.bilibili.com/video/BV1qwZqYJEUG/
    - 等用户拿到 Key 后继续
```

**B. DIDI MCP Key（滴滴出行）**

```
question: "你有滴滴出行 MCP 的 API Key 吗？（⚠ 不要粘贴在聊天里）"
选项:
  - "我有 Key，我会输入" → 用户输入值后，你将该值写入 .env 的 DIDI_MCP_KEY
  - "我没有 Key，需要申请" → 输出申请链接：
    - 官方：https://mcp.didichuxing.com/
    - 视频教程：https://www.bilibili.com/video/BV1vpb7zaECv/
    - 等用户拿到 Key 后继续
```

**C. VARIFLIGHT API Key（可选）**

```
question: "你有 VariFlight API Key 吗？（可选，用于航班备选数据源）"
选项:
  - "我有 Key" → 用户输入值后，同时写入 FlightTicketMCP/.env 的 VARIFLIGHT_API_KEY
  - "跳过，不用 VariFlight" → 跳过，航班查询会优先使用携程数据源
```

### 4.2 生成 .env 文件

收集完所有 Key 后，再从模板生成并填入真实值：

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

如果用户提供了 VariFlight Key，从模板复制：

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

> **安全警告**：**永远不要在回复中打印真实密钥**；不要提交 `.env` 到 git；写文件后立刻验证 `.env` 是否在 `.gitignore` 中。

## 5. 构建根网关并验证

```bash
npm run build
```

验证服务入口存在（确认 12306-mcp 也已构建，见 §3.5）：

```bash
node build/index.js
```

这是 stdio MCP 服务。启动后通常会等待 MCP 客户端通信；确认没有立即抛出缺失依赖（如 `Cannot find module .../12306-mcp/build/index.js`）、语法错误或环境读取错误即可。若 12306-mcp 构建文件缺失，请回到 §3.5 补构建。

期望的启动日志至少应包含：
- `12306 MCP Server running on stdio`
- `Flight Ticket MCP Server 启动中`
- `[gateway] travel MCP gateway running on stdio`

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

## 8. 部署后功能测试

配置完成后，验证该网关的四个域（train / flight / map / taxi）均可用。使用网关提供的 MCP 工具执行以下测试，确保各域下游连接正常。

### 8.1 获取当前日期

调用 `travel-mcp-gateway_train_12306_get_current_date`（或 `travel-mcp-gateway_flight_flight_ticket_mcp_server_getCurrentDate`）获取当天日期 `yyyy-MM-dd`，用于后续查询。

### 8.2 测试火车票查询（train 域）

查询当天从 **上海** 到 **北京** 的高铁票：

- 工具：`travel-mcp-gateway_train_12306_get_tickets`
- 参数：`date` = 当天日期，`fromStation` = "上海"，`toStation` = "北京"，`trainFilterFlags` = "G"，`limitedNum` = 3
- 格式：`text`

预期：返回高铁车次列表。若连接失败或 `station_code` 解析有误，检查 `.env` 中 `TRAIN_12306_ENTRY` 是否指向正确的 `12306-mcp/build/index.js`。

### 8.3 测试航班查询（flight 域）

查询当天从 **上海** 到 **北京** 的航班：

- 工具：`travel-mcp-gateway_flight_flight_ticket_mcp_server_searchFlightRoutes`
- 参数：`departure_city` = "上海"，`destination_city` = "北京"，`departure_date` = 当天日期
- 格式：`text`

预期：返回航班列表。若失败，检查 `FlightTicketMCP/.venv` 是否存在以及 `FLIGHT_MCP_PYTHON_COMMAND` 是否正确。

### 8.4 测试地图工具（map 域）

调用 `travel-mcp-gateway_map_amap_maps_geo` 将 "北京南站" 解析为经纬度坐标：

- 参数：`address` = "北京南站"，`city` = "北京"

预期：返回经纬度坐标。若失败，检查 `AMAP_MAPS_API_KEY` 是否有效。

### 8.5 测试结果汇总

向用户报告四项测试结果，格式如下：

```
| 域    | 工具                        | 状态 | 备注               |
|-------|----------------------------|------|-------------------|
| train | get_tickets (上海→北京)      | ✅/❌ | 返回 N 趟车次       |
| flight| searchFlightRoutes (上海→北京)| ✅/❌ | 返回 N 个航班       |
| map   | maps_geo (北京南站)          | ✅/❌ | 坐标: lng, lat     |
```

若所有域均通过，安装成功。若任一域失败，参考 §7 排障。
