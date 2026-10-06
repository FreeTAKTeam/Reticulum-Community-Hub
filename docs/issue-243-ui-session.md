# Issue #243: remembered UI login and permission denials

The connection store loaded opt-in saved credentials but initialized its verified
session to false. The synchronous route guard redirected protected reloads to
Connect before any authentication check. Separately, the API client treated
every 403 as global logout, including operation-specific permission denials.

The shared UI now uses an asynchronous protected-route guard to validate saved
credentials against `/Status` before entering the requested route. The check
has no retries, a ten-second deadline, and one attempt per connection identity
per application instance. Concurrent navigation shares the pending check.
Bootstrap waits for initial routing. A new tab validates independently; no
authenticated flag is persisted or trusted. Remembering remains opt-in, and
Connect explains the memory-only reload policy.

The API client preserves a scoped 403 and its server detail while checking
`/Status` once for an active session. A 401/403 from that authentication endpoint
invalidates the session, including compatible backends using 403 for invalid
credentials. An unavailable check does not prove invalid credentials and does
not discard the session. The original denied operation is never retried.
Actual 401 responses continue to invalidate authentication.

Connection, WebSocket endpoint, authentication mode and credential changes
invalidate the session immediately. An ephemeral configuration revision also
rejects stale responses when settings change away and back to their original
values. Pending restoration is cancelled when the identity changes. Credentials
stay in headers; remote HTTPS/WSS enforcement, omitted cookies and redirect
rejection remain in the existing client. Backend authorization remains final.

This uses the existing Vue/Pinia client and a small routing helper rather than
adding authentication requests to page components or another transport layer.
[Vue's asynchronous navigation guards](https://router.vuejs.org/guide/advanced/navigation-guards.html)
allow initial navigation to remain pending until validation completes. The old
synchronous guard and unconditional forbidden-session invalidation are replaced.
The original production request producing `Access denied` is still unidentified;
this fix addresses the two confirmed UI weaknesses without attributing it to
SSH, origin policy or daemon readiness.

Validation on 6 October 2026:

- Locked UI dependencies installed from the local cache; type checking, lint,
  all 156 tests in 42 files and the production build passed.
- Regression tests cover remembered reload/new application instances, SSH
  loopback and HTTPS targets, memory-only persistence, 401/403 rejection,
  resource-denial authentication probes, unavailable probes, and stale results
  after origin/WebSocket/mode/credential changes including away-and-back changes.
- A real browser using the built UI, a disposable loopback RCH server and its
  isolated daemon logged in with a test-only key. Remembered reload and a new
  tab opened Chat; sidebar Topics/Files/Chat transitions retained login.
  Disabling persistence preserved current-session navigation and then sent a
  full reload to `/connect?redirect=/chat` with no saved key.
- Scoped/legacy 403 behavior and HTTPS validation were exercised with controlled
  HTTP responses in the client/router tests. Production credentials, the SSH
  tunnel and a production HTTPS/WSS deployment were not used in these tests.

This is a source fix after preview.13; existing published archives are unchanged.
