# RCH Core Administrative UI Design

## 1. Purpose and Scope

**RCH Core UI** is the **administrative control plane** for a Reticulum Community Hub (RCH) instance.

It is intended for:

- Operators of RCH nodes (fixed, mobile, or gateway)
- Administrators managing telemetry, topics, subscribers, files/images, identities, and configuration
- Situational awareness and network hygiene (abuse prevention, bans, blackholing)

This is **not** a Sideband/MeshChat-style client; it is a **server management console**.

---

## 2. Architecture

### 2.1 High-Level

- UI: single-page app (SPA) in a web browser
- Backend: RCH REST API + WebSockets
- Source of truth: RCH storage + runtime state

### 2.2 Communication Model

| Channel | Technology | Purpose |
| --- | --- | --- |
| REST | JSON over HTTPS | CRUD, configuration, snapshots, command-like actions |
| WebSocket | JSON over WSS | live telemetry + live dashboard events |
| Auth | API key and/or JWT | required for protected admin operations |

### 2.3 WebSocket Event Contracts (RCH-WS v1)

#### 2.3.1 Envelope

All WS payloads are UTF-8 JSON text frames using a shared envelope:

```json
{
  "type": "system.status",
  "ts": "2026-01-11T00:00:00Z",
  "data": {}
}
```

- `type` (string, required): message discriminator
- `ts` (string, RFC3339, required): server timestamp when emitted
- `data` (object, required): type-specific payload

#### 2.3.2 Authentication Handshake

1. Client opens a socket to the endpoint (see below).
2. Client must send one auth message within 5 seconds:

```json
{
  "type": "auth",
  "ts": "2026-01-11T00:00:00Z",
  "data": { "token": "<JWT>", "api_key": "<API_KEY>" }
}
```

- Provide **either** `token` or `api_key` (or both).
- Server replies with:
  - `auth.ok` (stream begins), or
  - `error` and then closes.

#### 2.3.3 `/events/system` (dashboard + event stream)

Server-to-client messages:

- `system.status` → `data` is the same shape as `GET /Status`.
- `system.event` → `data` is the same shape as one item from `GET /Events`.
- `ping` → `data: { "nonce": "<string>" }` (periodic keepalive).

Client-to-server messages:

- `pong` → `data: { "nonce": "<string>" }` (echo nonce).
- `system.subscribe` (optional) → `data: { "include_status": true, "include_events": true, "events_limit": 50 }`.

#### 2.3.4 `/telemetry/stream` (live telemetry)

Client-to-server messages:

```json
{
  "type": "telemetry.subscribe",
  "ts": "2026-01-11T00:00:00Z",
  "data": { "since": 1700000000, "topic_id": "topic-123", "follow": true }
}
```

- `since` (unix seconds, required): identical meaning to `GET /Telemetry?since=...`
- `topic_id` (string, optional): identical meaning to `GET /Telemetry?topic_id=...`
- `follow` (boolean, optional, default `true`): whether to stream updates after the snapshot

Server-to-client messages:

- `telemetry.snapshot` → `data: { "entries": [TelemetryEntry...] }`
- `telemetry.update` → `data: { "entry": TelemetryEntry }`
- `ping` / `pong` same as `/events/system`

#### 2.3.5 Errors

Errors are always:

```json
{
  "type": "error",
  "ts": "2026-01-11T00:00:00Z",
  "data": { "code": "unauthorized", "message": "..." }
}
```

---

## 3. UI Technology Stack (Recommended)

| Layer | Recommendation |
| --- | --- |
| Frontend | Vue 3 + TypeScript (Vite) |
| Mapping | MapLibre GL JS (offline-capable, non-Google) |
| Styling | TailwindCSS + custom dark theme |
| State | Pinia |
| Transport | REST + WebSocket |
| Packaging | static build served by RCH or reverse proxy |

---

## 4. Navigation / Information Architecture

Primary sidebar items:

