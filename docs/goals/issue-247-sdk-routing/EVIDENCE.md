# Issue 247 validation evidence

Validated on 2026-10-06 against LXMF-rs revision `81344ae1eccc79612fe933efe990c8da55809254`. No SDK dependency or daemon change was required.

## Local checks

- `cargo fmt --all -- --check`: passed.
- `cargo clippy --workspace --all-targets --offline -- -D warnings`: passed.
- `cargo test --workspace --offline`: 657 passed, zero failed, two existing ignored qualifications (external local mesh load and release-mode announce profiling).
- Explicit checks of `r3akt-rch-server`, `r3akt-rch-core`, `r3akt-transport-rns` and `r3akt-tak-connector`: passed.
- Server debug build and workspace Rustdoc with denied warnings: passed.
- Documentation links, module budgets and diff checks: passed without increasing module allowances.

Regression coverage includes 100,001 corrupt announce payloads for targeted, explicit-recipient and empty-roster selection; complete recipient idempotency keys; known/missing/malformed SDK paths; selected-node sync; typed admission uncertainty and invalid batch correlation results; receipt terminality beyond old deadlines; restart aggregation; separate registered identities with equal names; pending admission retries and durable permanent rejection evidence.

## Final daemon acceptance

Two disposable TCP-connected daemons and the rebuilt RCH server were used. Typed SDK path status matched the active daemon destination, next hop, interface and hop metadata. A missing destination requested normal daemon path discovery. Six outbound messages reached terminal SDK delivered receipts and appeared independently in the receiver's SDK history. Requested destinations were unchanged.

Three sends ran with one history row, followed by three after inserting 100,001 malformed unrelated history rows. Every inserted row remained byte-for-byte unchanged. Median admission was 0.7165 seconds before insertion and 0.6223 seconds afterward. These small samples demonstrate functional independence; they are not a general performance benchmark. All three services exited successfully.

- Final server SHA256: `fef636f3d276e28f4bffa1524f7d9037e805a2e80c75ca588c8c3ae5159115c2`.
- Daemon SHA256: `a1c02bcc7e0411439b1ed944537a53f4eca7af168e5e3c0cf4c97b2b7ec4aac8`.
- Frozen Rust/Cargo source-manifest SHA256: `e76229fa4db406aa98d869a8f1c53845ecad19e4d54ffb75005f2e7742e13f13`.

Local raw evidence is retained under `/tmp/rch247-live/` (`result.json`, `path-parity.json`, `peer-message-history.json`, `terminal.json`, `final-source-manifest.json`). The disposable runner is `/tmp/rch247-live-acceptance.py`; the earlier successful setup is retained under `/tmp/rch247-live-initial-success/`. Runtime data and logs remain untracked. Source hashes were unchanged across final acceptance.

## Scope and review

PRE and POST ownership/correctness review passed. Removed strategies and unused delivery callback endpoints have no compatibility shim. RCH retains application recipients, moderation, payload encoding and its pre-admission queue. SDK/daemon state owns routes and admitted transport outcomes. Announce retention remains separate.

Production infrastructure, physical phone/radio networks and a release package are not certified by this local test. The live mesh used native daemon delivery destinations; initial imported-service announce setup attempts remain unclassified. Delivery beyond former receipt deadlines is covered by persisted SDK regression fixtures, not a live delayed-network run. Hosted CI is reported separately on the PR.
