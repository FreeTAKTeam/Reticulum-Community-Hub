# JavaScript / TypeScript frontend engineering principles

## Timeless constraints, not a checklist

Minimize expected lifetime cost in THIS codebase: implementation, review,
operation, debugging, compatibility, and future change. Correctness, security,
data integrity, accessibility, and explicit product contracts constrain that
choice. Preserve the repository's stack, visual conventions, and Git workflow.
These are design constraints, not permission for an unrelated rewrite.

Scope: browser UIs, WebViews, renderers, UI stores, hooks, composables, and their
client adapters. Server-side JavaScript/TypeScript and native runtimes are not
presentation code merely because they share a repository or language. Assign
responsibilities by execution boundary and authority, not file extension.

## Refactor first when the structure obstructs the change

Read the affected code, callers, tests, and applicable AGENTS.md first. Identify
which layer owns the requested behavior. Protect relevant behavior with tests;
then make the smallest behavior-preserving extraction needed to enable the
change. Verify the extraction separately before altering behavior.

Do not append another unrelated responsibility to a large component or store.
Do not move the same mixed responsibilities into one giant hook, composable,
service, base class, or utilities file and call that a refactor. Extraction must
reduce coupling and provide an independently understandable, testable boundary.

A small correction that needs no extraction requires none. An urgent fix may
precede structural work when that is safer; record the remaining problem. Moving
a rule across an API/native boundary can change errors, timing, persistence, or
atomicity: treat that as a behavior/contract change, not merely moving code.

## 1. Keep domain authority outside presentation

Apply Separation of Concerns, Single Responsibility, and high cohesion/loose
coupling. Group code by the knowledge it owns and the reasons it changes.

| Responsibility | Correct owner |
| --- | --- |
| Rendering, layout, focus, selection, formatting, visible-list filtering, form drafts, immediate input feedback | Components and small presentation helpers |
| UI interaction sequencing, loading/error states, draft lifecycle, query coordination | Feature-level hooks, composables, controllers, or stores |
| HTTP, WebSocket, IPC, native calls, response decoding, API-to-view mapping | Explicit client/platform adapters |
| Authorization, domain invariants, semantic inference, authoritative scoring, business workflow transitions, transactions, replication/conflict policy, protocol encoding and delivery rules | The designated backend, daemon, or native domain/runtime service |

Stores, hooks, composables, and frontend `services/` are NOT alternative homes
for business rules. They may request an operation and reflect its result; they
must not decide the authoritative outcome. A domain-specific calculation remains
a business rule even when it is pure, short, or easy to unit-test. Conversely,
layout arithmetic, display formatting, and client-side input checks belong in
the client; do not move ordinary presentation behavior to a server.

Client-side validation is feedback, not enforcement. The authoritative service
must validate again. Display-only permission hints must not confer permission.
A missing backend operation is a contract gap: implement it in the right owner
when authorized, or report the gap. Do not fabricate success or add a second
rule engine, truth store, or client-orchestrated substitute for an atomic use case.

Offline is not an exception to ownership. Use the existing local native/domain
runtime when it is the designated authority. Otherwise retain a clearly marked
pending draft/request until that authority accepts it; do not invent an offline
business engine in a store. Preserve the product's actual local-first behavior.

## 2. Encapsulate state and expose narrow interfaces

Apply Information Hiding and Interface Segregation. Give components the values
and operations they need, not the entire application store, global event bus,
HTTP client, or native plugin. Keep feature-private state behind its owner.
Use explicit props/events and purpose-specific operations; avoid flag-heavy
universal components, shared mutable objects, and deep imports into other features.

Keep related view, interaction, mapping, and test code together where practical.
Reuse existing shared visual primitives. Do not scatter a feature across dozens
of generic folders or create one-line forwarding modules solely for symmetry.

## 3. Depend on contracts at actual boundaries

Apply Dependency Inversion. Presentation depends on UI-facing capabilities;
adapters implement them using the existing transport or platform. Assemble
these dependencies at the application/feature boundary, not inside every widget.
Plain functions, parameters, or small objects are often sufficient; a dependency
injection container, class hierarchy, or interface for every function is not required.

