# Identity directory pagination and independent UI loading

Issue #264: an identity directory above the UI's 8 MiB response limit prevented
Users, Teams and Chat from initializing in preview.21. Receipt and storage of
inbound LXMF messages were unaffected by this browser loading failure.

## HTTP contract

`GET /Identities` continues to return the complete Python-compatible array.
When `page` or `per_page` is supplied, it returns the same pagination envelope
as `/Client`: `items`, `page`, `per_page`, `total`, `total_pages`, `has_next`,
`has_previous`. Pages start at 1, default to 50 entries, and accept at most 500.
Invalid bounds return 422. Out-of-range pages contain an empty `items` array.

Identity order is ascending by normalized identity. Counts and page boundaries
exclude suppressed voice aliases, matching the legacy directory. Metadata,
moderation, REM classification and authentication rules are unchanged. Each
request observes current state; pagination is not an immutable inventory
snapshot when identities change concurrently.

## Shared UI behavior

The shared Python/Rust UI requests client and identity pages of 100 entries,
publishes each successful page, and follows the server's continuation metadata.
Legacy Python array responses are also supported. A directory page is validated
before publication. The 8 MiB response safeguard remains in force for every
request, including legacy responses and individually oversized records.

Clients, identities and REM peers load independently, with per-resource errors.
Successful identity pages remain visible if a later page fails; the Users screen
labels that directory incomplete and shows loaded/total counts. Refresh retries
the directory from page 1. Backend connection changes invalidate pending results.

Teams, members and missions publish their own successful results and errors.
Chat requests clients, topics and history separately and connects its live
stream immediately, without fetching identities. A pending history response
preserves live messages received while it was loading. Stream disposal remains
owned by the Chat page.

## Regression evidence

Server coverage creates 30,001 identities with a legacy body above 8 MiB and
checks every 100-entry page against that full legacy directory, including the
last partial page, out-of-range pages and invalid bounds. Existing identity
annotation and voice alias tests still protect the original directory semantics.

UI coverage exercises real oversized response decoding, all-page loading,
malformed continuation responses, resource isolation, stale connection results,
received chat history, live updates during history loading and stream cleanup.
Returning to Chat with cached messages reproduced the separate
`undefined.length` rendering crash. The immediate attachment-preview watcher
computed visible messages before `resolveMessageScope` had been initialized,
raising a ReferenceError followed by the undefined-length errors. The helper is
now initialized before that watcher; a cached-message mounting regression covers
this path independently of directory loading.
