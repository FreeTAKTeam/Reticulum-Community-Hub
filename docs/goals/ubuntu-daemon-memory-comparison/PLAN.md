# Ubuntu Python and Rust Daemon Memory Comparison Plan

**Intent:** Determine whether the Python reference and Rust daemon deliver equivalent Reticulum/LXMF work within the same resource budget, and identify the workloads responsible for memory pressure.
**Current Behavior:** The production droplet has recurring reported memory pressure. Earlier investigation implicated file cache and database activity, but did not establish a heap leak or its cause.
**Expected Outcome:** A repeatable local Ubuntu experiment with separate conclusions for functional parity, memory growth, pressure, throughput, and delivery latency.
**Target-Perspective Output:** The operator can inspect paired run manifests, time-series plots, receiver delivery ledgers, and a report explaining which implementation meets the declared workload and memory budget.
**Truth Owner:** This document owns the experiment contract; pinned implementation documentation owns supported settings; per-run manifests and raw measurements own the results.
**Contract Boundary:** Scripted test peers send and receive Reticulum/LXMF traffic through either the Python reference stack or Rust `reticulumd`. RCH integration is a separate diagnostic lane.
**Cutover:** None in production. Locally, stop the entire tested stack, reset the test environment, and switch the implementation between runs.
**Displaced Path:** No production path is replaced. Controlled paired runs replace ad hoc process-memory snapshots as comparison evidence.
**Value Density:** Establish parity and collect a short paired baseline before investing in long soaks or allocation profiling.
**Acceptance Evidence:** Equivalent offered workloads, reconciled receiver results, verified resource limits, reproducible memory measurements, and explicit explanations of unmatched functionality.
**Evidence Lane:** Local Ubuntu controlled comparison, followed by a separately scheduled DigitalOcean validation if local findings justify it.
**Kill Criteria:** Stop a run on test isolation failure, incorrect resource limits, exhausted host/disk safety budgets, or invalid measurement capture. Preserve evidence. An implementation crash/OOM or delivery failure is a result, not a reason to discard the run.
**Architecture Slice:** Test peers -> isolated Reticulum interfaces -> selected daemon stack -> implementation-owned persistence; optional RCH connects only in the integration lane.
**Plan Review Gate:** PRE review passed on November 1, 2026; Ubuntu preflight and the paired smoke test remain required before measured experiments.

## Scope and ownership

This change commits the plan and [Ubuntu handoff prompt](GOAL.md) only. It does not install software, run benchmarks, change production, or implement a fix.

The Ubuntu execution session should start in the `LXMF-rs` checkout. Resolve the actual Ubuntu paths during preflight. Do not assume Windows paths or enumerate other repositories.

| Area | Owner and permitted work during execution |
| --- | --- |
| Experiment plan and handoff | This RCH repository, `docs/goals/ubuntu-daemon-memory-comparison/` |
| Harness and sanitized reusable fixtures | Proposed `LXMF-rs/tools/daemon-memory-bench/`; inspect existing tooling first and reuse it if an equivalent owner exists |
| Python reference | Pinned upstream Reticulum and LXMF packages in an isolated environment; preserve their source behavior |
| Rust subject | Pinned `LXMF-rs` release build, including recorded feature flags and executable checksum |
| RCH integration subject | Pinned RCH server binary, introduced only for the integration lane |
| Run artifacts | Dedicated local directory outside source checkouts, such as `~/rch-daemon-memory-results/<experiment-id>/` |
| Protected areas | Production services, production identities/secrets/stores, unrelated worktrees, and the RCH `rch-python` branch |

The harness owns workload generation and evidence collection, not daemon persistence semantics. Inputs are a normalized experiment manifest, implementation-specific config files, and logical fixtures. Outputs are immutable run manifests, raw samples, receiver ledgers, and a report. Do not add Python implementation source to the Rust RCH repository. This plan does not authorize unrelated multi-repository changes; identify the exact checkout scope before execution under the applicable repository instructions.

## Historical context and assumptions