Keep raw business-endpoint calls and payload construction out of view components.
Use a cohesive adapter rather than a universal API manager. Protocol primitives,
credentials, IPC channel names, and retry policy must not spread across screens.
Low-level transport should not import a page or feature store; supply connection
settings, credentials, and callbacks through its boundary instead. Do not add
new cycles, including cycles hidden by barrel exports or path aliases. Improve
existing couplings in the touched area without inventing a second client stack.

## 4. Require behavioral substitutability

Apply Liskov Substitution to client adapters, hooks, injected functions, and fakes.
Matching TypeScript shapes or JavaScript method names does not establish matching
behavior. Preserve documented errors, ordering, cancellation, subscription
cleanup, identity, and persistence semantics across implementations.

An HTTP success or accepted/queued response is not proof of durable commit,
message delivery, or remote acknowledgment. A fake must not claim guarantees it
does not implement. Unsupported operations need explicit capability/error results,
not empty success. Use shared contract tests when multiple adapters exist.

## 5. Keep one authority for each piece of knowledge

Apply DRY to rules, schemas, identities, units, and protocol meanings, not merely
similar lines. Consume the versioned authoritative API/native contract. Where
code generation exists, regenerate types and decoders from its source rather
than editing outputs or maintaining parallel handwritten wire definitions.

Keep wire types separate from view models when their purposes differ, with
explicit mappings. Do not reinterpret domain values, guess required fields,
shorten persistent identities, or convert missing values into meaningful defaults.
Schema-driven form constraints may be reused for feedback without becoming a
second authority. Caches and projections need ownership, freshness, invalidation,
and connection/workspace identity. Do not copy server state into several stores
and synchronize the copies with effects or watchers.

## 6. Keep modules small through cohesive design

Apply KISS, YAGNI, and disciplined Open/Closed. Prefer the fewest interacting
concepts, not the fewest lines. Reuse stable extension points for demonstrated
variation; do not add speculative plugin systems, universal schemas, managers,
or inheritance hierarchies. A second occurrence is evidence, not a numeric law.

For hand-maintained frontend code, aim for a component/module that can be read as
one responsibility, commonly around 150-300 lines. Above roughly 400 lines,
review its responsibilities before extending it. A 1,000+ line component, store,
or orchestration module requires an explicit decomposition assessment; do not
add unrelated behavior to it. These are review triggers, not universal numeric
limits. Existing repository size gates remain binding and must not be weakened.

Count Vue/Svelte script, template, and styles separately when explaining a large
file. Distinguish executable code from generated clients, static catalogues,
fixtures, and vendored assets. Do not count third-party bundles as first-party
engineering defects. Do not game limits by minifying, deleting explanatory text,
compressing functions, or splitting into coupled fragments with shared globals.

## 7. Use composition, SOLID, and researched patterns

For a non-trivial design/refactor, inspect existing implementations and tests;
research applicable language/library idioms and design patterns using primary
sources. Check the installed versions. Compare the proposed pattern with the
existing design and a simpler alternative. Record the problem it solves and its
cost in the existing task notes; routine edits need no research ceremony.

SOLID applies to modules, functions, components, and adapters, not just classes:
SRP groups reasons for change; OCP protects stable consumers; LSP preserves
behavior; ISP keeps consumer contracts small; DIP protects dependency direction.

| Pattern | Appropriate use | Misuse to reject |
| --- | --- | --- |
| Presentation Model / small feature controller | Separate screen state and interaction behavior from rendering. | A second domain model or one giant useEverything hook. |
| Adapter / Facade | Hide transport, native, and vendor details behind needed capabilities. | A universal client/store or one wrapper per line. |
| Reducer / explicit state machine | Model draft, loading, connection, and request lifecycles. | Reimplementing authoritative business transitions. |
| Command as data | Carry a user's intent to the authority and associate its response. | Executing approval, persistence, or domain transactions in the renderer. |
| Strategy through a function/object | Select a genuinely variable display or interaction algorithm. | A plugin hierarchy for one algorithm, or a client business-policy engine. |
| Observer / subscription | Consume typed events with a clear owner and cleanup. | An unrestricted global bus carrying hidden workflow logic. |

