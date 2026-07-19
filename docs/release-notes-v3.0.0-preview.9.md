# RCH Rust v3.0.0-preview.9 release notes

This prerelease fortifies the Rust 3.0 product line for broader evaluation.
Python 2.9.x remains the maintenance line on `rch-python`.

## Highlights

- Argon2id PHC password and kill-switch PIN storage with transparent migration
  from legacy preview hashes.
- Per-client authentication throttling with five-minute lockouts and explicit
  HTTP `429`/`Retry-After` responses.
- Sanitized unexpected 500 responses with `X-Request-ID` log correlation.
- Correct UI API error-body handling plus a required Vue/TypeScript type-check.
- Safer Tauri sidecar lifecycle handling without an embedded desktop API key.
- Workspace coverage for `r3akt-identity` and a maintained Rust ingest example;
  retired prototype crates and broken examples are gone.
- Expanded `/Examples`, a complete examples guide, and current operations and
  troubleshooting guidance.
- Stronger Rust 1.85 server-workspace MSRV, Rust 1.88 desktop/release, rustdoc,
  audit, UI, packaging, and release-readiness gates.

## Compatibility

No REST or WebSocket route was removed or renamed. Python-compatible response
envelopes remain the target. Existing databases upgrade password/PIN hashes
automatically after successful authentication.

ZeroMQ remains mandatory for southbound LXMF delivery; RPC is control-only.

## Validation and artifacts

See the [preview.9 stabilization report](stabilization-v3.0.0-preview.9.md) for
the final local, hosted, live-runtime, and published-asset evidence. Release
archives embed `v3.0.0-preview.9`, the exact tag/commit, the LXMF-rs baseline,
and SHA-256 metadata.

## Known boundaries

- This is preview software, not stable `v3.0.0`.
- External TAK and REM phone/deck checks depend on available infrastructure and
  are disclosed separately when unavailable.
- The Linux desktop inherits GTK3 maintenance and `glib` audit notices from the
  current Tauri runtime; RCH does not use the warned `VariantStrIter` API.
- Operators should verify `/Status`, `/diagnostics/runtime`, processes,
  listeners, and live ZeroMQ attachment for each deployment.
