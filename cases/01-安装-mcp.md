# 案例 1：安装 Travel MCP Gateway

按 [Agent 安装指南](../docs/agent-install.zh.md) 在本仓库完成依赖安装、密钥配置、构建和 MCP 客户端配置。模型为 **ds-v4.1-flash（谷时定价）**。两次安装的起始上下文相同，差别是安装结束后是否执行指南 §8 的部署后功能测试。

| ds-v4.1-flash（谷时定价） | initial tokens | total tokens | cost | time cost |
| --- | --- | --- | --- | --- |
| 功能测试 | 43856 | 126916 | $0.0811 | ~15 min |
| 没有功能测试 | 43856 | 85753 | $0.0516 | ~10 min |

功能测试对应指南 §8：先询问是否执行，选择「是」后在仓库根目录运行 `scripts/mcp-test.mjs` 的 `config`、`train`、`flight`、`hotel`、`login`、`map`、`taxi`。其中 `flight` 与 `hotel` 会打开可见浏览器，通常需要数分钟。选择不做功能测试时，安装停在构建与配置，不跑这些验收。