Compose with functions, small objects, props/events, hooks, or composables.
Follow the existing React/Vue style; do not convert an entire app to a different
component API, state library, or language just to apply these principles.

## 8. Make types, UI states, and errors explicit

In TypeScript, preserve strictness and narrow `unknown` data at boundaries.
Interfaces, type assertions, `satisfies`, and generic request signatures do not
validate runtime payloads. Use the existing runtime schemas/decoders or focused
validated parsers. Avoid `any`, double casts, and non-null assertions used to
silence an unresolved mismatch. Distinguish absent, null, empty, zero, and false.

In JavaScript, use small modules, documented contracts/JSDoc, runtime validation,
and focused tests. Adopt checked JavaScript where the existing tooling supports
it; do not require a whole-repository TypeScript conversion. Preserve the owning
package's ESM/CommonJS setup. Prefer tagged states/discriminated unions to
combinations of booleans that admit impossible states.

Keep loading, empty, unavailable, stale, rejected, cancelled, and failed states
distinct. Preserve actionable errors. Do not catch failures and return `[]`, `{}`,
zero, or mock data as successful results. Optional absence may have a documented
fallback; an incompatible contract must remain visible.

## 9. Own effects, subscriptions, and privileged resources

Use React effects/Vue watchers for synchronization with external systems, not
for duplicating derived state or triggering hidden business workflows. Compute
presentation values with pure functions/selectors/computed values. Reuse existing
query/subscription facilities before writing another lifecycle mechanism.

Assign one owner to each subscription, timer, socket, observer, object URL,
media stream, and native listener. Clean it up on disposal and when identity or
connection changes. Bound queues, retries, payloads, and concurrency. Account for
mobile pause/resume and daemon restarts. Ignore stale responses or cancel the
request as supported; transport cancellation does not undo a committed mutation.
Do not retry writes blindly: use the authoritative idempotency contract or expose
an uncertain result. Preserve drafts across failures and reconcile optimistic
pending state against authoritative results rather than claiming completion.

Keep Electron main/preload/renderer and Tauri/Capacitor native boundaries intact.
Expose narrow operations and validate inputs in the privileged handler; a typed
bridge is not a security control by itself. Keep privileged secrets and unrestricted
filesystem/shell access out of renderers. Treat model output, messages, and remote
markup as untrusted data; use safe rendering and existing reviewed sanitization.
A privileged process is not a reason to duplicate the product's domain service.

## 10. Verify boundaries and behavior, then report the evidence

Protect existing behavior before extraction. Test presentation transforms without
mounting an entire app, interaction controllers with explicit dependencies, and
adapters against the real contract. Add component tests for input/error states
and focused integration/E2E tests for the affected user flow. Verify cleanup,
reconnection, stale responses, rejection, and uncertain writes when relevant.
A browser mock does not prove native behavior, delivery, or interoperability.

Use installed, locked local tools and the correct workspace/package manager.
For code changes, run applicable type/lint checks, focused tests, and builds;
for UI changes, inspect the real output, keyboard/focus behavior, and useful
window sizes. A typecheck is not a visual test. Documentation-only changes need
policy/link/diff checks, not an application build or device test.

Use existing import-boundary, contract-generation, and size checks where present.
When implementing a substantive boundary change, add a focused regression using
existing test/lint facilities where practical. Do not introduce a new architecture
checker or broad lint rollout as incidental policy work. Never suppress rules,
relax size limits, loosen types, or rewrite snapshots merely to pass checks.
Remove superseded paths safely; report exactly what was tested and not tested.

## Research basis

This is project-specific policy, not a quotation or a claim that the sources
prescribe these thresholds. Primary references checked on 30 September 2026:

- SOLID: Robert C. Martin, *Solid Relevance*:
  `https://blog.cleancoder.com/uncle-bob/2020/10/18/Solid-Relevance.html`