The October 31, 2026 investigation recorded approximately 773-775 MiB of daemon cgroup memory against a 768 MiB `memory.high` threshold, including approximately 478 MiB file cache and 202 MiB anonymous memory. These are historical observations, not a current baseline or proof of a leak. The earlier production configuration was `/var/lib/rch/reticulumd.toml`, with additional launch arguments; do not substitute a legacy Python configuration for the effective Rust configuration.

During preflight obtain a sanitized production manifest or already captured evidence. If current production settings or workload rates are unavailable, run an explicitly labeled synthetic profile; do not claim production equivalence. No production login or service change is required to prepare the local harness.

Ubuntu version, hardware capacity, available virtualization, reference versions, and production workload rates remain inputs to discover. Freeze their values before the first measured pair. Never resolve a moving `latest` version separately for each run.

## Comparison lanes

1. **Shared daemon lane:** Python Reticulum plus LXMF routing/propagation versus Rust `reticulumd`. Include all required daemon processes in the subject's aggregate memory/CPU accounting. Determine whether the pinned Python setup embeds Reticulum or uses a separate shared instance; never omit that instance's cost. RCH, UI, TAK, and load generators are outside the subject.
2. **Production integration lane:** Rust daemon plus a fixed RCH workload, including ZeroMQ event polling, announce reconciliation, and persistence. Measure daemon and RCH separately and as a combined system. Compare Rust with/without this workload using the same protocol traffic. Do not claim Python parity for a Rust-only API or invent a compatibility shim to force a comparison.
3. **Attribution lane:** Follow up on a reproducible difference with database/IO measurements or allocation profiling. Profile separately from the primary uninstrumented comparison and quantify observer overhead.

If a feature cannot be disabled or matched, label the difference in the report. The production-shaped run retains required production functionality; any reduced-feature diagnostic run gets its own manifest and result.

## Environment and reset contract

- Prefer one dedicated Ubuntu VM on the local machine, with fixed vCPU, RAM, swap, and disk configuration. Boot the same clean baseline for each run; exclude saved guest RAM from the baseline so it does not silently restore an arbitrary warm cache. Match the droplet's OS and resource envelope where practical and document remaining differences.
- Native Ubuntu is an alternative: use cgroup v2/systemd resource limits and a dedicated test network namespace. Declare a repeatable warm-up/cache policy. A process restart alone does not establish a cold filesystem cache, and do not drop host-wide caches on a shared workstation.
- Run only one subject implementation at a time. Put required daemon processes in one measured cgroup subtree. Put traffic generators, test peers, and collectors outside it, preferably outside the subject VM. Reserve CPU and memory for them and monitor generator saturation and host contention.
- Verify effective CPU allocation/quota, `memory.high`, `memory.max`, swap limit, filesystem, and disk capacity from the running environment. Record host and guest configuration, not just requested settings. Use identical limits for each pair.
- Isolate protocol traffic from production and the public mesh. Disable unintended discovery/uplinks and verify routes/interfaces before starting. Use test identities only; restore the same test identities across sequential paired runs when supported.
- Restore subject, peer, and generator state before each independent run: message stores, identity/path caches, propagation queues, receiver ledgers, and workload random seed. Stop all prior run processes and verify ports are released.
- Test both empty state and a populated logical fixture. Populate each native store through supported APIs/protocol operations; do not copy a Rust SQLite database into Python. Match logical message count/bytes, peer count, retention age, and expiration schedule, and verify them before measurement. If equivalent announce history is unsupported, record that difference explicitly.
- Control page-cache accounting during fixture preparation: run subject-store population and warm-up inside the same measured cgroup that will run the daemon. External protocol clients may drive population, but must not directly read or write subject-store files. Alternatively, prepare an offline fixture and cold-boot the dedicated VM before the measured daemon accesses it. Keep the subject cgroup alive across population, warm-up, and measurement; do not move a warmed process into a new cgroup. Verify file-memory charging during smoke tests. On native Ubuntu, existing pages may remain charged elsewhere; disclose that limitation and use the VM route if comparable accounting cannot be demonstrated.
- Keep startup and fixture-population costs as separate measured phases. Start the steady-state window only after a fixed warm-up policy, verified fixture state, and a fixed queue-drain deadline. An implementation that cannot reach that starting condition fails preflight for that profile.
- In the Rust integration comparison, preserve identical daemon limits with and without RCH. Give RCH its own fixed cgroup budget and record host/VM headroom in both runs. A shared daemon-plus-RCH budget is a separate profile and must not be substituted silently.

