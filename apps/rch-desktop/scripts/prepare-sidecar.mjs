import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const appDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(appDir, "..", "..");
const binariesDir = join(appDir, "src-tauri", "binaries");
const targetTriple = execFileSync("rustc", ["--print", "host-tuple"], {
  encoding: "utf8",
}).trim();

if (!targetTriple) {
  throw new Error("Could not determine Rust host target triple");
}

const exeSuffix = process.platform === "win32" ? ".exe" : "";
mkdirSync(binariesDir, { recursive: true });

const sidecars = [
  {
    packageName: "r3akt-rch-server",
    binaryName: "r3akt-rch-server",
    cargoArgs: ["build", "--release", "-p", "r3akt-rch-server"],
  },
  {
    packageName: "r3akt-tak-connector",
    binaryName: "r3akt-tak-service",
    cargoArgs: [
      "build",
      "--release",
      "-p",
      "r3akt-tak-connector",
      "--bin",
      "r3akt-tak-service",
    ],
  },
];

for (const sidecar of sidecars) {
  execFileSync("cargo", sidecar.cargoArgs, {
    cwd: repoRoot,
    stdio: "inherit",
  });

  const source = join(repoRoot, "target", "release", `${sidecar.binaryName}${exeSuffix}`);
  const destination = join(binariesDir, `${sidecar.binaryName}-${targetTriple}${exeSuffix}`);

  if (!existsSync(source)) {
    throw new Error(`Expected ${sidecar.packageName} binary at ${source}`);
  }

  copyFileSync(source, destination);
  console.log(`Prepared Tauri sidecar: ${destination}`);
}
