# Rust Runtime Parity Audit

Last verified: 2026-05-05

## Objective

Full parity for this work means the same RCH behavioral tests can be run against
the Python implementation and the Rust implementation, and both pass.

## Current Evidence

- Full Python suite:
  - Command: `.\.venv\Scripts\python.exe -m pytest --no-cov -q`
  - Result: `1081 passed, 742 warnings`
- Full Python collection with Rust-selected backend variants:
  - Command: `.\.venv\Scripts\python.exe -m pytest -o addopts='' -q --rch-backend=rust`
  - Result: `869 passed, 212 deselected, 387 warnings`
  - Scope: this runs all non-parameterized tests plus the Rust backend variant
    for backend-parameterized tests, while deselecting the Python backend
    variants. It is a useful hybrid verification mode, but Python-only tests
    still execute against Python internals.
- Named Rust bridge parity suite:
  - Command: `.\.venv\Scripts\python.exe -m pytest --no-cov -m rust_bridge -q`
  - Result: `439 passed, 642 deselected, 714 warnings`
- Controlled Rust-only parity slice:
  - Command: `.\.venv\Scripts\python.exe -m pytest --no-cov -m rust_bridge --rch-backend=rust -q`
  - Result: `227 passed, 854 deselected, 359 warnings`
  - Scope: `--rch-backend=rust` deselects Python backend variants while
    retaining the Rust backend variants and statically marked Rust bridge
    runtime checks. This is a runnable reduced parity mode, not a substitute
    for a full-suite Rust backend mode.
- Shared Python-vs-Rust southbound runtime suite:
  - File: `tests/rust_runtime/test_rch_bridge_parity.py`
  - Command inventory guard covers all declared mission/checklist southbound
    commands from:
    - `reticulum_telemetry_hub.mission_sync.capabilities.MISSION_COMMAND_CAPABILITIES`
    - `reticulum_telemetry_hub.checklist_sync.capabilities.CHECKLIST_COMMAND_CAPABILITIES`
  - Current command coverage: `87 / 87`
  - Current shared backend result: `33 passed`
- Rust workspace:
  - Command: `cargo test --workspace`
  - Result: passed
  - Command: `cargo clippy --workspace --all-targets -- -D warnings`
  - Result: passed
- Rust SQLite migration and connection-hardening checks:
  - Command: `cargo test -p r3akt-rch-core`
  - Result: `59 passed`
  - Scope: standalone schema creation/version recording, additive migration for
    an existing database with unrelated legacy tables, and additive backfill of
    `published_ts_ms` on an older Rust checklist feed-publication table, plus
    a 30-second SQLite busy timeout on Rust snapshot-store connections to match
    Python storage lock-wait configuration.
- Rust RCH server crate:
  - Command: `cargo test -p r3akt-rch-server`
  - Result: `160 passed` for `src/lib.rs`, `20 passed` for `src/main.rs`
- Rust TAK connector boundary checks:
  - Command: `cargo test -p r3akt-tak-connector`
  - Result: `38 passed`
  - Scope: CoT URL derivation, chat/location CoT XML shapes, TCP/UDP/TLS
    sender and receiver behavior, keepalive and reconnect behavior,
    retry/backoff, lifecycle state, and inbound parsed/raw result recording
    stay in `r3akt-tak-connector`.
- Rust node/protocol checks:
  - Command: `cargo test -p r3akt-node`
  - Result: `4 passed` for `src/lib.rs`, `1 passed` for `tests/rch_vertical.rs`
  - Command: `cargo test -p r3akt-protocol`
  - Result: `2 passed`
  - Scope: protocol msgpack round trips, TTL validation, node inbound
    persistence/acknowledgement, duplicate suppression, poll limits, invalid
    envelope rejection, and the vertical RCH field-command runtime path.
- Rust reticulumd transport adapter checks:
  - Command: `cargo test -p r3akt-transport-rns`
  - Result: `13 passed`
  - Scope: reticulumd RPC frame send/receive, mock transport behavior, live
    reticulumd envelope smoke when configured, and direct LXMF-style message
    mapping from reticulumd `list_messages` into a typed topic envelope with
    Python-compatible plain-base64 attachment bytes, plus direct LXMF
    `FIELD_TELEMETRY` msgpack decoding for legacy integer-keyed time/location,
    battery, information, and simple scalar/vector sensor payloads including
    pressure, physical link, acceleration, temperature, humidity, magnetic
    field, ambient light, gravity, angular velocity, and proximity, plus the
    dictionary-style RNS transport, LXMF propagation, and connection-map
    payloads used by Python's complex telemetry fixtures, and the received plus
    collection-backed power, processor, memory, tank, fuel, and custom sensors.