- Presentation Model: Martin Fowler:
  `https://martinfowler.com/eaaDev/PresentationModel.html`
- React, effects and derived state:
  `https://react.dev/learn/you-might-not-need-an-effect`
- Vue, composable ownership and cleanup:
  `https://vuejs.org/guide/reusability/composables.html`
- TypeScript, assertions and runtime behavior:
  `https://www.typescriptlang.org/docs/handbook/2/everyday-types.html`
- OWASP, client-side versus authoritative input validation:
  `https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html`
- Electron, privileged boundaries and IPC:
  `https://www.electronjs.org/docs/latest/tutorial/security`
- Tauri, native/WebView security boundaries:
  `https://v2.tauri.app/security/`

## Repository application: Reticulum Community Hub

Reviewed default branch `main` at
`e91465fff39de6827b3e6de2e669718a1db97691` on 30 September 2026.
Measurements refer to this committed snapshot, not uncommitted local changes.
This is a targeted source/policy review, not a full runtime/security audit.

### Observed starting points

- `ui/src/pages/missions/MissionsLegacyPage.vue`: 5,123 lines, approximately
  4,607 script lines. Despite its name, `ui/src/router/index.ts:48-49` uses it
  for both `/missions` and `/missions/legacy`.
- `ui/src/pages/WebMapPage.vue`: 3,631 lines, approximately 3,041 script lines.
- `ui/src/pages/ChecklistsPage.vue`: 1,950 lines, approximately 1,342 script lines.
  Checklist name/column resolution helpers also appear in the mission page;
  determine shared presentation knowledge before extracting them.
- `MissionsLegacyPage.vue:4484-4500` computes zone links/unlinks and performs
  multiple writes. This requires an explicit partial-failure/atomicity contract,
  not an assumption that Promise.all makes the operation transactional.
- `ui/src/api/client.ts` and `ui/src/api/ws.ts` already centralize transport,
  but import the connection store. Preserve the existing clients; when this
  boundary is touched, prefer supplied connection/auth state over tighter
  transport-to-store coupling. Do not invent a second transport layer.

The `ui/src` scan found six files over 1,000 lines among 171 selected source
files; one is `api/mock.ts`. Generated/test files were excluded. Treat mock
infrastructure separately from shipping page complexity.

### Ownership and implementation direction

The existing `ui/` Vue 3/Pinia client is supported. The former opening instruction
against adding Vue to the Rust branch conflicted with the same AGENTS.md's
shared-UI section; it is clarified, not used to remove the shipped UI.
Preserve the declared Python/Rust northbound compatibility and existing routes.
`apps/rch-desktop` is a Tauri packaging/native-shell boundary, not a new domain
implementation. Do not restore legacy Electron packaging as UI cleanup.

Keep mission/checklist rules, team rights enforcement, assignment decisions,
authoritative state changes, and domain persistence in `crates/r3akt-rch-core`
and the server boundary in `crates/r3akt-rch-server`. Pages/stores may collect
intent, display permissions returned by the server, and track pending requests.
A client-side rights matrix is not authorization. A multi-write use case needing
atomic behavior belongs in an authoritative operation, not a composable loop.

Prioritize cohesive slices of the active mission/map/checklist views when they
are changed. Separate display mapping, draft interaction, endpoint adapters, and
authoritative operations; do not recreate each large page as a large composable.
Keep mock mode explicit and separate from real connection errors. Preserve
WebSocket cleanup and stale-result handling when the connection changes.

### Relevant local checks for later code changes

Use installed locked tools: `npm --prefix ui run typecheck`,
`npm --prefix ui run lint`, `npm --prefix ui run test`, and
`npm --prefix ui run build`, narrowed to relevant tests where supported.
Run native/server checks when those layers actually change. Read packaging
scripts before invoking the Tauri build: it also builds UI/sidecar/native outputs.
Documentation-only changes do not require dependency reinstall or packaging.
This policy does not modify local source changes, API behavior, or release files.
