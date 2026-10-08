# Linux resource stability evidence

These tools are being developed for RCH #252–#257 and LXMF-rs #657. The current
baseline runner is an **attribution experiment**, not final acceptance. It has
synthetic control-API announce ingress and dashboard/chat HTTP traffic; it does
not combine independent real peer delivery or browser heap measurement with its
large-history workload. Separate short preflights qualify those instruments.
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


## Real bidirectional delivery preflight

Build the public-SDK peer in the matching LXMF-rs checkout:

```sh
cargo build --release --locked --offline -p lxmf-sdk \
  --example resource_sdk_peer --features zmq-pipeline-backend
```

Freeze/copy binaries before starting, then use a new short output path:

```sh
python3 scripts/resource-stability/delivery_preflight.py \
  --server /absolute/path/r3akt-rch-server \
  --daemon /absolute/path/reticulumd \
  --sdk-peer /absolute/path/resource_sdk_peer \
  --output /tmp/rch-delivery-new --messages 5
```

Two isolated daemons exchange real TCP Reticulum traffic. RCH and the independent
public SDK each register their own service identity; neither sends under the
daemon's default identity. The SDK peer explicitly activates and announces its
created identity and validates the returned identity/destination binding. The
harness waits for real announces before sending.
Inbound chat content is 480 bytes, within RCH's existing 500-character limit;
outbound content is 4 KiB. Both use unique tokens and zero stamp cost.

Success requires unique returned sender IDs, unchanged full payloads, terminal
SDK/RCH receipts, exact sender and receiver SQLite rows, authenticated/encrypted
receiver metadata and zero RCH poll errors. SDK, RCH and wire IDs can differ;
unique tokens plus exact content and identities establish their relationship.
HTTP and Unix RPC reads have whole-exchange deadlines, including trickling
headers/bodies. The caller's remaining qualification time bounds each exchange.
Pipe framing and SDK process startup/cleanup also have failure regressions.

This empty-history lane always writes `passed_final_acceptance: false`. It does
not exercise propagation history, stamp mining, browser load, the required soak
or slow-peer resource recovery. Those remain separate acceptance requirements.

The populated attribution lane reuses the immutable large fixture:

```sh
python3 scripts/resource-stability/delivery_preflight.py \
  --server /absolute/path/r3akt-rch-server \
  --daemon /absolute/path/reticulumd \
  --sdk-peer /absolute/path/resource_sdk_peer \
  --fixture-from /path/to/immutable-large-baseline \
  --output /tmp/rch-populated-delivery-new --messages 65
```

This sends one unique pair every five seconds, with a frozen observation deadline
of `max(480, messages * 5 + 60)` seconds. It requires a verified pair before an
observed successful 300-second storage-maintenance cycle and a new verified pair
admitted after that completion was observed. Dashboard APIs run every 30 seconds;
daemon buffer diagnostics and both services' Linux memory accounting are sampled.
Original payloads, completed marks, all peer histories and RCH rows must survive;
only logged pending-association pruning is allowed, with at least 90% of original
associations retained. New rows cannot mask missing original records. Fixture
hashes and nonempty WAL files are checked before startup and after cleanup. The
lane rejects fixtures whose pending/completed TTLs expire during observation.
SQLite proof reads carry the same deadline, including bounded lock waits and
interruptible VM work. Any maintenance failure, process identity change, sampled
OOM event or cleanup failure invalidates success. Cancellation attempts cleanup
of every owner and retains primary and nested cleanup errors in the report.
Populated peer activation uses the baseline's separate 120-second setup allowance,
records its elapsed time, then restores the normal 10-second control RPC timeout.
It does not extend observation or shutdown deadlines.
Both TCP ends start before activation. Setup retries both real service announces
through the SDK and `/Control/Announce` within 30 seconds; learned signed identity
records are required, and bounded discovery attempts are saved even on failure.

It remains attribution: historical peer keys model bookkeeping, not independent
physical peers. Seeded propagation fetch/ack transitions, browser load, slow-peer
recovery and the sustained memory plateau still require their acceptance lanes.
`passed_final_acceptance` remains false.

Browser measurement was preflighted with the existing Playwright CLI and cached
Chromium against a frozen UI bundle served through `--ui-dist-path`. CDP
Performance/Memory metrics expose JavaScript heap, DOM nodes and listeners. That
single dashboard snapshot qualifies measurement only; sustained chat navigation,
backfill and heap/DOM plateau evidence remain outstanding.
