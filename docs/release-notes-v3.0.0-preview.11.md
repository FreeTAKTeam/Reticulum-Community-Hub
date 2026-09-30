# RCH Rust v3.0.0-preview.11 release notes

This candidate updates the Rust product line to LXMF-rs 0.12.0 and corrects
confirmed authorization, persistence, attachment, UI and TAK defects. It remains
preview software. Python 2.9.x maintenance continues on `rch-python`.

## Runtime baseline

The library dependencies and packaged daemon use LXMF-rs `v0.12.0`, commit
`20717f4456d1b402bcc3cb7e8a1a3a86c9bb4755`. The daemon is built with
`zmq-pipeline-rpc`; RCH requires SDK configuration version 2 and contract release
`v2.6`. Rust library builds resolve the immutable Git revision without a sibling
checkout. Local daemon development still uses the documented sibling layout.

## Operator-visible changes

- Protected HTTP, internal bridge routes and WebSocket streams require configured
  credentials, including on loopback. Credential-free setup is limited to a
  trusted local first run. Setup-status responses expose readiness without secret
  values or configuration paths. Existing legacy password records migrate
  atomically to salted Argon2 hashes after successful authentication.
- Browser origins are checked against the listening authority and explicitly
  configured `RCH_ALLOWED_ORIGINS`. Remote UI connections require HTTPS/WSS;
  local loopback HTTP/WS remains supported. UI requests, caches and preview URLs
  are invalidated when the connection identity changes.
- Uploads accept one file up to 8 MiB, with bounded metadata and total request
  size. Only recognized raster image signatures are served inline. Other content,
  including HTML/SVG and spoofed types, downloads as an octet stream with safe
  response headers. Rejected persistence leaves no published attachment.
- Domain writes reserve SQLite before reading and publish projections after
  commit. Failed writes preserve the previous live state. Stale dispatch
  completions and failure callbacks cannot overwrite an accepted delivery
  receipt; weaker propagation acknowledgements cannot downgrade confirmed
  delivery. Moderation, roster and attachment changes survive the tested restart
  paths without false-success cache changes. Legacy roster aliases are coalesced
  during join/leave, preventing stale whitespace/case variants from reappearing.
- Terminal shutdown wakes and joins owned workers before SDK and daemon cleanup.
  A timed-out blocking delivery tick remains owned until it finishes, preventing
  overlapping ticks. `/Control/Stop` remains a resumable pause.
- TAK TLS validates certificates and hostnames by default. TCP/TLS receivers
  retain partial XML frames across poll timeouts and separate coalesced events.
  Truncated, malformed and oversized frames report errors and reset the stream.
  The service retains bounded pending work through transient bridge failures,
  checks cancellation between sends and reports partial-send counts correctly.
- TAK marker retries supply an optional `Idempotency-Key`. With SQLite enabled,
  marker creation and its original response commit together; a retry receives the
  same 201 response without duplicate activity. Reusing a key with a different
  normalized payload returns 409. Requests without the header retain their
  existing creation behavior.

## Upgrade and deployment

Use the [README runtime commands](../README.md#getting-started) and
[operations guide](operations-and-troubleshooting.md). Existing deployments
must supply a configured credential for protected routes and internal adapters.
For a separately hosted UI or TLS proxy, configure exact browser origins without
paths or wildcards. The server does not infer trust from forwarded addresses.

Private TAK authorities require `R3AKT_TAK_TLS_CA`; client authentication supports
PEM certificate/key pairs or the documented PKCS#12/PFX identity configuration.
Explicit `R3AKT_TAK_TLS_INSECURE=true` disables verification and emits a warning;
it is intended for deliberate local diagnostics. Remote northbound TAK bridge
URLs require HTTPS, while loopback HTTP is supported.

## Evidence and limits

The [candidate stabilization report](stabilization-v3.0.0-preview.11.md) records
current checks and package/runtime evidence: 682 workspace tests and 136 UI tests
passed, the real three-daemon load delivered 500 of 500 messages, and the extracted
package passed authenticated setup, daemon recovery and durable restart checks.
The report records the local checkpoint before PR creation. Hosted qualification,
review follow-ups and published assets are recorded on
[PR #239](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/239) and the
versioned GitHub release; historical evidence in earlier reports does not qualify
this version.

The TAK service queue, recent-key history and identity-directory component are
process-local. Socket DNS uses the platform resolver; the socket I/O deadline
does not cancel DNS. Inbound TAK protobuf is explicitly unsupported; outbound
TAK Protocol v1 encoding remains supported. A committed mutation's subsequent
notifications are observable best-effort operations, not a durable distributed
outbox. Python servers that ignore the optional marker header cannot guarantee
its durable replay behavior.

The Linux desktop bundle was built and inspected, but its native window workflow
remains implemented but unproven in this run. External TAK, REM phone/deck hardware
and Windows/macOS/ARM package acceptance require their own evidence. Local
software gates do not establish those results or stable v3.0.0 readiness.
