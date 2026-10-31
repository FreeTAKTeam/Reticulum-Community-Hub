# R3S/1 origin sensor telemetry

R3S attaches up to four sensors to an authenticated device or canonical map object. The shared `r3akt-map-core` crate owns checked models, MessagePack, SQLite lifecycle and display geometry. Native REM/RCH services own authorization; the maps consume native projections. SID 128 is provisional, and this implementation is not a claim of physical drone, camera, ATAK or radio qualification.

## Wire and ownership

The numeric Telemeter SID 128 value is `[1, [readings...]]`; every reading has exactly ten fields: sensor ID, azimuth/elevation/roll/HFOV/VFOV in centidegrees, slant range in centimetres, image north in centidegrees, source UTC milliseconds and range kind (`0` unknown, `1` measured target, `2` display limit). Unknown readings use MessagePack nil. The extension is limited to 512 original encoded bytes, four unique sensors per origin, and a 1 MiB outer field payload. A stream may contain 1,024 ordinary tuples and at most 16 sensor-bearing origins. Relay/collector replies send one R3S origin per packet.

Self samples use LXMF field 2 and the authenticated source identity. Independent objects use field 3 with their binary canonical object hash. The controller never acquires the object's position. Fresh authenticated marker creation establishes an immutable writer association; an existing unbound object cannot be claimed by its first tuple or by a claimed `origin_rch` field. RCH applies current `mission.content.write` rights, origin/team scope, moderation and destination policy. Collector access additionally requires `mission.content.read` and current topic membership where applicable.

Typed field-13 events are:

| Event | Payload |
|---|---|
| `mission.registry.origin.telemetry.upsert` | `{originId, position}` |
| `mission.registry.sensor_manifest.upsert` | `{originId, manifest, updatedAtMs}` |
| `mission.registry.sensor.remove` | `{originId, sensorId, deletedAtMs}` |
| `mission.registry.origin.remove` | `{originId, deletedAtMs}` |
| `mission.registry.sensor_origin.assert` | `{originId, writerId, originKind, label}`; trusted hub assertion only |
| `mission.registry.sensor.expiry` | `{originId, sensorId, sampleAtMs, expiresAtMs}`; optional CoT source expiry |

Exact nullable position sidecars are canonical. Standard sensor 2 is emitted only when all required slots are known; redundant sensor 2 must match standard wire rounding. Source milliseconds, altitude datum and motion stay separate from receive time. Sensor-only packets retain the prior position. Updates are monotonic; identical equal-time replays are idempotent, conflicting ones fail. Omission does not delete a component. Origin tombstones are permanent and survive restart; repeated deletion assertions remain safe. Stored origins are bounded to 4,096, including tombstones; each has at most four live sensors/manifests and 128 component tombstones.

Unchanged checked packets retain original bytes. Collector snapshots materialize the complete accepted sensor set after partial updates, canonical movement or deletion, preserving unrelated encoded sensor values. The ordinary collector removes optional SID 128 and retains standard SID 2 bytes; separately authorized R3S replies carry origin bindings and metadata. Old clients may discard unknown SIDs when repacking, so a route through an old client cannot guarantee overlay retention.

## Native HTTP API

Both methods require the configured northbound API credential and SQLite persistence.

`GET /Sensors` returns `{items, observedAtMs, ttlMs}`. Items contain `originId`, `writerId`, `originKind`, `label`, nullable `position`, and sorted sensors with `state`, optional `manifest`, optional `sourceExpiresAtMs` and native `display` flags/GeoJSON. RCH's `sensor_telemetry_ttl_ms` setting defaults to 300,000 ms and is clamped to 1,000–86,400,000 ms. Missing, stale or unsynchronized moving fixes suppress precise sectors; pose/fix skew is limited to two seconds. Near-nadir samples do not draw a misleading direction. Sectors are planar display extents, without terrain intersection.

`POST /Sensors` is the explicit operator/TAK boundary for an existing marker:

