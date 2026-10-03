# 酒店登录交互 / Hotel login interaction

酒店查询需要登录时会返回 `LOGIN_REQUIRED`，缺少 cookie 时在限速等待和浏览器启动之前返回。调用 `hotel_ctrip_login` 后，支持 MCP form elicitation 的客户端会展示“打开登录页 / 取消本次酒店查询”。选择打开后，项目管理的可见浏览器直接进入 `https://passport.ctrip.com/user/login`，并带酒店页面返回地址。密码、验证码与扫码操作都在携程页面完成。

## Agent 客户端

1. 保存原始酒店搜索参数，收到 `LOGIN_REQUIRED` 后使用返回的 `next_arguments` 调用 `hotel_ctrip_login`。
2. 网关在支持的客户端使用原生 MCP elicitation。若返回 `USER_INTERACTION_REQUIRED`，用宿主的 `AskUserQuestion` 或原生用户输入工具展示 `user_action.question/options`。Codex 中可使用 `request_user_input_async` 或可用的 `request_user_input`。必须等待实际回答；不要把授权执行代码、错误消息或经过一段时间解释为用户已经选择登录。
3. 用户选择打开后，以 `user_action: "open_login"` 和原 `return_url` 再调用登录；取消则传 `user_action: "cancel"` 或结束本次酒店查询。已取得用户选择时不会再次弹出 elicitation。
4. 登录成功后，使用 `resume_request.arguments` 或原始调用参数重试酒店查询一次。再次需要登录时停止，不反复弹窗。登录、查询和恢复查询是独立工具调用。

普通日志不能代替交互问题。没有 elicitation、也没有宿主用户输入工具的客户端必须显示需用户操作的结果并停止；服务端无法为这种客户端制造原生弹窗。

## 命令行与 Agent 运行脚本

交互终端：`node scripts/mcp-test.mjs hotel`。需要登录时出现终端选择问题；`login` 模式也会先提问。登录成功后校验既有武汉酒店实例的实际记录。

Agent 在非交互终端中运行脚本时，若收到 `USER_INTERACTION_REQUIRED`，先在聊天客户端调用用户输入工具并等待回答，再运行对应命令：

```sh
# 仅在用户已选择“打开登录页”后：
node scripts/mcp-test.mjs hotel --login-action=open_login
# 用户选择取消时：
node scripts/mcp-test.mjs login --login-action=cancel
```

该参数记录外部已取得的用户回答，不是自动确认开关。航班测试仍使用上海→北京，酒店测试仍使用武汉。

## 浏览器、状态与超时

- 登录强制显示浏览器，独立于搜索的 `HOTEL_MCP_HEADLESS` 配置。登录完成或取消后关闭本次拥有的浏览器。
- `HOTEL_MCP_PROFILE_DIR` 可指定酒店 profile（默认仍为 `HotelTicketMCP/.browser-profile`）；`HOTEL_MCP_COOKIE_FILE` 指定 cookie 文件。测试应同时使用独立位置，不清除用户现有登录资料。
- 空白页面、未知站点、页面拦截与未加载状态不会被识别为已登录。登录成功需要官方酒店页面的有效状态，并在保存 cookie 前验证；cookie 以原子替换方式保存。
- `HOTEL_MCP_LOGIN_TIMEOUT` 控制页面就绪后的等待秒数，默认及最大值 840 秒。登录流程受总预算约束，网关下游调用上限 960 秒；宿主的登录工具超时建议至少 1110 秒，以容纳提问、页面启动和清理。
- 进度通知报告打开页面、等待登录、验证和完成。客户端取消会通知登录工作线程并清理其浏览器。
- `LOGIN_STATE_UNKNOWN` 表示当前页面无法可靠判断登录态，应检查页面或稍后重试，不应自动触发重新登录。
- 登录跳转期间的页面读取异常会触发最长 20 秒的恢复等待，并受原登录总超时约束。页面读取和连接探测分别限制为最多 3 秒和 2 秒；取消请求会中止恢复。
- `LOGIN_BROWSER_CLOSED` 需要浏览器进程退出或连续两次确认原标签页消失的证据。进程身份使用 PID 与创建时间共同校验；有关联后续标签页时保留未知状态。`LOGIN_CONNECTION_LOST` 表示控制连接中断，不能据此认定浏览器已退出。
- 日志用 `hotel_login id=...` 关联一次请求，记录阶段、异常类型、连接探测结果、恢复次数、保存完成及最终 `close_reason`。客户端取消与异步通知失败分别记录为 `client_cancelled`、`async_failure`；日志不包含账号文本、完整 URL、cookie 值或原始浏览器异常内容。

