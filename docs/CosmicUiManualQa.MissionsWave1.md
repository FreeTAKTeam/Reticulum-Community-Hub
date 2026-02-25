# Cosmic UI Manual QA Run: Missions Wave 1

Date: 2026-02-24  
Scope: First progressive split wave on `MissionsPage` (mission create/edit form + preview extracted into `MissionFormScreen`).

## Change Summary
- Extracted mission create/edit form and preview from `MissionsPage.vue` into:
  - `ui/src/pages/missions/MissionFormScreen.vue`
- Rewired field updates through typed component emits.
- Removed now-unused inline handlers from `MissionsPage.vue`.

## Progressive Size Check
- `ui/src/pages/MissionsPage.vue`: **6390 -> 6260 lines** (reduced by 130 lines in this wave).
- New module created: `ui/src/pages/missions/MissionFormScreen.vue` (442 lines).

## QA Checklist Execution

### 1. Session Setup
- [x] Branch state verified and migration scope defined.
- [ ] Live browser walkthrough completed (requires interactive UI session).

### 2. Build/Test Gate
- [x] `npm run lint` passed.
- [x] `npm run test -- --run` passed.
- [x] `npm run build` passed.

### 3. Global Cosmic Baseline
- [x] Shared status strip/wigdet contract preserved in `MissionsPage`.
- [ ] Keyboard/focus-visible walkthrough on extracted form (pending interactive session).
- [ ] Reduced-motion walkthrough (pending interactive session).
- [x] No build-time Vue/TypeScript errors introduced.

### 4. Forms and Validation
- [x] Mission create/edit field set preserved.
- [x] Advanced Properties fold/unfold behavior preserved via emitted state toggle.
- [ ] Visual validation state consistency verified manually (pending interactive session).

### 5. Tables and Data Views
- [x] Mission form preview remains rendered as a separate panel.
- [ ] Narrow viewport behavior of extracted form panel verified manually (pending interactive session).

### 6. Overlays and Navigation
- [x] Route/API contracts unchanged for mission create/edit save path.
- [x] Action routing from screen actions (`Save`, `Save Mission`) unchanged.

### 7. Responsive Verification
- [ ] Desktop/tablet/mobile visual checks pending interactive session.

### 8. Page Family Checks
- [x] `Missions` workspace behavior compiles and builds after extraction.
- [ ] End-to-end in-browser mission create/edit flow pending interactive session.

### 9. Migration-Specific Checks
- [x] No route path/name changes.
- [x] No endpoint contract changes.
- [x] Oversized page reduced in line count this wave (progressive enforcement satisfied).

### 10. Sign-Off
- [ ] Manual interactive QA sign-off pending.
- [x] Automated acceptance gate passed (`lint`, `test`, `build`).

## Notes
- This wave satisfies the progressive split rule by reducing `MissionsPage.vue` and extracting a complete feature slice (UI + handlers).
- Remaining acceptance items require a real browser interaction pass by operator/developer.
