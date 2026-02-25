# Cosmic UI Manual QA Checklist

Use this checklist for every Cosmic UI migration wave and before release cut. Complete the checklist in a real browser session (not only tests) using current desktop and mobile viewport sizes.

## 1. Session Setup
- [ ] Pull latest branch and confirm migrated page list for this wave.
- [ ] Start UI with `cd ui && npm run dev`.
- [ ] Confirm API target is correct (same-origin or configured Connect settings).
- [ ] Open browser devtools with console and network tabs visible.

## 2. Build/Test Gate (Before Manual QA)
- [ ] `npm run lint` passes.
- [ ] `npm run test -- --run` passes.
- [ ] `npm run build` passes.

## 3. Global Cosmic Baseline
- [ ] Top status area is rendered with shared cosmic primitives (title, status pills, URL strip).
- [ ] Buttons, tabs, chips, and badges match shared tokenized styles (no obvious page-local variants).
- [ ] Focus outlines are visible with keyboard navigation (`Tab`/`Shift+Tab`).
- [ ] Reduced motion mode (`prefers-reduced-motion`) removes non-essential animations.
- [ ] No console errors or Vue warnings appear during navigation and interactions.

## 4. Forms and Validation
- [ ] Fields use consistent anatomy: label, control, hint/error rows.
- [ ] Invalid state styling is consistent across `BaseInput`, `BaseSelect`, `BaseTextarea`, checkbox/radio/switch controls.
- [ ] Disabled and readonly controls are visually distinct and semantically disabled.
- [ ] Required indicators appear consistently where required.
- [ ] Advanced/collapsible sections expand/collapse without layout breakage.

## 5. Tables and Data Views
- [ ] Empty states render with consistent cosmic empty-state treatment.
- [ ] Compact/striped/sticky header table variants render correctly where enabled.
- [ ] Long datasets scroll correctly in intended container (no clipped rows, no hidden action buttons).
- [ ] Row actions remain keyboard accessible and visible at narrow widths.

## 6. Overlays and Navigation
- [ ] Modals and drawers trap focus and close on `Escape`.
- [ ] Overlay headers/footers and action rows align with shared component contracts.
- [ ] Tab navigation updates selected state and content panels correctly.
- [ ] Tree/list navigation selected state remains consistent across route/query changes.

## 7. Responsive Verification
- [ ] Desktop large viewport (>=1440px) layout is stable.
- [ ] Laptop viewport (~1280px) layout is stable.
- [ ] Tablet width (~768-1024px) stacks/pivots correctly.
- [ ] Mobile width (~360-430px) keeps critical actions usable and readable.

## 8. Page Family Checks
Run at least one scenario per page family:

- [ ] Registry pages (`Users`, `Topics`, `Files`, `TeamRoster`, `MissionAssets`, `MissionLogs`) use shared shell/panel/status patterns.
- [ ] Workspace pages (`Missions`, `Checklists`, `Configure`) preserve key workflows end-to-end.
- [ ] Realtime pages (`Dashboard`, `Chat`, `WebMap`) preserve live updates and interactive controls.

## 9. Migration-Specific Checks
- [ ] Route/API behavior remains unchanged from baseline.
- [ ] No duplicated primitive CSS blocks were reintroduced in migrated pages.
- [ ] New/updated shared widgets and forms are documented in `docs/CosmicUi.md`.
- [ ] Large page decomposition follows progressive file-size target (toward `<=500` lines).

## 10. Sign-Off
- [ ] QA findings recorded (pass/fail + notes).
- [ ] Blocking issues triaged and assigned.
- [ ] Wave approved for merge/release.