## Configuration equivalence manifest

Create `config-equivalence.md` and `experiment.json` in the experiment artifacts. For each row record the Python setting, Rust setting, effective value, evidence used to verify it, and status (`matched`, `unmatched`, or `not applicable`). No silent defaults.

| Dimension | Required match or explicit difference |
| --- | --- |
| Build | Reference package versions/hashes; Rust commit, toolchain, release flags/features, binary hash |
| Network | Topology, interface type, transport role, MTU, link rate/latency/loss, connection count, discovery behavior |
| LXMF | Routing/propagation roles, peer policy, message sizes, transfer limits, retry/timeout policy, stamp/security settings |
| Announce workload | Existing versus new identities, unique identity count, announce cadence, duplicate rate, reconnect schedule |
| Persistence | Logical retention/TTL, capacity quotas, durability semantics, expiration/cleanup behavior; list internal differences |
| Resources | CPU, RAM/cgroup limits, swap, disk, OS/kernel, filesystem and VM configuration |
| Observability | Logging level/rotation, metrics polling, collector cadence, profiling disabled for baseline |
| Initial state | Fixture version/hash, logical counts and ages, fixed workload seed, reset and cache policy |

Configuration syntax need not match. Effective behavior and workload must match. In particular, retaining more historical records is extra work even if both implementations use similarly named retention settings.

## Workload and schedule

The generator must use a fixed offered-load schedule, rather than reducing the offered rate when a subject slows down. Log scheduled, attempted, accepted, and received counts separately. Recreate equivalent logical messages with fresh protocol-valid envelopes; do not replay stale encrypted packet captures as the primary workload.

Record fixed numeric peer counts, message sizes/rates, announce rates, burst duration, retention durations, queue-drain deadlines, and latency targets in `experiment.json` before execution. Derive the production profile from captured measurements when available. Use a small synthetic smoke profile to verify the harness first.

| Scenario | Initial proposed duration per implementation | Evidence |
| --- | --- | --- |
| Smoke | 10 minutes | Routing, one propagation/offline retrieval cycle, complete receiver reconciliation, collector coverage |
| Idle | 30 minutes after warm-up | Baseline memory/cache/CPU, background maintenance, zero unexpected traffic |
| Normal traffic | 2 hours | Fixed offered rate and payload distribution, delivery success, latency, memory trend |
| Announce/peer churn | 2 hours | Separate repeated announces from new-identity growth; reconnects, retention/expiry, DB writes |
| Offline delivery | 2 hours plus declared drain deadline | Fixed offline interval/backlog, reconnection, retrieval, no missing or duplicate logical deliveries |
| Soak | 24 hours, extend both sides to 48 hours if maintenance/expiry cycles require it | Bounded-state memory trend, maintenance cycles, pressure intervals, queue stability |
| Recovery | 1 hour after each load scenario; extend equally if declared maintenance cadence is longer | Queue drain and retained-state stability, anonymous/file memory trajectories |

Run short scenarios with both empty and populated starting fixtures. Run at least three paired repetitions, alternating first implementation (Python/Rust, Rust/Python, Python/Rust). Reset between runs. Use at least one paired populated-state soak after the short runs pass the harness validity gate; a single soak is exploratory, and repeat it before claiming reproducible long-term growth. Record all failures and do not discard unfavorable runs.

Start with the constrained droplet-shaped envelope. If it exhibits pressure, add a separately labeled higher-memory diagnostic pair to distinguish growth from reclaim/throttling effects. Change only the declared resource limit between those profiles. Freeze each profile before running both implementations.

