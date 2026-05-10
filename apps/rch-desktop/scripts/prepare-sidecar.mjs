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

execFileSync("cargo", ["build", "--release", "-p", "r3akt-rch-server"], {
  cwd: repoRoot,
  stdio: "inherit",
});

const exeSuffix = process.platform === "win32" ? ".exe" : "";
const source = join(repoRoot, "target", "release", `r3akt-rch-server${exeSuffix}`);
const destination = join(binariesDir, `r3akt-rch-server-${targetTriple}${exeSuffix}`);

if (!existsSync(source)) {
  throw new Error(`Expected server binary at ${source}`);
}

mkdirSync(binariesDir, { recursive: true });
copyFileSync(source, destination);
console.log(`Prepared Tauri sidecar: ${destination}`);
