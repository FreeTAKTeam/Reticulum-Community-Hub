# UI Architecture

## Overview
The Reticulum Community Hub UI is a Vue 3 + Vite + TypeScript single-page
application (SPA) that serves as the administrative console for the hub. It
communicates with REST and WebSocket endpoints for data retrieval and live
updates.

## Application Entry and Shell
- The app boots in `src/main.ts`, where Vue, Pinia, and the router are
  initialized before mounting on `#app`.
- `App.vue` provides the top-level composition with `AppShell`, `ErrorBoundary`,
  and global toast notifications.
- `AppShell` provides the persistent navigation frame (sidebar, header, status
  banner, and routed content area).

## Routing and Pages
- Routing is configured in `src/router/index.ts` and maps route paths to page
  components under `src/pages/`.
- Core pages include dashboard, web map, topics, files, users, configuration,
  about, and connect.
- `WebMapPage.vue` is the operator workspace for marker and zone interactions,
  including zone draw, rename, geometry edit, focus, and delete workflows.

## State Management and Data Flow
- Domain state lives in Pinia stores under `src/stores/`.
- `connection` store owns base URL/auth configuration and online/auth status.
- `dashboard` store fetches and normalizes status/event data for dashboard views.
- `zones` store owns zone collection state, computed index maps, and REST-backed
  create/update/delete actions with point normalization for rendering.

## API Layer (REST)
- REST requests are centralized in `src/api/client.ts`, which applies auth
  headers, timeout/retry behavior, and connection/auth state updates.
- Zone operations use northbound endpoints under `/api/zones` for list/create/
  update/delete.
- Mock mode (`VITE_RCH_MOCK=true`) can return simulated API responses for
  offline development.

## WebSocket Layer (Live Updates)
- Live telemetry and system events are handled by `WsClient` in `src/api/ws.ts`.
- The client authenticates on connect, tracks active connections, handles
  ping/pong, and retries with exponential backoff.
- Mock mode can emit simulated live events to support UI development without a
  running backend.

## Configuration and Deployment
- Environment variables control REST/WebSocket base URLs and mock behavior.
- The UI can run embedded with the hub (serving `dist/`) or be hosted
  externally and pointed at a hub from the Connect screen.
