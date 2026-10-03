import { z } from "zod";

type JsonSchema = Record<string, any>;

/** Preserve provider validation without inserting defaults into forwarded arguments. */
export const jsonSchemaToZod = (
  schema?: JsonSchema, root: JsonSchema = schema ?? {}, refs: Set<string> = new Set(),
): z.ZodTypeAny => {
  if (!schema) return z.object({}).passthrough();
  const convert = (child: JsonSchema) => jsonSchemaToZod(child, root, refs);
  const union = (items: z.ZodTypeAny[]) => items.length === 0 ? z.never()
    : items.length === 1 ? items[0] : z.union(items as [z.ZodTypeAny, z.ZodTypeAny, ...z.ZodTypeAny[]]);
  let result: z.ZodTypeAny;
  if (schema.$ref?.startsWith("#/") && !refs.has(schema.$ref)) {
    const target = schema.$ref.slice(2).split("/").reduce(
      (node: any, key: string) => node?.[key.replaceAll("~1", "/").replaceAll("~0", "~")], root);
    result = target ? jsonSchemaToZod(target, root, new Set([...refs, schema.$ref])) : z.unknown();
  } else if (schema.anyOf || schema.oneOf) {
    result = union((schema.anyOf ?? schema.oneOf).map(convert));
  } else if (Array.isArray(schema.type)) {
    result = union(schema.type.map((type: string) => convert({ ...schema, type })));
  } else {
    switch (schema.type ?? (schema.properties ? "object" : undefined)) {
      case "object": {
        const required = new Set(schema.required ?? []);
        const shape = Object.fromEntries(Object.entries(schema.properties ?? {}).map(([key, value]) => {
          const child = convert(value as JsonSchema);
          return [key, required.has(key) ? child : child.optional()];
        }));
        const object = z.object(shape);
        result = schema.additionalProperties === false ? object.strict()
          : typeof schema.additionalProperties === "object" ? object.catchall(convert(schema.additionalProperties))
          : object.passthrough();
        break;
      }
      case "array": {
        let array = z.array(schema.items ? convert(schema.items) : z.unknown());
        if (schema.minItems !== undefined) array = array.min(schema.minItems);
        if (schema.maxItems !== undefined) array = array.max(schema.maxItems);
        result = array;
        break;
      }
      case "string": {
        let string = z.string();
        if (schema.minLength !== undefined) string = string.min(schema.minLength);
        if (schema.maxLength !== undefined) string = string.max(schema.maxLength);
        if (schema.pattern) string = string.regex(new RegExp(schema.pattern));
        result = string;
        break;
      }
      case "number":
      case "integer": {
        let number = schema.type === "integer" ? z.number().int() : z.number();
        if (schema.minimum !== undefined) number = number.min(schema.minimum);
        if (schema.maximum !== undefined) number = number.max(schema.maximum);
        if (typeof schema.exclusiveMinimum === "number") number = number.gt(schema.exclusiveMinimum);
        if (typeof schema.exclusiveMaximum === "number") number = number.lt(schema.exclusiveMaximum);
        if (schema.multipleOf !== undefined) number = number.multipleOf(schema.multipleOf);
        result = number;
        break;
      }
      case "boolean": result = z.boolean(); break;
      case "null": result = z.null(); break;
      default: result = z.unknown();
    }
  }
  if (schema.enum || Object.hasOwn(schema, "const")) {
    const literals = (schema.enum ?? [schema.const]).map((value: any) =>
      value === null ? z.null() : ["string", "number", "boolean"].includes(typeof value)
        ? z.literal(value) : z.unknown().refine((input) => JSON.stringify(input) === JSON.stringify(value)));
    const choices = union(literals);
    result = schema.type ? z.intersection(result, choices) : choices;
  }
  const meta: Record<string, unknown> = {};
  for (const key of ["title", "description", "default", "examples"]) {
    if (Object.hasOwn(schema, key)) meta[key] = schema[key];
  }
  return Object.keys(meta).length ? result.meta(meta) : result;
};
