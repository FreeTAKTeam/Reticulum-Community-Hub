# Cosmic UI Design System

## 1. Purpose and Principles
Cosmic UI is the canonical visual and interaction system for the RCH admin console. It provides one reusable language for surfaces, forms, status indicators, widgets, and overlays across all Vue pages.

Principles:
- One source of truth: shared tokens + shared primitives.
- Composition over page-local CSS duplication.
- Accessibility first: keyboard navigation, `:focus-visible`, reduced motion support.
- Compatibility during migration: keep legacy `rth-*` and `cui-*` classes functional.

## 2. Token Reference
Cosmic tokens live in `ui/src/assets/cosmic/tokens.css`.

### 2.1 Color Tokens
| Token | Purpose | Default |
|---|---|---|
| `--cui-color-bg-0` | App background base | `#07131f` |
| `--cui-color-bg-1` | Alternate background | `#0f1320` |
| `--cui-color-panel-0` | Primary panel fill | `#0a2234` |
| `--cui-color-panel-1` | Secondary panel fill | `#071a2a` |
| `--cui-color-border-soft` | Subtle border | `rgba(0,180,255,0.22)` |
| `--cui-color-border` | Default border | `rgba(0,180,255,0.45)` |
| `--cui-color-text` | Primary text | `#e8f3ff` |
| `--cui-color-text-muted` | Muted text | `#9fb6cc` |
| `--cui-color-tone-primary` | Primary accent | `#00b4ff` |
| `--cui-color-tone-secondary` | Secondary accent | `#56708a` |
| `--cui-color-tone-success` | Success accent | `#00d0b0` |
| `--cui-color-tone-warning` | Warning accent | `#f59e0b` |
| `--cui-color-tone-danger` | Danger accent | `#ff3b7a` |
| `--cui-color-tone-info` | Informational accent | `#4db6ff` |
| `--cui-color-tone-neutral` | Neutral accent | `#8aa3ba` |

### 2.2 Typography Tokens
| Token | Purpose | Default |
|---|---|---|
| `--cui-font-display` | Headings/titles | `Orbitron, Rajdhani, Barlow, sans-serif` |
| `--cui-font-body` | Body text | `Barlow, IBM Plex Sans, Source Sans 3, Segoe UI, sans-serif` |
| `--cui-font-mono` | Numeric/structured text | `JetBrains Mono, Cascadia Mono, Consolas, monospace` |
| `--cui-text-xs/sm/md/lg` | Type scale | `0.7rem..1rem` |
| `--cui-track-tight/wide/ultra` | Letter spacing scale | `0.04em/0.16em/0.22em` |

### 2.3 Spacing Tokens
`--cui-space-1..10` define 0.125rem to 3rem increments.

### 2.4 Radius / Geometry Tokens
| Token | Purpose |
|---|---|
| `--cui-radius-sm/md/lg/xl` | Radius scale |
| `--cui-cut-sm/md/lg` | Polygon corner-cut scale |

### 2.5 Elevation / Glow Tokens
| Token | Purpose |
|---|---|
| `--cui-shadow-panel` | Default panel elevation |
| `--cui-shadow-modal` | Modal elevation |
| `--cui-shadow-soft-glow` | Generic glow |
| `--cui-glow-primary` | Primary glow effect |

### 2.6 Motion Tokens
| Token | Purpose |
|---|---|
| `--cui-motion-fast/base/slow` | Timing durations |
| `--cui-ease-standard/decel/accel` | Easing curves |

### 2.7 Z-Index Tokens
| Token | Purpose |
|---|---|
| `--cui-z-base` | Content base |
| `--cui-z-header` | Header layers |
| `--cui-z-overlay` | Floating overlays |
| `--cui-z-modal` | Modal containers |
| `--cui-z-toast` | Toast stack |

### 2.8 Compatibility Aliases
Migration-safe aliases are defined for:
- Legacy `--cui-*` variables (`--cui-bg`, `--cui-primary`, etc.).
- Legacy `--rth-*` variables (`--rth-bg`, `--rth-border`, etc.).