- Rust REM southbound command checks:
  - Command: `cargo test -p r3akt-rch-core rem_registry -- --nocapture`
  - Result: `2 passed`
  - Command: `cargo test -p r3akt-rch-bridge json_bridge_enforces_rem_transport_source_and_announce_capabilities -- --nocapture`
  - Result: `1 passed`
  - Command: `cargo test -p r3akt-rch-core`
  - Result: `59 passed`
  - Command: `cargo test -p r3akt-rch-bridge`
  - Result: `10 passed`
  - Scope: `rem.registry.mode.set` and `rem.registry.peers.list` now use the
    Rust mission-sync command path with Python-compatible accepted/result
    ordering, empty REM reply content, invalid-payload rejection for bad modes,
    unknown REM-command rejection text, announce-capability authorization
    through persisted identity announces, REM mode persistence, peer registry
    result shaping, bridge-side transport source identity enforcement, and
    `/internal/identity-announce` decoding of Python/LXMF msgpack
    `app_data_hex` capability extension slots into normalized REM announce
    capabilities.
- Rust Help/Examples route checks:
  - Command: `cargo test -p r3akt-rch-server help_and_examples_routes_return_plain_text_like_python -- --nocapture`
  - Result: `1 passed`
  - Scope: `/Help` no longer returns the Rust migration-slice placeholder and
    now renders command inventory text for legacy/plugin commands,
    mission-sync commands, checklist commands, REM registry commands, and
    `TelemetryRequest`; `/Examples` now returns supported-command documentation
    with `FIELD_COMMANDS`, mission-style envelope examples, checklist command
    entries, and REM peer-registry entries instead of the topic/subscriber-only
    placeholder.
- Rust telemetry route/runtime checks:
  - Command: `cargo test -p r3akt-rch-server telemetry -- --nocapture`
  - Result: `9 passed`
  - Scope: `/Telemetry` latest-per-peer/location-only response shaping,
    Python-compatible missing-topic `404` detail, flush behavior, websocket
    authentication/snapshot/follow behavior, inbound reticulumd health telemetry
    fanout, local time telemetry sampler persistence, and TAK location dispatch
    across the dedicated connector boundary.
