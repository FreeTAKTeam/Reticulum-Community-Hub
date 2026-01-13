# RTH Core UI

The RTH Core UI is the administrative console for the Reticulum Telemetry Hub. It is a Vue 3 + Vite + TypeScript SPA that talks to the hub's REST and WebSocket endpoints.

## Requirements

- Node.js 20 LTS (recommended)
- npm 10+

## Development

```bash
cd ui
npm install
npm run dev
```

By default, the UI talks to the same origin. To target a different hub, set `VITE_RTH_BASE_URL`:

```bash
VITE_RTH_BASE_URL="https://example-hub" npm run dev
```

## Build

```bash
npm run build
npm run preview
```

## Environment Variables

- `VITE_RTH_BASE_URL`: Optional base URL for the REST/WS endpoints. When unset, the UI uses the browser origin.
- `VITE_RTH_WS_BASE_URL`: Optional explicit WebSocket base URL (defaults to the REST base URL with ws/wss).
- `VITE_RTH_MAP_STYLE_URL`: Optional MapLibre style URL (use a local/offline style for disconnected environments).
- `VITE_RTH_MOCK`: Set to `true` to enable mock REST/WS responses for offline UI development.

## Deployment Modes

- **Embedded UI**: Serve the `dist/` folder from the hub service (same-origin).
- **External UI**: Host the `dist/` folder behind a reverse proxy and use the Connect screen to set base URL and credentials.
