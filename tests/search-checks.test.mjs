import test from "node:test";
import assert from "node:assert/strict";
import { searchArguments, shanghaiDate, validateSearchResult } from "../scripts/search-checks.mjs";

const now = new Date("2026-09-30T18:00:00Z");
const flightArgs = searchArguments("flight", [], now);
const hotelArgs = searchArguments("hotel", [], now);
const flight = { ...flightArgs, status: "success", data_source: "ctrip_web_scraping",
  flight_count: 1, flights: [{ "航班号": "MU5101", "出发时间": "08:30", "到达时间": "10:45" }] };
const hotel = { ...hotelArgs, status: "success", data_source: "ctrip_web_scraping",
  count: 1, hotels: [{ name: "武汉示例酒店", price: null }] };
const result = (data) => ({ content: [{ type: "text", text: JSON.stringify(data) }] });

test("location echo and sort request cannot substitute for applied page evidence", () => {
  const expected = { ...hotelArgs, location: "梨园地铁站", sort: "distance" };
  assert.throws(() => validateSearchResult("hotel", result({ ...hotel, ...expected }), expected), /location/);
  const verified = { ...hotel, ...expected, location_resolution: {
    requested: expected.location, resolved_name: expected.location, status: "applied", applied: true,
    evidence: { selected_locations: [], distance_anchors: [expected.location] },
  }, sorting: { requested: "distance", actual: "distance", applied: true, anchor: expected.location } };
  assert.equal(validateSearchResult("hotel", result(verified), expected), 1);
  assert.throws(() => validateSearchResult("hotel", result({ ...verified, sorting: { ...verified.sorting, actual: "smart" } }), expected), /sorting/);
  assert.throws(() => validateSearchResult("hotel", result({ ...verified, location_resolution: { ...verified.location_resolution, applied: false } }), expected), /location/);
});

test("China dates, future defaults and explicit dates", () => {
  assert.equal(shanghaiDate(now), "2026-10-01");
  assert.equal(flightArgs.departure_date, "2026-10-08");
  assert.equal(hotelArgs.checkout, "2026-10-10");
  assert.equal(searchArguments("flight", ["2026-10-02"], now).departure_date, "2026-10-02");
  for (const dates of [["2026-02-30"], ["2026-01-01"], ["no-date"]]) {
    assert.throws(() => searchArguments("flight", dates, now));
  }
  assert.throws(() => searchArguments("hotel", ["2026-10-04"], now));
  assert.throws(() => searchArguments("hotel", ["2026-10-05", "2026-10-04"], now));
});

for (const [mode, data, args] of [["flight", flight, flightArgs], ["hotel", hotel, hotelArgs]]) {
  test(`${mode} verifies complete structured/text results`, () => {
    assert.equal(validateSearchResult(mode, result(data), args), 1);
    assert.equal(validateSearchResult(mode, { structuredContent: data, content: [] }, args), 1);
  });
  test(`${mode} rejects empty, errors, bad metadata and malformed payloads`, () => {
    const list = mode === "flight" ? "flights" : "hotels";
    const count = mode === "flight" ? "flight_count" : "count";
    for (const changed of [
      { status: "error", error_code: "LOGIN_REQUIRED" }, { status: "empty" },
      { [list]: [], [count]: 0 }, { [count]: 2 }, { data_source: "mock" },
      mode === "flight" ? { destination_city: "深圳" } : { checkout: "2026-11-01" },
    ]) assert.throws(() => validateSearchResult(mode, result({ ...data, ...changed }), args));
    assert.throws(() => validateSearchResult(mode, { ...result(data), isError: true }, args));
    assert.throws(() => validateSearchResult(mode, { content: [{ type: "text", text: "bad" }] }, args));
  });
}

test("placeholder flight records and nameless hotels cannot pass", () => {
  assert.throws(() => validateSearchResult("flight", result({ ...flight, flights: [{ 航班号: "未知" }] }), flightArgs));
  assert.throws(() => validateSearchResult("hotel", result({ ...hotel, hotels: [{ name: " " }] }), hotelArgs));
});

test("Ctrip overnight arrival times are valid", () => {
  const overnight = { ...flight, flights: [{ "航班号": "MU5101", "出发时间": "23:30", "到达时间": "00:30 +1天" }] };
  assert.equal(validateSearchResult("flight", result(overnight), flightArgs), 1);
});

test("flight acceptance enforces five complete, valid records", () => {
  assert.equal(flightArgs.limit, 5);
  const records = Array.from({ length: 6 }, (_, i) => ({ ...flight.flights[0], 航班号: `MU${5101 + i}` }));
  assert.equal(validateSearchResult("flight", result({ ...flight, flights: records.slice(0, 5), flight_count: 5 }), flightArgs), 5);
  assert.throws(() => validateSearchResult("flight", result({ ...flight, flights: records, flight_count: 6 }), flightArgs), /limit/);
  assert.throws(() => validateSearchResult("flight", result({ ...flight,
    flights: [records[0], { 航班号: "未知" }], flight_count: 2 }), flightArgs), /invalid flight/);
});