## 3. Foundations
Foundations are split into:
- `foundations.css`: global scrollbar, font helpers.
- `layout.css`: shared shell/panel/grid/header/status primitives.
- `motion.css`: keyframes and reduced-motion behavior.
- `utilities.css`: helper classes and compatibility behavior.

Required baseline behavior:
- Use `:focus-visible` for interactive focus styles.
- Respect `@media (prefers-reduced-motion: reduce)`.
- Use tokenized status colors (`success`, `warning`, `danger`, `accent`).

## 4. Widget Catalog
Widgets live in `ui/src/components/cosmic/`.

### 4.1 Layout Widgets
- `CosmicPageFrame`: outer workspace container.
- `CosmicTopStatus`: title + connection pills + URL strip.
- `CosmicRegistryGrid`: side/main grid wrapper.
- `CosmicPanel`: panel surface wrapper.
- `CosmicPanelHeader`: consistent title/subtitle/chip header.
- `CosmicActionRow`: standard action button row.

### 4.2 Navigation Widgets
- `CosmicTabs`: tab switch strip (`v-model`).
- `CosmicTreeList`: left-tree stack wrapper.
- `CosmicBreadcrumb`: breadcrumb trail.

### 4.3 Data Widgets
- `CosmicStageCard`: stage card wrapper.
- `CosmicStatCard`: KPI card.
- `CosmicMiniTable`: compact table shell.
- `CosmicDataTable`: rich table wrapper over `BaseTable`.
- `CosmicEmptyState`: standard empty message panel.
- `CosmicPagination`: pagination wrapper over `BasePagination`.

### 4.4 Feedback Widgets
- `CosmicBadge`: semantic badge.
- `CosmicChip`: compact status chip.
- `CosmicToast`: global toast surface (wraps `BaseToast`).
- `CosmicBanner`: inline status banner.
- `CosmicSkeleton`: loading skeleton wrapper.

### 4.5 Overlay Widgets
- `CosmicModal`: modal wrapper over `BaseModal`.
- `CosmicDrawer`: drawer wrapper over `BaseDrawer`.
- `CosmicInspector`: floating inspector panel shell.

### 4.6 Widget Contract Rules
Every widget must document:
- Purpose and intended page contexts.
- Props and emits.
- Variant and state support.
- Accessibility notes.
- Usage example.

Example:
```vue
<CosmicPanel>
  <CosmicPanelHeader title="Asset Inventory" subtitle="Create, update, retire" chip="12 assets" />
  <CosmicDataTable :headers="headers" :rows="rows" striped empty-state="No assets found." />
</CosmicPanel>
```

## 5. Form System
Form primitives are in `ui/src/components/`:
- `BaseField`
- `BaseInput`
- `BaseSelect`
- `BaseTextarea`
- `BaseCheckbox`
- `BaseRadioGroup`
- `BaseSwitch`
- `BaseFormSection`

### 5.1 Field Anatomy
- Label row: `.cui-field__label` + required marker.
- Control row: `.cui-field__control`.
- Message row: `.cui-field__hint` or `.cui-field__error`.

### 5.2 Field States
Canonical states:
- `default`
- `focus`
- `invalid`
- `disabled`
- `readonly`

State classes:
- `is-focus`
- `is-invalid`
- `is-disabled`
- `is-readonly`

### 5.3 Form Layout Classes
- `.cui-form-grid--1`
- `.cui-form-grid--2`
- `.cui-form-grid--3`
- `.cui-form-row-actions`
- `.cui-form-section`
- `.cui-form-section--advanced`

### 5.4 Advanced Section Pattern
Use `BaseFormSection` with `advanced` for foldable or grouped secondary properties. This replaces ad-hoc page-local advanced-field styling.

## 6. Page Recipes
### 6.1 Registry Page
- `CosmicPageFrame`
- `CosmicTopStatus`
- `CosmicRegistryGrid`
- `CosmicPanel` + `CosmicPanelHeader`
- `CosmicDataTable`/cards + `CosmicPagination`

### 6.2 Workspace Page
- Header/status top strip.
- Tab row (`CosmicTabs`) for sub-areas.
- Main content in `CosmicStageCard` groups.

