# Reticulum Community Hub - Rust Edition

This branch is the staged Rust edition of Reticulum Community Hub (RCH). It
imports the R3AKT/RCH Rust workspace as the future repository root while the
Python edition is preserved on the long-term `rch-python` branch.

## Current Repository

The active transition branch is `rust-next`. The current GitHub default branch
remains `main` until the Rust edition completes release validation and the
default branch is switched deliberately. Python security and critical-fix
maintenance belongs on `rch-python`.

This root is a Rust 2024 Cargo workspace. The primary server replacement is
`r3akt-rch-server`; `r3akt-rch-core` owns RCH domain/state behavior;
`r3akt-transport-rns` owns LXMF/reticulumd integration; and
`r3akt-tak-connector` remains an independent TAK service boundary.

This workspace currently expects the Rust LXMF implementation to be checked out
beside this repository as `LXMF-rs`.

The shared Vue web UI is maintained on the `ui-shared` branch and is imported
into `ui/` on this branch for Rust server and desktop work. Python 2.9.x
continues on `rch-python` with its Electron wrapper. The server-only alpha gate
is built from `r3akt-rch-server`; the full Rust release workflow also assembles
server archives with the UI bundle and `r3akt-tak-service`, plus Tauri desktop
artifacts for Windows x64 NSIS and Linux x64 AppImage.

Crates:

- `r3akt-protocol`: typed envelopes, NodeHello, Heartbeat, HealthTelemetry,
  TopicMessage, Command, AckAccepted, AckRejected, AckCompleted, and MessagePack
  encode/decode.
- `r3akt-identity`: node identity, trust records, and tested enrollment
  decision helpers.
- `r3akt-transport-rns`: `MessageBus` trait, bounded mock transport with
  backpressure, an LXMF-rs adapter boundary that accepts raw LXMF payload bytes,
  and a `reticulumd` RPC-backed `LxmfRsAdapter` for sending/polling R3AKT
  MessagePack envelopes through LXMF-rs. This crate depends on the inspected
  sibling LXMF-rs `lxmf-wire` package at `crates/libs/lxmf-core` and exposes
  helpers for packing/unpacking LXMF-rs `WireMessage` storage bytes.
- `r3akt-profile-rch`: RCH LXMF field profile for `FIELD_COMMANDS` (`0x09`),
  `FIELD_RESULTS` (`0x0A`), and `FIELD_EVENT` (`0x0D`) command/result/event
  conversion.
- `docs/rem-southbound-interface.md`: optimized REM southbound command payload
  shape emitted by the Rust RCH runtime.
- `r3akt-rch-core`: RCH-specific core behavior extracted behind reusable Rust
  types: `RTHDelivery` validation, RCH topic/hash/message-id normalization,
  delivery mode classification, topic/subscriber state, command replay caching,
  and first-pass handlers for `mission.join`, `mission.leave`,
  `mission.events.list`, `mission.marker.list`, `mission.marker.create`,
  `mission.marker.position.patch`, `mission.zone.list`, `mission.zone.create`,
  `mission.zone.patch`, `mission.zone.delete`,
  `mission.registry.mission.upsert`, `mission.registry.mission.get`,
  `mission.registry.mission.list`, `mission.registry.mission.patch`,
  `mission.registry.mission.delete`, `mission.registry.mission.parent.set`,
  `mission.registry.mission_change.upsert`,
  `mission.registry.mission_change.list`,
  `mission.registry.log_entry.upsert`, `mission.registry.log_entry.list`,
  `mission.registry.eam.list`, `mission.registry.eam.upsert`,
  `mission.registry.eam.get`, `mission.registry.eam.latest`,
  `mission.registry.eam.delete`, `mission.registry.eam.team.summary`,
  `mission.registry.team.upsert`, `mission.registry.team.get`,
  `mission.registry.team.list`, `mission.registry.team.delete`,
  `mission.registry.team.mission.link`,
  `mission.registry.team.mission.unlink`,
  `mission.registry.team_member.upsert`,
  `mission.registry.team_member.get`, `mission.registry.team_member.list`,
  `mission.registry.team_member.delete`,
  `mission.registry.team_member.client.link`,
  `mission.registry.team_member.client.unlink`,
  `mission.registry.asset.upsert`, `mission.registry.asset.get`,
  `mission.registry.asset.list`, `mission.registry.asset.delete`,
  `mission.registry.skill.upsert`, `mission.registry.skill.list`,
  `mission.registry.team_member_skill.upsert`,
  `mission.registry.team_member_skill.list`,
  `mission.registry.task_skill_requirement.upsert`,
  `mission.registry.task_skill_requirement.list`,
  `mission.registry.assignment.upsert`, `mission.registry.assignment.list`,
  `mission.registry.assignment.asset.set`,
  `mission.registry.assignment.asset.link`,
  `mission.registry.assignment.asset.unlink`,
  `checklist.template.list`, `checklist.template.get`,
  `checklist.template.create`, `checklist.template.update`,
  `checklist.template.clone`, `checklist.template.delete`,
  `checklist.create.online`, `checklist.create.offline`,
  `checklist.list.active`, `checklist.get`, `checklist.update`,
  `checklist.delete`, `checklist.import.csv`, `checklist.join`,
  `checklist.upload`, `checklist.feed.publish`,
  `checklist.task.row.add`, `checklist.task.row.delete`,
  `checklist.task.row.style.set`, `checklist.task.cell.set`,
  `checklist.task.status.set`,
  `ListTopic`, `CreateTopic`, `SubscribeTopic`,
  `CreateSubscriber`/`AddSubscriber`, `topic.list`, `topic.create`,
  `topic.patch`, `topic.delete`, `topic.subscribe`, `mission.message.send`,
  and `PublishMessage`. It also provides a
  MessagePack-backed SQLite store with row-level topic, subscriber, client,
  audit-event, marker, zone, mission, mission-change, log-entry, EAM snapshot,
  team, mission-team-link, mission-zone-link, team-member, team-member-client-link, asset, skill,
  team-member-skill, task-skill-requirement, assignment,
  assignment-asset-link, checklist, checklist-template, checklist-column,
  checklist-task, checklist-cell, checklist-feed-publication, message, and
  command-result replay tables, plus mission-sync and checklist-sync response
  APIs that mirror Python RCH's accepted-then-result mission lifecycle and
  silent-success checklist lifecycle.
- `r3akt-rch-bridge`: minimal JSON stdin/stdout process bridge for Python RCH
  migration experiments. It loads Rust RCH core state from SQLite, executes a
  mission command or topic query, saves state, returns RCH-style field
  responses with `FIELD_RESULTS`/`FIELD_EVENT` keys, and can send outbound RCH
  payloads through the legacy LXMF-rs `reticulumd` RPC endpoint for migration
  experiments.
- `r3akt-rch-server`: long-running Rust HTTP server for the UI-facing backend
  replacement path. The current slice exposes Python-compatible OpenAPI
  metadata, `/Help`, `/Examples`, `/Status`, `/api/v1/app/info`, auth
  validation, event/telemetry/chat list shapes, Python-compatible pagination on
  topic/subscriber/client route
  families, file/image metadata and raw-byte APIs including Python-compatible
  attachment pagination bounds and ordering, checklist/admin route families,
  R3AKT mission/product APIs including Python-compatible R3AKT list limit
  validation, marker symbol registry/alias validation, and WebSocket stream
  contracts.
  When configured with `--lxmf-zmq-command`, `--lxmf-zmq-response`, and
  `--reticulumd-source`, outbound delivery uses the LXMF-rs ZeroMQ SDK
  pipeline. For the initial server package, ZeroMQ is mandatory for southbound
  command dispatch and daemon event polling. Multi-destination fanout is sent
  to the daemon as one `sdk_send_batch_v2` ZeroMQ request, so the server no
  longer performs one daemon send per recipient.
  Remaining backend service contracts should continue to be ported in small
  contract-tested slices.
- `r3akt-tak-connector`: dedicated Rust TAK connector crate and service
  boundary. The first slice ports Python-compatible Cursor-on-Target location
  and chat XML builders plus bounded outbound queue/backpressure behavior with
  golden-shape tests. It also has clear TCP/UDP CoT senders for the first
  non-PyTAK push path. `r3akt-tak-service` is the standalone process that reads
  RCH telemetry/chat over northbound HTTP and writes received TAK CoT-derived
  locations back through northbound marker routes; `r3akt-rch-server` does not
  own TAK socket lifecycle. The crate now has an explicit service
  lifecycle/status object for start/stop, queue drain, send counters, last-error
  reporting, and a background retry worker that drains pending CoTs after
  temporary send failures. Python-compatible TAK TLS config fields are owned by
  the connector service; `ssl://`/`tls://` CoT sends now use the Rust native TLS
  socket path. The worker retries failed sends with Python-style exponential
  backoff capped at 30 seconds. Remaining external TAK work is real target
  profile validation.
- `crates/r3akt-rch-core/migrations/0001_rch_core_snapshot.sql`: first explicit
  SQLite schema artifact for the Rust-owned bridge/runtime state database. This
  database stays separate from the Python RCH application database unless the
  disabled-by-default bridge is deliberately configured to use the same path for
  a migration experiment.
- `r3akt-router`: topic subscriptions, fanout, and dispatch recording for tests.
- `r3akt-store`: durable inbox/outbox trait, dedupe, audit records, retention,
  typed readback, in-memory store, and SQLite-backed store.
- `r3akt-node`: embeddable runtime path tying validation, persistence, dedupe,
  routing, ACK emission, bounded batch polling, audit, and metrics counters
  together.
