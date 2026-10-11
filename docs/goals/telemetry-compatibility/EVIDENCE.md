# Stage A evidence — 2026-10-10

Implementation is locally verified; the reported live deployment failure is **implemented but unproven** pending deployment and device evidence.

## Completed task board

- Source pins and contract: Columba2.2.6 `a402ed1052ba6993454352ce51ddfc336b729d9f`, Sideband2.2.0 `ef572b58e88ff4e4326d51778336922a53b2a03f`, RCH main baseline `f2e90c4826dc944134b2fe4339009fda3eeb01a1`, unchanged LXMF-rs dependency `e237f80c0c9e219e4090be04a4229d3328074f73`.
- Actual unmodified Columba Kotlin codec executed on JVM with an Android-free model stub; fixture bytes match, client roundtrip passes, collector timebase is seconds and null maps to zero. Reproducible harness is `scripts/check-columba-telemetry-fixture.py`.
- Before correction, two focused tests fail: daemon adapter location has no canonical latitude, and negative altitude becomes `42949660.46` instead of `-12.5`.
- Checked normalization and signed units implemented, with original sensor recovery from metadata-bound durable raw frames; historical flat packets stay unavailable.
- Both full/destination-stripped frames tested, along with malformed/truncated/nonfinite/wrong-type/out-of-range/excessive/deep/trailing/version-wrapper cases, optional and unknown sensors, and privacy-safe command/telemetry isolation.
- Broker acceptance proves actual codec fixture through journal application, SQLite storage, restart and authenticated normal `/Telemetry` response. Malformed telemetry produces a durable diagnostic without losing an independently valid collector command.

## Verification result

- `cargo test --locked --workspace`: **724 passed, 0 failed, 2 existing ignored**, 30 terminal suite results including doc tests. Conditional infrastructure tests retain their existing behavior; passing these does not establish live infrastructure acceptance.
- `cargo clippy --locked --workspace --all-targets -- -D warnings`: passed after fresh affected-crate compilation.
- `cargo fmt --all -- --check`: passed.
- `scripts/check-rust-module-size.ps1`: passed without budget changes.
- `scripts/check-doc-links.ps1`: passed for tracked documentation; task-specific new documentation links independently verified.
- Exact Columba JVM codec harness: passed.
- `git diff --check`: passed.

The initial full transport test run encountered sandbox loopback denial; rerunning with loopback access passed. A subsequent shared Cargo-cache collision exposed stale crate metadata from another checkout; affected crate artifacts were cleaned and all workspace tests and strict Clippy were freshly rerun before counting results. Installed locked dependencies were retained.

Local baseline/final logs are under the primary repository's ignored `target/rch-258-evidence/` directory. Public evidence consists only of synthetic fixtures, the reproducible harness and regression assertions; no private captures or actual client positions/identities were copied.

## Review and remaining gate

PRE plan review passed with the raw-recovery amendment. POST correctness/maintainability review identified raw preflight and schema-marker bypass gaps; both were repaired and regression-tested. Re-review found no remaining blockers and confirmed plan alignment.

The user identified latest Columba; official release resolves to2.2.6, but no installed APK was inspected. `adb devices -l` returned no devices. The actual failing RCH build, current transport configuration and receive-error message remain unspecified. Additional actual clients were not identified. Historical #260 production evidence is documented separately and is not attributed to the current #258 report.

Keep #258 live acceptance and #259 full handoff open until a real client upload is exercised through the actual Reticulum/daemon, storage, normal map rendering and collector reply path with pinned deployment/client versions and sanitized error reproduction. At the end of the initial local implementation stage, no deployment, issue closure, release, push or PR creation had been performed. The user subsequently authorized PR/CI/merge/pre-release publication; the candidate also carries preview.21's already published paired daemon pin and Linux durable-broker flag. Unrelated worktrees and root untracked work remain untouched.
