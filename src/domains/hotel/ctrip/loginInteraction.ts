import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { RequestHandlerExtra } from "@modelcontextprotocol/sdk/shared/protocol.js";
import { ElicitResultSchema, type CallToolResult, type ServerRequest, type ServerNotification } from "@modelcontextprotocol/sdk/types.js";

export const HOTEL_LOGIN_INSTRUCTIONS =
  "On hotel LOGIN_REQUIRED, call hotel_ctrip_login; it requests user interaction before opening the login page. " +
  "On USER_INTERACTION_REQUIRED, use AskUserQuestion or your native user-input tool (Codex: request_user_input_async/request_user_input) with the supplied question. " +
  "Wait for the user's answer; pass user_action=open_login only for an affirmative answer, or cancel otherwise. " +
  "After successful login, retry the original hotel query exactly once. Never ask for passwords or verification codes in chat.";

export const LOGIN_QUESTION = "当前酒店查询需要携程登录。选择“打开登录页”后，请在浏览器中完成登录；系统会自动检测，随后继续原酒店查询。";
export const LOGIN_OPTIONS = ["打开登录页", "取消本次酒店查询"];

type Extra = RequestHandlerExtra<ServerRequest, ServerNotification>;

export function hotelPayload(result: CallToolResult): Record<string, unknown> | undefined {
  for (const item of result.content) {
    if (item.type !== "text") continue;
    try {
      const data = JSON.parse(item.text);
      if (data && typeof data === "object" && !Array.isArray(data)) return data;
    } catch { /* Another content block may contain the payload. */ }
  }
  return result.structuredContent;
}

const response = (payload: Record<string, unknown>): CallToolResult => ({
  content: [{ type: "text", text: JSON.stringify(payload) }],
  structuredContent: payload,
  isError: payload.status === "error",
});

export function interactionRequired(args: Record<string, unknown> = {}): CallToolResult {
  return response({ status: "error", error_code: "USER_INTERACTION_REQUIRED",
    message: "请先使用客户端的提问工具提醒用户并等待回答，再调用登录工具。尚未打开浏览器。",
    user_action: { question: LOGIN_QUESTION, options: LOGIN_OPTIONS,
      instruction: "Use AskUserQuestion or an available native user-input tool; do not treat this message as a user answer.",
      next_tool: "hotel_ctrip_login", accept_arguments: {
        ...(typeof args.return_url === "string" ? { return_url: args.return_url } : {}), user_action: "open_login" },
      cancel_arguments: { user_action: "cancel" } },
  });
}

export async function prepareHotelLogin(server: McpServer, args: Record<string, unknown>, extra: Extra) {
  if (args.user_action === "open_login") return { args };
  if (args.user_action === "cancel") return { result: response({ status: "error", error_code: "LOGIN_CANCELLED", message: "本次酒店登录已取消。" }) };
  const capability = server.server.getClientCapabilities()?.elicitation;
  const formSupported = capability !== undefined &&
    (capability.form !== undefined || (capability.form === undefined && capability.url === undefined));
  if (!formSupported) return { result: interactionRequired(args) };
  try {
    // sendRequest binds the prompt to this tool call and also supports legacy elicitation:{} clients.
    const answer = await extra.sendRequest({ method: "elicitation/create", params: {
      mode: "form", message: LOGIN_QUESTION,
      requestedSchema: { type: "object", properties: {
        action: { type: "string", title: "携程登录", enum: LOGIN_OPTIONS },
      }, required: ["action"] },
    } }, ElicitResultSchema, { signal: extra.signal, timeout: 120_000 });
    if (answer.action !== "accept" || answer.content?.action !== LOGIN_OPTIONS[0]) {
      return { result: response({ status: "error", error_code: "LOGIN_CANCELLED", message: "本次酒店登录已取消。" }) };
    }
    return { args: { ...args, user_action: "open_login" } };
  } catch {
    if (extra.signal.aborted) return { result: response({ status: "error", error_code: "LOGIN_CANCELLED", message: "登录请求已取消。" }) };
    // An unavailable/timed-out dialog never counts as acceptance.
    return { result: interactionRequired(args) };
  }
}

export function withHotelRecovery(result: CallToolResult, args: Record<string, unknown>): CallToolResult {
  const data = hotelPayload(result);
  if (data?.error_code !== "LOGIN_REQUIRED") return result;
  return response({ ...data,
    next_tool: "hotel_ctrip_login",
    next_arguments: typeof data.return_url === "string" ? { return_url: data.return_url } : {},
    resume_request: { tool: "hotel_ctrip_searchHotels", arguments: args, max_retries: 1 },
    instructions: HOTEL_LOGIN_INSTRUCTIONS,
  });
}