- `examples/sim-agent`: local heartbeat/topic/command simulation over the mock
  transport.
- `examples/rch-ingest-sim`: RCH `FIELD_COMMANDS` MessagePack ingestion
  simulation that converts a mission command into a typed runtime envelope,
  executes the first RCH core command layer, and emits an RCH `FIELD_RESULTS`
  ACK.
- `crates/r3akt-node/tests/rch_vertical.rs`: integration coverage for the same
  RCH field-command to runtime to result-ACK path.

## Sister Repository Findings

### LXMF-rs

Found at `C:\Users\broth\Documents\work\ATAK\src\LXMF-rs`, remote
`https://github.com/FreeTAKTeam/LXMF-rs`.

Current Rust RCH verification targets the LXMF-rs `v0.5.1` release commit
`81acffc1409a760aeb9d7b09dc9a76b4be304a59`. The sibling dependency packages
resolved by `r3akt-transport-rns` are `lxmf-wire` `0.2.0`, `lxmf-sdk` `0.2.1`,
`reticulum-rs-rpc` `0.3.0`, and their `lxmf-reference` `0.1.0` dependency.

It contains real Rust Reticulum/LXMF crates, including the `lxmf-wire` package
at `crates/libs/lxmf-core`, `lxmf-sdk`, `reticulum-rs-transport`,
`reticulum-rs-rpc`, and the `reticulumd` app. The `lxmf-wire` crate already uses
MessagePack for LXMF payloads and exposes `WireMessage` packing, unpacking,
message IDs, signing, and verification. This milestone does not invent a
Reticulum/LXMF implementation. `r3akt-transport-rns` now includes a ZeroMQ
SDK-backed adapter for R3AKT MessagePack envelopes, normal RCH outbound LXMF
field payloads, and batched multi-recipient sends. The older `reticulumd` RPC
adapter remains in the crate for legacy tests and migration tooling, but the
Rust server runtime no longer uses it for southbound dispatch or event polling.

Gap: the ZeroMQ SDK path has unit coverage for outbound payload mapping and
inbound SDK event conversion, plus local live-daemon validation for
`sdk_poll_events_v2` over ZeroMQ. The default server package path requires
ZeroMQ endpoints for outbound commands and event polling; external Reticulum
and REM phone evidence should keep validating the ZeroMQ-only path.

### Reticulum Mobile Emergency Management

Found at
`C:\Users\broth\Documents\work\ATAK\src\reticulum_mobile_emergency_management`,
remote `https://github.com/FreeTAKTeam/reticulum_mobile_emergency_management.git`.

REM already has Rust runtime work in `crates/reticulum_mobile`. It depends on
the sibling LXMF-rs checkout via `../../../LXMF-rs/crates/libs/lxmf-core` and
`../../../LXMF-rs/crates/libs/lxmf-sdk`. It also uses `rmp-serde`, `rmpv`,
`rusqlite`, bounded send permits, peer routing state, mission-sync parsing,
ACK/correlation tracking, and RCH-compatible LXMF field constants:
`FIELD_COMMANDS = 0x09`, `FIELD_RESULTS = 0x0A`, and `FIELD_EVENT = 0x0D`.

Reuse decision: this milestone reuses REM's proven design choices rather than
copying product-specific code: MessagePack, SQLite-backed local state, bounded
runtime boundaries, ACK correlation, and LXMF-rs as a sibling dependency. The
current REM runtime is tightly coupled to Android/JNI, mobile projections, SOS,
EAM, checklist, and mission UI state, so those internals were not copied into
the shared crate skeleton.

Gap: mission/SOS parser modules should be extracted later into shared
protocol/profile crates instead of being duplicated here.

### Reticulum-Community-Hub

Found at `C:\Users\broth\Documents\work\ATAK\src\Reticulum-Telemetry-Hub`,
remotes `FreeTAKTeam/Reticulum-Community-Hub` and
`giu-Expedibox/Reticulum-Community-Hub`.

RCH is the Python behavioral reference. It uses Python 3.10, RNS 1.2.0, LXMF
0.9.6, FastAPI, SQLAlchemy, msgpack, and a modular runtime under
`reticulum_telemetry_hub/reticulum_server`. Important current behavior includes
topic-scoped fanout, canonical topic IDs, sender/subscriber tracking, inbound
command routing through `FIELD_COMMANDS`, replies through `FIELD_RESULTS` and
`FIELD_EVENT`, telemetry streams, delivery metadata (`RTHDelivery`), persisted
chat/topic/identity/telemetry state, ACK/retry/propagation fallback state, and a
propagation-first outbound policy for broadcast/topic sends.

Gap: the Rust server now owns the UI-facing northbound route inventory,
Python-shaped `/Status` dashboard payloads, WebSocket streams, chat list limit
coercion, Python-compatible pagination envelopes for
topic/subscriber/client/file/image APIs including attachment ordering,
checklist/admin route families, R3AKT mission/product APIs, telemetry
list/stream behavior, and optional built UI bundle serving with SPA fallback.
Remaining migration work is deeper runtime parity:
target TAK profile validation through the standalone `r3akt-tak-service`,
future dedicated analytics routes if the UI adds surfaces beyond Python's
current `/Status` and `/Telemetry` contracts, and final live validation before
retiring Python-owned runtime orchestration.

Python RCH now has a disabled-by-default bridge hook in the sister checkout:
`[rust_runtime] enabled`, `bridge_path`, and `db_path` load into
`HubRuntimeConfig`; `runtime_init.py` builds a `RustMissionSyncBridge` only when
enabled and a bridge binary path is configured. The Python router still performs
its existing validation, source checks, capability checks, and authorization
before delegating supported mission-sync command execution to Rust. The Python
bridge also exposes the Rust bridge's `list_topics`, `grant_capability`, and
`set_authorization` controls so tests and migration tooling can inspect and
prepare Rust-side state without bypassing the subprocess boundary. Checklist
sync now uses the same disabled-by-default bridge object after Python-side
source and capability checks, preserving Python's silent-success checklist
contract while allowing Rust-backed checklist command execution.

The likely
`C:\Users\broth\Documents\work\ATAK\src\Reticulum-Telemetry-HubMobile-Emergency-Management`
path was checked and was not present.

## Reuse Matrix

