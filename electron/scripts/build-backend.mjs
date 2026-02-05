import { spawnSync } from "child_process";
import path from "path";
import { fileURLToPath } from "url";

const filename = fileURLToPath(import.meta.url);
const dirname = path.dirname(filename);
const electronRoot = path.resolve(dirname, "..");
const repoRoot = path.resolve(electronRoot, "..");
const backendRoot = path.join(electronRoot, "backend");
const entrypoint = path.join(backendRoot, "rch_entrypoint.py");

const pythonCmd = process.env.RCH_PYTHON ?? "python";
const distPath = backendRoot;
const workPath = path.join(backendRoot, "build");

const args = [
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name",
  "rch-backend",
  "--distpath",
  distPath,
  "--workpath",
  workPath,
  "--specpath",
  backendRoot,
  "--paths",
  repoRoot,
  "--collect-submodules",
  "reticulum_telemetry_hub",
  "--collect-all",
  "RNS",
  "--collect-all",
  "LXMF",
  "--collect-all",
  "websockets",
  entrypoint
];

const result = spawnSync(pythonCmd, args, {
  cwd: repoRoot,
  stdio: "inherit"
});

if (result.error) {
  console.error(result.error);
  process.exit(1);
}

process.exit(result.status ?? 1);
