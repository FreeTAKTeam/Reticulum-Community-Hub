# Client telemetry compatibility diagnosis implementation plan

**Intent:** Diagnose RCH #258 from pinned client and adapter evidence before #259 extraction.
**Current Behavior:** LXMF-rs e237f80 converts binary field 2 into flat lat/lon/alt/updated JSON. RCH persists this object but its normal /Telemetry projection requires location.latitude/longitude. Packed RCH decoding also treats signed altitude/bearing as unsigned and malformed uploads have no diagnostics.
**Expected Outcome:** Both packed Telemeter and the pinned daemon projection normalize to the existing RCH telemetry contract; invalid supported payloads receive privacy-safe durable diagnostics.
**Target-Perspective Output:** A Columba 2.2.6 synthetic codec fixture crosses the actual pinned LXMF field adapter, persists through the broker, survives restart and appears in the normal /Telemetry API used by the map.
**Truth Owner:** Columba/Sideband own application encoding; LXMF transports fields; RCH transport adapter owns normalization; existing core SQLite owns storage; server /Telemetry owns projection.
**Contract Boundary:** Numeric LXMF field 0x02, MessagePack numeric sensor map, signed big-endian lat/lon/alt/bearing, unsigned speed/accuracy; normalized location and seconds timestamps.
**Cutover:** Redirect existing direct_lxmf_telemetry through one checked decoder; keep the existing northbound shape.
**Displaced Path:** Silent Option-only telemetry acceptance replaced at the receive boundary. No second persistence or map model.
**Value Density:** Fix the demonstrated daemon-to-map mismatch and signed values; add bounded decoding and regression diagnostics.
**Acceptance Evidence:** Versioned matrix, generated synthetic source codec fixture, pre-fix failures, post-fix transport and broker/restart/API evidence; identify missing live device/RCH build/error evidence explicitly.
**Evidence Lane:** Source-pinned synthetic integration. Installed Android application/real transport acceptance is unavailable (adb reports no devices); actual failing RCH build and error remain unspecified.
**Kill Criteria:** Do not reconstruct lost sensor packets, infer client version changes caused production errors, invent version negotiation, or start #259 extraction. Keep stage-A live acceptance open.
**Architecture Slice:** Modify transport lib.rs/direct_lxmf.rs and a telemetry boundary module; add transport fixture/tests and broker tests; extend broker application diagnostics. Existing SQLite and API/UI contracts stay authoritative. Avoid other worktrees, sibling LXMF source changes, UI, schema migrations, packaging and unrelated refactors.
**Plan Review Gate:** PRE reviewed by telemetry_receive_map; aligned after the raw recovery amendment below.

## Tasks
1. Pin sources and execute the Columba TelemeterCodec with synthetic inputs using a JVM harness (Android model stub only); save bytes, inputs and provenance under transport test fixtures. Independently inspect Sideband signed units. Sequential, no production writes.
2. Add a checked receive decoder: normalize daemon flat objects, validate known time/location fields and coordinates, preserve unknown numeric sensors, diagnose malformed/unsupported shapes separately from commands, bound packed parser allocations/depth. Add pre-fix failing regressions. Exact files: transport lib.rs, direct_lxmf.rs, telemetry_decode.rs, tests/telemetry_compatibility.rs, fixtures/columba_2_2_6.json. Sequential.
3. Persist telemetry diagnostic as its own system event while valid commands/chat remain usable; test packed and real pinned wire-adapter paths through durable persistence, restart and /Telemetry. Exact files: server durable_broker/application.rs and telemetry compatibility test module. Sequential.
4. Run affected tests, formatting/module budgets/doc links, strict workspace Clippy and workspace tests. Document measured evidence and unresolved live gate in docs/telemetry-receive-compatibility.md plus this goal package. Run POST/correctness/maintainability review. No publication without user request.

## Raw recovery amendment (PRE accepted)
`crates/r3akt-transport-rns/src/telemetry_decode.rs` also owns a public broker-event payload decoder. When `lxmf_bytes_hex` exists, try the pinned LXMF FullWire and DestinationStripped framing decoders; use raw field 2 only when candidate source, destination and message id all match verified daemon metadata. Keep the journal's existing 12 MiB frame ceiling and the collector's 1 MiB sensor ceiling; bound parser nesting/allocation. Malformed present raw data produces a telemetry diagnostic, without trusting its coordinates or disabling unrelated commands/chat. Absent raw data uses the projected-message compatibility path; never reconstruct unavailable historical packets. Tests must cover both framings, mismatch, malformed hex/truncation and parser bounds.
