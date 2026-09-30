import { execFile } from "node:child_process";
import { win32, posix } from "node:path";
import { promisify } from "node:util";

const execute = promisify(execFile);

export type PythonRequirement = {
  workspaceRoot: string;
  projectRoot: string;
  variable: string;
  explicitCommand?: string;
  modules: string[];
  resolvedSource?: string;
};

type PythonProbeResult = { executable: string; drissionPageVersion?: string };
export type PythonProbe = (command: string, cwd: string, modules: string[]) => Promise<PythonProbeResult>;

const supportsDrissionPage = (version?: string) => {
  if (!version || !/^\d+(?:\.\d+)*$/.test(version)) return false;
  const parts = version.split(".").map(Number);
  const minimum = [4, 1, 1, 4];
  for (let index = 0; index < Math.max(parts.length, minimum.length); index++) {
    const difference = (parts[index] ?? 0) - (minimum[index] ?? 0);
    if (difference !== 0) return difference > 0;
  }
  return true;
};

const probePython: PythonProbe = async (command, cwd, modules) => {
  const code = [
    "import sys, json, importlib",
    "assert sys.version_info >= (3, 11), 'Python 3.11+ is required'",
    `for name in ${JSON.stringify(modules)}: importlib.import_module(name)`,
    "result = {'executable': sys.executable}",
    ...(modules.includes("DrissionPage") ? [
      "from DrissionPage import Chromium, ChromiumOptions, __version__",
      "assert all(callable(getattr(ChromiumOptions, name, None)) for name in ('new_env', 'use_system_user_path', 'existing_only')), 'DrissionPage 4.1.1.4+ is required'",
      "result['drissionPageVersion'] = __version__",
    ] : []),
    "print(json.dumps(result))",
  ].join("\n");
  const { stdout } = await execute(command, ["-c", code], {
    cwd, timeout: 15_000, maxBuffer: 64 * 1024, windowsHide: true, shell: false,
    env: { ...process.env, PYTHONUTF8: "1" },
  });
  const result = JSON.parse(stdout.trim()) as PythonProbeResult;
  if (!result.executable) throw new Error("Interpreter did not report sys.executable");
  return result;
};

export const resolvePythonInterpreter = async (
  requirement: PythonRequirement,
  probe: PythonProbe = probePython,
  platform: string = process.platform,
) => {
  const paths = platform === "win32" ? win32 : posix;
  const suffix = platform === "win32" ? ["Scripts", "python.exe"] : ["bin", "python"];
  const explicit = requirement.explicitCommand?.trim();
  const candidates = explicit
    ? [{ source: "configured", command: /[\\/]/.test(explicit)
      ? paths.resolve(requirement.projectRoot, explicit) : explicit }]
    : [
      { source: "root-venv", command: paths.join(requirement.workspaceRoot, ".venv", ...suffix) },
      { source: "provider-venv", command: paths.join(requirement.projectRoot, ".venv", ...suffix) },
    ];
  const failures: string[] = [];
  for (const candidate of candidates) {
    try {
      const result = await probe(candidate.command, requirement.projectRoot, requirement.modules);
      if (requirement.modules.includes("DrissionPage") && !supportsDrissionPage(result.drissionPageVersion)) {
        throw new Error(`DrissionPage 4.1.1.4+ is required (found ${result.drissionPageVersion ?? "unknown"})`);
      }
      const command = result.executable;
      if (!paths.isAbsolute(command)) throw new Error("Interpreter path is not absolute");
      return { command, source: candidate.source };
    } catch (error) {
      const detail = error as { code?: string; stderr?: string; message?: string };
      // Last stderr line explains missing modules/version without printing an environment dump.
      const reason = detail.stderr?.trim().split(/\r?\n/).at(-1) ?? detail.code ?? detail.message;
      failures.push(`${candidate.source}: ${reason}`);
    }
  }
  throw new Error(`PYTHON_INTERPRETER_UNAVAILABLE (${failures.join("; ")}). ` +
    `Use uv to install this provider in the repository .venv with Python 3.11+, ` +
    `or set ${requirement.variable} to its interpreter's absolute path.`);
};
