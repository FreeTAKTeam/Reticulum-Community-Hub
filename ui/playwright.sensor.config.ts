import { defineConfig } from "@playwright/test";
import config from "./playwright.config";
export default defineConfig({ ...config, testMatch:"sensor-geometry.spec.ts", testIgnore:[], use:{...config.use,baseURL:"http://127.0.0.1:4188"},
  webServer:{command:"npm run dev -- --host 127.0.0.1 --port 4188 --strictPort",url:"http://127.0.0.1:4188/connect",reuseExistingServer:false,timeout:60000} });