| Component | Found in repo | Reuse decision | Reason | Follow-up needed |
| --- | --- | --- | --- | --- |
| LXMF wire/runtime | LXMF-rs | Reuse `lxmf-core` for wire-message byte helpers; wrap live transport via `LxmfRsAdapter` and `MessageBus`; added a `reticulumd` RPC adapter for R3AKT envelope send/poll plus opt-in Rust-server live direct-receipt and multi-recipient fanout validation hooks | Real Rust LXMF/RNS crates exist; avoid fake transport | Keep local live receipt/fanout validation in the release gate and add broader real-network validation before default-branch switch |
| MessagePack payloads | LXMF-rs, REM, RCH | Implemented in `r3akt-protocol` with `rmp-serde` | All sister repos use or document MsgPack on hot path | Add golden vectors against RCH/REM command envelopes |
| RCH field IDs | REM, RCH docs | Implemented in `r3akt-profile-rch` with Python-generated `FIELD_COMMANDS`, `FIELD_RESULTS` accepted/result/rejected, and `FIELD_EVENT` MessagePack fixtures plus RCH status mapping and event encode/decode coverage; product-specific command fixtures now cover REM checklist create commands with topics and EAM upsert fanout commands without optional correlation/topic fields, and event decoding accepts Python mission-sync's single-object event envelope with event ID/source/timestamp/topics | Core envelopes stay transport-neutral while the RCH profile preserves field compatibility | Add Python-generated hex fixtures for any future product-specific payload variants introduced by the UI/runtime |
| Durable local state | REM, RCH | Added `DurableStore`, `MemoryStore`, `SqliteStore` | REM and RCH both persist runtime/message state | Add migrations for production inbox/outbox schemas |
| Dedupe | LXMF-rs, REM, RCH delivery metadata | Implemented by stable dedupe key | Message ID/correlation keys are required for retries | Align with LXMF `WireMessage::message_id` |
| ACK lifecycle | REM, RCH | Implemented accepted/rejected/completed payloads; RCH profile serializes completed as `FIELD_RESULTS` status `result` and decodes Python mission-sync's single-object `FIELD_RESULTS` accepted/rejected/result fixtures as well as list-form result batches | Matches command lifecycle direction while preserving RCH wire wording | Add live rejected/result vectors from a running Python RCH instance when a real transport peer is available |
| Topic fanout | RCH, REM docs | Implemented generic `TopicRouter`; added RCH-specific create/list/patch/delete/subscribe state in `r3akt-rch-core`; topic create now matches Python's required name/path and generated-ID behavior when no explicit `TopicID` is supplied; Rust HTTP topic create upserts existing IDs like Python storage `merge`, while topic delete preserves subscriber rows and clears file/image topic links like Python | Required for RCH hub and REM/edge profiles | Add broader golden parity vectors for less common Python topic API edge cases |
| Client join/leave and event listing | RCH | Added Rust client state plus audit-event listing for `mission.join`, `mission.leave`, and `mission.events.list` with Python `EventLog`-style `mission_command_processed` entries, ISO timestamps, command metadata, newest-first ordering, and the Python `limit=50` mission-events cap | These are core Python mission-sync commands that do not require the full registry domain | Add broader golden vectors for shared event-log file tailing/import edge cases |
| Marker and zone content | RCH | Added Rust marker and zone state for list/create/update/delete command paths currently exposed by Python mission-sync and northbound HTTP, with focused coverage for marker timestamp fields, object identity preservation, zone timestamp fields, invalid zone geometry rejection, Python marker symbol registry/aliases, unsupported marker type/symbol rejection, and Pydantic-style 422 body validation for marker/zone HTTP payloads | These are bounded mission content models and can be shared before the larger registry domain | Add broader golden Python vectors for serialized marker/zone edge cases |
| Mission registry mission CRUD | RCH | Added Rust mission records for upsert/get/list/patch/delete/parent-set with Python-compatible capability names, response event types, topic expansion, mission-zone/marker links, mission RDE payloads, and `expand=all` mission payload coverage for teams, members, assets, changes, logs, assignments, checklists, and checklist tasks | Mission CRUD is the central registry aggregate and can move before checklists and RDE | Add broader golden Python fixture vectors for expanded mission payload edge cases |
| Mission changes and log entries | RCH | Added Rust mission-change and log-entry records with list/upsert command paths, default log mission behavior, automatic log-entry mission-change records, post-commit mission-change listener events on the Rust system stream, 24-hour duplicate fanout suppression metadata, reticulumd-backed R3AKT event fanout to linked mission team recipients, connected-REM checklist command fanout for mission-change task deltas, initial checklist create/upload row replay, and generic markdown fanout for LXMF peers without R3AKT capability | These are the next registry primitives used by RCH mission sync and do not require team/asset/checklist ownership yet | Add marker hash fixtures, full Python golden vectors, richer markdown name resolution, and broader real-network validation |
| EAM status snapshots | RCH, REM | Added Rust EAM snapshot records plus list/upsert/get/latest/delete/team-summary commands, Python-compatible status read/write capabilities, canonical color-team provisioning and expiry/deleted summary coverage, Python-style rejection when deleted subject/callsign recreation candidates conflict, and reticulumd-backed EAM update/delete fanout using REM `FIELD_COMMANDS` or Python-style generic markdown bodies | EAM is a southbound REM/RCH overlap surface and is required for status parity | Add broader golden vectors for serialized EAM payloads and broader real-network validation |
| Mission teams | RCH | Added Rust team records plus mission-team link/unlink, get/list/delete, Python-compatible read/write capabilities, canonical REM color-team UID mapping from team payloads, and Python-style delete cleanup for member team links and mission-team links | Teams are needed before team members, assets, assignments, and EAM team summaries | Add golden Python vectors for team cleanup edge cases |
| Team members | RCH | Added Rust team-member records plus client link/unlink, get/list/delete, Python-compatible team read/write capabilities, Python-style mission fanout recipient expansion across member RNS identity plus linked client identities, and Python-style delete cleanup for owned asset links, client links, and team-member skills | Team members are the owner surface for assets, skills, assignments, and status summaries | Add golden Python vectors for delete cleanup edge cases |
| Assets | RCH | Added Rust asset records with upsert/get/list/delete, Python-compatible asset read/write capabilities, assignment-link cleanup on delete, and automatic asset upsert/delete mission-change deltas | Assets hang off team members and feed assignment/status flows | Add golden Python vectors for asset cleanup edge cases and listener fanout |
| Skills and requirements | RCH | Added skill, team-member-skill, and task-skill-requirement records with Python-compatible skill read/write capabilities and checklist-task existence validation | Skills are required before assignment readiness and field-team capability matching | Add golden Python vectors for skill validation errors and edge cases |
| Assignments | RCH | Added assignment records plus assignment-asset set/link/unlink, Python-compatible assignment read/write capabilities, and automatic assignment upsert/assets set/link/unlink mission-change deltas | Assignments connect missions, tasks, team members, and assets on the RCH hot command path | Add golden Python vectors for assignment edge cases and listener fanout |
| Checklist sync | RCH, REM | Added template, online/offline checklist, row/cell/status, upload, feed publication, and CSV import command paths with Python-compatible silent success and rejection shape; CSV import now preserves quoted cells and ignores invalid UTF-8 bytes like Python; online checklist creation, checklist upload, task-row creation, idempotent existing-task row updates, row styling, cell edits, status changes, and task-row deletes now emit Python-style mission-change deltas when tied to a mission; checklist delete now has focused coverage for task/cell/requirement/assignment cleanup plus the Python-style `checklist.deleted` audit event without an auto mission-change | Checklist sync is already a Rust/mobile overlap surface and a core RCH parity domain | Add broader golden Python vectors for serialized checklist payloads and checklist listener/fanout edges |
| Backpressure/metrics | REM | Implemented bounded mock queues and `NodeMetrics` | REM already uses bounded send permits; shared runtime should expose pressure early | Add production queue telemetry and tracing subscribers |
| Identity/trust | RCH, REM, LXMF-rs | Added Rust identity/trust/enrollment directory helpers; RCH moderation, REM mode, capability grants, and team-member links are persisted in `r3akt-rch-core` | Product identity models differ today | Bind directory decisions to LXMF-rs identities and expose enrollment workflows through RCH HTTP when the UI needs them |
| RCH delivery contract | RCH | Implemented `RTHDelivery` build/validate, routing mode classification, Python-compatible envelope failure text for TTL and future clock-skew rejection, and Python-compatible presence-aware direct-vs-propagated outbound delivery policy in `r3akt-rch-core`; `r3akt-rch-server` persists method/reason dispatch metadata, accepted/failed/queued/in-progress state, direct pending-receipt and pending-dispatch diagnostics, receipt timeout finalization, stale-dispatch cleanup, polls `reticulumd` `sdk_status_v2` for terminal receipt state, exposes opt-in live direct-receipt and multi-recipient fanout validation hooks, and passes the selected method to `reticulumd` RPC | This is central to switching Python ingestion and outbound delivery to Rust safely | Add broader edge-case fixtures for dispatch failure metadata; keep local live LXMF receipt/fanout validation green |
| RCH core state | RCH | Added `RchCoreSnapshot`, row-level `RchSqliteStore` tables, explicit `0001_rch_core_snapshot.sql` migration, schema-version preservation, and `/diagnostics/runtime` persistence metadata | Backend switching needs topic/subscriber/message/mission/log/command replay state to survive process restarts and expose the opened schema | Add Python bridge access patterns once contracts are fixed |
| Mission-sync response lifecycle | RCH | Added `MissionSyncResponse` and `handle_mission_sync_command` accepted/result/rejected sequencing, with authorization rejection before acceptance and accepted-then-result/rejected execution responses | Python RCH emits separate accepted and result/rejected replies for executable mission-sync commands | Add more Python golden vectors for command-specific rejection details |
| Mission-sync authorization | RCH | Added RCH capability requirements for implemented commands plus persisted grants, mission-access roles, explicit operation grants/revokes, and bridge controls | Python RCH rejects unauthorized command issuers before execution while mission registry rights can grant scoped operations | Add more team-derived role edge-case vectors for registry commands |
| Rust-owned backend switch boundary | RCH | Added `r3akt-rch-bridge` JSON stdin/stdout binary plus disabled-by-default Python `RustMissionSyncBridge` wiring for mission-sync, checklist-sync, state controls, and outbound sends through `reticulumd` RPC, with an env-gated bridge-level live reticulumd outbound smoke; UI/admin pages, backing APIs, WebSocket streams, and northbound HTTP routes are explicitly in scope for the Rust-owned replacement of the Python backend | Lets Python call the Rust core as an isolated transition path while Rust takes over the UI-facing backend surface and Reticulum outbound runtime | Prove the remaining live Reticulum, TAK, and fanout validation gates before retiring the Python service |
| TAK connector service | RCH PyTAK integration | Added `r3akt-tak-connector` with Python-compatible CoT location/chat XML builders, PyTAK-shaped TAK hello/pong keepalive payloads, bounded outbound queue/backpressure behavior, clear TCP/UDP CoT senders, TAK Protocol v1 stream-framed protobuf payloads when `TAK_PROTO>0`, TLS CoT sender support for `ssl://`/`tls://` with CA/client-cert config, PKCS#12/PFX `tls_client_password` support and explicit unsupported encrypted-PEM failure, structured inbound CoT parsing with Python `ReceiveWorker` raw-fallback behavior, an inbound polling service boundary that records parsed/raw receive results and receiver errors, bounded TCP/UDP/TLS CoT socket receivers, golden-shape tests, local TCP/UDP/TLS loopback tests, local reconnect-after-close coverage, local bidirectional TCP loopback validation, env-gated live TAK keepalive, reconnect push, and inbound receive smokes, an explicit start/stop service lifecycle/status object, Python-compatible TAK TLS config loading with redacted runtime diagnostics covered by regression tests, outbound and inbound retry workers with Python-style exponential send-failure/receive-failure backoff, and the standalone `r3akt-tak-service` northbound bridge for RCH telemetry/chat to TAK plus TAK CoT to RCH marker ingestion | TAK connectivity runs as a separately deployable service for the final Rust product line, using the RCH northbound API for CoT send/receive integration rather than becoming part of the main server runtime | Add final validation against the target TAK server profile |
| Product command handlers | RCH, REM | Added the RCH core topic/message path, first mission registry families through assignments, state-backed checklist-sync, and EAM status snapshots | These are needed for backend-switch groundwork but telemetry and remaining mission side effects remain product-specific | Extract telemetry profiles incrementally |

## Runtime Path

`r3akt-node` implements the first vertical slice:

1. poll `MessageBus`
2. decode already typed `ProtocolEnvelope`
3. validate schema, source, topic, and TTL
4. persist inbound envelope before processing
5. dedupe by `dedupe_key` or envelope ID
6. dispatch through `TopicRouter`
7. emit `AckAccepted`, `AckRejected`, and `AckCompleted` envelopes
8. record audit entries for receive, persistence, routing, duplicate drops, and
   ACK emission
