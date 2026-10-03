// Pure helpers used only by the flight/hotel post-install examples.
export const shanghaiDate = (now = new Date()) => {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(now).map(({ type, value }) => [type, value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
};

const validDate = (value) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
};

const addDays = (date, days) => new Date(
  Date.parse(`${date}T00:00:00Z`) + days * 86_400_000,
).toISOString().slice(0, 10);

export const searchArguments = (mode, dates = [], now = new Date()) => {
  const today = shanghaiDate(now);
  if (dates.some((date) => !validDate(date) || date < today)) {
    throw new Error("Use valid YYYY-MM-DD dates on or after today in Asia/Shanghai.");
  }
  if (mode === "flight") {
    if (dates.length > 1) throw new Error("usage: flight [YYYY-MM-DD]");
    return { departure_city: "上海", destination_city: "北京",
      departure_date: dates[0] ?? addDays(today, 7), data_source_preference: "default", limit: 5 };
  }
  if (mode !== "hotel" || ![0, 2].includes(dates.length)) {
    throw new Error("usage: hotel [checkin checkout]");
  }
  const checkin = dates[0] ?? addDays(today, 7);
  const checkout = dates[1] ?? addDays(today, 9);
  if (checkout <= checkin) throw new Error("Hotel checkout must be after checkin.");
  return { city: "武汉", checkin, checkout, limit: 5 };
};

export const parseSearchResult = (result) => {
  if (result.isError) throw new Error("MCP tool returned isError=true");
  if (result.structuredContent && typeof result.structuredContent === "object") {
    return result.structuredContent;
  }
  const texts = (result.content ?? []).filter((part) => part.type === "text");
  return JSON.parse(texts.map((part) => part.text).join("\n"));
};

export const validateSearchResult = (mode, result, expected) => {
  const data = parseSearchResult(result);
  if (!data || data.status !== "success") {
    throw new Error(`Search not verified: ${data?.error_code ?? data?.status ?? "INVALID_RESULT"} ${data?.message ?? ""}`);
  }
  if (data.data_source !== "ctrip_web_scraping") throw new Error("Unexpected search data source");
  const keys = mode === "flight"
    ? ["departure_city", "destination_city", "departure_date"] : ["city", "checkin", "checkout"];
  for (const key of keys) {
    if (data[key] !== expected[key]) throw new Error(`Search result does not match requested ${key}`);
  }
  const records = mode === "flight" ? data.flights : data.hotels;
  const count = mode === "flight" ? data.flight_count : data.count;
  if (!Array.isArray(records) || records.length === 0) throw new Error("EMPTY_RESULTS: browser search not verified");
  if (!Number.isInteger(count) || count !== records.length) throw new Error("Result count does not match records");
  if (expected.limit != null && count > expected.limit) throw new Error("Result exceeds requested limit");
  if (mode === "flight") {
    const time = /^(?:[01]\d|2[0-3]):[0-5]\d(?:\s*\+\d+天)?$/;
    const meaningful = records.every((record) => record &&
      typeof record["航班号"] === "string" && /[A-Z0-9]{2}\s*\d{2,5}/i.test(record["航班号"]) &&
      time.test(record["出发时间"]) && time.test(record["到达时间"]));
    if (!meaningful) throw new Error("A flight has an invalid flight number or departure/arrival times");
  } else {
    if (expected.location) {
      const location = data.location_resolution;
      if (!location?.applied || location.status !== "applied" || location.requested !== expected.location ||
          !location.resolved_name || !location.evidence ||
          ![...(location.evidence.selected_locations ?? []), ...(location.evidence.distance_anchors ?? [])].includes(location.resolved_name)) {
        throw new Error("Hotel location was not verified on the page");
      }
    }
    if (expected.sort) {
      if (!data.sorting?.applied || data.sorting.actual !== expected.sort || data.sorting.requested !== expected.sort ||
          (expected.sort === "distance" && (!expected.location || data.sorting.anchor !== data.location_resolution?.resolved_name ||
            !data.location_resolution?.evidence?.distance_anchors?.includes(data.sorting.anchor)))) {
        throw new Error("Hotel sorting or distance anchor was not verified");
      }
    }
    if (count > expected.limit || records.some((record) =>
      !record || typeof record.name !== "string" || !record.name.trim())) {
      throw new Error("Invalid hotel names or result limit");
    }
  }
  return count;
};
