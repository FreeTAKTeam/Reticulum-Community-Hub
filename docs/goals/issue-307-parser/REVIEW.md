# PR 310 review follow-up

Addresses the [review comment](https://github.com/FreeTAKTeam/Reticulum-Community-Hub/pull/310#issuecomment-6776753474).

## Parser scope and simplification

The incident's excessive allocation came from RCH's unchecked slot-vector capacity, not a demonstrated serde allocation. The pinned `serde_json::Value` sequence visitor starts with `Vec::new()` and reads elements incrementally. The reviewer's direct-serde result is consistent with that implementation.

The structural walker is retained to enforce RCH's explicit 16 KiB, depth-32 and 4,096-item limits, including embedded documents. These are application resource budgets, not evidence of another serde vulnerability. Redundant passes were removed: non-array documents are validated only in `decode_value`, and slots already covered by whole-array validation are not revalidated for payload extraction or serde conversion. Embedded documents still require their own validation.

## Diagnostics semantics

`rejected_total` now increments once per failed outer app-data decode call. Optional slots may contain opaque data from other clients, so an unsuccessful capability probe neither increments this counter nor logs a rejection. The outer announce still enters the directory. Replaying the same failed app-data decode can increment the counter again; it does not count distinct peers, announcements or attacks. Runtime diagnostics expose the scope as `failed_app_data_decode_calls`.

Payload-free logging now allows the first failure immediately and at most one subsequent failure log per 60 seconds of monotonic time. An atomic compare-and-exchange shares this limit between callers. A later burst is visible even after a large lifetime count or an idle period. Runtime diagnostics expose `log_interval_seconds`.

Regression tests cover multiple opaque slots with and without a later valid capability, once-only outer failure counting, logging after a million prior failures and an idle period, and concurrent failures sharing one log window without losing counts. Existing parser bounds, incident-header and broker replay tests remain in place.

Validation passed: formatting, workspace clippy with warnings denied, all 762 workspace tests/doctests (including the 11 parser tests and ZeroMQ replay regression), and link checks for 72 tracked Markdown files. Commands used the existing locked dependency cache. The interval gate uses the established `compare_exchange` API to preserve the Rust 1.88 minimum version.

## Deployment boundary

This follow-up updates the PR. The production deployment and actual-payload replay evidence in [EVIDENCE.md](EVIDENCE.md) describe source commit `8e28f164188399eb8260622a9f442b417746624b`; these review changes have not been deployed.
