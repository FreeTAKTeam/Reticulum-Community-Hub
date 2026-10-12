# RCH Core UI

The RCH Core UI is the administrative console for the Reticulum Community Hub. It is a Vue 3 + Vite + TypeScript SPA that talks to the hub's REST and WebSocket endpoints.

## Requirements

- Node.js 20 LTS (recommended)
- npm 10+

## Development

```bash
cd ui
npm install
npm run dev
```

By default, the UI talks to the same origin. To target a different hub, set `VITE_RCH_BASE_URL`:

```bash
VITE_RCH_BASE_URL="https://example-hub" npm run dev
```

## Build

```bash
npm run build
npm run preview
```

## Environment Variables

- `VITE_RCH_BASE_URL`: Optional base URL for the REST/WS endpoints. When unset, the UI uses the browser origin.
- `VITE_RCH_WS_BASE_URL`: Optional explicit WebSocket base URL (defaults to the REST base URL with ws/wss).
- `VITE_RCH_MAP_STYLE_URL`: Optional MapLibre style URL (use a local/offline style for disconnected environments).
- `VITE_RCH_MOCK`: Set to `true` to enable mock REST/WS responses for offline UI development.

## Deployment Modes

- **Embedded UI**: Serve the `dist/` folder from the hub service (same-origin).
- **External UI**: Host the `dist/` folder behind a reverse proxy and use the Connect screen to set base URL and credentials.

## UI References

- `../docs/CosmicUi.md`: Cosmic UI design system (tokens, widgets, forms, migration patterns).
- `../docs/CosmicUiManualQa.md`: manual QA checklist for Cosmic UI migration and release validation.
- `../docs/architecture/ui-architecture.md`: page and data-flow architecture.
- `../docs/architecture/ui-design.md`: product-level UI design and behavior contract.
- `../docs/architecture/ui-wireframe.md`: structural wireframes.

## Mission Domain Routes

Canonical mission-domain routes:
- `/missions/:mission_uid/overview`
- `/missions/:mission_uid/mission`
- `/missions/:mission_uid/topic`
- `/missions/:mission_uid/checklists`
- `/missions/:mission_uid/checklist-tasks`
- `/missions/:mission_uid/checklist-templates`
- `/missions/:mission_uid/teams`
- `/missions/:mission_uid/team-members`
- `/missions/:mission_uid/skills`
- `/missions/:mission_uid/team-member-skills`
- `/missions/:mission_uid/task-skill-requirements`
- `/missions/:mission_uid/assets`
- `/missions/:mission_uid/assignments`
- `/missions/:mission_uid/zones`
- `/missions/:mission_uid/domain-events`
- `/missions/:mission_uid/mission-changes`
- `/missions/:mission_uid/log-entries`
- `/missions/:mission_uid/snapshots`
- `/missions/:mission_uid/audit-events`

Compatibility routes (preserved):
- `/missions` (primary mission entry; redirects to canonical mission-domain route)
- `/missions/assets` (redirect wrapper)
- `/missions/logs` (redirect wrapper)
- `/missions/legacy` (explicit legacy workspace route for staged migration)


## Chat retention configuration

`src/config/chat-retention.json` owns presentation policy. Defaults retain at most
200 messages per conversation and 2,000 messages / 16 MiB across conversations,
with 30 minutes of inactivity for completed messages. Pending outbound work and
in-flight send reservations stay protected. If they exhaust the budget, the UI
shows an error before sending. Completed history remains on the backend.

Override the defaults through Vite build environment or `ui/.env.local`:

```dotenv
VITE_CHAT_CONVERSATION_MESSAGES=200
VITE_CHAT_GLOBAL_MESSAGES=2000
VITE_CHAT_GLOBAL_BYTES=16777216
VITE_CHAT_IDLE_MS=1800000
VITE_CHAT_TOMBSTONES=4000
VITE_CHAT_PAGE_SIZE=100
VITE_CHAT_OVERSCAN_ROWS=4
VITE_CHAT_MAINTENANCE_MS=30000
```

These are build-time settings, so rebuild the shared UI after changing them.
All values must be positive safe integers; page size must fit the conversation
limit, that limit must fit the global count, and maintenance must not exceed
the inactivity period. The byte budget uses conservative estimates including
message, attachment, suppression and send reservation metadata; browser heap
also includes the rest of the application. Development builds show cache counts
and estimated bytes in Chat. The message viewport measures variable row heights
and renders visible rows with the configured overscan.

Rust durable backends expose `/Chat/History` keyset pages. Older/Latest controls
replace the selected conversation window while preserving pending and newer live
updates. Python backends without this endpoint use their bounded newest list;
the UI explicitly reports unavailable older paging. Its direct-message fallback
filters that newest global list locally, so sparse older direct messages may be
absent until the backend supports scoped paging. Attachment wire aliases from
both shared backends remain accepted.
