# Test evidence

Keep focused domain unit tests, northbound contract/integration tests and the
release-readiness/live integration gates. No useful test suite was removed.

`rust.yml` retains main/rust-next push and PR readiness execution and now permits
manual dispatch. `rust-pr-quality.yml` also runs on main pushes; its existing
independent Rust, documentation, audit, performance and release-build jobs remain.
UI lint, typecheck, unit tests, build and browser acceptance run in separate matrix
jobs with fail-fast disabled. A lint failure cannot suppress UI test execution.

Local UI checks, from the repository root:

```sh
npm --prefix ui run lint
npm --prefix ui run typecheck
npm --prefix ui run test
npm --prefix ui run build
npm --prefix ui run test:e2e
```

The three Chromium acceptance tests use the production UI bundle and exercise
login redirection/reload, refusal of missing remote credentials and refusal of
insecure remote transport. They require no server mock or live credentials and
prove frontend session behavior only. Vitest excludes the Playwright directory.
Browser failures retain traces/screenshots; CI uploads them. They do not prove
server authorization, message delivery or interoperability.

Rust checks remain `cargo fmt --all -- --check`,
`cargo clippy --locked --workspace --all-targets -- -D warnings` and
`cargo test --locked --workspace -- --test-threads=1`.
The immutable LXMF reference is unchanged.

Release readiness remains:

```sh
pwsh -NoProfile -File scripts/release-readiness.ps1 -ServerOnlyAlpha
```

 Use `-LiveTak` / `-LiveReticulum` only with their required
external infrastructure and environment variables. No live pass is inferred
from unconfigured tests. A plan-only run proves command selection, not readiness.

The hosted workflows were active when inspected on 6 October 2026; the latest
recorded main push run was 5 August 2026. Local edits cannot prove a new main run
or change hosted state until explicitly authorized publication. No workflow was
disabled or remotely dispatched as part of this local strategy update.
