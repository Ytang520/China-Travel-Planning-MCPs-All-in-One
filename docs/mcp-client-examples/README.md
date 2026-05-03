# MCP 客户端配置示例（按宿主）

本目录提供 **stdio** 网关「出行 MCP 统一网关」在各宿主下的 JSON 占位示例。**请勿将填好真实密钥的文件提交到 Git**；密钥优先放在本地 `.env` 或由宿主安全配置注入。

## 文件一览

| 文件 | 适用宿主 | 说明 |
|------|----------|------|
| [cursor.mcp.json.example](cursor.mcp.json.example) | **Cursor** | 可复制为项目内 `.cursor/mcp.json`，或与用户目录下的全局配置合并。 |
| [claude-code.mcp.json.example](claude-code.mcp.json.example) | **Claude Code** | 可复制为仓库根目录 `.mcp.json`（project scope）；也可用 CLI 添加（见下）。 |
| [opencode.mcp.fragment.json](opencode.mcp.fragment.json) | **OpenCode** | **仅** OpenCode：内容为 `mcp` 对象下的单个 server 条目；合并进用户的 `opencode.json` / `.opencode/opencode.json` 中的 `"mcp"` 键（勿与 `mcpServers` 混用）。 |

若宿主使用 **`mcpServers` + `command` + `args` + `env`**（Cursor、Claude Code 项目 `.mcp.json`），结构与本仓库示例一致。OpenCode 使用 **`mcp.<name>.type` / `command`（数组）/ `environment`**，字段名不同。

## 路径与工作目录

- 示例中 `args` / `command` 使用 **`./build/index.js`**，假定 MCP **进程启动时的当前工作目录为仓库根**。若宿主不支持或 cwd 不是仓库根，请将条目改为 **`build/index.js` 的绝对路径**。
- 环境变量中的 `./12306-mcp/...`、`./FlightTicketMCP` 同样相对于 **仓库根**（与网关进程 cwd 一致）。

## 官方文档链接

- **Cursor** MCP：[Cursor Docs · MCP](https://cursor.com/docs/context/mcp)（项目级 `.cursor/mcp.json` 与用户级配置合并规则见文档）。
- **Claude Code** MCP：[Connect Claude Code to tools via MCP](https://docs.claude.com/en/docs/claude-code/mcp.md)
- **OpenCode** 配置：`https://opencode.ai/config.json`（与本仓库 [.opencode/opencode.json](../../.opencode/opencode.json) 中 `$schema` 一致）。

### Claude Code：等价 CLI（可选）

在项目根、选项顺序符合官方要求时，可用 stdio 注册（将占位密钥替换为实际值或使用宿主支持的变量展开）：

```bash
claude mcp add --transport stdio \
  --env AMAP_MAPS_API_KEY=YOUR_AMAP_MAPS_API_KEY \
  --env DIDI_MCP_KEY=YOUR_DIDI_MCP_KEY \
  --env FLIGHT_MCP_PYTHON_COMMAND=python \
  --env TRAIN_12306_ENTRY=./12306-mcp/build/index.js \
  --env FLIGHT_MCP_PROJECT_ROOT=./FlightTicketMCP \
  --scope project travel-mcp-gateway -- node ./build/index.js
```

具体标志与 `--` 分隔规则以 [Claude Code MCP 文档](https://docs.claude.com/en/docs/claude-code/mcp.md) 为准。

## English summary

- **Cursor**: copy `cursor.mcp.json.example` to `.cursor/mcp.json` (project) or merge into your user-level Cursor MCP config.
- **Claude Code**: copy `claude-code.mcp.json.example` to `.mcp.json` at repo root, or use `claude mcp add --transport stdio ...` per docs.
- **OpenCode**: merge `opencode.mcp.fragment.json` under the `"mcp"` key—**do not** paste this shape into an `mcpServers` file.

---

**Security**: never commit real API keys; redact secrets in logs and support chats.