```json
{
  "originId": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "position": {"lat":45,"lon":-63,"altM":null,"altitudeDatum":"unknown","fixAtMs":1793440000000,"speedMps":null,"courseDeg":null,"accuracyM":null},
  "sensor": {"sensorId":"eo-main","sampleAtMs":1793440000000,"azimuthDeg":0,"elevationDeg":-30,"rollDeg":0,"horizontalFovDeg":20,"verticalFovDeg":10,"slantRangeM":2000,"rangeKind":"display-limit","imageNorthDeg":180},
  "staleAtMs":1793440030000
}
```

An optional `manifest` supplies `sensorId`, label/type/model, mount/intrinsics and an already approved non-secret video reference. The configured RCH destination is the writer; this API cannot take over another writer's object. Repeated or older source revisions cannot rewind its canonical position. CoT sensor imports use this atomic source-time path and do not subsequently patch the point with receive time.

## Metadata and delivery

Static marker/manifest/deletion metadata is separate from pose updates. Confirmation is per origin and recipient and occurs on a delivered receipt, not daemon admission. Failures leave metadata eligible for retransmission. Changes to names, manifests, removals or endpoint approval change the metadata revision; ordinary movement does not. Before admission, durable relay/collector intents recheck current writer rights, membership, reader rights and the current snapshot.

**Release gate:** the pinned LXMF daemon broker exposes no cancellation/policy callback after it admits a request. RCH cannot immediately revoke a retry already owned by that daemon. Pre-admission checks do not prove post-admission revocation. Resolve that upstream capability and measure real route/cadence behavior before operational release. RCH does not yet provide REM's per-radio pose coalescing policy; its broker bounds delivery work, and a high-rate input still requires field rate qualification.

## CoT adapter

The existing TAK connector resolves durable CoT UID-to-canonical-marker associations before sensor import. It accepts optional `detail.sensor` 0.6 attributes, preserves type/model, true azimuth, image north, slant range, exact event/stale milliseconds and nullable altitude/accuracy. Both latitude and longitude must be explicit. Invalid optional geometry leaves the ordinary parent parser usable. CoT's 9,999,999 point sentinel is unknown, not a real altitude.

`detail.__video` is parsed separately as an **unapproved endpoint candidate**. Invalid/credential-bearing candidates are diagnosed without dropping valid geometry. The bridge does not insert candidates into network-shared manifests or automatically play streams. Video export remains optional and is omitted.

Stock ATAK receives one sensor per parent: the connector selects the first sensor in native sorted ID order. It exports only current, synchronized state; names, manifests and source-expiry changes participate in deduplication. Display-limit ranges are omitted from CoT's measured `range` attribute. Physical ATAK interpretation and endpoint reachability remain unverified.

## Reproduce software evidence

Use Rust 1.99.1 for the checked dependency revision. Host builds need the system GCC/OpenSSL include path on this machine. Use a task-local `TMPDIR` when `/tmp` has exhausted its quota.

```sh
cargo +1.99.1 test --workspace
cargo +1.99.1 clippy --workspace --all-targets -- -D warnings
npm --prefix ui run test
npm --prefix ui run typecheck
npm --prefix ui run lint
npm --prefix ui run build
cd ui && npx playwright test --config playwright.sensor.config.ts
```

`cargo +1.99.1 run -p r3akt-map-core --features sqlite --example sensor_fixture` produces the checked-in native JSON fixture used by both browser tests. The browser checks exercise five sensors across controller A and drone B, visibility, style reconstruction, stale suppression and unavailable-service cleanup on one MapLibre map. They do not substitute for signed APK Binder instrumentation, real peers, LoRa, BLE or hardware calibration.

Software checks on 31 October 2026: 746 workspace Rust tests passed (two existing ignored tests), strict all-target Clippy passed, 210 UI tests/typecheck/lint/build passed, and the focused Chromium sensor map test passed. New origin/expiry/receipt and transport compatibility cases were rerun after their final edits. This is development evidence; the release gates above remain open.
