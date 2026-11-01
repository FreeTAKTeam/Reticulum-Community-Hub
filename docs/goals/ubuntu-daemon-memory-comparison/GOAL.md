# Goal: Compare Python and Rust Daemon Memory on Ubuntu

Use Krypton Execution to execute [PLAN.md](PLAN.md). Read the complete plan before installing or running anything.

Start in the Ubuntu `LXMF-rs` checkout with this RCH plan available. Identify actual paths and applicable repository instructions; inspect only explicitly scoped repositories. Reuse existing benchmark tooling where possible.

Core rules:

- Treat PLAN.md as the experiment contract. Complete its PRE review gate and freeze numeric settings, workloads, and acceptance targets before measured runs.
- Run Python Reticulum/LXMF and release-built Rust `reticulumd` sequentially in the same isolated Ubuntu environment, with equivalent effective configuration, resource limits, logical fixtures, and offered traffic.
- Reset both subject and peer state between independent runs. Keep test traffic and identities isolated from production and the public mesh.
- Measure the complete subject stack; keep generators outside its resource accounting. Separate shared daemon comparison from Rust-only RCH integration and from profiling runs.
- Verify delivery with sender/receiver ledgers, including offline retrieval. Report memory categories, interval pressure counters, IO, queue depth, and latency together.
- Keep runtime artifacts outside source checkouts and secrets out of committed evidence. Preserve unrelated local work.
- Do not change production services, limits, identities, or data. Local findings require a separately scoped production validation.
- Deliver reproducible commands, manifests, plots, and a report. State "implemented but unproven" if the required experiment evidence is unavailable; never substitute harness tests for completed benchmark results.

The committed package is a plan, not a completed benchmark or a production fix.
