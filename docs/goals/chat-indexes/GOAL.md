# Goal: Bounded browser chat and indexed persistence

> **Port status (2026-11-19):** this work was ported from
> `corvo/issues-253-256-chat-indexes` onto current `main`. The migration is now
> schema 11, not 7, and the duplicate policy is decided: case-insensitive duplicate
> message IDs keep the earliest row and archive the rest in
> `rch_messages_identity_archive`. Measurements below were taken on the pre-port
> branch (schema 6 → 7 on PR #266's base) and were not repeated after the port.


Use Krypton Execution to execute PLAN.md. Preserve backend domain authority,
shared UI compatibility and durable history. Replace unbounded presentation and
message delete/insert paths. Capture actual browser/SQL acceptance evidence and
independent PRE/POST review. Report unproven physical/production acceptance.

Status: implemented and ported to schema 11 on current `main` (2026-11-27). Duplicate
message IDs are archived (earliest row kept). Local checks re-run after the port;
measurements below predate it. No production or physical-network acceptance is claimed.
