#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const AGENT_DIRECTORIES = Object.freeze({
  opencode: '.opencode',
  'claude-code': '.claude',
  cursor: '.cursor',
});
const SKILL_NAME = 'error-processing';
const FILES = ['SKILL.md', 'mcp-error-references.json'];
const DEFAULT_TEMPLATE_ROOT = path.join(REPO_ROOT, 'skill-templates', SKILL_NAME);

function statIfPresent(filename) {
  try {
    return fs.lstatSync(filename);
  } catch (error) {
    if (error.code === 'ENOENT' || error.code === 'ENOTDIR') return undefined;
    throw error;
  }
}

function nonempty(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function readTemplate(templateRoot) {
  const files = Object.fromEntries(FILES.map(name => {
    const filename = path.join(templateRoot, name);
    if (!statIfPresent(filename)?.isFile()) throw new Error(`Missing template file: ${name}`);
    return [name, fs.readFileSync(filename)];
  }));
  const skill = files['SKILL.md'].toString('utf8').replace(/\r\n/g, '\n');
  const frontmatter = /^---\n([\s\S]*?)\n---(?:\n|$)/.exec(skill)?.[1];
  // A deliberately small YAML subset keeps this installer usable before npm install.
  // JSON-quoted strings are valid YAML scalars and can be validated without a YAML dependency.
  const metadata = /^name: error-processing\ndescription: ("[^\n]*")$/.exec(frontmatter ?? '');
  let description;
  try { description = JSON.parse(metadata?.[1] ?? 'null'); } catch { /* Invalid metadata. */ }
  if (!nonempty(description) || description.length > 1024 || !skill.includes('mcp-error-references.json')) {
    throw new Error('Invalid SKILL.md: expected name, JSON-quoted one-line description, and relative reference resource.');
  }
  let catalog;
  try {
    catalog = JSON.parse(files['mcp-error-references.json'].toString('utf8'));
  } catch {
    throw new Error('Invalid mcp-error-references.json: expected JSON.');
  }
  const ids = new Set();
  if (catalog?.version !== 1 || !Array.isArray(catalog.references) || !catalog.references.length) {
    throw new Error('Invalid reference catalog: expected version 1 and nonempty references.');
  }
  for (const reference of catalog.references) {
    if (!reference || !nonempty(reference.id) || ids.has(reference.id) ||
        !nonempty(reference.provider) || !nonempty(reference.description) ||
        !Array.isArray(reference.domains) || !reference.domains.length || !reference.domains.every(nonempty) ||
        !Array.isArray(reference.triggers) || !reference.triggers.every(nonempty) ||
        !Array.isArray(reference.urls) || !reference.urls.length) {
      throw new Error('Invalid reference catalog: incomplete or duplicate reference.');
    }
    ids.add(reference.id);
    for (const entry of reference.urls) {
      let url;
      try { url = new URL(entry?.url); } catch { /* Report without echoing source content. */ }
      if (!nonempty(entry?.label) || !nonempty(entry?.usage) || url?.protocol !== 'https:') {
        throw new Error('Invalid reference catalog: expected HTTPS URL, label, and usage.');
      }
    }
  }
  return files;
}

function assertDestination(projectRoot, agentDirectory) {
  let current = projectRoot;
  for (const segment of [agentDirectory, 'skills', SKILL_NAME]) {
    current = path.join(current, segment);
    const stat = statIfPresent(current);
    if (stat && (stat.isSymbolicLink() || !stat.isDirectory())) {
      throw new Error(`Destination component must be a regular directory: ${current}`);
    }
  }
  return current;
}

function findOtherCopies(projectRoot, selectedDirectory) {
  // Some hosts also discover compatible directories. Report ambiguity; never remove another copy.
  return ['.opencode', '.claude', '.cursor', '.agents', '.codex']
    .filter(directory => directory !== selectedDirectory)
    .map(directory => path.join(projectRoot, directory, 'skills', SKILL_NAME, 'SKILL.md'))
    .filter(filename => statIfPresent(filename))
    .map(filename => path.dirname(filename));
}

/** Install project-local instructions only; this never configures MCP or starts a host/provider. */
export function installAgentSkill({ agent, projectRoot = REPO_ROOT, check = false,
  templateRoot = DEFAULT_TEMPLATE_ROOT } = {}) {
  if (!Object.hasOwn(AGENT_DIRECTORIES, agent)) {
    throw new Error('Unsupported agent. Choose opencode, claude-code, or cursor.');
  }
  const source = readTemplate(templateRoot);
  const root = fs.realpathSync(path.resolve(projectRoot));
  if (!fs.statSync(root).isDirectory()) throw new Error('Project root must be an existing directory.');
  const directory = assertDestination(root, AGENT_DIRECTORIES[agent]);
  const missing = [];
  const conflicts = [];
  for (const name of FILES) {
    const filename = path.join(directory, name);
    const stat = statIfPresent(filename);
    if (!stat) missing.push(name);
    else if (!stat.isFile() || stat.isSymbolicLink() || !fs.readFileSync(filename).equals(source[name])) {
      conflicts.push(name);
    }
  }
  const otherCopies = findOtherCopies(root, AGENT_DIRECTORIES[agent]);
  const result = { agent, directory, status: conflicts.length ? 'conflict' : missing.length ? 'missing' : 'current',
    missing, conflicts, otherCopies, hostDiscovery: 'not-verified' };
  if (check || conflicts.length) return result;
  if (!missing.length) return { ...result, status: 'unchanged' };

  fs.mkdirSync(directory, { recursive: true });
  // Preflight every file before writing. Exclusive creation also protects concurrent user edits.
  const created = [];
  try {
    for (const name of missing) {
      const filename = path.join(directory, name);
      fs.writeFileSync(filename, source[name], { flag: 'wx' });
      created.push(filename);
    }
  } catch (error) {
    for (const filename of created) fs.unlinkSync(filename);
    throw error;
  }
  return { ...result, status: 'installed', missing: [], written: missing };
}

function parseArgs(args) {
  const options = {};
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--help' || arg === '-h') return { help: true };
    if (arg === '--check' && !options.check) { options.check = true; continue; }
    const key = arg === '--agent' ? 'agent' : arg === '--project-root' ? 'projectRoot' : undefined;
    if (!key || options[key] !== undefined || !args[i + 1] || args[i + 1].startsWith('--')) {
      throw new Error(`Invalid or incomplete option: ${arg}. Use --help.`);
    }
    options[key] = args[++i];
  }
  return options;
}

function main() {
  try {
    const options = parseArgs(process.argv.slice(2));
    if (options.help) {
      console.log('Usage: node scripts/install-agent-skill.mjs --agent <opencode|claude-code|cursor> [--project-root <directory>] [--check]\n' +
        'Default project root: this Travel MCP repository, regardless of the working directory.\n' +
        '--check is read-only and exits 1 for missing or conflicting files.\n' +
        'Existing different files are never overwritten. Host discovery must be verified in the chosen agent.');
      return;
    }
    const result = installAgentSkill(options);
    console.log(JSON.stringify(result, null, 2));
    if (result.otherCopies.length) {
      console.error('Other project copies of error-processing exist. Check host discovery for duplicate names; no copies were removed.');
    }
    if (result.status === 'conflict') {
      console.error('Existing skill files differ. Review and merge them manually; no files were written.');
      process.exitCode = 1;
    } else if (result.status === 'missing') process.exitCode = 1;
  } catch (error) {
    console.error(`[install-agent-skill] ${error.message}`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
