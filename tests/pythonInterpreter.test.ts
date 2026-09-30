import test from "node:test";
import assert from "node:assert/strict";
import { resolvePythonInterpreter } from "../src/utils/pythonInterpreter.js";

for (const platform of ["win32", "darwin", "linux"]) {
  const root = platform === "win32" ? "D:\\repo" : "/repo";
  const child = platform === "win32" ? "D:\\repo\\Hotel" : "/repo/Hotel";
  const requirement = { workspaceRoot: root, projectRoot: child, variable: "HOTEL_MCP_PYTHON_COMMAND", modules: ["fastmcp"] };
  test(`${platform}: an unusable root environment does not mask a usable legacy environment`, async () => {
    const calls: string[] = [];
    const resolved = await resolvePythonInterpreter(requirement, async (command) => {
      calls.push(command);
      if (calls.length === 1) throw new Error("Missing dependency or unsupported Python");
      return { executable: command };
    }, platform);
    assert.equal(resolved.source, "provider-venv");
    assert.equal(calls.length, 2);
    assert.match(calls[0], platform === "win32" ? /Scripts\\python.exe$/ : /bin\/python$/);
  });
  test(`${platform}: explicit failure is terminal`, async () => {
    let calls = 0;
    await assert.rejects(resolvePythonInterpreter({ ...requirement, explicitCommand: "python" }, async () => {
      calls++;
      throw new Error("not available");
    }, platform), /HOTEL_MCP_PYTHON_COMMAND/);
    assert.equal(calls, 1);
  });
  test(`${platform}: relative explicit paths resolve against provider root`, async () => {
    const command = platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python";
    const resolved = await resolvePythonInterpreter({ ...requirement, explicitCommand: command }, async (candidate) => ({ executable: candidate }), platform);
    assert.ok(resolved.command.startsWith(child));
    assert.equal(resolved.source, "configured");
  });

  test(`${platform}: obsolete DrissionPage falls through to a supported provider environment`, async () => {
    let calls = 0;
    const resolved = await resolvePythonInterpreter({ ...requirement, modules: ["DrissionPage"] }, async (command) => ({
      executable: command, drissionPageVersion: ++calls === 1 ? "4.0.5.6" : "4.1.1.4",
    }), platform);
    assert.equal(resolved.source, "provider-venv");
    assert.equal(calls, 2);
    for (const version of ["4.0.5.6", "4.1.1.3", "unknown", undefined]) {
      await assert.rejects(resolvePythonInterpreter({ ...requirement, modules: ["DrissionPage"], explicitCommand: "python" },
        async () => ({ executable: root, drissionPageVersion: version }), platform), /DrissionPage 4\.1\.1\.4\+/);
    }
  });
}
