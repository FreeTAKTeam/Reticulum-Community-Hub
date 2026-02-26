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
