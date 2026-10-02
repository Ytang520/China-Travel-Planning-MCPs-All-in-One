import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { AGENT_DIRECTORIES, REPO_ROOT, installAgentSkill } from '../scripts/install-agent-skill.mjs';

const template = path.join(REPO_ROOT, 'skill-templates', 'error-processing');
const installer = path.join(REPO_ROOT, 'scripts', 'install-agent-skill.mjs');
const files = ['SKILL.md', 'mcp-error-references.json'];

function fixture(t) {
  const parent = fs.realpathSync(os.tmpdir());
  const root = fs.mkdtempSync(path.join(parent, 'travel-agent-skill-'));
  t.after(() => {
    // Delete only this test's unique, verified temporary directory.
    assert.equal(path.dirname(path.resolve(root)), parent);
    assert.ok(path.basename(root).startsWith('travel-agent-skill-'));
    fs.rmSync(root, { recursive: true, force: true });
  });
  return root;
}

function destination(root, agent = 'opencode') {
  return path.join(root, AGENT_DIRECTORIES[agent], 'skills', 'error-processing');
}

function cli(args, cwd) {
  return spawnSync(process.execPath, [installer, ...args], { cwd, encoding: 'utf8' });
}

for (const agent of Object.keys(AGENT_DIRECTORIES)) {
  test(`installs both resources for ${agent} into a project with spaces and Chinese characters`, t => {
    const root = path.join(fixture(t), '旅行 project');
    fs.mkdirSync(root);
    const result = installAgentSkill({ agent, projectRoot: root });
    assert.equal(result.status, 'installed');
    assert.equal(result.directory, destination(root, agent));
    assert.equal(result.hostDiscovery, 'not-verified');
    for (const name of files) {
      assert.deepEqual(fs.readFileSync(path.join(result.directory, name)), fs.readFileSync(path.join(template, name)));
    }
    assert.deepEqual(fs.readdirSync(root), [AGENT_DIRECTORIES[agent]]);
    const snapshot = files.map(name => fs.statSync(path.join(result.directory, name)).mtimeMs);
    assert.equal(installAgentSkill({ agent, projectRoot: root }).status, 'unchanged');
    assert.deepEqual(files.map(name => fs.statSync(path.join(result.directory, name)).mtimeMs), snapshot);
    assert.equal(installAgentSkill({ agent, projectRoot: root, check: true }).status, 'current');
  });
}

test('--check is read-only and distinguishes missing, current, and conflicting files', t => {
  const root = fixture(t);
  const args = ['--agent', 'claude-code', '--project-root', root, '--check'];
  let result = cli(args, root);
  assert.equal(result.status, 1, result.stderr);
  assert.equal(JSON.parse(result.stdout).status, 'missing');
  assert.deepEqual(fs.readdirSync(root), []);
  installAgentSkill({ agent: 'claude-code', projectRoot: root });
  result = cli(args, root);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout).status, 'current');
  const skill = path.join(destination(root, 'claude-code'), 'SKILL.md');
  fs.writeFileSync(skill, 'custom instructions');
  result = cli(args, root);
  assert.equal(result.status, 1);
  assert.equal(JSON.parse(result.stdout).status, 'conflict');
  assert.equal(fs.readFileSync(skill, 'utf8'), 'custom instructions');
});

test('conflicts protect all files, including resources not yet installed', t => {
  const root = fixture(t);
  const target = destination(root);
  fs.mkdirSync(target, { recursive: true });
  fs.writeFileSync(path.join(target, 'SKILL.md'), 'user customization');
  const result = cli(['--agent', 'opencode', '--project-root', root], root);
  assert.equal(result.status, 1);
  assert.deepEqual(JSON.parse(result.stdout).conflicts, ['SKILL.md']);
  assert.deepEqual(fs.readdirSync(target), ['SKILL.md']);
  assert.equal(fs.readFileSync(path.join(target, 'SKILL.md'), 'utf8'), 'user customization');
});

test('fills a missing resource when existing files match and preserves unrelated files', t => {
  const root = fixture(t);
  const target = destination(root);
  fs.mkdirSync(target, { recursive: true });
  fs.copyFileSync(path.join(template, 'SKILL.md'), path.join(target, 'SKILL.md'));
  fs.writeFileSync(path.join(target, 'notes.txt'), 'personal notes');
  const result = installAgentSkill({ agent: 'opencode', projectRoot: root });
  assert.deepEqual(result.written, ['mcp-error-references.json']);
  assert.equal(fs.readFileSync(path.join(target, 'notes.txt'), 'utf8'), 'personal notes');
});

test('reports other project copies without overwriting or deleting them', t => {
  const root = fixture(t);
  installAgentSkill({ agent: 'claude-code', projectRoot: root });
  const original = fs.readFileSync(path.join(destination(root, 'claude-code'), 'SKILL.md'));
  const result = cli(['--agent', 'opencode', '--project-root', root], root);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout).otherCopies, [destination(root, 'claude-code')]);
  assert.match(result.stderr, /duplicate names/);
  assert.deepEqual(fs.readFileSync(path.join(destination(root, 'claude-code'), 'SKILL.md')), original);
});