- Home (Dashboard)
- WebMap (Telemetry)
- Topics (Topics + Subscribers)
- Files (Files + Images)
- Users (Clients + Identity moderation)
- Configure (Config editor + tools)
- About

Optional (only for “external UI” deployments):

- Connect (base URL + credentials)

---

## 5. Functional Modules

## 5.1 Dashboard (Home)

Purpose: immediate system situational awareness.

Features:

- uptime, connected clients, topic/subscriber counts
- telemetry ingest counters
- recent events
- “stale data” warnings (no telemetry ingest for N minutes)

Data Source:

- REST: `GET /Status`, `GET /Events`
- WS: `/events/system` (`system.status`, `system.event`)

---

## 5.2 WebMap (Telemetry Visualization)

Core capability: live map rendering of telemetry entities.

Features:

- topic filter (topic-scoped telemetry)
- identity filter and quick-search
- marker clustering
- telemetry inspector panel (raw + humanized)
- optional time replay (phase 2)

Data Flow:

- initial load: `GET /Telemetry?since=<unix>&topic_id=<TopicID>`
- live updates: WS `/telemetry/stream` (`telemetry.subscribe` + updates)

---

## 5.3 Topics & Subscribers

Topics:

- list / create / edit / delete topics
- view topic details (name/path/description/id)

Subscribers:

- list subscribers, filtered by topic and destination
- add subscriber mapping (admin)
- edit subscriber metadata / reject-tests flag
- delete subscriber mapping

API:

- `GET /Topic`, `GET /Topic/{id}`, `POST /Topic`, `PATCH /Topic`, `DELETE /Topic`
- `GET /Subscriber`, `GET /Subscriber/{id}`, `POST /Subscriber`, `POST /Subscriber/Add`, `PATCH /Subscriber`, `DELETE /Subscriber`
- client self-subscribe (public): `POST /Topic/Subscribe`

---

## 5.4 Files & Images

Features:

- list file and image attachments (with TopicID when available)
- preview images
- download raw bytes
- filter by topic_id and name

API:

- `GET /File`, `GET /File/{id}`, `GET /File/{id}/raw`
- `DELETE /File/{id}`
- `GET /Image`, `GET /Image/{id}`, `GET /Image/{id}/raw`
- `DELETE /Image/{id}`

---

## 5.5 Users (Clients + Identity Moderation)

Features:

- list joined clients and last-seen
- list identity moderation state (active/banned/blackholed)
- actions: ban / unban / blackhole
- routing snapshot (advanced)

API:

- `GET /Client` (joined clients)
- `GET /Identities`, `POST /Client/{id}/Ban`, `POST /Client/{id}/Unban`, `POST /Client/{id}/Blackhole`
- `GET /Command/DumpRouting`

---

## 5.6 Configuration

Features:

- view/edit `config.ini`
- validate before apply
- apply with restart-required warning
- rollback to latest backup

API:

- `GET /Config`, `PUT /Config`
- `POST /Config/Validate`, `POST /Config/Rollback`

---

## 5.7 Command Console (Advanced)

Purpose: controlled access to “power user” operations.

Capabilities:

- quick-call common operations (Status, Events, DumpRouting, ReloadConfig, FlushTelemetry)
- show raw HTTP response payload + errors

API:

- `GET /Help`, `GET /Examples`
- `POST /Command/FlushTelemetry`, `POST /Command/ReloadConfig`, `GET /Command/DumpRouting`

---

## 5.8 About

Features:

- app name, version, description
- Reticulum + LXMF versions
- storage paths (db/config/files/images)

API:

- `GET /api/v1/app/info`

---

## 6. Security Model

- Auth mechanism is intentionally minimal for phase 1; admin UI assumes trusted operators.
- Protected endpoints must require auth; public endpoints should remain safe to expose.
- The UI should support:
  - per-request auth headers for REST
  - WS `auth` handshake before streaming
- All stateful secrets stored client-side should be treated as sensitive (avoid localStorage in hardened deployments).

