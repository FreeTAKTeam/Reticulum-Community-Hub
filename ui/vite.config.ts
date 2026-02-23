import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ command }) => ({
  base: command === "build" ? "./" : "/",
  plugins: [vue()],
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          // Keep MDI raw SVG imports lazily split instead of forcing one giant vendor chunk.
          if (id.includes("@mdi/svg/svg/") && id.includes(".svg?raw")) {
            return undefined;
          }
          if (id.includes("maplibre-gl")) {
            return "vendor-maplibre";
          }
          if (id.includes("vue")) {
            return "vendor-vue";
          }
          if (id.includes("markdown-it")) {
            return "vendor-markdown";
          }
          return "vendor";
        }
      }
    }
  },
  server: {
    port: 5173,
    strictPort: true
  }
}));
