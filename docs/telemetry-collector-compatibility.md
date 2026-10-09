# Numeric telemetry collector compatibility

This is the RCH implementation follow-up to [issue #260](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/260).
[Issue #258](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/258)
retains the broader compatibility diagnosis and live acceptance evidence;
[issue #259](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/issues/259)
is the subsequent extraction handoff.

## Request and authorization contract

LXMF field `0x09` accepts numeric application command `1` as `{1: seconds}`
or `{1: [seconds, collector_flag]}`. At the SDK JSON boundary these become
string keys (`"9"`, `"1"`); the named field alias and `"0x09"`/`"0x01"` aliases
are also recognized. Seconds must be a non-negative number before year 10000;
fractional seconds are truncated as in Python. The flag must be boolean and is
ignored for response selection, matching the preserved Python collector.

Every entry is inspected. Existing `command_type`, `Command`, and `0` command
selectors retain their mission/plugin dispatch. Empty lists, non-object entries,
invalid arguments and ambiguous collector/mission selectors produce indexed
diagnostics without argument values, message content or identity hashes.
Unknown numeric commands are unsupported rather than malformed. REM's compact
`t`/`a` commands are explicitly unsupported here; their decoding remains tracked
by [REM #267](https://github.com/FreeTAKTeam/reticulum_mobile_emergency_management/issues/267)
and [REM #276](https://github.com/FreeTAKTeam/reticulum_mobile_emergency_management/issues/276).

The approved compatibility policy is:

- Without TopicID, the collector returns the global snapshot, as Python does.
- With TopicID (in the command or outer fields), the topic must exist and the
  verified LXMF sender must be a subscriber. Only that topic's subscriber
  destinations are eligible. An explicit command topic takes precedence.
  Invalid topic types are rejected rather than converted into a global query.
- Banned/blackholed inbound senders remain rejected. Banned/blackholed peers and
  peers outside the configured outbound identity allowlist are excluded.
- Valid field `0x02` uploads are processed before commands. Malformed or
  unsupported command metadata gets a separate durable diagnostic; it does not
  discard valid telemetry. Each independently valid command is dispatched.
- Historical bootstrap stores uploads but does not execute queries or commands.

## Response and persistence

A query selects the latest persisted location-bearing snapshot per peer with
`timestamp >= seconds`. Its response field `0x03` is a **plain array** of
`[peer_hash_bytes, timestamp_seconds, packed_telemeter_bytes, optional_appearance]`.
Appearance is currently `null`. Field `0x0D` describes the collector response,
including `entry_count` and `unavailable_records`.

New uploads preserve their original packed Telemeter alongside decoded readings
in an optional persistence field. Existing rows still decode with that field
absent. As explicitly requested, older humanized-only records are omitted and
reported unavailable; sensor bytes are not invented. Clients must upload fresh
packed telemetry to make those records eligible. HTTP/map projections continue
to use the decoded readings without exposing the packed persistence field.

The fields map is encoded once using numeric keys and MessagePack binary types,
then passed through the pinned SDK's `_lxmf_fields_msgpack_b64` transport wrapper.
The wrapper is removed by reticulumd when building the LXMF message; it is not an
application wire field. Encoding the field 3 list itself as binary would break
this contract.

Upload persistence, query diagnostics, logical-input deduplication, and outbound
reply intent staging share the inbox application transaction. Replies survive
restart and repeated broker delivery does not create duplicate intents. Command
entry count is bounded at 256; collector reads are bounded at 1024 candidates
and packed sensor data at 1 MiB. Exceeding a snapshot bound returns an explicit `unavailable` reply and records a
diagnostic; it does not truncate the stream or block later inbox work. Actual
storage/outbox backpressure still retains work for retry.

## Reusable evidence and remaining acceptance

Synthetic fixtures live in `crates/r3akt-transport-rns/tests/fixtures/`.
`field_commands` tests cover scalar/list requests, aliases, all entries, invalid
values, privacy-safe diagnostics, plugins, missions, and REM classification.
The durable collector tests cover upload/query, persistence/map-readable
location, topic isolation/denial, restart, logical replay, multiple replies,
mixed malformed/unsupported metadata, and unavailable old records.

`python3 scripts/check-telemetry-collector-fixture.py` independently verifies the
response fixture with Python MessagePack, including binary entry members and
numeric packed sensor keys. Rust tests compare generated replies to those
independent fixture bytes. This is structural compatibility evidence, not an
executed Columba/Sideband application session.

Local validation on 2026-10-09 passed locked workspace tests (713 passed,
2 explicitly ignored), strict workspace/all-target Clippy, formatting, module
size, documentation links, and the independent Python fixture check. Conditional
live tests that return early without configured infrastructure do not establish
live acceptance. The four backend package suites are also checked separately.

The request format is referenced by the pinned
[Columba v2.2.6 sender](https://github.com/torlando-tech/columba/blob/a402ed1052ba6993454352ce51ddfc336b729d9f/rns-backend-py/src/main/kotlin/network/columba/app/rns/backend/py/PythonRnsTelemetry.kt#L107-L140)
and the preserved Python collector on `origin/rch-python`. The production issue
comment records preview.19 RCH and daemon versions and confirms the real packet's
numeric-command/list/boolean key/type structure. It does not provide an exact
client version.

Before closing live acceptance, record the installed RCH commit, daemon revision,
Columba and Sideband versions, and transport path. Exercise fresh upload → durable
persistence → normal map projection → authorized query → response decoded by both
clients, including denial for an unsubscribed topic. Keep #258's broader criteria
open until that evidence exists; link verified results there before #259 handoff.
