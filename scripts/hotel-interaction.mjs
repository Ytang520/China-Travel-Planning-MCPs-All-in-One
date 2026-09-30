// Shared by the CLI and its regression tests. The caller owns the native/terminal prompt.
export const payloadOf = result => {
  for (const item of result.content ?? []) {
    if (item.type !== "text") continue;
    try { return JSON.parse(item.text); } catch { /* Try the next content block. */ }
  }
  return result.structuredContent ?? {};
};

export async function hotelSearchWithLogin(call, args, notify = () => {}) {
  let result = await call("hotel_ctrip_searchHotels", args);
  const data = payloadOf(result);
  if (data.error_code !== "LOGIN_REQUIRED") return result;
  notify("酒店查询需要登录，正在请求用户选择…");
  const login = await call("hotel_ctrip_login", data.next_arguments ?? {});
  if (login.isError || payloadOf(login).status !== "success") return login;
  notify("登录成功，使用原参数重新查询酒店…");
  return call("hotel_ctrip_searchHotels", args); // Exactly one recovery attempt.
}

export function loginAction(argv) {
  const flags = argv.filter(value => value.startsWith("--login-action="));
  if (flags.length > 1) throw new Error("Specify --login-action only once");
  const action = flags[0]?.split("=")[1];
  if (action !== undefined && !["open_login", "cancel"].includes(action)) {
    throw new Error("--login-action must be open_login or cancel, reflecting the user's answer");
  }
  return action;
}
