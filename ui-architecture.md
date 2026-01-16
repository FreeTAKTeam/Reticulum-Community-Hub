# UI Architecture

## Overview
The Reticulum Community Hub UI is a Vue 3 + Vite + TypeScript single-page application (SPA) that serves as the administrative console for the hub and communicates with REST and WebSocket endpoints for data and live updates.【F:ui/README.md†L1-L4】

## Application Entry and Shell
- The app boots in `src/main.ts`, which creates the Vue app, registers Pinia for state management and the router, loads base styles, and mounts the app to `#app`.【F:ui/src/main.ts†L1-L11】
- `App.vue` provides the top-level structure: an `AppShell` layout, an `ErrorBoundary` around the `RouterView`, and a global `BaseToast` for notifications.【F:ui/src/App.vue†L1-L13】
- `AppShell` composes the UI layout with a sidebar, header, a connection status banner, and a scrollable main content area for the routed pages.【F:ui/src/components/AppShell.vue†L1-L17】

## Routing and Pages
Routing is configured with Vue Router in `src/router/index.ts`. The UI defines routes for the dashboard, web map, topics, files, users, configuration, about, and a connect screen, each mapping to a page component under `src/pages/`.【F:ui/src/router/index.ts†L1-L22】

## State Management and Data Flow
- **Pinia stores** live in `src/stores/` and handle domain-specific state and operations. The connection store persists base URL, authentication mode, and credentials, exposes derived labels for status, and manages online/offline/auth state plus live connection counts.【F:ui/src/stores/connection.ts†L1-L144】
- Stores typically own data refresh and transformation logic. For example, the dashboard store fetches status and events from REST endpoints, normalizes payloads, updates UI state, and records connection status changes.【F:ui/src/stores/dashboard.ts†L1-L86】

## API Layer (REST)
- REST calls are centralized in `src/api/client.ts`. It builds headers based on the connection store (including bearer or API key auth), applies timeouts/retries, and updates connection/auth status based on responses.【F:ui/src/api/client.ts†L1-L150】
- Mock responses can be enabled with `VITE_RCH_MOCK=true` for offline development, returning simulated responses from `mockFetch` instead of issuing network requests.【F:ui/src/api/client.ts†L14-L16】【F:ui/src/api/client.ts†L70-L101】

## WebSocket Layer (Live Updates)
- Live telemetry/system events use `WsClient` in `src/api/ws.ts`. On connection, it sends authentication info, registers the live connection with the connection store, and listens for messages (including ping/pong handling).【F:ui/src/api/ws.ts†L10-L92】
- The WebSocket client retries with exponential backoff and can emit mock telemetry/system events when mock mode is enabled, providing realistic live-update behavior in offline development scenarios.【F:ui/src/api/ws.ts†L94-L147】

## Configuration and Deployment
- Environment variables control REST and WebSocket base URLs and optional mock mode; by default the UI uses the browser origin if no base URL is provided.【F:ui/README.md†L20-L38】
- The UI can be deployed either embedded with the hub (serving `dist/` from the service) or hosted externally behind a reverse proxy and configured via the Connect screen.【F:ui/README.md†L40-L43】
