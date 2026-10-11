# Telemetry receive compatibility: stage A

This is the source-pinned diagnosis for [RCH #258](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/258).
It complements the [collector contract](telemetry-collector-compatibility.md).
The broader live acceptance gate remains open before [stage B extraction](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/259).

## Selected versions and evidence

Verified on 2026-10-10. The user identified the client as “latest version of
Columba”; the official latest release resolves to **2.2.6**, commit
`a402ed1052ba6993454352ce51ddfc336b729d9f`. This pins the test source, not an
independently inspected installed APK. `adb devices -l` returned no devices.
The failing RCH build, current deployment configuration and precise receive
error were not supplied for #258.

| Client / reference | Protocol implementation | RCH / boundary | Evidence and result |
| --- | --- | --- | --- |
| Columba 2.2.6, `a402ed1` | Published official-rns-py flavor: RNS 1.4.2 fork `5b3a6ee4f25e2925cf84d4a2b108e6a708fbd395`; LXMF 1.1.0 fork `8912186e48b482a76bf04e2ac4b6c8940991aecc`; shared Kotlin TelemeterCodec and msgpack-core 0.9.10 | RCH baseline `f2e90c4826dc944134b2fe4339009fda3eeb01a1`, Rust LXMF-rs 0.13.0 pin `e237f80c0c9e219e4090be04a4229d3328074f73` | Exact client codec executed on JVM with a model-only stub; generated packet and client roundtrip checked. Baseline signed altitude and daemon projection regressions both fail; repaired path passes. No Android/Reticulum session claimed. |
| Sideband 2.2.0, `ef572b58e88ff4e4326d51778336922a53b2a03f` | Application reference `sbapp/sideband/sense.py` | Same RCH parser | Source confirms signed altitude/bearing and identical seven-element sensor layout. Source comparison only; installed version and live session unavailable. |
| Columba, exact installed version unknown | Bundled Rust daemon `e237f80`, durable ZeroMQ broker with dual endpoints | Production preview.19, RCH `5c6ea326fba1704fb057eb2e80f7786ea1ddbb9e` | Existing #260 production evidence confirms a numeric command-1 list/boolean rejection, separately addressed by the collector implementation. This does not identify #258's current failure or prove chat/telemetry transport loss. |
| Additional clients actually in use | Not supplied | Not supplied | Missing evidence explicitly retained; no compatibility claim. |

Sources: [Columba release](https://github.com/torlando-tech/columba/releases/tag/v2.2.6),
[shared codec](https://github.com/torlando-tech/columba/blob/a402ed1052ba6993454352ce51ddfc336b729d9f/rns-api/src/main/java/network/columba/app/rns/api/util/TelemeterCodec.kt),
[Python stack pins](https://github.com/torlando-tech/columba/blob/a402ed1052ba6993454352ce51ddfc336b729d9f/rns-backend-py/PINNED_VERSIONS.md),
[Sideband reference](https://github.com/markqvist/Sideband/blob/ef572b58e88ff4e4326d51778336922a53b2a03f/sbapp/sideband/sense.py),
[production collector evidence](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/260#issuecomment-6088539757).

## First reproduced failures

1. **Daemon JSON projection → RCH map projection.** The pinned LXMF-rs
   `rmpv_to_json` function recognizes field `2` and converts its binary Telemeter
   into `{lat, lon, alt, speed, bearing, accuracy, updated}`. RCH previously
   accepted that object unchanged. Persistence succeeded, but `/Telemetry`
   excluded it because map-readable data requires
   `location.latitude` and `location.longitude`. The regression uses the actual
   pinned LXMF conversion, not a hand-written approximation of its behavior.
2. **Packed sensor decoding.** Columba and Sideband encode altitude and bearing
   as signed big-endian i32. RCH used u32. A synthetic altitude of `-12.5` became
   `42949660.46` on the baseline. Latitude and longitude already used the correct
   signed representation.
3. **Malformed telemetry classification.** The previous Option-only path could
   discard malformed location data while retaining time, or fall back to chat
   without a telemetry failure diagnostic. The repaired boundary records a
   separate privacy-safe telemetry diagnostic while preserving independently
   valid commands and ordinary chat.

These are demonstrated application/adapter defects. They do not establish a
Reticulum framing or application-schema change as the cause of the user's
current deployment error. The format-change hypothesis is unnecessary for the
reproduced failures; attributing the unspecified real error still requires
versioned deployment and sanitized error evidence. Reticulum carries the LXMF
message; the Telemeter sensor format is an application contract.

Historical [Columba #927](https://github.com/torlando-tech/columba/issues/927)
reports a different milliseconds-versus-seconds collector failure. The pinned
2.2.6 codec converts request milliseconds into seconds and first requests into
zero; the JVM harness verifies both. Do not reinterpret milliseconds as seconds
or silently clamp unsupported collector timebases. Existing #260 handling owns
numeric request validation and authorization.

## Verified receive contract and cutover

Field `0x02` contains MessagePack bytes for a numeric sensor map. Sensor `1`
is epoch seconds. Location sensor `2` contains seven readings, in order:

| Reading | Encoding | Unit |
| --- | --- | --- |
| Latitude / longitude | signed i32, big endian | millionths of a degree |
| Altitude | signed i32, big endian | hundredths of a metre |
| Speed | unsigned u32, big endian | hundredths of a metre/second |
| Bearing | signed i32, big endian | hundredths of a degree |
| Accuracy | unsigned u16, big endian | hundredths of a metre |
| Last update | numeric epoch seconds | seconds |

Optional sensors and unknown numeric IDs remain available. Successfully decoded
known sensors use existing RCH names; unconverted sensor entries retain their
numeric keys. Binary dictionary keys are represented as `base64:` keys in the
JSON projection; preserved packed bytes retain the exact original map keys.
Inactive/null location sensors do not invalidate other readings. Present invalid
location sensors are diagnosed rather than persisted as a partial time-only
success. Coordinates must be finite and within latitude/longitude ranges;
known location readings and timestamps must have valid numeric types.

There is no schema/version negotiation in the pinned Telemeter contract.
Explicit `version`/`schema_version` envelopes are classified unsupported,
including when accompanied by otherwise valid locations. Unknown numeric
sensor IDs are extension data, not version selectors.

The existing direct decoder now routes through the checked telemetry boundary.
New durable journal events include `lxmf_bytes_hex`. RCH preflights both full-wire
and destination-stripped payloads, then decodes the raw frame with the pinned
LXMF library. Source, destination and message ID must all match verified daemon
metadata before raw field 2 replaces the lossy JSON projection. Invalid present
raw frames get a diagnostic; coordinates are not trusted from a fallback flat
projection in that case. Unrelated valid commands/chat continue through their
existing handlers.

The raw-frame ceiling follows the journal's 12 MiB ceiling; packed sensor data
follows the collector's 1 MiB ceiling. Checked MessagePack parsing requires exact
consumption, finite floats, unambiguous keys, at most 32 levels of nesting, and
container allocation bounded by available bytes. Both the outer raw frame and
its nested packed telemetry are checked before interpretation. A recovered raw
packet preserves sensor time, optional sensors and original packed bytes through
SQLite and restart. No daemon dependency bump is required.

Bootstrap/history entries lack raw packets. Their known flat locations normalize
to the existing nested map contract, and `updated` supplies the sensor time.
Their original packets remain unavailable (`packed_telemeter=None`), following
the user-approved collector policy. No sensors or packet bytes are reconstructed.
Records already persisted in an older wrong shape need fresh uploads or a
separately reviewed migration; this fix does not rewrite historical storage.

Diagnostics use `lxmf_telemetry_diagnostic`, alongside existing
`lxmf_command_diagnostic` events. Messages identify field and failure stage but
omit sensor values, raw frames, identities and message content. Existing broker
transaction, authorization, logical input deduplication, SQLite and HTTP/map
projection remain the owners of their respective behavior.

## Reproduction and stage B handoff

Synthetic fixture: [columba_2_2_6.json](../crates/r3akt-transport-rns/tests/fixtures/columba_2_2_6.json).
Its codec bytes come from executing the unmodified pinned Columba source. Optional
sensors and wire envelopes are explicitly synthetic extensions generated with
Python MessagePack. Zero coordinates, invented hashes and zero signature bytes
are test data, not a captured or signature-verified client session. Frame tests
exercise metadata binding after the daemon's separate signature-verification
boundary.

[Transport tests](../crates/r3akt-transport-rns/tests/telemetry_compatibility.rs)
cover the actual upstream field conversion, both wire framings, raw binding
failure, signed values, optional/unknown sensors, truncation, trailing bytes,
nonfinite data, malformed types/ranges, explicit unsupported envelopes and
resource bounds. [Broker acceptance tests](../crates/r3akt-rch-server/src/durable_broker/telemetry_compatibility_tests.rs)
prove durable storage, restart and authenticated `/Telemetry?since=0` responses
with the normal map shape, plus durable failure diagnostics and a valid collector
command alongside malformed telemetry. Existing collector regressions continue
to own stream replies, topic authorization and unavailable historical packets.

Run Rust evidence with installed locked dependencies:

```sh
cargo test --locked -p r3akt-transport-rns --test telemetry_compatibility
cargo test --locked -p r3akt-rch-server telemetry_compatibility_tests
cargo test --locked --workspace
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo fmt --all -- --check
```

The independent [JVM harness](../scripts/check-columba-telemetry-fixture.py)
requires a checkout at the exact Columba commit, a Kotlin compiler classpath,
Kotlin stdlib and msgpack-core 0.9.10. It downloads nothing, verifies the codec
has no local changes, checks its roundtrip/timebase and compares emitted bytes
with the fixture:

```sh
python3 scripts/check-columba-telemetry-fixture.py \
  --columba-root "$COLUMBA_ROOT" \
  --compiler-classpath "$KOTLIN_COMPILER_CLASSPATH" \
  --stdlib "$KOTLIN_STDLIB_JAR" --msgpack-jar "$MSGPACK_CORE_JAR"
```

Stage B can reuse this contract and synthetic regression evidence. Its full
handoff gate stays open: capture the actual installed client/build/daemon and
transport configuration; reproduce the sanitized error; execute an Android
upload through the real Reticulum/daemon path, durable storage, normal map
rendering and collector response decoded by the actual clients. Include additional
clients in use and a versioned known-working deployment baseline where available.
No physical client session, production remediation, release readiness or issue
closure is claimed here.

Local validation: 724 workspace tests passed, 2 existing ignores; strict Clippy,
formatting, module budgets, documentation links and the exact Columba JVM harness
passed. [Execution evidence](goals/telemetry-compatibility/EVIDENCE.md) records
the review gate and remaining live acceptance.

The publication candidate additionally retains preview.21's LXMF-rs pairing
`a424760137c7eaee5d5de7fb9ef2347871b85da1` and Linux durable-broker flag.
The baseline diagnosis above remains pinned to `e237f80`; publication CI and
readiness revalidate the repaired adapter against the paired candidate.
