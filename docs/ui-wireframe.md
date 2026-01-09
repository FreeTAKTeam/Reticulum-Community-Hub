Below are **low-fidelity UI wireframes** for the **RTH Core Administrative UI**, aligned with the screenshots and the previously defined specification.
They are **structural and behavioral wireframes**, not visual mockups, and are intended to guide frontend implementation.

---

## 1. Global Layout (All Screens)

```
┌──────────────────────────────────────────────────────────────┐
│  LEFT SIDEBAR (fixed)            │  MAIN CONTENT AREA         │
│                                  │                            │
│  ▣ RTH Logo                      │  Page Title                │
│                                  │  Context Actions           │
│  Home                            │  ───────────────────────   │
│  WebMap                          │  Page-Specific Content     │
│  Mission (Topics)                 │                            │
│  Topics                          │                            │
│  Files                           │                            │
│  Users                           │                            │
│  Configure                       │                            │
│  About                           │                            │
│                                  │                            │
└──────────────────────────────────────────────────────────────┘
```

**Rules**

* Sidebar always visible
* No modal-first navigation
* Context actions appear top-right
* Dark, low-contrast background

---

## 2. Home / Dashboard



```
┌──────────────────────────────────────────────────────────────┐
│ RTH STATUS                                                   │
│ ──────────────────────────────────────────────────────────   │
│ Uptime: 14d 06h     Nodes: 18     Topics: 7     Bans: 2      │
│                                                              │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐           │
│ │ Telemetry/s  │ │ LXMF Msg/s   │ │ Errors       │           │
│ │     42       │ │     11       │ │     0        │           │
│ └──────────────┘ └──────────────┘ └──────────────┘           │
│                                                              │
│ Recent Events                                                │
│ ──────────────────────────────────────────────────────────   │
│ [12:01] Node 8A3C joined topic SAR                           │
│ [12:00] Telemetry burst from CBT-Node-West                   │
│ [11:58] Identity 91F… blackholed                             │
└──────────────────────────────────────────────────────────────┘
```

**Data**

* REST: `GET /Status`, `GET /Events`
* WS: `/events/system` (status/event stream)

---

## 3. WebMap (Telemetry View)

