import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const filename = fileURLToPath(import.meta.url);
const dirname = path.dirname(filename);
const electronRoot = path.resolve(dirname, "..");
const distReleaseDir = path.join(electronRoot, "dist-release");
const packageJsonPath = path.join(electronRoot, "package.json");

const TARGET_WINDOWS = "windows";
const TARGET_MACOS = "macos";
const TARGET_LINUX_APPIMAGE = "linux-appimage";
const TARGET_LINUX_DEB = "linux-deb";

const APP_NAME = "rch";

const target = process.argv[2];
if (!target) {
  throw new Error(
    "Missing target. Expected one of: windows, macos, linux-appimage, linux-deb"
  );
}

if (!fs.existsSync(distReleaseDir)) {
  throw new Error(`dist-release directory not found: ${distReleaseDir}`);
}

const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
const version = packageJson.version;
if (!version || typeof version !== "string") {
  throw new Error("Could not determine version from electron/package.json");
}

const listFilesByExtension = (extension) => {
  const ext = extension.toLowerCase();
  return fs
    .readdirSync(distReleaseDir)
    .filter((entry) => fs.statSync(path.join(distReleaseDir, entry)).isFile())
    .filter((entry) => entry.toLowerCase().endsWith(ext))
    .sort();
};

const pickFile = (files, description, preferredPattern = null) => {
  if (files.length === 0) {
    throw new Error(`No ${description} found in ${distReleaseDir}`);
  }
  if (preferredPattern) {
    const preferred = files.find((file) => preferredPattern.test(file));
    if (preferred) {
      return preferred;
    }
  }
  return files[0];
};

const renameArtifact = (currentName, nextName) => {
  const currentPath = path.join(distReleaseDir, currentName);
  const nextPath = path.join(distReleaseDir, nextName);
  if (currentName === nextName) {
    console.log(`Name already normalized: ${nextName}`);
    return;
  }
  if (fs.existsSync(nextPath)) {
    fs.rmSync(nextPath, { force: true });
  }
  fs.renameSync(currentPath, nextPath);
  console.log(`Renamed ${currentName} -> ${nextName}`);
};

if (target === TARGET_WINDOWS) {
  const exes = listFilesByExtension(".exe");
  const portable = pickFile(
    exes.filter((file) => /portable/i.test(file)),
    "Windows portable executable",
    /portable/i
  );
  const installer = pickFile(
    exes.filter((file) => !/portable/i.test(file)),
    "Windows installer executable",
    /(install|setup|nsis)/i
  );
  renameArtifact(installer, `${APP_NAME}_${version}_windows_x64_installer.exe`);
  renameArtifact(portable, `${APP_NAME}_${version}_windows_x64_portable.exe`);
} else if (target === TARGET_MACOS) {
  const dmgs = listFilesByExtension(".dmg");
  const dmg = pickFile(dmgs, "macOS dmg artifact", /universal/i);
  renameArtifact(dmg, `${APP_NAME}_${version}_macos_universal.dmg`);
} else if (target === TARGET_LINUX_APPIMAGE) {
  const appImages = listFilesByExtension(".AppImage");
  const appImage = pickFile(appImages, "Linux AppImage artifact", /(x64|x86_64)/i);
  renameArtifact(appImage, `${APP_NAME}_${version}_linux_x64_appimage.AppImage`);
} else if (target === TARGET_LINUX_DEB) {
  const debs = listFilesByExtension(".deb");
  const deb = pickFile(debs, "Linux deb artifact", /arm64/i);
  renameArtifact(deb, `${APP_NAME}_${version}_linux_arm64_deb.deb`);
} else {
  throw new Error(
    `Unknown target "${target}". Expected one of: windows, macos, linux-appimage, linux-deb`
  );
}
