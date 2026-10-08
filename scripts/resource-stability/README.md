# Linux resource stability evidence

These tools are being developed for RCH #252–#257 and LXMF-rs #657. The current
baseline runner is an **attribution experiment**, not final acceptance. It has
synthetic control-API announce ingress and dashboard/chat HTTP traffic; it does
not yet include independent real peer delivery or browser heap measurement.
It explicitly records `passed_final_acceptance: false` even when the baseline
finishes. Follow `docs/goals/resource-stability/PLAN.md` for the remaining gates.

Requirements: Linux `/proc` and cgroup v2, delegated systemd user services,
Python 3.11 or newer with MessagePack, and installed locked Rust dependencies for the
fixture generators. Temporary services bind loopback/private Unix sockets only,
disable shared-instance networking, and stop only the randomly named units they
created. Fixture writes refuse occupied propagation tables and existing RCH
fixture files. No production data is used.

Build fixture tools from the paired source checkouts:

```sh
# In LXMF-rs; default std features are required.
cargo build --release --locked --offline -p lxmf-wire --example propagation_resource_fixture
# In RCH. Use different generator names if sharing a Cargo target directory.
cargo build --release --locked --offline -p r3akt-rch-core --example resource_fixture
```

Every generated propagation row uses the actual LXMF codec and identity crypto.
The generator authenticates decryption and verifies its signature before writing
it. Historical fixture stamp cost is zero, explicitly recorded: this tests stored
payload/association allocation, not production stamp-mining CPU behavior. Valid
payload history is separate from independently verified new-message delivery.

Run report regressions and effective resource-control preflight:

```sh
python3 -m unittest discover -s scripts/resource-stability -p 'test_*.py'
python3 scripts/resource-stability/preflight.py --output /tmp/rch-controls-new
```

Run a small baseline first, using absolute binary paths and a new output folder:

```sh
python3 scripts/resource-stability/baseline.py \
  --server /absolute/path/r3akt-rch-server \
  --daemon /absolute/path/reticulumd \
  --rch-fixture /absolute/path/resource_fixture \
  --wire-fixture /absolute/path/propagation_resource_fixture \
  --output /tmp/rch-baseline-small-new --small --duration 15
```

Omit `--small` for 135,893 valid payload records, one million associations across
940 historical peer keys, 512 configured active peers, 100,000 RCH announces and
25,000 terminal messages with 4 KiB content and attachment metadata. Activation
can legitimately refill pending slots and create a local service peer; record
counts before/after activation and maintenance rather than interpreting any
count change as corruption. The final fixture-qualification lane must establish
expected survival/pruning and exercise pending/completed transitions before the
sustained acceptance run.

Each run records binary and fixture hashes, actual effective CPU/memory/swap
controls, raw RSS/private/anonymous/PSS/swap accounting, pressure, I/O,
threads/descriptors, dashboard request latency, SDK poll counters and shutdown
outcome. Sixteen glibc arenas model the older production allocator geometry;
this is a controlled experimental setting, not an allocator fix. No periodic
trim or restart is used during observation.

Use `--fixture-from /path/to/earlier-run` to copy its immutable fixture databases
without regenerating the cryptographic history. `--resource-diagnostics` samples
the instrumented daemon's `daemon_status_ex.resources` buffer accounting. Keep
the output path short enough for private Unix sockets (the runner checks 100
bytes before creating files). Harness source hashes are frozen at startup.

`report.py` evaluates a supplied frozen criteria manifest and real traffic
results. It rejects idle/incomplete workload, a discarded/unqualified fixture,
errors, restart/OOM, resource growth or forced shutdown. Its thresholds must be
chosen before a final run and retained with the raw evidence. A short baseline
must never be re-labelled as the required sustained qualification.
