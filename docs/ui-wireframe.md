Below are **low-fidelity UI wireframes** for the **RTH Core Administrative UI**.
They are **structural and behavioral wireframes** (not visual mockups) intended to guide frontend implementation.

---

## 1. Global Layout (All Screens)

```
+----------------------+----------------------------------------------+
| LEFT SIDEBAR (fixed) | MAIN CONTENT                                  |
|----------------------|----------------------------------------------|
| RTH Logo             | Page Title                      [Actions...] |
|                      |----------------------------------------------|
| Home                 | Page-specific content                         |
| WebMap               |                                              |
| Topics               |                                              |
| Files                |                                              |
| Users                |                                              |
| Configure            |                                              |
| About                |                                              |
|                      |                                              |
| (optional) Connect   |                                              |
+----------------------+----------------------------------------------+
```

Rules:

- Sidebar always visible (desktop-first)
- Context actions live top-right of the main header
- Prefer pages over modal-first navigation (modals only for create/edit confirmations)
- Dark, low-contrast tactical theme

---

## 2. Connect (Optional; external UI deployments)

Purpose: configure how the UI connects/authenticates to an RTH instance when the UI is not embedded.

```
+--------------------------------------------------------------+
| CONNECT                                                      |
|--------------------------------------------------------------|
| API Base URL:  [ https://rth.local:8000                ]      |
| Auth Mode:     ( API Key ) ( JWT )                            |
| API Key / JWT: [ ************************************* ]      |
|                                                              |
| [ Test Connection ]  [ Save ]  [ Clear ]                      |
|--------------------------------------------------------------|
| Status: Connected | /api/v1/app/info: OK | /Status: OK        |
+--------------------------------------------------------------+
```

Notes:

- Stored settings should be clearly marked as sensitive.
- “Test Connection” calls `GET /api/v1/app/info` and `GET /Status`.

---

## 3. Home / Dashboard

```
+--------------------------------------------------------------+
| HOME / DASHBOARD                                             |
|--------------------------------------------------------------|
| Uptime: 14d 06h  | Clients: 18 | Topics: 7 | Subscribers: 22 |
| Files: 12 | Images: 4 | Telemetry ingest: 1234 (last: 1m)    |
|--------------------------------------------------------------|
| Recent Events                                                |
|--------------------------------------------------------------|
| [12:01] topic_created: Topic created: topic-abc              |
| [12:00] telemetry_received: Telemetry received from ...      |
| [11:58] identity_blackholed: Identity blackholed: ...        |
+--------------------------------------------------------------+
```

Data:

- REST: `GET /Status`, `GET /Events`
- WS: `/events/system` (status + event stream)

---

## 4. WebMap (Telemetry View)

```
+--------------------------------------------------------------+
| WEBMAP                                                       |
|--------------------------------------------------------------|
| [ Topic: All v ] [ Identity: search... ] [ Time: Live v ]     |
|--------------------------------------------------------------|
| +-------------------------------+  +------------------------+ |
| |                               |  | Selected Entity        | |
| |            MAP                |  |------------------------| |
| |      (MapLibre/GL)            |  | Identity: ...          | |
| |                               |  | Last seen: ...         | |
| |                               |  | Location: lat/lon/...  | |
| |                               |  | Sensors: ...           | |
| +-------------------------------+  +------------------------+ |
|--------------------------------------------------------------|
| (optional) Entity list / filters panel                         |
+--------------------------------------------------------------+
```

Actions:

- select marker → view telemetry inspector
- filter by topic and identity
- (phase 2) time replay

Data:

- REST: `GET /Telemetry?since=<unix>&topic_id=<TopicID>`, `GET /Topic`, `GET /Identities`
- WS: `/telemetry/stream`

---

## 5. Topics (Topics + Subscribers)

```
+--------------------------------------------------------------+
| TOPICS                                                       |
|--------------------------------------------------------------|
| Tabs: [ Topics ] [ Subscribers ]                              |
|--------------------------------------------------------------|
| (Topics tab)                                                  |
| [ + Create Topic ]                                            |
|--------------------------------------------------------------|
| TopicID     | TopicName | TopicPath          | Actions        |
| topic-1     | SAR       | sar                | Edit Delete    |
| topic-2     | Logistics | logistics          | Edit Delete    |
|--------------------------------------------------------------|
| (Subscribers tab)                                             |
| [ + Add Subscriber ]  Filter: Topic [All v] Destination [...] |
|--------------------------------------------------------------|
| SubscriberID | Destination | TopicID  | RejectTests | Actions |
| sub-1        | ...         | topic-1  | 0           | Edit Del |
+--------------------------------------------------------------+
```

