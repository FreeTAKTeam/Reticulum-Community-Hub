# r3akt-map-core

Shared R3AKT map objects (point markers and their symbol catalog) and the
Telemeter telemetry send/receive contract. RCH consumes this crate; REM must
consume the same pinned revision instead of re-implementing either model
([RCH #259](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/259)).

## Source revision

Extracted from RCH `main` at `46bf625e902c0616b854ded653304237c7d6c4f6`
(after #271, #272 and #274). The extraction moved existing code; it did not
introduce a second implementation. RCH's existing marker, telemetry, release
and parity tests run against this crate.

## What moved here

| Behavior | Previous location | Now |
| --- | --- | --- |
| `MarkerRecord` (stored layout) | `r3akt-rch-core` and a duplicate in `r3akt-rch-server` | `marker::MarkerRecord` (re-exported by both) |
| Coordinate validation | server `validate_lat_lon` (HTTP only) | `marker::Position::new` (HTTP, mission commands, zones) |
| Symbol normalization, aliases, supported set | duplicated in core and server (`*_for_http`) | `symbols::{normalize, is_supported, ALIASES}` |
| Symbol catalog (`/api/markers/symbols`) | server `default_marker_symbols` | `symbols::{CATALOG, catalog_json}` |
| Marker API JSON | duplicated: core `marker_value`, server `marker_to_python_value` | `MarkerRecord::api_value` |
| Create / move / rename | inline in core command handlers and server routes | `MarkerRecord::{create, move_to, rename}`, `marker::{marker_type, marker_symbol, supported_type, supported_symbol, normalize_name}` |
| Idempotency key rule, command ID, fingerprint | server `marker_idempotency.rs` | `idempotency` |
| Marker SQL (upsert, insert, delete, load, update, idempotent create) | `r3akt-rch-core` (`lib.rs`, `sqlite_record_updates.rs`, `sqlite_marker_idempotency.rs`) | `sqlite` (feature) |
| Checked MessagePack parser, JSON byte decoding | `r3akt-transport-rns/src/lib.rs` | `msgpack`, `bytes` |
| Telemeter decode, validation, normalization, sensor naming | `r3akt-transport-rns` (`lib.rs`, `telemetry_decode.rs`) | `telemetry` |
| Stage A Columba fixture | `r3akt-transport-rns/tests/fixtures/` | `tests/fixtures/columba_2_2_6.json` |

## API boundary

In scope: domain types, validation and normalization, the symbol catalog,
creation/update rules, the RCH marker JSON representation, idempotency rules,
optional SQLite persistence, checked Telemeter decoding and `telemetry_encode::encode`.

Sideband is the reference implementation. Location sensor 2 contains six
big-endian binary readings and an epoch-seconds fix timestamp. Latitude and
longitude are signed millionths of degrees, altitude signed centimetres,
speed unsigned hundredths of **km/h**, bearing signed hundredths of degrees,
and accuracy unsigned centimetres. The time sensor does not replace fix time.
Battery charge is a percentage, not a fraction. The encoder rejects invalid
coordinates, non-finite readings and overflow instead of silently saturating.

Columba 2.2.6 copies **m/s** into the speed slot. This is a documented client
compatibility exception, not the standard: callers must explicitly select that
profile. No unit discriminator exists in Telemeter, so receivers cannot infer
it from the bytes. Decoding preserves the numeric wire speed.

`tests/fixtures/sideband_pyxis.json` is imported unchanged from Pyxis
`5181fdd7b589e544b5825fbf1c631c4d79a7039d`, whose reference is Sideband
`2000d81a44bff57e3b3cb7d45915ba29bbde4e18`. Both directions are checked against
all five byte vectors. `scripts/check-sideband-pyxis-fixtures.py` executes the
pinned Sideband pack/unpack methods and Pyxis C++ codec independently. The
existing Columba 2.2.6 fixture and JVM harness remain regression gates.

RCH's collector still recognizes numeric command `1` in field `0x09`, returning
a plain field `0x03` list of `[source_bytes, seconds, packed_telemeter, appearance]`.
REM's `T1` command is not a collector request. Broker regressions exercise these
distinctions, preserving the original telemetry bytes and source age.

Out of scope, kept in each application's adapters: HTTP request parsing and
responses (RCH keeps its Python-compatible request schema, such as the
96-character name limit and the HTTP category default), server state, system
events and fanout, LXMF field lookup and raw-frame binding (RCH transport),
UI, Android/JNI, BLE and plugin APIs.

User telemetry positions and independently identified map objects remain
separate models. `object_destination_hash` is the authoritative marker
identifier; do not mint a second identifier for the same object.

The two RCH entry points keep their documented defaults: the HTTP route
requires `type` and `symbol` and keeps `category` text as given (defaulting
to the symbol); mission commands default missing values to `marker` and
normalize the category. Since the extraction, mission commands also reject
out-of-range coordinates, as HTTP always did.

## Replication

`replica::from_api_value` rebuilds a marker from its RCH API representation
with the same validation as local creation, and `replica::supersedes` keeps
the most recently updated copy. `MarkerRecord::create_with_id` and
`marker::object_destination_hash` let a client mint the canonical identifier
(REM does) so replicas never get a second ID. The wire contract is in
`docs/rem-southbound-interface.md`.

## Features and targets

- Default: pure domain and telemetry; no SQLite, no async runtime, no server
  crates.
- `sqlite`: `rusqlite` (bundled) and `r3akt-profile-rch`.
  `sqlite::ensure_schema` creates the RCH-compatible tables for standalone
  databases; RCH creates them through its own migrations.

Verified builds: `x86_64-unknown-linux-gnu` (workspace CI) and
`aarch64-linux-android`, both with and without `sqlite` (NDK 27,
API level 26 linker for the `sqlite` build):

```sh
cargo build -p r3akt-map-core --target aarch64-linux-android
CC_aarch64_linux_android=$NDK/aarch64-linux-android26-clang \
AR_aarch64_linux_android=$NDK/llvm-ar \
CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER=$NDK/aarch64-linux-android26-clang \
  cargo build -p r3akt-map-core --features sqlite --target aarch64-linux-android
```

Minimum Rust version follows the workspace (`1.89`).

## Consuming from REM

Pin an immutable RCH revision; do not track a branch:

```toml
r3akt-map-core = { git = "https://github.com/FreeTAKTeam/Reticulum-Community-Hub.git", rev = "<rch commit>", features = ["sqlite"] }
```

Record the pinned revision in REM's dependency documentation and update it
deliberately. Breaking changes to the stored layout, identifiers, symbol keys
or JSON representation require an explicit, tested migration in this crate
and coordinated updates in RCH and REM.

## Shared marker wire format

`marker_wire::encode_fields` is the shared RCH/REM marker encoder. Upserts
carry a plain `FIELD_TELEMETRY_STREAM` (`0x03`) list with binary object hash,
source timestamp in seconds, packed Telemeter and icon appearance. The
object hash is independent of the LXMF sender. The same message retains the
full R3AKT replica in `FIELD_EVENT` (`0x0D`) and optional legacy commands.
There is no `FIELD_TELEMETRY` (`0x02`) sender position in a marker message.
Name and notes are in the Information sensor. The marker model has no
altitude or movement, so altitude, speed, bearing and accuracy are zero.
Deletes carry the R3AKT event only: Sideband streams have no delete operation.

`tests/marker_wire.rs` verifies exact Sideband stream bytes, binary field
types, stable object identity, source age, replica preservation and deletion
limits. `scripts/check-marker-interop.py` executes the pinned Sideband
receiver and Columba Kotlin stream decoder against
`tests/fixtures/marker_stream.json`. This is source-level interoperability,
not Android or radio validation.

## Camera ground-point estimates

`camera_ground::ground_point` intersects a camera ray with an explicitly
chosen horizontal plane. `SensorState.azimuth_deg` is absolute true bearing,
not aircraft course; negative `elevation_deg` points below the horizon. An
optional `ImageOffset` uses half-image widths/heights, with positive x right
and y down, and carries the frame's capture time. Off-centre projection uses
a centered, undistorted pinhole model
and requires both fields of view, optical-axis roll, and explicit bounds on
roll and pixel/lens/frame-timing error. Positive roll turns image right toward
image down.
Adapters must convert their camera's orientation and image conventions.

`GroundModel::Flat` requires the origin altitude and ground height to share
the same known R3S datum. For AGL the ground height is zero. Alternatively,
`GroundModel::TakeoffRelative` explicitly supplies both heights relative to
the same take-off point without changing the R3S wire datum; its origin height
must be sampled at `OriginPosition.fix_at_ms`. The caller must
choose a height and a height-error bound that apply across the target area;
the function does not look up terrain or assume take-off elevation is flat.

The caller supplies bounds for horizontal position (`OriginPosition.accuracy_m`),
altitude, camera angles, and maximum 3D platform speed during any pose/fix
skew. These are absolute error bounds, not standard deviations. Limits specify
the current time, maximum sample age, minimum ray depression and maximum slant
range. Future, stale or more than two seconds out-of-sync position, pose or
frame samples are refused. The pixel angular-error bound must include camera
motion between the frame and pose times; timestamps alone do not measure it.
The limits apply to the uncertainty envelope as well as the nominal ray.
Missing calibration/accuracy, unknown or mismatched datums, non-positive
height, and unbounded horizon or polar cases also return a typed error.

The output includes the ground model, coordinate, ground/slant ranges, and a
conditional horizontal uncertainty radius. This radius is not CEP or a
confidence level: it holds only if the supplied bounds and flat-plane model
hold. It excludes Earth-curvature effects on the intersection, terrain or
obstacles outside the supplied height bound, unbounded lens distortion, and
unmodeled motion. `sensor_geometry::destination` exposes the existing
mean-radius spherical great-circle destination calculation with a normalized
longitude. The companion `sensor_geometry::distance_and_bearing` returns the
distance and initial true bearing between two positions using the same sphere.
The bearing is absent for coincident or antipodal positions and at a polar
origin. These calculations are not ellipsoidal survey measurements. Hardware
camera calibration and field accuracy have not been qualified by these tests.

## Compatibility fixtures and tests

```sh
cargo test -p r3akt-map-core --features sqlite
```

- `tests/markers.rs`: coordinate and symbol validation, normalization parity
  with the former server implementation, unchanged catalog JSON, create/move/
  rename and API representation, idempotency keys and fingerprints.
- `tests/replica.rs`: API representation round trip, replica validation
  matching local input, and last-writer-wins ordering.
- `tests/sqlite_markers.rs`: schema creation and `local_id` migration, CRUD
  across restart, idempotent replay and key conflicts, the named-MessagePack
  stored layout, and malformed rows as errors.
- `tests/telemetry.rs`: the stage A Columba 2.2.6 fixture (packed and daemon
  projection forms), optional/unknown sensors, and malformed, truncated,
  non-finite, oversized and versioned payloads.

RCH-side regressions remain in `r3akt-rch-server` (marker routes, release and
parity tests, durable telemetry compatibility) and `r3akt-transport-rns`
(`tests/telemetry_compatibility.rs`, LXMF frame binding).

## License

EPL-2.0, as for the RCH workspace (see the repository `LICENSE`). Consumers
distributing modified versions must meet EPL-2.0 source obligations; no
separate NOTICE file is required by this crate.
