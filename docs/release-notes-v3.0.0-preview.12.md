# RCH Rust v3.0.0-preview.12 testing release

RCH preview.12 is the matching testing release for [reticulumd rch241.2](https://github.com/FreeTAKTeam/LXMF-rs/releases/tag/reticulumd-test-0.13.0-rch241.2). It includes the RCH inbound polling correction and pins LXMF-rs 0.13.0 to `bbde8f2ce35eef8e5a4d99042faed38c6b8fbf68`, SDK configuration 2 / contract v2.6.

For the reported Linux x86_64 deployment, download `rch-rust-full-linux-amd64-v3.0.0-preview.12.tar.gz` and its adjacent SHA-256 file. The server archive includes RCH, the matching UI, TAK service, a ZeroMQ-capable daemon, service helpers and a source manifest. To test the standalone daemon prerelease already installed, update RCH and the UI from this archive while continuing to run that daemon with your existing service configuration. The bundled daemon is independently compiled from the same source revision; it is not asserted byte-identical to the standalone candidate.

The paired corrections keep imports progressing past the 1,024-event retained window, recover a persisted cursor after daemon restart, persist negotiated overflow policy, and keep readiness and event polling responsive during reproduced storage contention. Existing credentials and northbound routes remain required. Stop services and back up runtime state before replacing installed executables; preserve identities, databases and deployment configuration. The archive's `ui/` directory is the built UI: point `--ui-dist-path` at that directory. Keep your existing daemon command/response endpoints and local destination configuration.

The affected backend release gate, daemon CI and a 30-minute real-peer qualification passed, including four fresh persisted inbound messages and hot restart. This testing release does not establish that the original production stall or cgroup memory-growth cause is resolved. After installation, check authenticated `/Status` and `/diagnostics/runtime`, daemon `/readyz`, authenticated announce, and actual inbound messages beyond the reported 15-minute failure window.

Source review: [RCH PR #240](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/240) and [LXMF-rs PR #654](https://github.com/FreeTAKTeam/LXMF-rs/pull/654). Python 2.9.x maintenance and existing published releases remain unchanged. Package builds do not establish native desktop interaction or external TAK/REM hardware acceptance.

See the [issue #241 investigation](issue-241-sustained-polling.md) and [runtime launch commands](../README.md#getting-started) for evidence and configuration.
