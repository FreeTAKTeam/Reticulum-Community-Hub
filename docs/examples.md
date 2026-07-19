# RCH examples

These examples target the Rust 3.0 preview server while preserving the Python
2.9.x northbound route and envelope contract. Commands use Bash syntax; in
PowerShell, set equivalent variables and use `Invoke-RestMethod` if preferred.

## Start a local server

Build and run an HTTP-only development instance:

```bash
cargo build -p r3akt-rch-server
cargo run -p r3akt-rch-server -- \
  --bind 127.0.0.1:8080 \
  --api-key change-this-preview-key \
  --db-path ./rch-runtime.db \
  --config-path ./config.ini \
  --reticulum-config-path "${RCH_RETICULUM_CONFIG:-$HOME/.reticulum/config}"
```

Use a strong unique API key for non-loopback access. The desktop shell binds
only to loopback and therefore does not embed a default credential.

```bash
export RCH_URL=http://127.0.0.1:8080
export RCH_KEY=change-this-preview-key
```

## Authenticate and inspect runtime state

Loopback requests are trusted for compatibility. Remote clients send either
`X-API-Key` or `Authorization: Bearer`:

```bash
curl -H "X-API-Key: $RCH_KEY" "$RCH_URL/api/v1/auth/validate"
curl -H "Authorization: Bearer $RCH_KEY" "$RCH_URL/Status"
curl -H "X-API-Key: $RCH_KEY" "$RCH_URL/diagnostics/runtime"
```

Five failed attempts within five minutes lock only that client and auth
surface for five minutes. A locked HTTP client receives `429` and
`Retry-After: 300`. Unexpected server errors contain a generic detail and an
`X-Request-ID`; use that identifier to find the corresponding server log.

## Topics

```bash
curl -X POST -H "X-API-Key: $RCH_KEY" -H 'Content-Type: application/json' \
  -d '{"TopicID":"ops","TopicName":"Operations","TopicPath":"ops","TopicDescription":"Operational traffic"}' \
  "$RCH_URL/Topic"

curl -H "X-API-Key: $RCH_KEY" "$RCH_URL/Topic"
curl -H "X-API-Key: $RCH_KEY" "$RCH_URL/Topic?id=ops"
```

## Direct, topic, and broadcast chat

Direct messages require an LXMF destination. Topic and broadcast delivery use
the current roster and subscription state.

```bash
curl -X POST -H "X-API-Key: $RCH_KEY" -H 'Content-Type: application/json' \
  -d '{"Content":"Radio check","Scope":"dm","Destination":"<lxmf-destination>"}' \
  "$RCH_URL/Chat/Message"

curl -X POST -H "X-API-Key: $RCH_KEY" -H 'Content-Type: application/json' \
  -d '{"Content":"Team update","Scope":"topic","TopicID":"ops"}' \
  "$RCH_URL/Chat/Message"

curl -X POST -H "X-API-Key: $RCH_KEY" -H 'Content-Type: application/json' \
  -d '{"Content":"Broadcast update","Scope":"broadcast"}' \
  "$RCH_URL/Chat/Message"

curl -H "X-API-Key: $RCH_KEY" "$RCH_URL/Chat/Messages?limit=50"
```

Accepted delivery is not the same as a final receipt. Inspect the returned
delivery metadata and `/diagnostics/runtime` for queued, dispatched,
propagated, delivered, failed, or unavailable component states.

## Files and images

Upload an attachment, associate it with a topic, and list stored files:

```bash
curl -X POST -H "X-API-Key: $RCH_KEY" \
  -F category=file -F topic_id=ops -F file=@./report.txt \
  "$RCH_URL/Chat/Attachment"

curl -H "X-API-Key: $RCH_KEY" "$RCH_URL/File"
curl -H "X-API-Key: $RCH_KEY" "$RCH_URL/File/1/raw" --output downloaded-report.txt
```

Use `category=image` for images. The maximum chat attachment size is 8 MiB.

## Missions and checklists

The OpenAPI document is the canonical request-schema reference. Begin by
discovering the current records and role/operation metadata:

```bash
curl -H "X-API-Key: $RCH_KEY" "$RCH_URL/api/r3akt/missions"
curl -H "X-API-Key: $RCH_KEY" "$RCH_URL/api/r3akt/checklists"
curl -H "X-API-Key: $RCH_KEY" "$RCH_URL/openapi.json" --output rch-openapi.json
```

Mission and checklist writes retain the established Python-compatible success
and error envelopes. Use stable caller-generated UIDs for offline retry and
deduplication.

## WebSockets

Connect to one of the streams and immediately send an auth message:

```text
ws://127.0.0.1:8080/events/system
ws://127.0.0.1:8080/telemetry/stream
ws://127.0.0.1:8080/messages/stream
```

```json
{"type":"auth","data":{"api_key":"change-this-preview-key"}}
```

Clients should answer server pings, reconnect with backoff, and refresh
canonical HTTP state after a lag or dropped-oldest diagnostic event.

## Reticulum and LXMF

Start an LXMF-rs `reticulumd` with its ZeroMQ pipeline enabled, then point RCH
at its command and response sockets:

```bash
cargo run -p r3akt-rch-server -- \
  --bind 127.0.0.1:8080 \
  --db-path ./rch-runtime.db \
  --lxmf-zmq-command tcp://127.0.0.1:9100 \
  --lxmf-zmq-response tcp://127.0.0.1:9101 \
  --reticulumd-source <local-lxmf-destination>
```

ZeroMQ is the mandatory delivery data plane. RPC is control-only. Verify the
actual socket attachment and worker/process state:

```bash
curl -H "X-API-Key: $RCH_KEY" "$RCH_URL/diagnostics/runtime"
```

Use `scripts/local-reticulum-live-gate.ps1` for multi-node receipt, fanout,
event-poll, and load validation against the sibling LXMF-rs checkout.

## TAK sidecar

TAK is an independent service and does not share the RCH server socket
lifecycle:

```bash
cargo run -p r3akt-tak-connector --bin r3akt-tak-service -- --help
```

Configure its RCH base URL and TAK TCP, UDP, or TLS target according to the
printed options. Validate real external infrastructure only with explicit
`R3AKT_TAK_LIVE_COT_URL` and `R3AKT_TAK_LIVE_INBOUND_COT_URL` values; do not
copy deployment endpoints or credentials into repository configuration.