9. update `NodeMetrics` counters for accepted, rejected, duplicate, routed,
   ACK, and empty-poll outcomes
10. optionally process a bounded batch with `poll_batch(max_messages)`

## Functional Equivalence Direction

UI/admin pages, their backing APIs, WebSocket streams, and northbound HTTP
routes are part of the Rust RCH replacement scope and belong to the Rust-owned
runtime contract. They are explicitly in scope for the Rust runtime migration,
not excluded from it: the target architecture is for the UI and admin surfaces
to connect directly to Rust for these runtime APIs, with route-level parity
tests proving each ported endpoint before removing the equivalent Python FastAPI
paths.

RCH parity should proceed in this order:

1. Keep explicit migration files for the row-level `r3akt-rch-core` SQLite state
   as the Rust-owned database contract, and document any Python import/bridge
   access pattern before sharing an existing Python RCH database file.
2. Expand the disabled-by-default Python bridge path from topic,
   mission-message, marker/zone, mission CRUD, teams, members, assets, skills,
   assignments, and checklist-sync to the remaining mission-sync command
   families.
3. Keep the live-daemon E2E coverage for the `reticulumd` RPC-backed LXMF-rs
   adapter in the verification gate and add equivalent coverage for the Python
   outbound bridge path while it remains part of migration tooling.
4. Add golden test vectors from Python RCH for `FIELD_COMMANDS`,
   `FIELD_RESULTS`, `FIELD_EVENT`, `RTHDelivery`, topic APIs, and mission-sync
   command responses.
5. Map RCH `RTHDelivery` metadata into shared dedupe, TTL, retry, and ACK state
   at the live LXMF receive boundary.
6. Port the remaining southbound command ingestion path incrementally:
   mission marker links, checklist/EAM mission-change side effects, listener
   notifications, and REM registry envelopes.
7. Complete the dedicated `r3akt-tak-connector` service. The crate owns the
   Python-compatible CoT location/chat XML builders, PyTAK-shaped TAK hello/pong
   keepalive payloads, bounded outbound queue/backpressure behavior, and
   clear TCP/UDP CoT senders. TAK is not a `r3akt-rch-server` runtime service.
   `r3akt-tak-service` is the separate process boundary: it reads RCH
   telemetry/chat from northbound HTTP routes, emits TAK CoT over the configured
   TAK socket, receives TAK CoT through the connector transport, and publishes
   received CoT-derived location events back through northbound marker routes.
   `COT_URL` remains the transport selector as it is in PyTAK; `TAK_PROTO=0` is
   the XML payload mode and `TAK_PROTO>0` emits TAK Protocol v1 stream-framed
   protobuf payloads from the generated CoT XML. The connector crate owns an
   explicit start/stop lifecycle/status object plus a background retry worker
   with keepalive/ping scheduling, and `ssl://`/`tls://` sends use the Rust
   native TLS socket path. Send failures now back off exponentially up to 30
   seconds like the Python PyTAK manager, passworded PKCS#12/PFX client
   identities are supported through `tls_client_password`, unsupported encrypted
   PEM key/password combinations fail explicitly, structured inbound CoT parsing
   now mirrors Python `ReceiveWorker` raw-fallback behavior, an inbound polling
   service boundary records parsed/raw receive results and receiver errors, and
   bounded TCP/UDP/TLS socket receivers are covered by local loopback tests.
   Outbound and inbound workers both apply Python-style exponential backoff on
   temporary send/receive failures. The clear TCP sender reconnects after a
   server-side close in local loopback coverage, and a local TCP loopback test
   validates outbound keepalive plus inbound parsed CoT in one bidirectional
   workflow. Opt-in live TAK keepalive and
   reconnect push smokes run when `R3AKT_TAK_LIVE_COT_URL` is set, with optional TLS fields from
   `R3AKT_TAK_LIVE_TLS_CA`, `R3AKT_TAK_LIVE_TLS_CLIENT_CERT`,
   `R3AKT_TAK_LIVE_TLS_CLIENT_KEY`, `R3AKT_TAK_LIVE_TLS_CLIENT_PASSWORD`, and
   `R3AKT_TAK_LIVE_TLS_INSECURE`. TAK service tests keep certificate paths and
   passwords out of rendered diagnostics. TAK inbound CoT is a separate service
   boundary, not a `r3akt-rch-server` runtime service; it must
   use the northbound HTTP/WebSocket API for publishing received CoT-derived
   data into RCH and for reading RCH state/messages that need to be emitted to
   TAK. A separate opt-in live inbound receive smoke runs when
   `R3AKT_TAK_LIVE_INBOUND_COT_URL` is set and can assert a known UID through
   `R3AKT_TAK_LIVE_INBOUND_EXPECT_UID`; for clear TCP targets without an
   expected UID, it performs an active bidirectional probe by identifying the
   receiver, publishing a probe CoT through `R3AKT_TAK_LIVE_COT_URL`, and
   requiring a relayed inbound CoT. The remaining external service work is
   validation against a real Reticulum/LXMF network profile. The Rust server
   must not embed Python or own the final TAK socket lifecycle directly.
8. Replace the Python backend with a Rust northbound runtime incrementally:
   serve UI/admin HTTP routes and WebSocket streams directly from Rust, then
   retire each equivalent FastAPI path once behavioral parity is proven for
   the backing runtime service.

This is in scope for the Rust replacement path: UI/admin pages, northbound HTTP
routes, WebSocket streams, analytics endpoints, file/image attachment APIs,
dedicated TAK connector service integration, complete checklist
mission-feed/mission-change behavior, live Reticulum sockets, and production
identity enrollment. Route-shape parity is implemented for the current
northbound inventory, but deeper runtime behavior and final service ownership
still need to be proven before the Python backend can be removed.

Current Rust server slice:

```powershell
cargo run -p r3akt-rch-server -- --bind 127.0.0.1:8080 --db-path .\rch-runtime.db --config-path .\config.ini --reticulum-config-path $env:USERPROFILE\.reticulum\config
```

To make Rust send outbound UI messages through LXMF-rs `reticulumd` instead of
only recording them locally, add the ZeroMQ SDK endpoints and the local source
destination:

```powershell
cargo run -p r3akt-rch-server -- --bind 127.0.0.1:8080 --db-path .\rch-runtime.db --config-path .\config.ini --reticulum-config-path $env:USERPROFILE\.reticulum\config --lxmf-zmq-command tcp://localhost:9100 --lxmf-zmq-response tcp://localhost:9101 --reticulumd-source <local-destination>
```

To let the Rust server own the local LXMF-rs daemon lifecycle, also pass the
`reticulumd.exe` path and an optional daemon database path. The server starts
`reticulumd` before accepting runtime traffic, stops the managed child during
graceful shutdown, and applies `/Control/Stop` and `/Control/Start` to the child
process lifecycle. `/Control/Status` and `/diagnostics/runtime` expose the
managed child as `reticulumd_managed_process` with pid, endpoint, database path,
running status, and lifecycle timestamps. Managed `reticulumd` defaults to
`tcp://localhost:9100` for the ZeroMQ command endpoint and
`tcp://localhost:9101` for the SDK response endpoint. The managed daemon binary
must be built from LXMF-rs with `zmq-pipeline-rpc` support:

```powershell
cargo run -p r3akt-rch-server -- --bind 127.0.0.1:8080 --db-path .\rch-runtime.db --config-path .\config.ini --reticulum-config-path $env:USERPROFILE\.reticulum\config --reticulumd-source <local-destination> --reticulumd-exe "C:\Users\broth\Documents\work\ATAK\src\LXMF-rs\target\debug\reticulumd.exe" --reticulumd-db-path .\reticulumd.db
```

Pass `--ui-dist-path "C:\Users\broth\Documents\work\ATAK\src\Reticulum-Telemetry-Hub\ui\dist"`
or set `R3AKT_UI_DIST_PATH` to serve the built RCH UI bundle from the same Rust
server. Unknown non-API paths fall back to `index.html` so Vue router deep links
work without the Python FastAPI backend. The `/checklists` path is both a Vue
route and a legacy checklist API route; Rust serves `index.html` for
`Accept: text/html` navigation while preserving the JSON API response for
normal UI fetches.

To require the same protected-route credential shape as Python RCH, pass
`--api-key <secret>` or set `RTH_API_KEY`; `RCH_API_KEY` remains supported as
the legacy fallback. Protected HTTP routes accept `X-API-Key: <secret>` or
`Authorization: Bearer <secret>`. WebSocket auth frames validate the same
`api_key` or `token` values and use Python-compatible auth timeout, bad-auth,
and unauthorized close codes.

System WebSocket status fanout defaults to Python's `event_only` mode. Pass
`--system-status-fanout-mode periodic` or
`--system-status-fanout-mode event_plus_periodic`, or set
`RTH_WS_STATUS_FANOUT_MODE` / `RCH_WS_STATUS_FANOUT_MODE`, to enable the
Python-compatible periodic status stream and event-plus-status behavior.

Implemented route contracts in this first slice:

- `GET /openapi.json`
- `GET /openapi.yaml`
- `GET /Help`
- `GET /Examples`
- `GET /api/v1/app/info`
- `GET /Status`
- `GET /diagnostics/runtime`
- `GET /Diagnostics/Runtime`
- `GET /api/v1/auth/validate`
- `GET /Events`
- `GET /Telemetry?since=...&topic_id=...`
- `POST /Message`
- `GET /Command/DumpRouting`
- `POST /Command/FlushTelemetry` clears SQLite-backed telemetry records and
  records the `telemetry_flushed` system event