Data:

- Topics: `GET /Topic`, `GET /Topic/{id}`, `POST /Topic`, `PATCH /Topic`, `DELETE /Topic`
- Subscribers: `GET /Subscriber`, `GET /Subscriber/{id}`, `POST /Subscriber`, `POST /Subscriber/Add`, `PATCH /Subscriber`, `DELETE /Subscriber`

---

## 6. Files (Files + Images)

```
+--------------------------------------------------------------+
| FILES                                                        |
|--------------------------------------------------------------|
| Tabs: [ Files ] [ Images ]                                    |
| Filter: Topic [All v]  Search [ name... ]                     |
|--------------------------------------------------------------|
| FileID | Name      | TopicID | Size | UpdatedAt | Actions     |
| 1      | doc.pdf   | topic-1 | 12k  | ...       | Download    |
| 2      | photo.jpg | topic-2 | 88k  | ...       | Preview DL  |
+--------------------------------------------------------------+
```

Data:

- List: `GET /File`, `GET /Image`
- Metadata: `GET /File/{id}`, `GET /Image/{id}`
- Raw bytes: `GET /File/{id}/raw`, `GET /Image/{id}/raw`

---

## 7. Users (Clients + Identities)

```
+--------------------------------------------------------------+
| USERS                                                        |
|--------------------------------------------------------------|
| Tabs: [ Clients ] [ Identities ]                              |
|--------------------------------------------------------------|
| (Clients tab)                                                 |
| Identity     | LastSeen              | Metadata | Actions     |
| ...          | 2026-...              | {...}    | Inspect     |
|--------------------------------------------------------------|
| (Identities tab)                                              |
| Identity     | Status      | LastSeen | Actions                |
| ...          | active      | ...      | Ban  Blackhole         |
| ...          | banned      | ...      | Unban                  |
| ...          | blackholed  | ...      | Unban                  |
+--------------------------------------------------------------+
```

Data:

- REST: `GET /Client`, `GET /Identities`
- Actions: `POST /Client/{id}/Ban`, `POST /Client/{id}/Unban`, `POST /Client/{id}/Blackhole`
- Advanced: `GET /Command/DumpRouting`

---

## 8. Configure (Config Editor + Tools)

### 8.1 Configuration Editor

```
+--------------------------------------------------------------+
| CONFIGURE                                                     |
|--------------------------------------------------------------|
| Tabs: [ Config ] [ Tools ]                                    |
|--------------------------------------------------------------|
| (Config tab)                                                  |
| [ Validate ] [ Apply ] [ Rollback ]                           |
|--------------------------------------------------------------|
| config.ini (editor)                                           |
|--------------------------------------------------------------|
| [app]                                                        |
| name = ...                                                    |
| ...                                                          |
|--------------------------------------------------------------|
| Validation / Apply results (inline panel)                     |
+--------------------------------------------------------------+
```

Data:

- REST: `GET /Config`, `PUT /Config`, `POST /Config/Validate`, `POST /Config/Rollback`

### 8.2 Tools / Command Console (Advanced)

```
+--------------------------------------------------------------+
| TOOLS                                                        |
|--------------------------------------------------------------|
| Quick actions: [ Status ] [ Events ] [ DumpRouting ]          |
|               [ ReloadConfig ] [ FlushTelemetry ]             |
|--------------------------------------------------------------|
| Raw request / response log                                   |
|--------------------------------------------------------------|
| > GET /Status                                                 |
| < 200 { ... }                                                 |
+--------------------------------------------------------------+
```

---

## 9. About

```
+--------------------------------------------------------------+
| ABOUT                                                        |
|--------------------------------------------------------------|
| App: RTH (9.9.9)                                             |
| Description: ...                                             |
| Reticulum: ... | LXMF: ...                                   |
|--------------------------------------------------------------|
| Paths                                                         |
| - config.ini: ...                                             |
| - database: ...                                               |
| - storage: ...                                                |
| - files: ...                                                  |
| - images: ...                                                 |
+--------------------------------------------------------------+
```

Data:

- REST: `GET /api/v1/app/info`

---

## 10. Wireframe Usage Notes

- Desktop-first; tablet usable; mobile read-only.
- Live updates use WS `/events/system` and `/telemetry/stream` with REST fallback.
- All “protected” operations must surface auth failures clearly (401/403) and provide a recovery path (Connect screen / re-auth).

