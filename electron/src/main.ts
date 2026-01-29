import { app } from "electron";
import { BrowserWindow } from "electron";
import { spawn } from "child_process";
import { ChildProcess } from "child_process";
import fs from "fs";
import path from "path";

type UiTarget = {
  kind: "file" | "url";
  value: string;
};

const DEFAULT_WIDTH = 1280;
const DEFAULT_HEIGHT = 800;
const MIN_WIDTH = 960;
const MIN_HEIGHT = 640;
const DEFAULT_BACKEND_PORT = "8000";
const DEFAULT_LOG_LEVEL = "info";

let backendProcess: ChildProcess | null = null;
let backendLogStream: fs.WriteStream | null = null;

const shouldManageBackend = (): boolean => {
  const envValue = process.env.RCH_BACKEND_MANAGED;
  if (envValue !== undefined) {
    return envValue === "1" || envValue.toLowerCase() === "true";
  }
  return app.isPackaged;
};

const resolveBackendExecutable = (): string => {
  const backendName = process.platform === "win32" ? "rch-backend.exe" : "rch-backend";
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "backend", backendName);
  }
  return path.join(__dirname, "..", "backend", backendName);
};

const parseExtraArgs = (): string[] => {
  const rawArgs = process.env.RCH_BACKEND_ARGS;
  if (!rawArgs) {
    return [];
  }
  return rawArgs.split(" ").map((entry) => entry.trim()).filter(Boolean);
};

const resolveBackendArgs = (): string[] => {
  const dataDir = process.env.RCH_DATA_DIR ?? path.join(app.getPath("userData"), "RCH_Store");
  fs.mkdirSync(dataDir, { recursive: true });
  const port = process.env.RCH_BACKEND_PORT ?? DEFAULT_BACKEND_PORT;
  const logLevel = process.env.RCH_LOG_LEVEL ?? DEFAULT_LOG_LEVEL;
  return ["--data-dir", dataDir, "--port", port, "start", "--log-level", logLevel, ...parseExtraArgs()];
};

const resolveBackendLogPath = (): string => {
  return path.join(app.getPath("userData"), "backend.log");
};

const startBackendLogging = (): fs.WriteStream => {
  const logPath = resolveBackendLogPath();
  const stream = fs.createWriteStream(logPath, { flags: "a" });
  stream.write(`\n--- RCH backend start ${new Date().toISOString()} ---\n`);
  return stream;
};

const startBackend = (): void => {
  if (!shouldManageBackend() || backendProcess) {
    return;
  }
  const backendPath = resolveBackendExecutable();
  if (!fs.existsSync(backendPath)) {
    console.warn(`RCH backend executable not found at ${backendPath}.`);
    return;
  }
  const spawnOptions = {
    cwd: app.getPath("userData"),
    windowsHide: true,
    stdio: app.isPackaged ? "pipe" : "inherit"
  } as const;
  backendProcess = spawn(backendPath, resolveBackendArgs(), spawnOptions);
  if (app.isPackaged && backendProcess.stdout && backendProcess.stderr) {
    backendLogStream = startBackendLogging();
    backendProcess.stdout.pipe(backendLogStream, { end: false });
    backendProcess.stderr.pipe(backendLogStream, { end: false });
  }
  backendProcess.on("error", (error) => {
    console.warn("Failed to start RCH backend.", error);
    if (backendLogStream) {
      backendLogStream.write(`Backend spawn error: ${String(error)}\n`);
    }
  });
  backendProcess.on("exit", (code, signal) => {
    console.warn(`RCH backend exited (code=${code ?? "null"}, signal=${signal ?? "none"}).`);
    if (backendLogStream) {
      backendLogStream.write(`Backend exit (code=${code ?? "null"}, signal=${signal ?? "none"})\n`);
      backendLogStream.end();
      backendLogStream = null;
    }
    backendProcess = null;
  });
};

const stopBackend = (): void => {
  if (!backendProcess) {
    return;
  }
  backendProcess.kill();
  backendProcess = null;
  if (backendLogStream) {
    backendLogStream.write(`Backend stop ${new Date().toISOString()}\n`);
    backendLogStream.end();
    backendLogStream = null;
  }
};

const resolveUiTarget = (): UiTarget => {
  const devServerUrl = process.env.ELECTRON_START_URL;
  if (devServerUrl && devServerUrl.trim() !== "") {
    return { kind: "url", value: devServerUrl };
  }

  if (app.isPackaged) {
    return {
      kind: "file",
      value: path.join(process.resourcesPath, "ui", "index.html"),
    };
  }

  return {
    kind: "file",
    value: path.join(__dirname, "..", "..", "ui", "dist", "index.html"),
  };
};

const createWindow = async (): Promise<void> => {
  const mainWindow = new BrowserWindow({
    width: DEFAULT_WIDTH,
    height: DEFAULT_HEIGHT,
    minWidth: MIN_WIDTH,
    minHeight: MIN_HEIGHT,
    backgroundColor: "#0a0f18",
    show: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  const uiTarget = resolveUiTarget();
  if (uiTarget.kind === "url") {
    await mainWindow.loadURL(uiTarget.value);
  } else {
    await mainWindow.loadFile(uiTarget.value);
  }
};

const startApp = (): void => {
  app.whenReady()
    .then(() => {
      startBackend();
      return createWindow();
    })
    .catch((error) => {
      console.error("Failed to create Electron window.", error);
      app.quit();
    });
};

startApp();

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    void createWindow();
  }
});

app.on("window-all-closed", () => {
  stopBackend();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  stopBackend();
});