- `POST /Command/ReloadConfig` returns the Rust app info/config path payload
  and records the Python-style `config_reloaded` system event
- `GET /Control/Status`
- `POST /Control/Stop`
- `POST /Control/Start`
- `POST /Control/Announce` dispatches `sdk_identity_announce_now_v2` through
  the configured LXMF-rs `reticulumd` RPC endpoint and records a Rust system
  event; without an RPC endpoint it preserves Python's `503` unavailable shape
- `POST /Control/Sync` lists peers through the configured LXMF-rs
  `reticulumd` RPC endpoint, requests `peer_sync` for the selected propagation
  peer, records a Rust system event, and preserves Python's `503` unavailable
  shape when no sync target is available
- `GET /Reticulum/Interfaces/Capabilities` returns Python-compatible fallback
  data without a runtime and, when configured, derives runtime-active interface
  support from LXMF-rs `reticulumd` `daemon_status_ex`/`list_interfaces`
- `GET /Reticulum/Discovery` returns Python-compatible discovery keys and,
  when configured, normalizes LXMF-rs `reticulumd` interface runtime metadata
- `GET /Config`
- `PUT /Config`
- `POST /Config/Validate`
- `POST /Config/Rollback`
- `GET /Reticulum/Config`
- `PUT /Reticulum/Config`
- `POST /Reticulum/Config/Validate`
- `POST /Reticulum/Config/Rollback`
- `GET /File` with SQLite-backed metadata and Python-compatible pagination
  envelope
- `GET /File/{file_id}`
- `PATCH /File/{file_id}`
- `DELETE /File/{file_id}`
- `GET /File/{file_id}/raw`
- `GET /Image` with SQLite-backed metadata and Python-compatible pagination
  envelope
- `GET /Image/{file_id}`
- `PATCH /Image/{file_id}`
- `DELETE /Image/{file_id}`
- `GET /Image/{file_id}/raw`
- `GET /Chat/Messages`
- `POST /Chat/Message` with SQLite-backed outbound persistence plus
  reticulumd-bound `FIELD_EVENT` and canonical LXMF-rs `attachments` fields for
  attached file/image payloads
- `POST /Chat/Attachment` multipart upload with Python-compatible validation,
  SQLite-backed metadata, and raw-byte storage
- `GET /api/rem/peers` with SQLite-backed active REM peer registry, moderation
  filtering, destination-announce preference, registered REM mode, and
  connected-mode flag
- `GET /api/EmergencyActionMessage`
- `POST /api/EmergencyActionMessage`
- `GET /api/EmergencyActionMessage/latest/{team_member_uid}`
- `GET /api/EmergencyActionMessage/team/{team_uid}/summary`
- `GET /api/EmergencyActionMessage/{callsign}`
- `PUT /api/EmergencyActionMessage/{callsign}`
- `DELETE /api/EmergencyActionMessage/{callsign}`
- `GET /api/markers` with SQLite-backed marker persistence and Python-compatible
  empty-store shape
- `GET /api/markers/symbols`
- `POST /api/markers` with SQLite-backed persistence plus marker event and
  local telemetry side effects
- `PATCH /api/markers/{object_destination_hash}/position` with marker event
  and local telemetry side effects
- `PATCH /api/markers/{object_destination_hash}` with marker event and local
  telemetry side effects
- `DELETE /api/markers/{object_destination_hash}` with marker event and local
  telemetry side effects
- `GET /api/zones` with SQLite-backed zone persistence and Python-compatible
  empty-store shape
- `POST /api/zones` with SQLite-backed persistence
- `PATCH /api/zones/{zone_id}`
- `DELETE /api/zones/{zone_id}`
- `GET /checklists/templates` with SQLite-backed template persistence
- `POST /checklists/templates`
- `GET /checklists/templates/{template_id}`
- `PATCH /checklists/templates/{template_id}`
- `POST /checklists/templates/{template_id}/clone`
- `DELETE /checklists/templates/{template_id}`
- `GET /checklists` with SQLite-backed checklist persistence and
  Python-compatible empty-store envelope
- `POST /checklists/offline` with SQLite-backed checklist persistence
- `POST /checklists` through the Rust checklist core command path; online
  mission checklists emit the Python-style `mission.checklist.created`
  mission-change delta
- `GET /checklists/{checklist_id}`
- `PATCH /checklists/{checklist_id}`
- `DELETE /checklists/{checklist_id}`
- `POST /checklists/import/csv`
- `POST /checklists/{checklist_id}/join`
- `POST /checklists/{checklist_id}/upload`
- `POST /checklists/{checklist_id}/feeds/{feed_id}`
- `POST /checklists/{checklist_id}/tasks` with Python-style
  `mission.checklist.task.row.added` mission-change delta for mission-backed
  checklists
- `DELETE /checklists/{checklist_id}/tasks/{task_id}`
- `PATCH /checklists/{checklist_id}/tasks/{task_id}/row-style`
- `PATCH /checklists/{checklist_id}/tasks/{task_id}/cells/{column_id}`
- Row-style and cell-edit routes emit Python-style mission-change deltas for
  mission-backed checklists
- `POST /checklists/{checklist_id}/tasks/{task_id}/status`
  emits the Python-style `mission.checklist.task.status_set` mission-change
  delta for mission-backed checklists
- Core R3AKT registry routes are backed by the Rust SQLite state for missions,
  teams, members, assets, skills, assignments, rights, mission links, RDEs,
  audit events, and snapshots while preserving Python-compatible empty-store
  shapes. Missing resource routes return Python-style `404`; event and snapshot
  writes are not exposed as HTTP mutations.
- Internal adapter REST routes are registered without API-key protection to
  match Python's `/internal` adapter boundary: topic/subscriber reads,
  node-status reads, message acceptance, and Rust-owned RCH announce-capability
  snapshots for the implemented server surfaces.
- `GET /internal/events/stream` WebSocket accepts without API-key auth and
  fans out Rust internal adapter events such as `MessagePublished` with the
  Python internal API event-envelope shape.
- `GET /Topic` legacy list plus Python-compatible pagination envelope when
  `page` or `per_page` is supplied
- `POST /Topic`
- `PATCH /Topic`
- `DELETE /Topic?id=...`
- `POST /Topic/Associate`
- `POST /Topic/Subscribe`
- `GET /Topic/{topic_id}`
- `GET /Subscriber` legacy list plus Python-compatible pagination envelope when
  `page` or `per_page` is supplied
- `POST /Subscriber`
- `POST /Subscriber/Add`
- `PATCH /Subscriber`
- `DELETE /Subscriber?id=...`
- `GET /Subscriber/{subscriber_id}`
- `GET /Client` legacy list plus Python-compatible pagination envelope when
  `page` or `per_page` is supplied, including SQLite-backed REM metadata
  annotation from persisted identity announces and REM modes
- `GET /Identities` with SQLite-backed REM metadata annotation from persisted
  identity announces and REM modes
- `POST /Client/{identity}/Ban`
- `POST /Client/{identity}/Unban`
- `POST /Client/{identity}/Blackhole`
- `POST /RTH?identity=...`
- `PUT /RTH?identity=...`
- `POST /RCH?identity=...`
- `PUT /RCH?identity=...`
- `GET /events/system` WebSocket auth plus `system.subscribe` status,
  Python-style default event replay after auth, persisted event replay on
  subscribe including Python-style `events_limit` defaults, Python-style
  `ping`/`pong` keepalive, stale-client timeout close, and configurable
  Python-style `system.status` fanout
- `GET /telemetry/stream` WebSocket auth plus `telemetry.subscribe`,
  persisted telemetry snapshot, Python-style default `follow=true`,
  Python-style `ping`/`pong` keepalive, stale-client timeout close, and
  `telemetry.update` fanout
- `GET /messages/stream` WebSocket auth plus `message.subscribe`,
  `message.send`, Python-style `ping`/`pong` keepalive, stale-client timeout
  close, outbound SQLite persistence, and filtered `message.receive` fanout
- `GET /api/r3akt/missions` with SQLite-backed mission registry persistence
- `POST /api/r3akt/missions`
- `GET /api/r3akt/missions/{mission_uid}`
- `PATCH /api/r3akt/missions/{mission_uid}`
- `DELETE /api/r3akt/missions/{mission_uid}`
- `PUT /api/r3akt/missions/{mission_uid}/parent`
- `GET /api/r3akt/capabilities/{identity}` with SQLite-backed explicit
  operation grants
- `PUT /api/r3akt/capabilities/{identity}/{capability}`
- `DELETE /api/r3akt/capabilities/{identity}/{capability}`
- `GET /api/r3akt/rights/definitions`
- `GET /api/r3akt/rights/subjects` with SQLite-backed team-member subject
  resolution
- `GET /api/r3akt/rights/grants` with SQLite-backed explicit operation grants
- `PUT /api/r3akt/rights/grants`
- `DELETE /api/r3akt/rights/grants`
- `GET /api/r3akt/rights/mission-access` with SQLite-backed role assignments
- `PUT /api/r3akt/rights/mission-access`
- `DELETE /api/r3akt/rights/mission-access`
- `GET /api/r3akt/missions/{mission_uid}/zones` with SQLite-backed mission-zone
  links
- `PUT /api/r3akt/missions/{mission_uid}/zones/{zone_id}`
- `DELETE /api/r3akt/missions/{mission_uid}/zones/{zone_id}`
- `GET /api/r3akt/missions/{mission_uid}/markers` with SQLite-backed
  mission-marker links
- `PUT /api/r3akt/missions/{mission_uid}/markers/{marker_id}`
- `DELETE /api/r3akt/missions/{mission_uid}/markers/{marker_id}`
- `GET /api/r3akt/missions/{mission_uid}/rde` with SQLite-backed mission RDE
  role state