### 6.3 Editor Modal
- `CosmicModal` + `BaseFormSection`.
- All fields from `BaseField` ecosystem.
- Footer actions in `.cui-form-row-actions`.

### 6.4 Data Table Page
- `CosmicDataTable` with `emptyState` and optional `stickyHeader`.
- Row actions use `BaseButton` variants and tones.

## 7. Do and Don’t Rules
Do:
- Use shared cosmic tokens/classes/components.
- Reuse `useConnectionPills` for status strip behavior.
- Keep action and status semantics consistent across pages.

Don’t:
- Duplicate `registry-shell`, `panel-header`, `mini-table`, `field-control` blocks in page styles.
- Create one-off status-pill color rules.
- Hardcode colors when a token exists.

## 8. Migration Guide
### 8.1 CSS Migration
1. Move shared classes from page-scoped CSS into `ui/src/assets/cosmic/*`.
2. Extract page CSS into dedicated files under `ui/src/pages/styles/*.css` (or page-specific folders like `ui/src/pages/missions/*`) and reference via `<style scoped src="...">`.
3. Replace page-local primitives with cosmic widgets.
4. Keep only page-specific layout exceptions in page CSS.

### 8.2 Legacy Class Mapping
| Legacy | Cosmic Replacement |
|---|---|
| `field-control` | `BaseField` + control primitive |
| `panel-tab` | `CosmicTabs` |
| `panel-empty` | `CosmicEmptyState` |
| `mini-table` | `CosmicMiniTable` / `CosmicDataTable` |

### 8.3 Rollout Order
1. Foundation pass (styles + base components).
2. Low-risk pages (`About`, `Connect`, `Configure`, `Files`, `Topics`).
3. Registry/workspace pages (`Users`, `TeamRoster`, `MissionAssets`, `MissionLogs`, `Checklists`, `Missions`).
4. Realtime pages (`Dashboard`, `Chat`, `WebMap`).

### 8.4 Progressive File Size Enforcement
- File-size target: route pages should trend toward `<=500` lines, preferred `250-400`.
- Enforcement is progressive, not blocking for legacy oversized pages in one PR.
- Rule per migration wave:
  - Do not increase line count of oversized legacy pages.
  - Every structural refactor wave must reduce line count for targeted pages.
  - New route pages must be created at `<=500` lines.
- If a page cannot be reduced in one wave, extract one feature slice (UI + state logic) into colocated components/composables.

## 9. Testing Checklist
For each migrated page/component:
- Widget renders correctly for all variants/states.
- Form controls handle default/focus/invalid/disabled/readonly states.
- Modal/drawer focus trap and escape close work.
- Tab/tree controls are keyboard accessible.
- Focus-visible outline is visible.
- Reduced-motion mode deactivates nonessential animation.
- `npm run lint`, `npm run test`, `npm run build` pass.
- Manual QA checklist is completed and attached: `docs/CosmicUiManualQa.md`.

## 10. Governance
Owner: UI maintainers for `ui/src/assets/cosmic`, base components, and `ui/src/components/cosmic`.

Change policy:
- Any token change must update this document in the same PR.
- Any new widget/form primitive must include usage example and state notes.
- Any page migration must remove replaced page-local duplicate styles.

Review checklist for PRs touching Cosmic UI:
- Token usage over hardcoded values.
- No duplicate primitive CSS introduced.
- Accessibility checks completed.
- Documentation updated (`docs/CosmicUi.md`, changelog notes if needed).
- Manual QA checklist completed for migrated pages (`docs/CosmicUiManualQa.md`).

Best-practice implementation rules:
- Prefer container/presentational split: page container orchestrates data; child components render UI.
- Extract repeated async/state logic into composables rather than duplicating in pages.
- Co-locate page-specific modules under `ui/src/pages/<page>/` when not reused globally.
- Promote reusable modules to `ui/src/components/cosmic/` or `ui/src/composables/` once used across 2+ pages.
- Keep props/events explicit and typed; avoid implicit cross-component coupling.

