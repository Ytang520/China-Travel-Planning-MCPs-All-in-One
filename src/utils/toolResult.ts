import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";

const stringifyValue = (value: unknown) => {
  if (typeof value === "string") {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

export const normalizeToolResult = (
  result:
    | CallToolResult
    | {
        toolResult: unknown;
        _meta?: Record<string, unknown>;
      },
): CallToolResult => {
  if ("toolResult" in result) {
    return {
      content: [
        {
          type: "text",
          text: stringifyValue(result.toolResult),
        },
      ],
      _meta: result._meta,
    };
  }

  if (result.content.length > 0) {
    return result;
  }

  if (result.structuredContent) {
    return {
      ...result,
      content: [
        {
          type: "text",
          text: stringifyValue(result.structuredContent),
        },
      ],
    };
  }

  return {
    ...result,
    content: [
      {
        type: "text",
        text: "",
      },
    ],
  };
};