- `PUT /api/r3akt/missions/{mission_uid}/rde`
- `GET /api/r3akt/mission-changes` with SQLite-backed mission-change persistence
- `POST /api/r3akt/mission-changes`
- `GET /api/r3akt/log-entries` with SQLite-backed log-entry persistence
- `POST /api/r3akt/log-entries`
- `GET /api/r3akt/teams` with SQLite-backed team persistence
- `POST /api/r3akt/teams`
- `GET /api/r3akt/teams/{team_uid}`
- `DELETE /api/r3akt/teams/{team_uid}`
- `GET /api/r3akt/teams/{team_uid}/missions`
- `PUT /api/r3akt/teams/{team_uid}/missions/{mission_uid}`
- `DELETE /api/r3akt/teams/{team_uid}/missions/{mission_uid}`
- `GET /api/r3akt/team-members` with SQLite-backed team-member persistence
- `POST /api/r3akt/team-members`
- `GET /api/r3akt/team-members/{team_member_uid}`
- `DELETE /api/r3akt/team-members/{team_member_uid}`
- `GET /api/r3akt/team-members/{team_member_uid}/clients`
- `PUT /api/r3akt/team-members/{team_member_uid}/clients/{client_identity}`
- `DELETE /api/r3akt/team-members/{team_member_uid}/clients/{client_identity}`
- `GET /api/r3akt/assets` with SQLite-backed asset persistence
- `POST /api/r3akt/assets`
- `GET /api/r3akt/assets/{asset_uid}`
- `DELETE /api/r3akt/assets/{asset_uid}`
- `GET /api/r3akt/skills` with SQLite-backed skill persistence
- `POST /api/r3akt/skills`
- `GET /api/r3akt/team-member-skills`
- `POST /api/r3akt/team-member-skills`
- `GET /api/r3akt/task-skill-requirements`
- `POST /api/r3akt/task-skill-requirements`
- `GET /api/r3akt/assignments` with SQLite-backed assignment persistence
- `POST /api/r3akt/assignments`
- `PUT /api/r3akt/assignments/{assignment_uid}/assets`
- `PUT /api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}`
- `DELETE /api/r3akt/assignments/{assignment_uid}/assets/{asset_uid}`

When `--db-path` is supplied, the server loads and saves clients, topics,
subscribers, identity moderation state, file/image attachment metadata and chat
attachment references, markers, zones, checklist templates, checklists,
checklist tasks, checklist cells, checklist feed publications, and R3AKT
mission/mission-zone-link/mission-marker-link/mission-RDE/mission-change/
log-entry/team/team-member/asset/skill/assignment registry records plus
explicit operation grants and mission-access assignments through the existing
`r3akt-rch-core` SQLite snapshot schema while preserving other snapshot tables
already present in that database.

Python database migration boundary: Rust-owned state is stored in the
`rch_*` tables from `crates/r3akt-rch-core/migrations/0001_rch_core_snapshot.sql`.
The legacy SQLAlchemy tables from Python RCH
`reticulum_telemetry_hub/api/storage_models.py` (`topics`, `subscribers`,
`clients`, `file_records`, `markers`, `zones`, `chat_messages`,
`identity_states`, `identity_announces`, `identity_rem_modes`, and
`identity_capability_grants`) are treated as reference/import sources, not as
tables Rust mutates in place. Sharing an existing Python database file preserves
non-`rch_*` tables, but it does not automatically import those legacy rows into
Rust runtime state. Preserve existing Python deployments by either replaying
state through the Rust HTTP/bridge command surfaces or adding an explicit import
tool that maps each named Python table into the corresponding `rch_*` snapshot
record before making Rust the only UI-facing backend.

## External Runtime Validation

The Rust server owns the UI-facing RCH contract and passes the local Rust
release gates below. The remaining release evidence is external live validation
against real Reticulum and TAK infrastructure:

| Python source | Behavior still to prove or port | Reason / follow-up |
| --- | --- | --- |
| `reticulum_telemetry_hub/reticulum_server/outbound_queue_delivery.py` and `outbound_queue_stats.py` | LXMF delivery callbacks, receipt registration, timeout finalization, pending dispatch cleanup, and queue retry worker transitions | Rust can send through `reticulumd` RPC, applies the Python-style delivery policy before dispatch, persists accepted/failed/queued/in-progress dispatch state and metadata, reports direct pending-receipt and pending-dispatch diagnostics plus Python-style queue metric keys, accepts internal delivery-receipt, delivery-failure, delivery-retry, propagation-fallback, payload-drop, and attempt-start callbacks that clear pending receipts and emit Python-style `message_delivered`/`message_propagated`/`message_delivery_failed`/`message_delivery_retrying`/`message_propagation_queued` events, polls LXMF-rs `sdk_status_v2` for terminal delivered/failed/cancelled/expired/rejected receipt state, tags callback-origin metadata, summarizes callback totals in runtime diagnostics, finalizes expired direct receipts and stale pending dispatches from diagnostics and the background outbound worker, records Python-style `message_delivery_failed` system events for send failures, receipt timeouts, queue drops, and dispatch timeouts, cools down direct destinations after send failure, runs a Rust retry pickup worker for due `retry_scheduled` messages with metadata-driven backoff and runtime diagnostics counters, and includes opt-in live direct-receipt and fanout validation hooks; local two-daemon direct receipt and three-daemon fanout receipt validation now pass |
| `reticulum_telemetry_hub/reticulum_server/runtime_init.py` and `runtime_lifecycle.py` | Full hub startup/shutdown orchestration, listener registration, identity capability/presence callbacks, and service wiring | `r3akt-rch-server` owns HTTP/WebSocket state, optional `reticulumd` RPC configuration, optional managed `reticulumd.exe` child startup/shutdown with `/Control/Status` and `/diagnostics/runtime` service inventory visibility, runtime service inventory diagnostics for Reticulum RPC and managed process state, control start/stop applies to managed `reticulumd.exe` child process state plus Reticulum RPC running status, the outbound delivery worker now pauses/resumes across control stop/start instead of exiting permanently, process shutdown now uses Axum graceful shutdown plus outbound/inbound worker abort plus managed `reticulumd` child termination, `/internal/identity-announce` lets a Rust-owned listener persist identity announce metadata, update client presence, annotate REM peers, and emit a system event, and the Rust server starts a `reticulumd` inbound event-cursor worker that consumes LXMF-rs `sdk_poll_events_v2` batches for R3AKT inbound envelopes and Reticulum announces; inbound mission/checklist commands are executed through `RchCore`, reply through `reticulumd`, persist Rust state, and fan out `FIELD_EVENT` mission replies to linked mission team recipients. The Rust replacement architecture treats managed LXMF-rs `reticulumd` as the Reticulum listener/socket owner; TAK socket lifecycle is owned by the separate `r3akt-tak-service`. Remaining work is live service-orchestration validation across real Reticulum peers, the external TAK service, inbound event ingestion, outbound retry, and shutdown/restart sequencing. |
| `reticulum_telemetry_hub/reticulum_server/services.py` and `reticulum_telemetry_hub/reticulum_server/runtime_tak_fields.py` | Configured TAK connector lifecycle, telemetry-to-CoT scheduling, and richer failure logging | Rust now has CoT builders, PyTAK-shaped TAK hello/pong payloads, clear TCP/UDP and native TLS CoT senders, queue/backpressure, PKCS#12/PFX `tls_client_password` support with explicit unsupported encrypted-PEM failure, structured inbound CoT parsing with Python `ReceiveWorker` raw-fallback behavior, an inbound polling service boundary for parsed/raw receive result recording, bounded TCP/UDP/TLS socket receivers with local loopback coverage, outbound and inbound background retry workers with Python-style exponential send/receive-failure backoff, keepalive/ping scheduling, local bidirectional TCP loopback validation, opt-in live TAK push/reconnect/inbound smoke hooks, and standalone `r3akt-tak-service` northbound bridging from RCH telemetry/chat to TAK CoT plus TAK CoT to RCH marker ingestion; final validation against the target TAK server profile remains external |
| `reticulum_telemetry_hub/mission_domain/service_lifecycle.py`, `service_checklists.py`, `service_checklist_tasks.py`, `service_assets.py`, and `service_skills_assignments.py` | Automatic mission-change side effects, post-commit listener notifications, and recipient fanout from checklist delete and skill-related mutations | Rust persists the route families and core records; online checklist creation, checklist upload, task-row creation, row styling, cell edits, status changes, task-row deletes, checklist delete cleanup for tasks/cells/requirements/assignments/assignment-asset links, checklist deleted audit events without auto mission-change creation, asset upsert/delete, assignment upsert/assets set/link/unlink, team delete cleanup, team-member delete cleanup, and post-commit mission-change listener events now match the Python side-effect/listener boundary; checklist upload and assignment asset link fanout now have generic LXMF markdown golden-shape coverage with resolved mission/task/asset names; remaining validation is broader live recipient fanout against real peers |
| `reticulum_telemetry_hub/reticulum_server/runtime_rem_fanout.py` and `rem_checklist_commands.py` | REM registry/checklist/EAM fanout for mission-change events and duplicate fanout suppression | Rust exposes checklist and mission APIs, tracks mission-change duplicate suppression state/metadata, sends R3AKT mission-delta event fields to linked mission team recipients through reticulumd including each team member's RNS identity plus linked client identities like Python, emits connected-REM `FIELD_COMMANDS` checklist command envelopes for task deltas plus initial checklist create/upload row replay when persisted REM connected mode is effective like Python, sends Python-style markdown-rendered fallback bodies with persisted mission/checklist/task/team/asset name resolution to generic LXMF peers, matches Python's generic mission-log update markdown shape, treats voice-capable LXMF peers as chat-capable destinations with voice as an additional feature, now emits EAM upsert/delete fanout as REM `FIELD_COMMANDS` or generic markdown only when persisted REM connected mode is effective like Python, and passes local three-daemon multi-recipient fanout receipt validation |