## Measurement and functional evidence

Sample lightweight counters every 5 seconds and heavier process/store observations every 60 seconds. Record UTC plus monotonic elapsed time, run/phase IDs, process start times, restarts, and collector errors. Keep deep profiling outside these runs.

| Category | Measurements |
| --- | --- |
| Memory | Cgroup current/peak where supported; `memory.stat` anonymous, file, kernel, dirty/writeback; process RSS/PSS and swap |
| Pressure | Interval deltas for `memory.events` high/max/OOM/OOM-kill; cgroup and host memory PSI; swap-in/out and IO pressure |
| Work and cost | CPU time, throttling, disk read/write bytes, network bytes, successful deliveries per second |
| Storage | Native store size/counts, retained logical bytes, Rust DB/WAL size, cleanup/checkpoint timing where observable |
| Backlog | Pending delivery/propagation queue depth and age, peer counts, announce counts, expiry counts |
| Correctness | Sender/receiver application IDs, payload hash, expected recipient, receive time, duplicates, errors, expiry reason |
| Integration | RCH/daemon diagnostics, ZeroMQ polling errors/latency and reconciliation progress when available |

Aggregate all subject processes without summing overlapping cgroup ancestors. Do not add process RSS to cgroup memory. Treat anonymous RSS as a category, not a direct live-heap measurement. File cache and kernel memory belong in the operational budget even when reclaimable. Compare interval counter deltas, not lifetime cumulative counters.

Use generator-side monotonic timing for send-to-ack latency on one clock, or document and measure cross-host clock synchronization error for receiver timestamps. Report p50/p95/p99 latency alongside delivered counts; never compute latency only for a small successful subset without exposing losses.

For the integration lane, verify `/Status` and `/diagnostics/runtime` with the configured authentication, plus actual receiver evidence. HTTP readiness alone cannot establish message delivery. Keep credentials and private payloads out of artifacts committed to Git.

## Acceptance and interpretation

- **Harness validity:** Matching declared settings, verified fixture/reset state, unsaturated generators, functioning isolation, and at least 99% expected sample coverage with no unexplained gap longer than 30 seconds. Mark contaminated runs invalid with reasons and retain them.
- **Functional gate:** For deterministic no-loss scenarios, all expected logical messages arrive within the declared drain deadline, with matching payloads and no unintended duplicates. For lossy/expiry scenarios, define the expected outcome before running. Persist and report missing, late, expired, duplicate, and rejected counts.
- **Budget gate:** No subject OOM, unexpected restart, or failed delivery deadline at the target offered load. Report time above `memory.high`, PSI stall time, throughput, and latency against the predeclared operational targets; a lower RSS alone is not a pass.
- **Growth assessment:** Plot memory against elapsed time, successful work, retained state, and queue depth. Compare equivalent steady-state windows after warm-up. Report MiB/hour slopes for anonymous and file memory separately, peaks/medians, per-run variation, and recovery behavior. Require retained state and backlog to be bounded before describing unexplained growth.
- **Leak claims:** Failure to return to startup RSS is insufficient. Repeated unexplained growth motivates allocation/retention profiling; only attribution evidence can support a leak diagnosis. A plateau may reflect legitimate caches or allocator retention.
- **Comparative conclusion:** Separate Python/Rust common-function results from Rust integration overhead. A lower memory footprint with less retained state, lost messages, or a growing backlog is not an equivalent-work improvement.
- **Production relevance:** Local CPU/storage and virtualization differ from DigitalOcean. State these limits and propose a bounded production validation only after the local result is understood; this plan performs no production cutover.

## Ordered execution tasks

All measured runs are sequential. There is no parallel execution of competing subjects on the same host.