![Image](https://cyberspacemanmike.com/wp-content/uploads/2025/04/cyberspacemanmikeTheWorldIsYours4.png)


```
┌──────────────────────────────────────────────────────────────┐
│ MAP CONTROLS (top-right)                                     │
│ [ Layers ] [ Topics ] [ Time ]                               │
│                                                              │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │                                                          │ │
│ │   ○ CBT (Canada)                                         │ │
│ │   ○ CBT (Europe)                                         │ │
│ │   ○ CBT (Africa)                                         │ │
│ │                                                          │ │
│ │   (Live markers update via WebSocket)                    │ │
│ │                                                          │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ TELEMETRY DETAILS (slide-in panel)                           │
│ ──────────────────────────────────────────────────────────   │
│ ID: CBT-Node-West                                           │
│ Topic: SAR                                                  │
│ Lat/Lon: …                                                  │
│ Speed: …   Heading: …                                       │
│ Battery: …                                                  │
└──────────────────────────────────────────────────────────────┘
```

**Notes**

* MapLibre GL
* Marker color by topic
* Offline tile support
* REST: `GET /Telemetry?since=<unix>&topic_id=<TopicID>`
* WS: `/telemetry/stream` (topic-scoped updates for subscribed identities)

---

## 4. Topics Management

![Image](https://cdn.dribbble.com/userupload/17756456/file/original-3d7fa94534b32923256a0a23fabd74c7.png?crop=0x0-3414x2561\&format=webp\&resize=400x300\&vertical=center)

![Image](https://balsamiq.com/assets/learn/articles/data-table/one-app.jpg)

![Image](https://docs.kentico.com/docsassets/k82/configuring-permissions/Permission_matrix.png)

```
┌──────────────────────────────────────────────────────────────┐
│ TOPICS                                                       │
│ ──────────────────────────────────────────────────────────   │
│ [ + Add Topic ]                                              │
│                                                              │
│ Name        | Subscribers | Msg/s | Private | Actions        │
│─────────────|─────────────|───────|─────────|──────────────│
│ SAR         | 12          | 4.2   | No      | Edit Delete  │
│ Logistics   | 5           | 0.9   | Yes     | Edit Delete  │
│ Broadcast   | 18          | 6.1   | No      | Edit Delete  │
└──────────────────────────────────────────────────────────────┘
```

**Notes**

* REST: `GET /Topic`, `POST /Topic`, `PATCH /Topic`, `DELETE /Topic?id=<TopicID>`
* Subscribers/Msg/s/Private columns are future (derived metrics + new fields).

---


```
┌──────────────────────────────────────────────────────────────┐
│ FILES & IMAGES                                               │
│ ──────────────────────────────────────────────────────────   │
│ [ Retrieve ]                                                 │
│                                                              │
│ Name              | Size | Media | Topic | Date    │
│───────────────────|──────|──────|───────|───────── |──────── │
│ map_tiles.zip     | 12MB | zip   | MAP   | …       │
│ mission_01.jpg    | 2MB  | jpg   | SAR   | …       │
│ config_backup.yml | 4KB  | yml   | —     | Yes     | …       │
└──────────────────────────────────────────────────────────────┘
```

**Notes**

* REST: `GET /File`, `GET /Image`, `GET /File/{id}`, `GET /Image/{id}`
* Upload/delete/visibility controls are future (requires new commands).

---

## 6. User & Identity Management



```
┌──────────────────────────────────────────────────────────────┐
│ IDENTITIES                                                   │
│ ────────────────────────────────────────────────────────── │
│ Identity Hash      | Alias | Status | Last Seen | Actions   │
│────────────────────|───────|────────|───────────|──────────│
│ 91F…A32            | —     | BANNED | 2h ago    | Unban    │
│ 8A3…C9E            | CBT-W | Active | Now       | Ban      │
│ D21…FF9            | —     | Active | 1m ago    | Blackhole│
└──────────────────────────────────────────────────────────────┘
```

**Actions**

* Ban
* Unban
* Blackhole (RNS 1.1.1)
* Inspect activity

**Data**

* REST: `GET /Identities`, `POST /Client/{id}/Ban`, `POST /Client/{id}/Unban`, `POST /Client/{id}/Blackhole`

---

## 7. Configuration Editor



```
┌──────────────────────────────────────────────────────────────┐
│ CONFIGURATION                                                │
│ ────────────────────────────────────────────────────────── │
│ [ Validate ] [ Apply ] [ Rollback ]                          │
│                                                              │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ telemetry:                                               │ │
│ │   retention_days: 7                                      │ │
│ │ topics:                                                  │ │
│ │   - sar                                                  │ │
│ │   - logistics                                            │ │
│ │ blackhole:                                               │ │
│ │   enabled: true                                          │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ ⚠ Restart required after apply                              │
└──────────────────────────────────────────────────────────────┘
```

**Data**

* REST: `GET /Config`, `PUT /Config`, `POST /Config/Validate`, `POST /Config/Rollback`

---

## 8. Command Console (Advanced)

```
┌──────────────────────────────────────────────────────────────┐
│ COMMAND CONSOLE                                              │
│ ──────────────────────────────────────────────────────────   │
│ > GetStatus                                                  │
│ > FlushTelemetry                                             │
│ > DumpRouting                                                │
│                                                              │
│ Output:                                                      │
│ [OK] Status returned                                         │
│ [OK] Telemetry flushed                                       │
│ [OK] Routing dumped                                          │
└──────────────────────────────────────────────────────────────┘
```

---

## 9. Wireframe Usage Notes

* Designed for **desktop-first**
* Tablet usable, mobile read-only
* No dependency on continuous connectivity
* Live updates via WS `/events/system` and `/telemetry/stream` (REST fallback)

---