## Verify

Current local verification snapshot, refreshed on 2026-05-11:

- `cargo fmt --all -- --check` passed.
- `cargo clippy --workspace --all-targets -- -D warnings` passed.
- `cargo test --workspace` passed, including the Rust HTTP/WebSocket contract,
  persistence, runtime lifecycle, local live `reticulumd` RPC, and TAK connector
  test suites.
- `cargo test -p r3akt-rch-server` passed, including 213 server library tests,
  21 gateway binary tests, the release-major functionality suite, and SAR HTTP
  seeder coverage.
- `cargo test -p r3akt-rch-core`, `cargo test -p r3akt-transport-rns`, and
  `cargo test -p r3akt-tak-connector` passed.
- `r3akt-tak-connector tak_tcp_loopback_validates_bidirectional_cot_workflow`
  passed, covering outbound TCP keepalive send and inbound parsed CoT receive in
  one local bidirectional TAK workflow.
- `r3akt-tak-connector tak_proto_tcp_sender_pushes_stream_framed_protobuf_payload`
  passed, covering `TAK_PROTO>0` stream-framed protobuf payload emission while
  preserving `COT_URL` as the transport selector.
- `r3akt-tak-service service_bridges_rch_telemetry_and_chat_to_tak_cot_socket`
  and `service_bridges_inbound_tak_cot_to_rch_marker_route` passed, covering
  the standalone northbound HTTP bridge in both CoT directions.
- `cargo build --release -p r3akt-rch-server` passed.
- `.\scripts\release-readiness.ps1 -ServerOnlyAlpha -SkipClippy
  -SkipWorkspaceTests` passed, covering the committed alpha gate runner, Rust
  format check, the server release build, and a release HTTP smoke started with
  mandatory ZeroMQ SDK endpoints.
- `.github/workflows/rust-pr-quality.yml` runs PR quality-control checks for
  Rust formatting, clippy with warnings denied, locked workspace tests, release
  binary builds, and `cargo audit` against Rust 1.85.
- `.github/workflows/rust.yml` runs the committed release gate runner with
  `-ServerOnlyAlpha` so push and PR CI still cover the alpha verifier, the
  server release build, and the ZeroMQ-configured release HTTP smoke.
- A release-binary smoke test with a temporary SQLite database passed for
  `/Status`, `/openapi.json`, `/Help`, `/api/v1/app/info`, topic creation/list,
  chat creation/list, checklist template creation, mission creation/list, and
  offline checklist creation/list.
- `npm ci` and `npm audit --audit-level=moderate` in
  `C:\Users\broth\Documents\work\ATAK\src\Reticulum-Telemetry-Hub\ui` passed
  with zero audited vulnerabilities after the lockfile refresh.
- `npm run lint` in the same UI directory passed.
- `npm run test` in
  `C:\Users\broth\Documents\work\ATAK\src\Reticulum-Telemetry-Hub\ui` passed
  with 23 files and 70 tests.
- `npm run build` in the same UI directory passed.
- `npm run build` in
  `C:\Users\broth\Documents\work\ATAK\src\Reticulum-Telemetry-Hub\apps\rch-desktop`
  passed, including shared UI build,
  Tauri sidecar preparation, optimized desktop build, and Windows x64 NSIS
  installer generation for `RCH Desktop_3.0.0-preview.2_x64-setup.exe`.
- A local Rust-backend UI smoke against the built `ui/dist` passed: `/`,
  `/missions/workspace`, and HTML `/checklists` served the SPA, while
  `/Status`, `/api/v1/app/info`, `/checklists`, `/Telemetry?since=0`, and
  `/api/r3akt/missions` returned Rust-backed API payloads without Python
  FastAPI running.
- Local self-loopback `reticulumd.exe` checks passed for
  `r3akt-transport-rns` live send/receive, `r3akt-rch-bridge` live outbound
  send acceptance, and `r3akt-rch-server` managed daemon lifecycle.
- Repeatable local three-node `reticulumd.exe` receipt/fanout/ZeroMQ event
  validation is available through `scripts/local-reticulum-live-gate.ps1`; the
  latest run on 2026-05-30 passed direct receipt, two-recipient fanout, and
  `sdk_poll_events_v2` over the LXMF-rs ZeroMQ RPC loop with
  `-IncludeZmqEventPoll -DiscoverySettleSeconds 10 -ReceiptPollAttempts 180`.
- Controlled external RMAP Reticulum validation passed on 2026-05-11 by running
  `scripts/local-reticulum-live-gate.ps1` with
  `-ExternalConfigPath C:\Users\broth\Documents\work\ATAK\src\LXMF-rs\target\local\reticulumd-rmap-testnet.toml`;
  three temporary local identities connected through the public TCP hubs and
  delivered both direct receipt and two-recipient fanout through the Rust server.
- Local two-daemon `reticulumd.exe` receipt validation passed for
  `r3akt-rch-server live_reticulumd_direct_send_receipt_is_delivered_when_configured`,
  sending from one local daemon to another daemon's announced LXMF delivery
  destination and settling the direct delivery receipt.
- Local three-daemon `reticulumd.exe` fanout validation passed for
  `r3akt-rch-server live_reticulumd_topic_fanout_receipts_are_delivered_when_configured`,
  sending one topic fanout message from a source daemon to two announced LXMF
  delivery destinations and settling both direct delivery receipts.
- The inbound mission-command fanout parity pass added
  `reticulumd_inbound_mission_command_replies_and_fans_out_team_event`, and the
  latest pass also verifies valid team/client RNS identities plus propagated
  fallback when no fresh direct presence exists.
- The checklist-delete cascade parity pass tightened
  `checklist_delete_cleans_assignment_links_like_python_cascade` to cover task
  skill requirement cleanup, assignment/assignment-asset cleanup, the
  `checklist.deleted` audit event, and the absence of an auto mission-change;
  `cargo test -p r3akt-rch-core` passed.
- The assignment fanout parity pass added
  `assignment_asset_link_fanout_uses_python_generic_markdown_shape`, proving
  generic LXMF recipients receive resolved mission, checklist task, and asset
  names for assignment asset link deltas.
- The voice routing parity pass confirms voice-capable LXMF peers remain in
  chat/fanout routing; voice is additional capability metadata, not a
  voice-only destination class.
- The reticulumd inbound worker parity pass verifies current event polling,
  `list_messages`, announce import, stream cursor reset, and diagnostics
  behavior without order-dependent background-worker races.
- The direct delivery parity pass verifies SDK direct-send methods,
  SDK-prefixed receipt status IDs, retry scheduling after receipt timeout, and
  propagated fallback after direct-send failure.

The configured target TAK profile on `tcp://137.184.101.250:8087` passed
keepalive, reconnect, and bidirectional inbound relay validation on 2026-05-11.
The initial alpha decision is scoped to the server package. Full release
packaging now builds UI, TAK, and desktop artifacts in CI, while local
Reticulum and controlled external RMAP evidence remain useful validation
history. Only the server-package alpha gates are release-blocking for this
milestone.

The local server-only alpha release gate runner is:

```powershell
.\scripts\release-readiness.ps1 -ServerOnlyAlpha
```

Use explicit live gates only after configuring reachable infrastructure:

```powershell
.\scripts\release-readiness.ps1 -LiveTak -LiveReticulum
```

Build full GitHub release artifacts with `.github/workflows/rust-release.yml`.
Manual runs upload workflow artifacts; published GitHub releases receive the
server archives, checksums, and desktop bundles as release assets.

Run the repeatable local Reticulum receipt/fanout/ZeroMQ event-poll harness when sibling
`LXMF-rs\target\debug\reticulumd.exe` is available:

```powershell
.\scripts\local-reticulum-live-gate.ps1 `
  -IncludeZmqEventPoll `
  -DiscoverySettleSeconds 10 `
  -ReceiptPollAttempts 180
```

Run the same local mesh with a daemon-involved ZeroMQ load check. This sends
normal individual `sdk_send_v2` messages from node 0 to the local receiver
daemons and confirms delivery through receiver-side `sdk_poll_events_v2`:

```powershell
.\scripts\local-reticulum-live-gate.ps1 `
  -IncludeZmqLoad `
  -LoadMessages 1000 `
  -LoadSenderClients 4 `
  -DiscoverySettleSeconds 10
```

Use `-ZmqLoadOnly` to run only the load check while tuning daemon delivery
throughput.

The Rust daemon delivery path now uses a bounded persistent scheduler rather
than spawning one delivery runtime per message. Tune burst capacity with the
daemon environment variables `LXMD_DELIVERY_QUEUE_CAPACITY`,
`LXMD_DELIVERY_GLOBAL_CONCURRENCY`, and `LXMD_DELIVERY_PER_PEER_IN_FLIGHT`.
Use `daemon_status_ex`, `sdk_snapshot_v2`, or `sdk_status_v2` to inspect the
`delivery_pipeline` counters while running `-ZmqLoadOnly`.

Run the same harness against a controlled external Reticulum/RMAP profile by
passing a `reticulumd` TOML config:

```powershell
.\scripts\local-reticulum-live-gate.ps1 `
  -ExternalConfigPath "C:\Users\broth\Documents\work\ATAK\src\LXMF-rs\target\local\reticulumd-rmap-testnet.toml" `
  -TimeoutSeconds 180 `
  -DiscoverySettleSeconds 45 `
  -ReceiptPollAttempts 240 `
  -ReceiptPollDelayMs 1000
```

