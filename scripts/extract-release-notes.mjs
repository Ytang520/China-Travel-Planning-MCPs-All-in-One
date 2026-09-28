import { readFileSync } from "node:fs";

const version = process.argv[2]?.replace(/^v/, "");

if (!version) {
  console.error("usage: node scripts/extract-release-notes.mjs <version>");
  process.exit(1);
}

const changelog = readFileSync(new URL("../CHANGELOG.md", import.meta.url), "utf8");
const lines = changelog.split(/\r?\n/);
const header = `## [${version}]`;
const start = lines.findIndex((line) => line.startsWith(header));

if (start < 0) {
  console.error(`CHANGELOG.md has no section for ${version}`);
  process.exit(1);
}

const nextHeader = lines.findIndex((line, index) => index > start && line.startsWith("## ["));
const end = nextHeader < 0 ? lines.length : nextHeader;
const body = lines.slice(start + 1, end).join("\n").trim();

if (!body) {
  console.error(`CHANGELOG section ${version} is empty`);
  process.exit(1);
}

process.stdout.write(`${body}\n`);
