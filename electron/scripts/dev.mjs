import { spawn } from "child_process";
import { existsSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const filename = fileURLToPath(import.meta.url);
const dirname = path.dirname(filename);
const electronRoot = path.resolve(dirname, "..");
const repoRoot = path.resolve(electronRoot, "..");
const uiRoot = path.join(repoRoot, "ui");

const devHost = process.env.RCH_UI_HOST ?? "127.0.0.1";
const devPort = process.env.RCH_UI_PORT ?? "5173";
const devUrl = `http://${devHost}:${devPort}`;

const isWindows = process.platform === "win32";
const npmCmd = isWindows ? "npm.cmd" : "npm";
const tscBin = path.join(
  electronRoot,
  "node_modules",
  ".bin",
  isWindows ? "tsc.cmd" : "tsc"
);
const electronBin = path.join(
  electronRoot,
  "node_modules",
  ".bin",
  isWindows ? "electron.cmd" : "electron"
);

const assertBinary = (binaryPath, name) => {
  if (existsSync(binaryPath)) {
    return;
  }

  console.error(`${name} not found. Run "npm install" in ${electronRoot}.`);
  process.exit(1);
};

assertBinary(tscBin, "TypeScript compiler");
assertBinary(electronBin, "Electron");

const children = [];

const startProcess = (command, args, options) => {
  const child = spawn(command, args, { stdio: "inherit", ...options });
  children.push(child);
  return child;
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const waitForFile = async (filePath, attempts = 40, delayMs = 250) => {
  for (let i = 0; i < attempts; i += 1) {
    if (existsSync(filePath)) {
      return;
    }
    await sleep(delayMs);
  }

  throw new Error(`Timed out waiting for ${filePath}.`);
};

const shutdown = () => {
  children.forEach((child) => {
    if (!child.killed) {
      child.kill();
    }
  });
};

const run = async () => {
  const uiProcess = startProcess(
    npmCmd,
    ["--prefix", uiRoot, "run", "dev", "--", "--host", devHost, "--port", devPort],
    { cwd: repoRoot, env: process.env }
  );

  const tscProcess = startProcess(
    tscBin,
    ["-p", "tsconfig.json", "--watch"],
    { cwd: electronRoot, env: process.env }
  );

  const mainPath = path.join(electronRoot, "dist", "main.js");
  await waitForFile(mainPath);

  const electronProcess = startProcess(
    electronBin,
    ["dist/main.js"],
    {
      cwd: electronRoot,
      env: {
        ...process.env,
        ELECTRON_START_URL: devUrl,
      },
    }
  );

  const exitHandler = () => {
    shutdown();
    process.exit(0);
  };

  process.on("SIGINT", exitHandler);
  process.on("SIGTERM", exitHandler);

  electronProcess.on("close", exitHandler);
  uiProcess.on("close", exitHandler);
  tscProcess.on("close", exitHandler);
};

run().catch((error) => {
  console.error(error);
  shutdown();
  process.exit(1);
});
