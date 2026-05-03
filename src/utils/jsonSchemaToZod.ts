import { z } from "zod";

type JsonSchema = {
  type?: string | string[];
  description?: string;
  default?: unknown;
  enum?: unknown[];
  properties?: Record<string, JsonSchema | undefined>;
  required?: string[];
  items?: JsonSchema | JsonSchema[];
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  additionalProperties?: boolean | JsonSchema;
};

const withDescription = <T extends z.ZodTypeAny>(
  schema: T,
  description?: string,
) => {
  return description ? schema.describe(description) : schema;
};

const fromEnum = (values: unknown[], description?: string) => {
  const filtered = values.filter(
    (value) =>
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean",
  );

  if (filtered.length === 0) {
    return withDescription(z.any(), description);
  }

  if (filtered.every((value) => typeof value === "string")) {
    const literalValues = filtered as [string, ...string[]];
    return withDescription(z.enum(literalValues), description);
  }

  return withDescription(z.any(), description);
};

const fromUnion = (schemas: JsonSchema[], description?: string) => {
  const options = schemas.map((schema) => jsonSchemaToZod(schema));

  if (options.length === 0) {
    return withDescription(z.any(), description);
  }

  if (options.length === 1) {
    return withDescription(options[0], description);
  }

  return withDescription(
    z.union(
      options as [z.ZodTypeAny, z.ZodTypeAny, ...z.ZodTypeAny[]],
    ),
    description,
  );
};

const fromArray = (schema: JsonSchema) => {
  const description = schema.description;
  const items = Array.isArray(schema.items) ? schema.items[0] : schema.items;
  const itemSchema = items ? jsonSchemaToZod(items) : z.any();

  return withDescription(z.array(itemSchema), description);
};

const fromObject = (schema: JsonSchema) => {
  const description = schema.description;
  const required = new Set(schema.required ?? []);
  const properties = schema.properties ?? {};

  const shape = Object.fromEntries(
    Object.entries(properties).map(([key, value]) => {
      const childSchema = jsonSchemaToZod(value);
      return [key, required.has(key) ? childSchema : childSchema.optional()];
    }),
  );

  let objectSchema = z.object(shape);

  if (schema.additionalProperties === false) {
    objectSchema = objectSchema.strict();
  } else if (schema.additionalProperties === true || schema.additionalProperties === undefined) {
    objectSchema = objectSchema.passthrough();
  } else {
    objectSchema = objectSchema.catchall(jsonSchemaToZod(schema.additionalProperties));
  }

  return withDescription(objectSchema, description);
};

export const jsonSchemaToZod = (
  schema?: JsonSchema | Record<string, unknown>,
): z.ZodTypeAny => {
  if (!schema) {
    return z.object({}).passthrough();
  }

  const normalizedSchema = schema as JsonSchema;

  if (normalizedSchema.enum) {
    return fromEnum(normalizedSchema.enum, normalizedSchema.description);
  }

  if (normalizedSchema.anyOf) {
    return fromUnion(normalizedSchema.anyOf, normalizedSchema.description);
  }

  if (normalizedSchema.oneOf) {
    return fromUnion(normalizedSchema.oneOf, normalizedSchema.description);
  }

  const schemaType = Array.isArray(normalizedSchema.type)
    ? normalizedSchema.type[0]
    : normalizedSchema.type;

  switch (schemaType) {
    case "string":
      return withDescription(z.string(), normalizedSchema.description);
    case "number":
      return withDescription(z.number(), normalizedSchema.description);
    case "integer":
      return withDescription(z.number().int(), normalizedSchema.description);
    case "boolean":
      return withDescription(z.boolean(), normalizedSchema.description);
    case "array":
      return fromArray(normalizedSchema);
    case "object":
      return fromObject(normalizedSchema);
    default:
      if (normalizedSchema.properties) {
        return fromObject({ ...normalizedSchema, type: "object" });
      }

      return withDescription(z.any(), normalizedSchema.description);
  }
};
