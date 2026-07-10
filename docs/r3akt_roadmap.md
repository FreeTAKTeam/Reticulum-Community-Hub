# REM-Hosted r3akt Shared Crates Plan

## Summary

- REM becomes the home for shared Rust crates, all under the `r3akt-*` namespace.
- RCH consumes those crates from the REM checkout by path dependency first, then by git/tag once APIs stabilize.
- First align wire/runtime behavior, then domain state, so both apps can share protocol, delivery, ACK, and routing rules before moving persistence or UI-facing surfaces.

## Key Changes

- Add a REM root Cargo workspace with `crates/reticulum_mobile` plus new shared members such as `crates/r3akt-mission-wire`, `crates/r3akt-mesh-delivery`, and later `crates/r3akt-ops-core`.
- Keep shared crates product-neutral: no Android, JNI, UniFFI, Capacitor, RCH HTTP, Tauri, TAK service, or server packaging dependencies.
- RCH updates its workspace dependencies to point at REM-hosted `r3akt-*` crates, while keeping RCH-owned crates for server, HTTP/WebSocket, SQLite hub state, TAK connector, packaging, and diagnostics.
- REM's `reticulum_mobile` crate becomes a product shell over the shared crates, keeping mobile projections, app state, native bridge, notifications, SOS platform triggers, and mobile runtime orchestration.

## Migration Phases

### Phase 1: REM Workspace Foundation

- Create a REM root workspace and move shared-crate ownership there without changing runtime behavior.
- Add `r3akt-mission-wire` for `FIELD_COMMANDS = 0x09`, `FIELD_RESULTS = 0x0A`, `FIELD_EVENT = 0x0D`, command/result/event envelopes, compact aliases, command code tables, MsgPack encode/decode, and metadata parsing.
- Add golden fixtures from current REM and RCH before replacing existing parsers.

### Phase 2: RCH Adoption

- Replace duplicated RCH wire constants and mission-envelope logic with REM-hosted `r3akt-mission-wire`.
- Preserve RCH output contracts, including full RCH envelopes where required and reduced REM southbound envelopes documented in `docs/rem-southbound-interface.md`.
- Keep `r3akt-profile-rch` as a compatibility/profile layer if needed, but delegate shared codec behavior to REM-hosted crates.

### Phase 3: Shared Delivery Runtime

- Add `r3akt-mesh-delivery` in REM for peer delivery state traits, route freshness, direct cooldowns, propagation fallback, retry budgets, ACK correlation, and delivery-state normalization.
- Migrate REM `delivery_policy.rs` and RCH outbound policy logic onto this crate.
- Keep transport adapters separate: REM uses mobile LXMF-rs integration; RCH uses reticulumd/ZeroMQ SDK paths.

### Phase 4: Shared Operational Domain

- Add `r3akt-ops-core` for shared checklist, EAM, telemetry, mission log/event, MECP, and CSV checklist validation models.
- Move validation and wire shapes first; persistence remains product-specific until the shared models are stable.
- Share SOS wire parsing only. REM keeps SOS triggers, audio, device telemetry capture, and mobile UX behavior.

### Phase 5: Stabilization

- Convert RCH path dependencies to REM git dependencies once shared APIs settle.
- Add versioned compatibility tests that both repos run before changing shared command shapes.
- Retire duplicate parser, command-map, and delivery-policy code from both apps after both products compile and pass integration tests on the shared crates.

## Test Plan

- REM shared crates: unit tests for expanded RCH command, reduced REM command, compact REM command, result/event envelopes, SOS-vs-mission parser separation, checklist snapshot v1/v2, telemetry snapshot request, and command aliases.
- Delivery tests: direct-ready peer, stale saved route, propagation relay, cooldown, hop priority, direct retry budget, ACK by command ID, and ACK by correlation ID.
- REM integration: `cargo test --manifest-path crates/reticulum_mobile/Cargo.toml`, `npm --workspace apps/mobile run typecheck`, and relevant Playwright specs for events, EAM, checklist, telemetry, and peer routing.
- RCH integration: `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace`, plus release-critical crate tests when backend behavior changes.

## Assumptions

- Shared crate names remain in the `r3akt-*` namespace even though REM hosts them.
- REM root workspace creation is acceptable and should preserve existing REM package commands.
- LXMF-rs remains the shared Reticulum/LXMF implementation; shared crates must not recreate LXMF wire/runtime internals.
- Product-specific shells stay separate: REM owns mobile/native concerns; RCH owns hub/server/operator concerns.