浏览器回归测试使用独立临时 profile 和模拟 cookie。设置 `HOTEL_MCP_RUN_EDGE_TESTS=1` 后运行 `HotelTicketMCP/tests/test_login_edge.py` 可验证真实 Edge 的上下文失效、关闭标签页和连接中断；页面响应由本地 CDP 拦截提供，不执行真实账号登录。

## Edge 登录后在 Chrome 复用

酒店 provider 支持向项目管理的 Edge 或 Chrome 注入项目 Cookie 文件。登录成功后保存的 Cookie 保留 HttpOnly、Secure、SameSite、路径、有效期和可恢复的分区信息；会话 Cookie 不会被改成永久 Cookie，过期或无法恢复的 Cookie 不注入。旧版 Cookie 列表和 `cookies` 包装格式仍可读取。

两种浏览器使用各自独立的 `HOTEL_MCP_PROFILE_DIR`，并使用同一个明确指定的 `HOTEL_MCP_COOKIE_FILE`。例如 Edge 设置 `HOTEL_MCP_BROWSER=edge`、profile 为 `HotelTicketMCP/.browser-profile-edge`；Chrome 设置 `HOTEL_MCP_BROWSER=chrome`、profile 为 `HotelTicketMCP/.browser-profile-chrome`。这些路径建议在宿主配置中使用绝对路径。浏览器发现可能回退，因此需要严格使用 Chrome 时应把 `HOTEL_MCP_BROWSER_PATH` 设为安装的 `chrome.exe`。

复用通过保存的项目 Cookie 完成，不读取或迁移个人 Edge/Chrome 默认 profile。能否恢复当前账号由导航后的官方酒店页面登录状态决定，不能以注入未报错作为成功依据；失效则沿用 `LOGIN_REQUIRED` 流程。

`HOTEL_MCP_RUN_COOKIE_TRANSFER=1` 启用 `HotelTicketMCP/tests/test_cookie_transfer.py` 的独立 Edge→Chrome 属性测试。`HOTEL_MCP_RUN_LOCATION_LIVE=1` 启用 `test_location_live.py` 的实际携程登录复用测试；该测试使用现有项目凭据、独立临时 profile 和临时 Cookie 文件，并检查实际启动的浏览器身份。

## Chrome 登录与复用验收

在用户明确要求打开登录页后，从仓库根目录运行：

```powershell
uv run --no-project --python .venv/Scripts/python.exe python -u scripts/hotel-session-check.py --login-action=open_login
```

脚本打开全新的 Chrome，由用户在携程页面完成登录，然后验证 Cookie 写入、Chrome 新会话复用、Chrome → Edge 复用及 Edge → Chrome 回传复用。每个浏览器启动时检查实际身份及初始携程 Cookie 数量；每次复用必须确认酒店登录态并读到酒店卡片。测试浏览器关闭后删除其独立临时 profile。

登录 Cookie 保留在 `.validation/chrome-session-<时间与标识>/chrome-cookies.json`，Edge 导出的 Cookie 保留在同目录的 `edge-cookies.json`。这些文件被 Git 忽略。`report.json` 记录各项结果、浏览器身份、Cookie 数量和清理状态，不含 Cookie 值、账号或密码。脚本会检查 Chrome 原始 Cookie 文件在复用测试期间未被改写。

已有该测试保存的 Cookie 时，可以仅重跑复用检查：

```powershell
uv run --no-project --python .venv/Scripts/python.exe python -u scripts/hotel-session-check.py --reuse-only --cookie-file "<已保存的 chrome-cookies.json 的绝对路径>"
```

后续普通酒店查询可将 `HOTEL_MCP_COOKIE_FILE` 指向该文件。Cookie 是否仍有效由携程页面确认；失效时按原登录流程处理。

## English client contract

On `LOGIN_REQUIRED`, preserve the original query and call `hotel_ctrip_login` with `next_arguments`. The gateway uses native form elicitation when available. On `USER_INTERACTION_REQUIRED`, actually invoke the host's question/input tool and wait for an answer. Only then pass `user_action: "open_login"` or `"cancel"`; preserve `return_url`. Never request account credentials in chat. Retry the original query exactly once after successful login.

Noninteractive CLI execution cannot display an Agent's native question. The Agent must collect the answer itself before using `--login-action=open_login`. Unsupported clients receive an explicit action-required result instead of opening a browser and silently waiting. Native UI rendering must be verified in the actual host; protocol tests alone do not establish that UI behavior.

Protocol references: [MCP elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation), [OpenAI server instructions and elicitation](https://developers.openai.com/plugins/build/mcp-server).
