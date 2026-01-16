# RCH Core UI — Implementation Tasks (Codex)

This task list implements the **RCH Core Administrative UI** described in:

- `docs/ui-design.md`
- `docs/ui-wireframe.md`
- `API/ReticulumCommunityHub-OAS.yaml`

## Assumptions / Inputs

- REST base URL is configurable (embedded UI uses same-origin).
- Protected endpoints require auth (`bearerAuth` and/or `X-API-Key`) as defined in `API/ReticulumCommunityHub-OAS.yaml`.
- WebSocket endpoints follow the RCH-WS v1 envelope described in `docs/ui-design.md` and documented (as extensions) in `API/ReticulumCommunityHub-OAS.yaml`:
  - `/events/system`
  - `/telemetry/stream`

---

## 0) Repo Scaffolding

- [x] Create a new frontend workspace folder (recommended: `ui/`).
- [x] Add a top-level `ui/README.md` with dev + build instructions.
- [x] Decide and document the supported Node version (recommend LTS) and package manager (npm/pnpm).

---

## 1) UI Project Setup (Vue 3 + Vite + TS + Tailwind)

- [x] Scaffold a Vue 3 + TypeScript app (Vite).
- [x] Add TailwindCSS (dark theme baseline) and a minimal design-token layer (CSS variables or Tailwind theme extension).
- [x] Add Vue Router (SPA routes) and Pinia (state).
- [x] Add a small component library layer (shared `Button`, `Input`, `Select`, `Card`, `Table`, `Badge`, `Modal/Drawer`, `Toast`).
- [x] Add dev-time API base URL config:
  - `.env` support (e.g., `VITE_RCH_BASE_URL`)
  - optional Vite dev proxy for same-origin local development

Acceptance:
- `npm run dev` starts the UI.
- `npm run build` produces a production build artifact.

---

## 2) Route Map + App Shell

- [x] Implement app shell layout:
  - fixed left sidebar
  - header with page title + context actions area
  - content area with consistent padding and scrolling behavior
- [x] Implement routes (exact paths can vary, but map 1:1 to modules):
  - Home (Dashboard)
  - WebMap
  - Topics
  - Files
  - Users
  - Configure (Config + Tools)
  - About
  - (optional) Connect
- [x] Add a global error boundary + “offline/connection lost” banner region.

Acceptance:
- Navigation matches `docs/ui-wireframe.md` and is keyboard accessible.

---

## 3) Typed REST Client (OpenAPI-first)

- [x] Generate TypeScript types from `API/ReticulumCommunityHub-OAS.yaml` (or hand-author minimal types if generation is skipped).
- [x] Implement a small `rthApi` client:
  - base URL handling
  - JSON + text/plain endpoints
  - timeout + retry policy for idempotent GETs
  - consistent error shape (status, message, body)
- [x] Implement auth injection:
  - `Authorization: Bearer <token>` OR `X-API-Key: <key>`
  - allow runtime switching (Connect page)
- [x] Implement request helpers for the UI surface:
  - status/events
  - topics CRUD
  - subscribers CRUD + add
  - identities list + ban/unban/blackhole
  - clients list
  - files/images list + metadata + raw download
  - config get/validate/apply/rollback
  - tools endpoints (`/Command/*`, `/Help`, `/Examples`)

Acceptance:
- One place to configure base URL + auth; all pages use it.

---

## 4) WebSocket Client (RCH-WS v1)

- [x] Implement a reusable WS client wrapper:
  - connect/reconnect with exponential backoff
  - send `auth` message immediately after open
  - ping/pong handling (application-level)
  - clean close + state transitions
- [x] Implement `/events/system` stream consumption:
  - handle `system.status` updates → update dashboard store
  - handle `system.event` updates → append to event feed store (bounded buffer)
- [x] Implement `/telemetry/stream` stream consumption:
  - send `telemetry.subscribe` with `since` and optional `topic_id`
  - handle `telemetry.snapshot` → hydrate telemetry store
  - handle `telemetry.update` → incremental marker updates

Acceptance:
- UI shows “Live” connection indicators and falls back to REST polling if WS is unavailable.

---

## 5) Pinia Stores (Single Source of Truth)