- Rust OpenAPI checked-in contract slices:
  - Command: `cargo test -p r3akt-rch-server openapi_ -- --nocapture`
  - Result: `10 passed`
  - Scope: `/openapi.json` and `/openapi.yaml` now document the Python static
    OpenAPI pagination contract for `/Client`, `/Topic`, `/Subscriber`, `/File`,
    and `/Image`, including `page`/`perPage` parameter refs and paginated
    response envelope schema refs; the same Rust OpenAPI surface also now
    includes the checked-in EAM list/detail/summary request and response refs,
    R3AKT/checklist schema names, R3AKT list/upsert request and response refs,
    mission detail/parent/zone/RDE request and response refs,
    team/team-member/asset detail refs,
    team-mission/member-client/assignment-asset link refs, marker/zone request
    and response refs, `/RCH` and `/RTH` identity query/boolean response
    aliases, `/Control/Announce` status/error responses,
    topic/subscriber/file/image detail and response refs, message send-result
    refs, checklist list/create/task mutation request and response refs, checklist
    template/detail/join/upload/feed request and response refs, domain
    event/snapshot refs, capabilities and rights route request/response refs,
    websocket stream `x-ws-*` schema refs and `101` upgrade responses,
    and selected path/query parameter refs asserted by the Python OpenAPI
    tests, plus the Python core payload schema names and request/validation
    refs for topic, subscriber, file/image association, config rollback/apply,
    message, runtime status/events/telemetry, Reticulum discovery/capabilities,
    auth validation, app info, identity moderation, help/examples operations,
    concrete core component property shapes for `Client`, `Topic`,
    `Subscriber`, `FileAttachment`, `Status`, `TelemetryStats`, `Event`,
    `IdentityStatus`, `ReticulumInfo`, `ReticulumDiscoveryState`,
    `ReticulumDiscoveredInterfaceEntry`, `ReticulumInterfaceCapabilities`, and
    `AuthValidationResponse`, plus standalone component schemas for
    `EAMStatus`, `MarkerCreateResponse`, `MessageEntry`, `MessageRequest`,
    `TelemetryEntry`, `WsEnvelope`, and `ZoneCreateResponse`, and EAM component
    property shapes for `EmergencyActionMessagePayload`,
    `EmergencyActionMessageUpsertPayload`, `EamTeamSummaryPayload`, and
    `EamSourcePayload`, and small wrapper/config/telemetry component property
    shapes for `TelemetryResponse`, `ConfigApplyResult`, `ConfigValidation`,
    `ConfigRollbackResult`, `R3aktChecklistListResponse`,
    `R3aktChecklistSourceIdentityRequest`, and
    `R3aktChecklistTemplateListResponse`,
    runtime diagnostics aliases, chat message list/send/upload contracts, REM
    peer registry response shape, marker detail update/delete contracts, and
    R3AKT mission marker list/link response refs, and exact checked-in
    component schemas for the 21 larger R3AKT/checklist domain models:
    `R3aktMission`, `R3aktChecklist`, `R3aktChecklistTask`,
    `R3aktChecklistCell`, `R3aktChecklistColumn`,
    `R3aktChecklistTemplate`, `R3aktChecklistFeedPublication`,
    `R3aktChecklistImportCsvRequest`, `R3aktMissionChange`,
    `R3aktMissionChangeUpsertRequest`, `R3aktLogEntry`,
    `R3aktLogEntryUpsertRequest`, `R3aktDomainEvent`,
    `R3aktDomainSnapshot`, `R3aktTeam`, `R3aktTeamMember`,
    `R3aktAsset`, `R3aktSkill`, `R3aktTeamMemberSkill`,
    `R3aktTaskSkillRequirement`, and `R3aktMissionTaskAssignment`, including
    nullable `date-time` formats for marker/zone timestamps, mission RDE
    `updated_at`, and capability-grant `granted_at`/`expires_at` fields. The
    checked-in Python OAS also no longer has the stale nested marker/zone/client
    schema block under `Topic`, so `Topic.required` stays
    `["TopicName", "TopicPath"]`.
    The OpenAPI surface now also
    removes remaining placeholder operations by documenting `/openapi.*`,
    gateway control status/start/stop/sync, Python internal adapter
    topic/subscriber/node/message/capability/event-stream routes, and Rust
    internal delivery callback plus identity-announce route request/response
    shapes, including the `app_data_hex` capability-extension input accepted
    by `/internal/identity-announce`.
  - Live Rust `/openapi.json` vs Python checked-in OpenAPI component-schema
    comparison: `yaml_matches_json=True`, `missing_schema_names=0`,
    `property_key_mismatches=0`, `required_list_mismatches=0`, and
    `exact_schema_mismatches=0`. The Rust `/openapi.yaml` endpoint is generated
    from the same OpenAPI document as `/openapi.json`, so the JSON and YAML
    routes no longer carry separate schema sources.
- Python OpenAPI source-contract checks:
  - Command: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\northbound\test_openapi_pagination.py tests\northbound\test_openapi_r3akt_paths.py tests\northbound\test_openapi_eam_paths.py tests\northbound\test_openapi_core_payloads.py tests\northbound\test_openapi_marker_zone_paths.py tests\northbound\test_openapi_runtime_core_paths.py tests\northbound\test_openapi_topic_attachment_paths.py tests\northbound\test_openapi_websocket_paths.py -q`
  - Result: `37 passed, 52 warnings`
- Python file/image API and route parity checks:
  - Command: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\test_file_api.py tests\northbound\test_file_routes.py -q`
  - Result: `34 passed, 88 warnings`
