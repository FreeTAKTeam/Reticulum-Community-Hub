# Issue 307 parser repair and deployment evidence

This records the initial deployed hotfix. Subsequent PR changes and their deployment boundary are documented in [the review follow-up](REVIEW.md).

## Scope and artifact

The server hotfix was built from commit `8e28f164188399eb8260622a9f442b417746624b`, based on the deployed `v3.0.0-preview.36` commit `719c9dbc9ebad0790488a1e3b2dc387caea23156`. The LXMF dependency remains `213af2d8048ded5ff38f67ca8c0b4cc143d19ada`. The patch changes announcement capability parsing and its diagnostics/tests; it does not change database schemas, the daemon, UI, identities or configuration.

Linux AMD64 binary SHA-256:

```text
2a103b1c7fe40fe5ea6f4925c3140b822e24c61a41cee101caafd0d19dce9e9a
```

Built with Rust 1.99.1 in the repository's Debian Bookworm packaging image, using the existing lockfile and four build jobs. Source and lockfile were clean when built. Later evidence-only commits do not change the deployed source.

## Local verification

- `cargo fmt --all -- --check`: passed.
- `cargo clippy --locked --workspace --all-targets -- -D warnings`: passed.
- `scripts/release-readiness.ps1 -ServerOnlyAlpha -SkipClippy`: passed. Clippy had already passed separately. The gate ran 759 workspace tests/doctests, Rust documentation with warnings denied, a release build and authenticated HTTP smoke checks.
- Additional release-critical run, `cargo test --locked -p r3akt-rch-server -p r3akt-rch-core -p r3akt-transport-rns -p r3akt-tak-connector -- --test-threads=1`: passed all 682 tests/doctests.
- `scripts/check-doc-links.ps1`: passed against all 71 tracked Markdown files in the Windows checkout including this evidence document. The Linux gate used mirrored Git index metadata because a Windows worktree pointer cannot resolve inside Docker; its additional link check covered only the three root Markdown paths expanded by the shell.
- Eight focused decoder tests cover hostile counts, payload sizes, truncation, all scalar widths, extensions, nesting/item limits, nested encodings and compatible formats.
- Real ZeroMQ replay regression imports all 75 peers despite malformed capability entries at page/restart boundaries; valid capabilities remain available after replay.
- The exact two private incident payloads were replayed against the release binary locally, 20 times each. All 40 requests returned HTTP 200 with empty capabilities, the process stayed alive, and a subsequent valid capability announcement succeeded. The rejection counter was 40; sampled RSS was 20,748 KiB. These records were not injected into production or committed.

The decoder now validates the complete MessagePack structure before collection or serde allocation, including embedded values. Limits are 16 KiB input, depth 32 and 4,096 MessagePack items. Invalid optional metadata yields empty capabilities while ingestion continues. Aggregate rejection counts include unsupported ordinary metadata and replay; they are not an attack count. Logs contain no payload and are emitted only at power-of-two counts.

## Production deployment

At 2026-11-10 19:00:56 UTC the installed and running binary hashes matched the tested artifact. The release directory is `/opt/rch/releases/v3.0.0-preview.36-issue307-8e28f16`; only the server executable symlink was switched.

Before stopping RCH, preflight verified the previous release/hash, required database, runtime libraries and service-account executable access. A consistent RCH database and broker-owner database backup plus rollback metadata were saved under `/opt/rch/backups/issue307-deploy-20261110T190051Z` with restricted permissions. The old release remains available.

The patched server started with PID 1895920 and zero automatic restarts. The daemon retained PID 1894556 throughout the cutover. Authenticated Status/runtime checks passed and the durable broker was healthy. The deployment helper would restore the previous executable on failed startup or health checks; rollback was not needed.

Live acceptance passed over 301.1 seconds, from 19:01:08 to 19:06:09 UTC, with 11 samples:

- Status and runtime returned HTTP 200 throughout; both services retained their PIDs with zero automatic restarts and the broker remained healthy.
- The journal contained zero allocation aborts or unexpected main-process exits during the window.
- Event polls advanced from 85 to 2,328 (2,243 additional polls). One polling error occurred in the first 30 seconds; none followed during the remaining samples. This hotfix does not claim to eliminate SDK polling errors.
- Announce-cache records advanced from 204,191 to 204,206 and the latest announcement timestamp advanced. The durable event checkpoint remained 5,706; no claim of new durable-event application or remote-recipient delivery is made from this window.
- RCH's sampled systemd memory accounting was 65.7 to 76.5 MiB. The parser's cumulative rejection counter advanced during historical announce replay without aborting ingestion; this includes non-capability metadata and repeated records, not distinct hostile packets.

An independent read-only POST review found no remaining implementation/deployment blocker. Its final condition was completing this observation and recording the actual counters, including the polling error and checkpoint limitation; both are now complete.

## Limits and retained work

This closes the demonstrated capability-parser allocation abort and bounds its decoding work. It does not establish attribution or promise protection against every attack. The separate SDK session-lifecycle problem described in issue 307 remains outside this patch. Live polling/broker progress establishes continued service operation, not delivery to every remote recipient.

The active hotfix branch/worktree must remain for review. Other pre-existing worktrees were not removed because their active-chat ownership and cleanup eligibility were not established. No secrets, databases, keys or user notes were removed during repository cleanup.