test('an unrelated host path that is a file does not block the selected host', t => {
  const root = fixture(t);
  fs.writeFileSync(path.join(root, '.claude'), 'unrelated file');
  const result = installAgentSkill({ agent: 'opencode', projectRoot: root });
  assert.equal(result.status, 'installed');
  assert.deepEqual(result.otherCopies, []);
  assert.equal(fs.readFileSync(path.join(root, '.claude'), 'utf8'), 'unrelated file');
});

test('resolves the template and default project root relative to the script, without dependencies', t => {
  const root = fixture(t);
  const repository = path.join(root, 'MCP repository');
  const elsewhere = path.join(root, 'different cwd');
  fs.mkdirSync(path.join(repository, 'scripts'), { recursive: true });
  fs.mkdirSync(elsewhere);
  fs.copyFileSync(installer, path.join(repository, 'scripts', 'install-agent-skill.mjs'));
  fs.cpSync(template, path.join(repository, 'skill-templates', 'error-processing'), { recursive: true });
  const result = spawnSync(process.execPath, [path.join(repository, 'scripts', 'install-agent-skill.mjs'),
    '--agent', 'cursor'], { cwd: elsewhere, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout).directory, destination(repository, 'cursor'));
  assert.deepEqual(fs.readdirSync(elsewhere), []);
});

test('relative --project-root is interpreted from the invocation directory', t => {
  const root = fixture(t);
  fs.mkdirSync(path.join(root, 'selected project'));
  const result = cli(['--agent', 'cursor', '--project-root', 'selected project'], root);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout).directory, destination(path.join(root, 'selected project'), 'cursor'));
});

for (const args of [[], ['--agent', 'unknown'], ['--agent', 'toString'], ['--agent'],
  ['--agent', 'cursor', '--agent', 'opencode'], ['--agent', 'cursor', '--force'],
  ['--agent', 'cursor', '--check', '--check']]) {
  test(`rejects invalid CLI arguments before writing: ${JSON.stringify(args)}`, t => {
    const root = fixture(t);
    const result = cli([...args, '--project-root', root], root);
    assert.equal(result.status, 1);
    assert.deepEqual(fs.readdirSync(root), []);
  });
}

for (const [label, mutate] of [
  ['missing file', source => fs.unlinkSync(path.join(source, 'mcp-error-references.json'))],
  ['invalid frontmatter', source => fs.writeFileSync(path.join(source, 'SKILL.md'), 'no frontmatter')],
  ['wrong name', source => fs.writeFileSync(path.join(source, 'SKILL.md'), fs.readFileSync(path.join(source, 'SKILL.md'), 'utf8').replace('name: error-processing', 'name: another-skill'))],
  ['malformed YAML description', source => fs.writeFileSync(path.join(source, 'SKILL.md'), '---\nname: error-processing\ndescription: [broken\n---\nmcp-error-references.json')],
  ['duplicate metadata', source => fs.writeFileSync(path.join(source, 'SKILL.md'), '---\nname: error-processing\ndescription: "test"\nname: different\n---\nmcp-error-references.json')],
  ['invalid JSON', source => fs.writeFileSync(path.join(source, 'mcp-error-references.json'), '{broken')],
  ['invalid references', source => fs.writeFileSync(path.join(source, 'mcp-error-references.json'), '{"version":1,"references":[{}]}')],
  ['unsupported version', source => fs.writeFileSync(path.join(source, 'mcp-error-references.json'), '{"version":2,"references":[]}')],
]) {
  test(`${label} is rejected before any destination files are created`, t => {
    const root = fixture(t);
    const source = path.join(root, 'source');
    const project = path.join(root, 'project');
    fs.cpSync(template, source, { recursive: true });
    fs.mkdirSync(project);
    mutate(source);
    assert.throws(() => installAgentSkill({ agent: 'opencode', projectRoot: project, templateRoot: source }));
    assert.deepEqual(fs.readdirSync(project), []);
  });
}

test('rejects a directory where a skill file is expected without partial writes', t => {
  const root = fixture(t);
  fs.mkdirSync(path.join(destination(root), 'SKILL.md'), { recursive: true });
  const result = installAgentSkill({ agent: 'opencode', projectRoot: root });
  assert.equal(result.status, 'conflict');
  assert.deepEqual(fs.readdirSync(destination(root)), ['SKILL.md']);
});

test('refuses to follow a host directory junction or symlink', t => {
  const root = fixture(t);
  const elsewhere = path.join(root, 'outside project');
  const project = path.join(root, 'project');
  fs.mkdirSync(elsewhere);
  fs.mkdirSync(project);
  fs.symlinkSync(elsewhere, path.join(project, '.opencode'), process.platform === 'win32' ? 'junction' : 'dir');
  assert.throws(() => installAgentSkill({ agent: 'opencode', projectRoot: project }), /regular directory/);
  assert.deepEqual(fs.readdirSync(elsewhere), []);
});

test('help does not write any files', t => {
  const root = fixture(t);
  const result = cli(['--help'], root);
  assert.equal(result.status, 0);
  assert.match(result.stdout, /--project-root/);
  assert.deepEqual(fs.readdirSync(root), []);
});