- [x] `connectionStore`: base URL, auth mode, credentials (with secure persistence rules), connection status.
- [x] `dashboardStore`: status snapshot + recent events buffer.
- [x] `topicsStore`: topics list + CRUD helpers + optimistic UI state.
- [x] `subscribersStore`: list + filters + CRUD helpers.
- [x] `filesStore`: files/images lists + download/preview state.
- [x] `usersStore`: clients + identities + moderation actions.
- [x] `configStore`: config text + validate/apply/rollback state.
- [x] `telemetryStore`: telemetry entries keyed by identity + derived map marker model.

Acceptance:
- Page refresh does not lose navigation; optional persistence only for Connect settings (configurable).

---

## 6) Pages

### 6.1 Home (Dashboard)

- [x] Render status cards from `GET /Status` and live updates from `/events/system`.
- [x] Render recent events list from `GET /Events` and live updates.
- [x] Add “stale telemetry” indicator based on `telemetry.last_ingest_at`.

### 6.2 WebMap

- [x] Add MapLibre GL map with dark style (offline-capable style configuration).
- [x] Render markers for identities with recent location telemetry.
- [x] Implement topic filter (drives REST query + WS subscription).
- [x] Implement identity quick-search and selection.
- [x] Implement a telemetry inspector panel (raw JSON + key fields).

### 6.3 Topics

- [x] Topics table (list, create, edit, delete) using `/Topic`.
- [x] Subscribers tab:
  - list subscribers (`GET /Subscriber`)
  - add subscriber (`POST /Subscriber/Add` or `POST /Subscriber`)
  - edit (`PATCH /Subscriber`)
  - delete (`DELETE /Subscriber?id=...`)
- [x] Confirm destructive operations and handle 401/403 gracefully.

### 6.4 Files

- [x] Tabs: Files and Images.
- [x] List + metadata views (`GET /File`, `GET /Image`).
- [x] Download raw bytes (`GET /File/{id}/raw`, `GET /Image/{id}/raw`).
- [x] Image preview modal (blob URL) + download.

### 6.5 Users

- [x] Clients tab (`GET /Client`) with last-seen and metadata display.
- [x] Identities tab (`GET /Identities`) with moderation status.
- [x] Actions: ban/unban/blackhole (`POST /Client/{id}/...`) with optimistic UI + rollback on failure.
- [x] Advanced: routing snapshot (`GET /Command/DumpRouting`) shown as a collapsible panel.

### 6.6 Configure

- [x] Config editor:
  - load (`GET /Config`)
  - validate (`POST /Config/Validate`)
  - apply (`PUT /Config`)
  - rollback (`POST /Config/Rollback`)
  - show apply/rollback results and warnings (restart required)
- [x] Tools tab:
  - quick actions for `/Command/*`
  - raw response viewer
  - link to `/Help` and `/Examples`

### 6.7 About

- [x] Display `GET /api/v1/app/info` (name/version/description + RNS/LXMF versions + storage paths).
- [x] Link to project docs (`docs/`) and OpenAPI reference (`API/ReticulumCommunityHub-OAS.yaml`).

### 6.8 Connect (Optional)

- [x] Provide base URL + auth configuration UX.
- [x] Implement “Test Connection” using `/api/v1/app/info` and `/Status`.

Acceptance:
- All pages match `docs/ui-wireframe.md` behaviorally (same modules, data sources, and actions).

---

## 7) UX, Accessibility, and Resilience

- [x] Loading skeletons for table/map-heavy pages.
- [x] Toasts for success/failure; inline error details for validation failures.
- [x] Pagination or client-side virtualization for large tables (topics/subscribers/identities/files).
- [x] Keyboard navigation and focus management (modals/drawers).
- [x] Role/permission messaging: differentiate “not authenticated” vs “forbidden”.

---

## 8) QA / Testing

- [x] Add unit tests for:
  - REST client error handling and auth injection
  - WS message parsing and reconnect behavior
  - telemetry-to-marker derivation helpers
- [x] Add a mock API mode (fixture JSON + mock WS) so UI can be developed without a live hub.

---

## 9) Packaging / Deployment

- [x] Document two deployment modes:
  - embedded UI (served by the hub / same-origin)
  - external UI (reverse proxy; Connect screen enabled)
- [x] Produce a “build artifact” plan (where `dist/` is published/served from).