```powershell
cargo fmt --all
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo run -p sim-agent
cargo run -p rch-ingest-sim
```

RCH UI build and live Rust-backend smoke:

```powershell
Push-Location "C:\Users\broth\Documents\work\ATAK\src\Reticulum-Telemetry-Hub\ui"
npm run test -- --run
npm run build
Pop-Location

$server = Start-Process -FilePath ".\target\release\r3akt-rch-server.exe" `
  -ArgumentList "--bind","127.0.0.1:8080","--api-key","secret","--db-path",(Join-Path $env:TEMP "r3akt-rch-ui-smoke.db"),"--ui-dist-path","C:\Users\broth\Documents\work\ATAK\src\Reticulum-Telemetry-Hub\ui\dist" `
  -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru
try {
  (Invoke-RestMethod -Headers @{ "X-API-Key" = "secret" } -Uri "http://127.0.0.1:8080/").Contains('id="app"')
  (Invoke-RestMethod -Headers @{ "X-API-Key" = "secret" } -Uri "http://127.0.0.1:8080/missions/workspace").Contains('id="app"')
  (Invoke-WebRequest -Headers @{ "Accept" = "text/html" } -Uri "http://127.0.0.1:8080/checklists").Content.Contains('id="app"')
  Invoke-RestMethod -Headers @{ "X-API-Key" = "secret" } -Uri "http://127.0.0.1:8080/Status"
  Invoke-RestMethod -Headers @{ "X-API-Key" = "secret" } -Uri "http://127.0.0.1:8080/api/v1/app/info"
  Invoke-RestMethod -Headers @{ "X-API-Key" = "secret" } -Uri "http://127.0.0.1:8080/checklists"
  Invoke-RestMethod -Headers @{ "X-API-Key" = "secret" } -Uri "http://127.0.0.1:8080/Telemetry?since=0"
  Invoke-RestMethod -Headers @{ "X-API-Key" = "secret" } -Uri "http://127.0.0.1:8080/api/r3akt/missions"
} finally {
  Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
```

Live reticulumd RPC adapter check with a local self-loopback daemon:

```powershell
$rpc = "127.0.0.1:7777"
$db = Join-Path $env:TEMP ("r3akt-live-reticulumd-" + [guid]::NewGuid().ToString() + ".db")
$reticulumd = "C:\Users\broth\Documents\work\ATAK\src\LXMF-rs\target\debug\reticulumd.exe"
$p = Start-Process -FilePath $reticulumd -ArgumentList "--rpc",$rpc,"--db",$db -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
$env:R3AKT_RETICULUMD_RPC_ENDPOINT = "127.0.0.1:7777"
$env:R3AKT_RETICULUMD_SOURCE = "r3akt-live-source"
$env:R3AKT_RETICULUMD_DESTINATION = "r3akt-live-source"
try {
  cargo test -p r3akt-transport-rns live_reticulumd_rpc_adapter_sends_and_receives_r3akt_envelope -- --nocapture
  cargo test -p r3akt-rch-bridge live_reticulumd_outbound_send_request_is_accepted_when_configured -- --nocapture
  $env:R3AKT_RETICULUMD_EXE = $reticulumd
  cargo test -p r3akt-rch-server live_managed_reticulumd_start_stop_start_cycle_when_configured -- --nocapture
} finally {
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
```

Repeatable local Reticulum receipt, fanout, and ZeroMQ event-poll validation:

```powershell
.\scripts\local-reticulum-live-gate.ps1 `
  -IncludeZmqEventPoll `
  -DiscoverySettleSeconds 10 `
  -ReceiptPollAttempts 180
```

Controlled external RMAP Reticulum receipt and fanout validation:

```powershell
.\scripts\local-reticulum-live-gate.ps1 `
  -ExternalConfigPath "C:\Users\broth\Documents\work\ATAK\src\LXMF-rs\target\local\reticulumd-rmap-testnet.toml" `
  -TimeoutSeconds 180 `
  -DiscoverySettleSeconds 45 `
  -ReceiptPollAttempts 240 `
  -ReceiptPollDelayMs 1000
```

Optional live Reticulum receipt validation against a real reachable peer:

```powershell
$env:R3AKT_RETICULUMD_RPC_ENDPOINT = "127.0.0.1:7777"
$env:R3AKT_RETICULUMD_SOURCE = "r3akt-live-source"
$env:R3AKT_RETICULUMD_RECEIPT_DESTINATION = "<reachable-peer-destination>"
cargo test -p r3akt-rch-server live_reticulumd_direct_send_receipt_is_delivered_when_configured -- --nocapture
```

Optional live Reticulum fanout validation against two or more reachable peers:

```powershell
$env:R3AKT_RETICULUMD_RPC_ENDPOINT = "127.0.0.1:7777"
$env:R3AKT_RETICULUMD_SOURCE = "r3akt-live-source"
$env:R3AKT_RETICULUMD_FANOUT_DESTINATIONS = "<peer-a-destination>,<peer-b-destination>"
cargo test -p r3akt-rch-server live_reticulumd_topic_fanout_receipts_are_delivered_when_configured -- --nocapture
```

Optional live Reticulum event/announce validation against real reachable peers:

```powershell
$env:R3AKT_RETICULUMD_RPC_ENDPOINT = "127.0.0.1:7777"
$env:R3AKT_RETICULUMD_EXPECT_ANNOUNCE = "1"
cargo test -p r3akt-transport-rns live_reticulumd_rpc_adapter_lists_announces_when_configured -- --nocapture

$server = Start-Process -FilePath ".\target\debug\r3akt-rch-server.exe" `
  -ArgumentList "--bind","127.0.0.1:8080","--api-key","secret","--reticulumd-rpc",$env:R3AKT_RETICULUMD_RPC_ENDPOINT,"--reticulumd-source","<local-destination>" `
  -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru
try {
  Start-Sleep -Seconds 3
  $diag = Invoke-RestMethod -Headers @{ "X-API-Key" = "secret" } -Uri "http://127.0.0.1:8080/diagnostics/runtime"
  $diag.reticulumd_inbound.event_polls_total
  $diag.reticulumd_inbound.events_seen_total
  $diag.reticulumd_inbound.announces_imported_total
  $diag.reticulumd_inbound.last_event_cursor
  $diag.reticulumd_inbound.last_event_type
} finally {
  Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
```

Optional live TAK keepalive and reconnect push smokes:

```powershell
$env:R3AKT_TAK_LIVE_COT_URL = "tcp://127.0.0.1:8087" # or ssl://host:port / tls://host:port
# Optional TLS settings:
# $env:R3AKT_TAK_LIVE_TLS_CA = "C:\path\ca.pem"
# $env:R3AKT_TAK_LIVE_TLS_CLIENT_CERT = "C:\path\client.p12"
# $env:R3AKT_TAK_LIVE_TLS_CLIENT_PASSWORD = "<password>"
# $env:R3AKT_TAK_LIVE_TLS_INSECURE = "true"
cargo test -p r3akt-tak-connector live_tak_server_accepts_keepalive_when_configured -- --nocapture
cargo test -p r3akt-tak-connector live_tak_server_accepts_reconnect_when_configured -- --nocapture
```

Optional live TAK inbound receive smoke. For clear TCP targets without
`R3AKT_TAK_LIVE_INBOUND_EXPECT_UID`, this test actively publishes a probe CoT
through `R3AKT_TAK_LIVE_COT_URL` and requires the inbound connection to receive
a relayed CoT response:

```powershell
$env:R3AKT_TAK_LIVE_COT_URL = "tcp://127.0.0.1:8087"
$env:R3AKT_TAK_LIVE_INBOUND_COT_URL = "tcp://127.0.0.1:8087" # or ssl://host:port / tls://host:port
# Optional:
# $env:R3AKT_TAK_LIVE_INBOUND_EXPECT_UID = "expected-cot-uid"
cargo test -p r3akt-tak-connector live_tak_server_provides_inbound_cot_when_configured -- --nocapture
```

Standalone TAK connector service smoke:

```powershell
$env:R3AKT_TAK_RCH_BASE_URL = "http://127.0.0.1:8080"
$env:R3AKT_TAK_RCH_API_KEY = "<optional-rch-api-key>"
$env:COT_URL = "tcp://127.0.0.1:8087" # or udp://host:port / ssl://host:port / tls://host:port
$env:TAK_PROTO = "0" # non-zero enables TAK Protocol v1 stream-framed protobuf payloads
cargo run -p r3akt-tak-connector --bin r3akt-tak-service -- --once
```

`r3akt-tak-service` is the final TAK runtime boundary. It reads RCH
telemetry/chat through `/Telemetry` and `/Chat/Messages`, emits TAK CoT over the
configured TAK socket, receives TAK CoT through the same connector transport,
and publishes received CoT location events back through `/api/markers`. It is
not hosted by `r3akt-rch-server`.

Bridge smoke example:

```powershell
@'
{"type":"mission_command","command":{"command_id":"cmd-cli-1","source":{"rns_identity":"ABCDEF","display_name":"Field Agent"},"timestamp":"2026-05-03T12:00:00Z","command_type":"topic.create","args":{"topic_path":"mission-cli","topic_name":"Mission CLI"},"correlation_id":"corr-cli-1","topics":["mission-cli"]}}
'@ | cargo run -p r3akt-rch-bridge -- --db target\rch-bridge-smoke.sqlite
```
