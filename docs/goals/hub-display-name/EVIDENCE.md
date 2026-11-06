# Issue #294 validation evidence

Date: 2026-11-03. Base: `c2bf78a`; working branch: `corvo/fix-294-hub-name`.

The server now owns the service name in `rch_settings.hub_name`. Startup and
reload reconcile legacy INI aliases; setup, config renames and rollback update
the same name and announce path. App-info and setup status share that resolver.
The daemon's own identity/name remains separate.

## Automated evidence

The focused regressions exercise:

- Saved-name precedence over conflicting legacy INI names, independent of line
  order; fallback migration from name/display_name/RCH.
- Reconciliation across reconstructed AppState instances and reinstalled
  conflicting configuration defaults, preserving existing identity bytes.
- BOM-prefixed Windows configuration, quoted names and spaced section headers.
- Rename through either alias, equal edits, competing edits, absent/unchanged
  aliases, blank/overlong names and colon-separated INI values.
- File restoration after SQLite rejects a name save.
- HTTP setup, config save, reload, rollback and concurrent renames over the real
  pinned SDK/RPC daemon fixture, including automatic announcement metadata.
- Failed announce preserving the desired name, visible diagnostics, retry via
  ReloadConfig, and setup enrollment succeeding with publication pending.
- Unchanged private-key bytes, identity hashes and delivery destination hashes.
- Existing setup security/atomic-enrollment regressions, updated to require both
  name mirrors. Invalid configuration is rejected before backup creation.

Rust 1.99.1 and locked, offline dependencies were used. The local `cc` is a Zig
wrapper that misses the installed OpenSSL multiarch headers; setting
`CC=/usr/bin/gcc` uses the installed headers without adding dependencies.

Checks completed:

- `cargo +1.99.1 fmt --all -- --check`: passed.
- `CC=/usr/bin/gcc cargo +1.99.1 clippy --workspace --all-targets --locked --offline -- -D warnings`: passed.
- Server library: 338 passed, 2 intentionally ignored; main binary: 30 passed;
  the server integration suites also passed.
- All five new hub-name tests, both focused config/setup regressions and all 17
  existing release-security tests passed.
- Default-parallel workspace execution: 738 passed, 1 failed, 2 ignored before
  Cargo stopped. The unchanged transport test
  `issue_238_event_poll_waits_for_delayed_identity_restoration` hit its 400 ms
  initial ZeroMQ negotiation deadline twice. No transport source was changed.
- `cargo ... test -p r3akt-transport-rns --lib -- --test-threads=1`: all 64 passed.

A reduced-concurrency run encountered SQLite I/O errors while using the host's
16 GiB `/tmp` tmpfs. The final run uses `RUST_TEST_THREADS=4` and a dedicated
`TMPDIR` under the evidence directory on the main disk. It passed: 756 tests,
zero failures, two intentionally ignored live/performance qualifications. No unrelated transport or core code was changed to adjust
the environment-sensitive tests.

## Isolated real-network evidence

Two real `reticulumd` processes communicated through explicitly configured
loopback TCP interfaces. The daemon was built directly from the workspace's
pinned LXMF-rs revision `888355c580932f886cfbf9f7076758b065a69879`, separately
from the newer sibling checkout. RCH used its real ZeroMQ SDK endpoints.
Only disposable databases, configuration and identities were used.

Archived artifacts: `/home/pgiuseppe/rch-issue294-evidence/20261103/live/`.
The directory includes `harness.py`, `result.json`, process logs and disposable
database/configuration artifacts. The result records binary checksums, runtime
diagnostics, the service destination, identity-file checksum and received
announce records with raw application data.

The remote daemon received these distinct records for destination
`cb47553b6862de0b1c5a9e971c4fa352`:

| Operation | Received name | Remote record timestamp | Record suffix |
| --- | --- | --- | --- |
| Legacy migration/connectivity | Legacy Hub | 1793734867 | 1 |
| First-run setup | Live Initial Hub | 1793734874 | 3 |
| Edit only display_name through PUT /Config | Live Renamed Hub | 1793734881 | 4 |
| Restart after replacing INI with conflicting upgrade defaults | Live Renamed Hub | 1793734888 | 5 |

`name_source` was `delivery_app_data`; the received capabilities remained
`r3akt`, `emergencymessages`, `telemetry`. Manual announces were used only to
establish initial connectivity. Subsequent setup, rename and restart announces
were automatic. Restart evidence explicitly excluded every pre-restart announce
ID, so an old cached row could not satisfy the check. Setup/app-info agreed
after restart. Identity-file SHA-256 remained
`e1bb90ab9f118ebdd0ae444d3aa430f25d97fa028a5e0c772e6340586029ce5c`.
All owned processes shut down successfully.

The archived live result's server and daemon SHA-256 values were checked against
the final rebuilt binaries after the validation-before-backup fix.

Operations were separated by six seconds. An earlier rapid-poll harness attempt
hit the daemon's per-IP RPC rate limit; the successful run polled once per second.
This evidence does not qualify immediate repeated rename bursts.

## Review and remaining acceptance

PRE review clarified alias edits, rollback precedence, serialized persistence and
publication, and setup partial success. POST correctness/maintainability review
found BOM/quoted-name compatibility regressions; those were fixed and re-reviewed
with no remaining source findings.

The fix is implemented but unproven in the actual Columba and Ratspeak UIs.
No production service, phone, physical radio, package release, or installed-package
upgrade was changed or qualified. Upgrade evidence above tests preservation when
legacy/default configuration is replaced while retaining the SQLite database and
identity file; it is not a Debian/package-manager lifecycle test. Clients can
retain the old cached name until a fresh announce reaches them.