1. [ ] **Freeze inputs and ownership.** Inspect the Ubuntu environment and existing LXMF-rs test tooling. Create artifact `environment.json`, `config-equivalence.md`, and `experiment.json`. Resolve exact versions, paths, numeric workload/acceptance values, and unsupported settings. Verification: recorded version/help output and effective resource/config readings. Gate: manifest complete; no claims based on unknown defaults.
2. [ ] **Prepare isolated execution.** Create/reuse harness `README.md`, `run.sh`, and sanitized `configs/` under the resolved harness owner. Implement startup, resource enforcement, isolation, phase timing, and stop behavior. Verification: launch/stop each subject, inspect cgroups/routes/listeners, and prove public interfaces are absent. Gate: only declared local endpoints reachable.
3. [ ] **Build repeatable fixtures and traffic.** Create/reuse `fixtures/`, `workloads/`, and a protocol client in the harness's existing language. Reset peers and subjects, seed native stores, and generate fixed logical schedules. Verification: fixture count/hash comparison and 10-minute paired smoke. Gate: receiver ledgers reconcile; offline retrieval actually exercised.
4. [ ] **Add collection and reporting.** Create/reuse `collect.sh` and `report/` tooling; emit `runs/<run-id>/{manifest.json,samples.jsonl,sender.jsonl,receiver.jsonl,summary.json}` outside Git. Verification: deliberately simulate a missing sample and unmatched delivery in test input; validator must flag both. Gate: metric coverage, process aggregation, timing, and failure classification verified.
5. [ ] **Run the shared daemon matrix.** Execute `run.sh --manifest <experiment.json>` (planned harness interface), capturing both fixture states and ordered repetitions. Verification: run manifests plus receiver reconciliation and resource checks for every run. Gate: all valid/invalid/failed runs accounted for before interpreting results.
6. [ ] **Run the paired soak and Rust integration comparison.** Reuse the accepted profile; add a separately declared fixed RCH workload and separate accounting. Verification: same protocol workload, daemon-only versus daemon+RCH results, runtime diagnostics, receiver outcomes. Gate: isolate integration cost; do not present it as Python daemon parity.
7. [ ] **Attribute reproducible differences.** If needed, add targeted IO/database observations or allocation profiles in separate runs. Verification: reproduce the same workload boundary with measured instrumentation overhead. Gate: distinguish measured correlation, supported cause, and unresolved hypothesis.
8. [ ] **Deliver the report and clean up test resources.** Produce `report.md`, CSV summaries, and standalone memory/pressure/delivery plots with run IDs and reproduction commands. Stop task-owned processes, retain evidence, and remove only proven temporary test resources. Gate: operator can reproduce a pair and inspect delivered-message evidence; any later production validation has a separate scope and rollback plan.

Proposed harness filenames and CLI above are implementation targets, not commands that exist today. Verify actual daemon CLI flags against pinned local builds. If existing tooling serves the same purpose, record its exact paths and reuse it rather than creating a competing harness.

## Completion checklist

- [x] PRE review complete; blockers resolved.
- [ ] Config equivalence and deviations recorded before measurement.
- [ ] Short repetitions and paired soak completed, or explicitly reported incomplete.
- [ ] Raw samples and receiver evidence retained; secrets excluded.
- [ ] Report distinguishes functional failure, memory pressure, legitimate state growth, and suspected leaks.
- [ ] Ubuntu environment differences and limits on production conclusions disclosed.
- [ ] Production unchanged; test services stopped when finished.

## PRE review record

Reviewed on November 1, 2026. Initial review identified one major accounting issue (fixture preparation could charge file cache outside the measured cgroup) and one minor omission (RCH's integration resource envelope). The environment/reset contract now specifies fixture page-cache ownership and smoke verification, plus fixed separate RCH limits and unchanged daemon limits. Final PRE verdict: aligned, with no remaining blockers or major findings. This review evaluates the plan only; no experiment has been executed.

## References

- [Linux cgroup v2 documentation](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html): memory accounting, limits, events, and pressure.
- [Python LXMF reference](https://github.com/markqvist/LXMF): reference routing/propagation behavior; pin the tested revision.
- [RCH runtime documentation](../../rust-migration-status.md): daemon integration and runtime verification; verify commands against the selected version.
