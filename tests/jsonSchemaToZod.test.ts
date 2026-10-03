import { test } from "node:test";
import assert from "node:assert/strict";
import { z } from "zod";
import { jsonSchemaToZod } from "../src/utils/jsonSchemaToZod.js";

test("nullable parameters, bounds, mixed enums and nested required survive conversion", () => {
  const schema = jsonSchemaToZod({ type: "object", required: ["nested"], properties: {
    price: { type: ["integer", "null"], minimum: 0, maximum: 100 },
    mode: { enum: [1, false, "auto", null] },
    nested: { type: "object", required: ["name"], additionalProperties: false,
      properties: { name: { type: "string", minLength: 1 } } },
  } });
  assert.equal(schema.safeParse({ price: null, mode: false, nested: { name: "x" } }).success, true);
  for (const bad of [{ price: -1 }, { price: 101 }, { price: 1.5 }, { mode: true }, { nested: {} }, { nested: { name: "" } }]) {
    assert.equal(schema.safeParse({ nested: { name: "x" }, ...bad }).success, false);
  }
});

test("defaults/examples remain metadata and omitted fields remain omitted", () => {
  const schema = jsonSchemaToZod({ type: "object", properties: {
    limit: { type: "integer", minimum: 1, default: 20, examples: [5], description: "Maximum results" },
  } });
  assert.deepEqual(schema.parse({}), {});
  const published = z.toJSONSchema(schema) as any;
  assert.equal(published.properties.limit.default, 20);
  assert.deepEqual(published.properties.limit.examples, [5]);
  assert.deepEqual(published.required ?? [], []);
});

test("provider anyOf and local references retain validation", () => {
  const schema = jsonSchemaToZod({ type: "object", required: ["value"], $defs: {
    score: { type: "number", minimum: 0, maximum: 5 },
  }, properties: { value: { anyOf: [{ $ref: "#/$defs/score" }, { type: "null" }] } } });
  assert.equal(schema.safeParse({ value: null }).success, true);
  assert.equal(schema.safeParse({ value: 6 }).success, false);
});
