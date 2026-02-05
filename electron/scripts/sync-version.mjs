import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const filename = fileURLToPath(import.meta.url);
const dirname = path.dirname(filename);
const electronRoot = path.resolve(dirname, "..");
const repoRoot = path.resolve(electronRoot, "..");
const pyprojectPath = path.join(repoRoot, "pyproject.toml");
const packageJsonPath = path.join(electronRoot, "package.json");
const packageLockPath = path.join(electronRoot, "package-lock.json");

const extractVersion = (tomlText) => {
  const lines = tomlText.split(/\r?\n/);
  let inPoetry = false;
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line === "[tool.poetry]") {
      inPoetry = true;
      continue;
    }
    if (inPoetry && line.startsWith("[")) {
      break;
    }
    if (inPoetry) {
      const match = /^version\s*=\s*"([^"]+)"\s*$/.exec(line);
      if (match) {
        return match[1];
      }
    }
  }
  throw new Error("Could not find tool.poetry version in pyproject.toml.");
};

const updateJsonFile = (filePath, transform) => {
  const raw = fs.readFileSync(filePath, "utf8");
  const parsed = JSON.parse(raw);
  const updated = transform(parsed);
  fs.writeFileSync(filePath, `${JSON.stringify(updated, null, 2)}\n`, "utf8");
};

const pyprojectText = fs.readFileSync(pyprojectPath, "utf8");
const pythonVersion = extractVersion(pyprojectText);

updateJsonFile(packageJsonPath, (pkg) => {
  pkg.version = pythonVersion;
  return pkg;
});

if (fs.existsSync(packageLockPath)) {
  updateJsonFile(packageLockPath, (lock) => {
    lock.version = pythonVersion;
    if (lock.packages && lock.packages[""]) {
      lock.packages[""].version = pythonVersion;
    }
    return lock;
  });
}

console.log(`Synced electron version to ${pythonVersion}.`);
