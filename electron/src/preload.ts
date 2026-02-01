import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("rchDesktop", {
  platform: process.platform,
  versions: {
    chrome: process.versions.chrome,
    electron: process.versions.electron,
    node: process.versions.node,
  },
});