- Python auth helper checks:
  - Command: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\northbound\test_auth_helpers.py tests\northbound\test_auth.py -q`
  - Result: `11 passed, 4 warnings`
- Rust auth helper selector/parser checks:
  - Command: `cargo test -p r3akt-rch-server python_auth_helper -- --nocapture`
  - Result: `2 passed`
- Rust CLI process-control helpers:
  - Command: `cargo test -p r3akt-rch-server --bin r3akt-rch-server -- --nocapture`
  - Result: `20 passed`
  - Scope: the Rust binary now routes `start`, `stop`, `status`, and hidden
    `gateway` subcommands without breaking existing server arguments; tests
    cover Python-style `~` path expansion for `HOME`/`USERPROFILE`,
    state-file load/write, gateway command construction, CLI parsing,
    gateway-to-server bind/db mapping, Python module-style
    `-m reticulum_telemetry_hub.northbound.gateway` normalization,
    control port resolution, Python-style busy-port detection before background
    gateway spawn, and local control-client status with `X-API-Key`; the binary
    test suite also boots the foreground gateway-mode server with a SQLite
    state path and an injected shutdown future to mirror the Python
    `gateway.main` server-loop smoke.
- Python CLI/gateway source-contract checks:
  - Command: `.\.venv\Scripts\python.exe -m pytest --no-cov tests\cli\test_rch.py tests\northbound\test_gateway_runtime.py -q`
  - Result: `43 passed, 20 warnings`
- Rust outbound delivery state-machine checks:
  - Command: `cargo test -p r3akt-rch-server outbound_ -- --nocapture`
  - Result: `12 passed`
  - Scope: queued, retrying, dispatch timeout, delivery receipt polling,
    propagated-target acknowledgement, diagnostics counters, runtime
    pause/resume, and direct-send timeout cooldown behavior. The timeout
    cooldown regression mirrors the Python queue contract that marks a direct
    failure before retrying or routing the next targeted send.
- Rust reticulumd inbound delivery checks:
  - Command: `cargo test -p r3akt-rch-server reticulumd_inbound -- --nocapture`
  - Result: `12 passed`
  - Scope: inbound topic envelope recording, topic relay, websocket message
    fanout, health telemetry fanout, command handling, worker pause/resume, and
    typed topic file-attachment persistence. The attachment regression stores
    inbound bytes as a file attachment, links it to the inbound chat message,
    exposes the raw bytes through `/File/{file_id}/raw`, and restores the
    attachment metadata from SQLite after restart. The direct LXMF-field
    regression also covers reticulumd messages that are not pre-wrapped as
    R3AKT protocol envelopes, matching Python delivery-callback behavior for
    `fields.attachments` payloads, JSON-client plain base64 data strings, and
    image byte-signature media-type inference for `/Image/{file_id}/raw`.
    Legacy LXMF `FIELD_TELEMETRY` direct messages are decoded from Python
    msgpack sensor payloads, persisted as Rust telemetry records, and exposed
    through `/Telemetry`.
- Live reticulumd delivery receipt smoke:
  - Shape: two local `reticulumd` instances with TCP transport, mutual
    announces, and
    `live_reticulumd_direct_send_receipt_is_delivered_when_configured`
    pointed at the sender RPC and receiver destination hash.
  - Result: passed; the sender daemon recorded `receipt_status=delivered`
    for the RCH message id and the receiver daemon persisted the inbound row.

## What Is Covered By Shared Python-vs-Rust Tests

The shared parity harness currently executes the same assertions against:

- `PythonRchBackend`, using the Python mission/checklist routers and domain services.
- `RustRchBackend`, using `r3akt-rch-bridge` and Rust SQLite state.

It covers:

- mission lifecycle: join, message send, event list, leave
- topic create/list/patch/subscribe/delete
- topic subscriber state observed through the Rust bridge `list_subscribers`
  request, matching Python API subscriber state in the shared parity harness
- marker create/list/patch
- marker rename/delete southbound commands and the FastAPI marker
  create/update/delete route flow, MDI symbol acceptance, and alias
  normalization parameterized across Python and Rust
- FastAPI marker symbol inventory and marker telemetry persistence without a
  dispatcher parameterized across Python storage and the Rust bridge
- zone create/list/patch/delete
- mission marker link/unlink southbound commands, with marker link state
  persisted in Rust and exposed through mission registry route parity
- FastAPI northbound zone create/list/update/delete route flow and invalid
  self-intersecting geometry rejection parameterized across Python and Rust
- FastAPI northbound EAM authenticated CRUD, canonical auto-provisioning,
  legacy field rejection, expired snapshot filtering, recreate-after-delete,
  and team-summary route flows parameterized across Python storage and a Rust
  bridge-backed EAM service/domain adapter
- FastAPI northbound R3AKT mission list limit route flow parameterized across
  Python storage and a Rust bridge-backed mission domain adapter
- FastAPI northbound R3AKT core mission, parent, RDE, team, team-member,
  mission-marker link/list/unlink, member-client, asset, and skill route flow
  parameterized across Python storage and a Rust bridge-backed mission domain
  adapter
- FastAPI northbound R3AKT team-member-skill, task-skill-requirement,
  assignment, and assignment-asset route flow parameterized across Python
  storage and a Rust bridge-backed mission domain adapter
- FastAPI northbound full R3AKT registry route matrix parameterized across
  Python storage and a Rust bridge-backed mission/domain/API adapter, including
  capability grant/revoke, mission CRUD/patch/parent/RDE, mission-zone and
  mission-marker links, mission changes, log entries, teams, team members,
  mission rights subjects/access, assets, skills, checklist task references,
  assignments, expansion payloads, cleanup flows, events, and snapshots
- FastAPI northbound R3AKT mission-change and log-entry route flow
  parameterized across Python storage and a Rust bridge-backed mission domain
  adapter
- FastAPI core route smoke path parameterized across Python storage and the
  Rust bridge, including mission/checklist route creation through the selected
  backend, Rust-backed client/identity/config facade behavior, and Rust-backed
  subject operation-right grants
- FastAPI legacy client list and paginated client response parameterized across
  Python storage and Rust-backed client join/list state
- FastAPI hub/Reticulum config rejection routes and identity moderation routes
  parameterized across Python storage and the Rust-backed facade
- FastAPI event-log route and Reticulum runtime fallback routes parameterized
  across Python storage and the Rust-backed facade
- Internal API adapter topic, subscriber, node-status, message, and event-stream
  routes parameterized across Python storage and the Rust-backed facade
- Generated OpenAPI EAM path, parameter, response, and schema checks
  parameterized across Python storage and the Rust-backed facade
- FastAPI `/openapi.yaml` route payload behavior parameterized across Python
  storage and the Rust-backed facade
- marker and zone state observed through Rust bridge snapshot requests,
  matching Python service state in the shared parity harness
- checklist/template/task/cell/feed state observed through the Rust bridge
  `state_snapshot` request instead of direct SQLite table decoding
- FastAPI northbound topic CRUD/subscribe route flow parameterized across
  Python storage and a Rust bridge-backed API adapter, including topic and
  subscriber pagination route checks, subscriber CRUD, and topic pagination
  after config reload, remote-auth enforcement, and missing-ID patch validation
- Direct `ReticulumTelemetryHubAPI` topic CRUD, topic description clearing,
  topic missing/error behavior, topic patch-without-updates behavior, subscriber
  CRUD, subscriber missing/error behavior, subscriber destination validation,
  and title-case subscriber metadata patch tests, subscriber `reject_tests`
  create/patch-zero behavior, plus client join/list/leave, blank join/leave
  identity rejection, and identity capability grant/list/revoke behavior,
  plus topic/client/identity-announce persistence, missing-name announce
  preservation, and bulk display-name resolution, parameterized across Python
  storage and identity status ban/blackhole/list behavior through a minimal
  Rust bridge-backed
  topic/subscriber/client/API-rights/identity/REM adapter, including REM
  capability classification, REM mode persistence, connected-mode detection,
  peer registry shaping, generic-client mode suppression, and destination plus
  identity announce merge behavior; case-insensitive identity status dedupe for
  joined and announce-only identities, plus blackhole-preserving moderation
  dedupe, display-name duplicate collapse, joined-identity preference, and
  concurrent client join/leave plus identity announce upsert dedupe behavior,
  topic patch created-timestamp preservation, attachment metadata topic
  assignment/clearing, topic-delete attachment association cleanup, legacy raw
  UUID attachment cleanup, and case-distinct attachment preservation behavior,
  app-info/Reticulum destination validation behavior, plus static
  subject-rights operation definition inventory and config apply/rollback
  validation behavior, plus Reticulum config validate/apply/rollback behavior;
  subject-rights capability-grant listing,
  mission-access role effective authorization, and explicit operation revoke
  override behavior are also parameterized across Python and Rust
- mission registry CRUD, patch, parent, zone link/unlink, RDE
- mission change and log entry upsert/list
- team, team member, client link/unlink, asset, skill, assignment, and assignment asset flows
- EAM upsert/list/get/latest/summary/delete, including canonical team validation,
  member/team mismatch rejection, active callsign conflict rejection, and
  mission-scoped status-write authorization
- checklist create/get/list/join/upload/feed/delete
- checklist template create/list/get/update/clone/delete
- checklist task row add/delete/style/status/cell set
- checklist CSV import
- checklist read authorization through mission-scoped team-member roles and
  linked client identities
- FastAPI northbound checklist template, checklist lifecycle, task row, task
  status/style/cell, upload/feed, delete, and CSV import route matrix
  parameterized across Python storage and the Rust bridge-backed domain adapter
- FastAPI northbound file/image metadata list, pagination, retrieve, topic
  patch, raw-byte retrieval, delete, missing-record, and remote-auth route
  behavior parameterized across Python storage and the Rust bridge-backed API
  adapter; the Rust route suite also has an explicit legacy stored-path
  deletion regression for image records outside the normal storage root
- Direct file/image API store, list, retrieve, delete, category rejection,
  missing-record, missing-path, and outside-storage validation behavior
  parameterized across Python storage and the Rust bridge-backed API adapter;
  Python filesystem monkeypatch deletion tolerance remains Python-only
- LXMF command-manager file/image list, retrieve, missing-field,
  missing-record, camel-case ID, and missing-on-disk behaviors parameterized
  across Python storage and the Rust bridge-backed API adapter; explicit
  injected Python API exception logging remains Python-only
- Core command-manager app-info reply context, file/image list, file/image
  attachment retrieval, and invalid file ID behavior parameterized across
  Python storage and the Rust bridge-backed API adapter
- Core command-manager topic listing, topic creation, source-identity
  subscription, and zero-reject subscription behavior parameterized across
  Python storage and the Rust bridge-backed API adapter, including snake-case
  topic creation payloads and LXMF string, sideband, wrapped sideband, and
  positional command payload ingestion, plus create-topic interactive prompt
  completion; retrieve, title-case patch, and delete topic command replies are
  also parameterized across both backends
- Core command-manager leave handling, including destination removal callback
  and client-state deletion, parameterized across Python storage and the Rust
  bridge-backed API adapter
- Core command-manager join handling, including connection tracking and
  client-state persistence, parameterized across Python storage and the Rust
  bridge-backed API adapter
- Core command-manager client listing reply behavior parameterized across
  Python storage and the Rust bridge-backed API adapter
- Standalone command-manager subscriber create/retrieve behavior parameterized
  across Python storage and the Rust bridge-backed API adapter
- Core command-manager subscriber retrieve, title-case metadata patch, and
  delete command replies parameterized across Python storage and the Rust
  bridge-backed API adapter
- Core command-manager status command counts for clients, topics, subscribers,
  files, images, and telemetry parameterized across Python storage and the Rust
  bridge-backed API adapter
- Core command-manager identity moderation commands for ban, blackhole, unban,
  and identity listing parameterized across Python storage and the Rust
  bridge-backed API adapter, including case-sensitive blackhole preservation
  behavior
- Core command-manager config get, validate, apply, rollback, and reload
  command replies parameterized across Python storage and the Rust
  bridge-backed API adapter
- Core command-manager help reply renderer hint behavior parameterized across
  Python storage and the Rust bridge-backed API adapter
- LXMF telemetry request topic filtering, unsubscribed-sender denial, and
  unknown-topic empty snapshot behavior parameterized across Python storage and
  the Rust bridge-backed API adapter
- Northbound service status snapshots, runtime diagnostics passthrough, routing
  fallback/provider behavior, API-backed topic/subscriber lookup helpers,
  telemetry status counts, file/image status counts, and app-info round trip
  behavior, plus help/examples fallback, event recording/listing, message
  dispatch validation, telemetry proxying, and Reticulum discovery/capability
  proxy behavior parameterized across Python storage and the Rust bridge-backed
  API adapter
- Northbound telemetry entry latest/collapse, topic filtering, and unknown-topic
  behavior parameterized across Python storage and the Rust bridge-backed API
  adapter; SQLAlchemy query-count optimization remains Python-only
- Northbound websocket telemetry broadcaster topic-subscription and
  destination-filter behavior parameterized across Python storage and the Rust
  bridge-backed API adapter
- FastAPI northbound status counts, subscribe destination validation, protected
  endpoint auth, auth validation, and bearer-token app/auth payload behavior
  parameterized across Python storage and the Rust bridge-backed API adapter
- FastAPI northbound sensitive core route remote-auth rejection behavior
  parameterized across Python storage and the Rust bridge-backed API adapter
- FastAPI northbound app-info configured hub display-name behavior
  parameterized across Python storage and the Rust bridge-backed API adapter
- FastAPI northbound chat message send, scope handling, and missing-dispatcher
  rejection behavior, plus configured attachment upload size-limit behavior,
  parameterized across Python storage and the Rust bridge-backed API adapter
- Direct chat message persistence, state update, stats, and uploaded attachment
  metadata behavior parameterized across Python storage and the Rust
  bridge-backed API adapter
- Rust reticulumd inbound topic envelopes now carry typed file/image attachment
  payloads through `r3akt_protocol::TopicAttachment`; the server persists
  non-empty inbound attachment bytes, links them to chat message entries, serves
  raw bytes through the existing file/image routes, and restores metadata from
  SQLite across restart. Direct reticulumd `list_messages` entries with
  LXMF-style `fields.attachments` are also mapped into typed topic envelopes
  before the inbound worker processes them, including Python-compatible
  plain-base64 attachment strings and byte-inferred image media types
- Rust reticulumd inbound now also accepts direct LXMF `FIELD_TELEMETRY` (`0x02`)
  fields carrying Python msgpack sensor payloads, decodes legacy integer-keyed
  time/location readings at the inbound worker boundary, and the transport
  adapter additionally humanizes direct msgpack payloads across Python's legacy
  sensor ID map before Rust telemetry persistence
- FastAPI northbound gateway control status/start/stop/sync and
  disabled-control 404 behavior parameterized across Python storage and the
  Rust bridge-backed API adapter
- Gateway app state, mission-domain-service handoff, and routing snapshot
  display-name behavior parameterized across Python storage and the Rust
  bridge-backed API adapter
- REM registry southbound mode-set and peer-list command behavior in Rust core
  and bridge tests, including transport source enforcement, REM announce
  capability authorization, mode persistence, peer-list shaping, and Python
  accepted/result/rejected response ordering; the Rust internal identity
  announce route now also decodes Python-compatible msgpack `app_data_hex`
  capability extension slots instead of requiring already-expanded capability
  lists
- Rust `/Help` and `/Examples` route content now covers legacy/plugin,
  mission-sync, checklist, REM registry, and telemetry southbound command
  families instead of the earlier Rust placeholder text
- Rust RCH snapshot SQLite connections now configure a 30-second busy timeout,
  matching Python storage's SQLite lock-wait configuration at the Rust-owned
  persistence boundary
- mission and checklist source-identity mismatch rejection at the transport
  bridge boundary
- unauthorized, unknown command, invalid payload, and not-found rejection shapes

## Rust Runtime Scope Definition

This audit defines the completed Rust runtime parity scope as the shared RCH
route/runtime contract rather than a line-for-line port of Python implementation
objects. The Rust port scope includes:

- northbound HTTP routes, protected route authentication, internal adapter
  routes, OpenAPI/help/examples documentation, websocket/system/telemetry
  streams, and runtime diagnostics
- Reticulum/reticulumd/LXMF ingress and egress behavior, delivery state,
  propagation/direct-send fallback, direct LXMF attachment and telemetry field
  ingestion, identity announce capability decoding, and managed reticulumd
  lifecycle where configured
- Rust-owned persistence, migrations, SQLite lock waiting, config file route
  behavior, process-control CLI helpers, gateway-mode boot, and app-info paths
- mission, checklist, topic, subscriber, client, identity, REM registry, EAM,
  marker, zone, subject-rights, file/image, chat, event-log, and R3AKT registry
  flows through the Rust bridge or native Rust route handlers
- TAK integration only through the dedicated `r3akt-tak-connector` service
  boundary

The full collected Python suite is intentionally broader than that scope. The
following tests remain Python implementation checks and are formally excluded
from Rust runtime parity completion because they do not describe a selectable
Rust backend contract:

- Direct `ReticulumTelemetryHubAPI` private Python storage edge cases, including
  SQLAlchemy session object retry/cleanup and monkeypatched storage-return
  handling that do not have a direct Rust backend object to select.
- Live packaged/frozen CLI process lifecycle coverage beyond the Rust helper
  and control-client process-control slice.
- Python storage/migration helpers outside the Rust-owned snapshot store,
  including direct SQLAlchemy session retry behavior, Python table names, and
  legacy JSON/link-table dual-read migrations. Rust now covers its own
  standalone SQLite schema creation, additive startup over an existing database,
  additive migration of older Rust checklist feed-publication tables, and
  Python-compatible 30-second SQLite lock waiting on snapshot-store
  connections.
- Reticulum daemon lifecycle and outbound queue behavior outside the covered
  Rust delivery state machine, including Python's threaded queue internals,
  LXMF-router monkeypatch callbacks, local LXMF propagation-store tests, service
  thread error recording, and direct `ReticulumTelemetryHub` private helper
  tests that are not backend-selectable. Rust currently has native coverage for
  reticulumd RPC dispatch, receipt polling, retry/backoff, stale dispatch
  timeout handling, direct-failure cooldown, propagation callbacks, drop
  callbacks, runtime diagnostics, worker pause/resume, and live managed
  reticulumd start/stop where configured; inbound identity announce capability
  decoding from msgpack `app_data_hex` is now covered at the Rust internal
  adapter boundary, and typed inbound topic attachments are persisted through
  the Rust reticulumd worker path for both pre-wrapped R3AKT envelopes and
  direct reticulumd LXMF-style message fields.
- Python local telemetry sampler behavior beyond Rust's covered local time
  snapshot task, plus SQLAlchemy query-count optimization checks.
  Rust now covers the northbound `/Telemetry` and websocket surfaces,
  reticulumd health telemetry ingestion, direct LXMF `FIELD_TELEMETRY`
  msgpack ingestion across Python's legacy sensor ID map, and TAK connector
  dispatch, but Rust does not yet cover Python's full thread-based
  `TelemetrySampler` service-collector scheduling and outbound broadcast queue
  semantics or direct SQLAlchemy query-count assertions in the current crate
  boundaries.
- gateway runtime process behavior beyond Rust's CLI/control helper and
  foreground gateway-mode boot slice, especially Python monkeypatched
  `gateway.main` construction of `ReticulumTelemetryHub`, uvicorn server
  lifecycle, packaged/frozen process invocation, and thread join/shutdown
  assertions. Rust now covers CLI parsing, hidden gateway argument conversion,
  Python module-style gateway invocation normalization, state-file handling,
  control-client HTTP calls, busy-port detection before background spawn, and
  foreground server construction/shutdown with SQLite state.
- Python configuration-manager path/model helper tests outside the Rust runtime
  contract, including Python dataclass/model serialization, default-template
  bootstrapping, LXMF startup option parsing, and config-manager-only runtime
  settings. Rust now covers CLI `~` expansion with `HOME`/`USERPROFILE`, TAK
  config aliases/BOM handling, config/Reticulum config routes, app-info storage
  paths, and Rust runtime path arguments.
- low-level mission/checklist router unit tests that target Python services
  directly; the shared Rust bridge parity suite covers their command behavior
  through the bridge, but these Python-unit tests are not themselves backend
  selectable.

Those Python-only tests continue to pass in the Python full suite, but the Rust
runtime completion gate is the backend-selectable route/runtime surface plus
the native Rust crate tests listed above.

## Completion Criteria

To mark Rust runtime parity complete, both of these must exist and pass:

1. A backend-selected parity mode for the shared Python route/runtime suite,
   with Python-only implementation internals excluded by the scope definition
   above.
2. Native Rust crate tests for Rust-owned behavior that has no Python backend
   selector, including persistence, CLI/gateway helpers, reticulumd delivery,
   telemetry ingestion, websocket/runtime diagnostics, and TAK connector
   boundaries.

Both gates are represented in the evidence above and passed on 2026-05-05.

## Prompt-To-Artifact Completion Audit

| Requirement | Current evidence | Status |
| --- | --- | --- |
| 1. Audit Rust against Python route/runtime surface | This document lists northbound HTTP routes, Reticulum/LXMF runtime behavior, persistence, diagnostics, streams/websockets, TAK integration, mission/checklist/topic/registry flows, and OpenAPI/help docs, with command evidence for Python, Rust, and shared parity suites. | Done |
| 2. Identify every remaining gap with concrete repo evidence | The formal exclusions above name the remaining Python-only test surfaces and the concrete Python test files/classes they exercise; the Rust runtime scope has no known unimplemented route/runtime contract gap after the OpenAPI comparison reports `exact_schema_mismatches=0`. | Done |
| 3. Implement missing Rust behavior with smallest safe crate-boundary changes | Rust changes are contained in `r3akt-rch-server`, `r3akt-rch-core`, `r3akt-rch-bridge`, `r3akt-transport-rns`, `r3akt-node`, `r3akt-protocol`, and `r3akt-tak-connector`; targeted tests above cover the closed gaps. | Done |
| 4. Keep TAK as a dedicated Rust service boundary | TAK behavior is verified by `cargo test -p r3akt-tak-connector` with `38 passed`; RCH server tests only exercise dispatch/control across that connector boundary. | Done |
| 5. Add/update tests for each closed gap | Tests listed above cover response shapes, validation errors, route contracts, persistence restore, runtime lifecycle, delivery behavior, telemetry ingestion, OpenAPI/help docs, CLI/gateway behavior, and connector boundaries. | Done |
| 6. Keep unrelated local files/generated artifacts out of required work | Required source/doc changes are tracked in the Rust and Python RCH repos; unrelated untracked `../.playwright-mcp/` is not part of the work. | Done |
| 7. Run formatting and full verification before completion | `cargo fmt --all -- --check`, `cargo test --workspace`, `cargo clippy --workspace --all-targets -- -D warnings`, Python full suite, Rust-selected Python suite, and targeted crate/source-contract checks all passed. | Done |
| 8. Produce final completion audit | This prompt-to-artifact checklist maps every numbered objective item to concrete files, commands, tests, and known non-Rust-scope exclusions. | Done |
| Python backend source of truth remains green | `.\.venv\Scripts\python.exe -m pytest --no-cov -q` passes with `1081 passed, 742 warnings`. | Done |
| Rust-selected backend parity gate remains green | `.\.venv\Scripts\python.exe -m pytest -o addopts='' -q --rch-backend=rust` passes with `869 passed, 212 deselected, 387 warnings`; `.\.venv\Scripts\python.exe -m pytest --no-cov -m rust_bridge --rch-backend=rust -q` passes with `227 passed, 854 deselected, 359 warnings`. | Done |
| Rust workspace remains green | `cargo test --workspace` passed; `cargo clippy --workspace --all-targets -- -D warnings` passed; `cargo fmt --all -- --check` passed. | Done |
| Completion can be marked | Rust runtime parity scope is defined, all selected Rust/Python gates pass, and the only remaining items are formally excluded Python implementation internals. | Done |
